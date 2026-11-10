"""Creator retainer tracker — reads the video + LIVE analytics feeds, aggregates by creator."""
import copy
import datetime as dt
import difflib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROSTER_PATH = Path(__file__).parent / "roster.json"

VIDEOS_PATH = "/analytics/202409/shop_videos/performance"
LIVES_PATH = "/analytics/202509/shop_lives/performance"


def load_roster() -> Dict[str, Any]:
    return json.loads(ROSTER_PATH.read_text())


def creator_key(typ: str, r: Dict[str, Any]) -> str:
    """Stable identity for a roster row: type + handle (lowered), or name when
    there is no handle. Computed from the SEED roster before overrides are
    applied, so a corrected handle does not orphan statuses or overrides."""
    h = (r.get("handle") or "").strip().lower()
    return f"{typ}:{h or r.get('name', '')}"


def merge_roster(seed: Dict[str, Any], sdata: Dict[str, Any]) -> Dict[str, Any]:
    """roster.json stays source of truth; the store layers edits and additions
    on top. Tracker rows get source='tracker' plus overridden_fields; rows AJ
    added in the app get source='custom'."""
    roster = copy.deepcopy(seed)
    overrides = (sdata or {}).get("roster_overrides", {}) or {}
    for typ in ("video", "live"):
        for r in roster.get(typ, []):
            r["source"] = "tracker"
            r["key"] = creator_key(typ, r)          # seed-based, stable
            o = overrides.get(r["key"])
            r["overridden_fields"] = []
            if o:
                for f, v in o.items():
                    if r.get(f) != v:
                        r[f] = v
                        r["overridden_fields"].append(f)
                r["overridden_fields"].sort()
                if "handle" in o:                   # corrected handle re-resolves
                    r["resolved"] = bool(r.get("handle"))
    for a in (sdata or {}).get("roster_added", []) or []:
        typ = (a.get("type") or "video").lower()
        if typ not in ("video", "live"):
            continue
        row = {k: v for k, v in a.items() if k != "type"}
        row["source"] = "custom"
        row["key"] = creator_key(typ, row)
        row["overridden_fields"] = []
        if typ == "video":
            row.setdefault("videos", 0)
            row.setdefault("rate", 0.0)
        else:
            row.setdefault("hourly", None)
            row.setdefault("hours_cap", None)
        roster.setdefault(typ, []).append(row)
    return roster


# ---------------------------------------------------------------- status model
# Four states. How each affects the money, chosen with AJ's rules:
#   Active   — earned = delivered-to-date, committed = full monthly commitment.
#   Paused   — delivered posts, GMV and earned-to-date all still count, but the
#              remaining commitment is frozen: committed = earned so far. This is
#              a CHOSEN rule (AJ asked for Paused to be distinct from Inactive
#              without specifying the maths) and it is stated in the UI.
#   Ended    — requires an end date. Cost for the month = committed pro-rated by
#              the engaged fraction of the month (month start -> end date), and
#              never less than what they actually earned before ending.
#   Inactive — excluded from earned and committed entirely; posts/GMV still shown.
STATUSES = ("Active", "Paused", "Ended", "Inactive")

PAUSED_RULE_NOTE = ("Paused keeps the creator's delivered posts, GMV and earned-to-date "
                    "in every total, but freezes the commitment at what they have already "
                    "earned — a paused deal stops accruing committed cost until it is "
                    "reactivated. Inactive removes their cost from totals entirely.")
ENDED_RULE_NOTE = ("Ended requires the date the deal ended. The month still carries their "
                   "cost: committed is pro-rated by the engaged fraction of the month "
                   "(month start → end date), and the counted cost is the greater of that "
                   "pro-rated commitment and what they actually earned before ending.")


def base_status(row: Dict[str, Any]) -> str:
    s = (row.get("status") or "").strip().title()
    return s if s in STATUSES else "Active"       # blank counts, per the tracker rule


def apply_statuses(result: Dict[str, Any], statuses: Dict[str, Any],
                   month_start: dt.date) -> Dict[str, Any]:
    """Overlay stored status changes on build() output and recompute effective
    money fields + totals. Mutates and returns result."""
    days_in_month = (
        (month_start.replace(month=month_start.month % 12 + 1,
                             year=month_start.year + (month_start.month == 12), day=1)
         - month_start.replace(day=1)).days
    )
    for row in list(result.get("creators", [])) + list(result.get("live_creators", [])):
        key = row.get("key") or creator_key(row.get("type", "video"), row)
        row["key"] = key
        ovr = (statuses or {}).get(key) or {}
        base = base_status(row)
        eff = ovr.get("status") or base
        end_date = ovr.get("end_date") if eff == "Ended" else None
        row["eff_status"] = eff
        row["end_date"] = end_date
        row["status_overridden"] = bool(ovr) and eff != base
        er = float(row.get("earned_raw") or 0.0)
        cr = float(row.get("committed_raw") or 0.0)
        prorata = None
        if eff == "Inactive":
            e, c, cost = 0.0, 0.0, 0.0
        elif eff == "Paused":
            e, c, cost = er, er, er
        elif eff == "Ended":
            frac, engaged = 1.0, days_in_month
            if end_date:
                try:
                    ed = dt.date.fromisoformat(end_date)
                    engaged = max(0, min((ed - month_start.replace(day=1)).days + 1,
                                         days_in_month))
                    frac = engaged / days_in_month
                except ValueError:
                    pass
            c = round(cr * frac, 2)
            e = er
            cost = round(max(er, c), 2)
            prorata = {"days_engaged": engaged, "days_in_month": days_in_month,
                       "fraction": round(frac, 4), "full_committed": cr}
        else:
            e, c, cost = er, cr, er
        row["earned_eff"] = round(e, 2)
        row["committed_eff"] = round(c, 2)
        row["retainer_cost"] = round(cost, 2)
        row["prorata"] = prorata

    vids = result.get("creators", [])
    lives = result.get("live_creators", [])
    counted = [r for r in vids if r["eff_status"] != "Inactive"]
    lcounted = [r for r in lives if r["eff_status"] != "Inactive"]
    result["totals_effective"] = {
        "videos_posted": sum(r["posted"] for r in counted),
        "videos_committed": sum(r["committed_videos"] for r in counted),
        "earned": round(sum(r["earned_eff"] for r in vids), 2),
        "committed": round(sum(r["committed_eff"] for r in vids), 2),
        "retainer_cost_video": round(sum(r["retainer_cost"] for r in vids), 2),
        "live_hours": round(sum(r["hours"] for r in lcounted), 2),
        "live_earned": round(sum(r["earned_eff"] for r in lives), 2),
        "live_committed": round(sum(r["committed_eff"] for r in lives), 2),
        "retainer_cost_live": round(sum(r["retainer_cost"] for r in lives), 2),
        "counted": len(counted) + len(lcounted),
        "total": len(vids) + len(lives),
        "ended": sum(1 for r in vids + lives if r["eff_status"] == "Ended"),
        "paused": sum(1 for r in vids + lives if r["eff_status"] == "Paused"),
    }
    result["status_rules"] = {"paused": PAUSED_RULE_NOTE, "ended": ENDED_RULE_NOTE}
    return result


# ---------------------------------------------------------------- handle validation
def _feed_usernames(videos: List[Dict[str, Any]],
                    lives: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    users: Dict[str, Dict[str, Any]] = {}
    for v in videos or []:
        u = (v.get("username") or "").strip().lower()
        if not u:
            continue
        d = users.setdefault(u, {"videos": 0, "video_gmv": 0.0, "sessions": 0, "live_gmv": 0.0})
        d["videos"] += 1
        d["video_gmv"] += money(v.get("gmv"))
    for s in lives or []:
        u = (s.get("username") or "").strip().lower()
        if not u:
            continue
        d = users.setdefault(u, {"videos": 0, "video_gmv": 0.0, "sessions": 0, "live_gmv": 0.0})
        d["sessions"] += 1
        d["live_gmv"] += money((s.get("sales_performance") or {}).get("gmv"))
    return users


def _similarity(a: str, b: str) -> float:
    """Catches both near-misses and scrambles: juicegyalprncess vs
    princessjuicegyal shares its letters but not its order, so score on the
    raw string AND on the sorted characters."""
    direct = difflib.SequenceMatcher(None, a, b).ratio()
    scrambled = difflib.SequenceMatcher(None, "".join(sorted(a)), "".join(sorted(b))).ratio()
    return max(direct, scrambled * 0.95)


def validate_handle(handle: Optional[str], videos: List[Dict[str, Any]],
                    lives: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Check a handle against the live feed. Returns found counts, or a no-data
    verdict with fuzzy near-miss suggestions — this is exactly how the
    juicegyalprncess and myblackgirlroots typos were caught."""
    h = (handle or "").strip().lstrip("@").lower()
    users = _feed_usernames(videos, lives)
    if not h:
        return {"handle": "", "status": "empty", "suggestions": []}
    hit = users.get(h)
    if hit:
        return {
            "handle": h,
            "status": "ok" if (hit["videos"] or hit["sessions"]) else "no_data",
            "videos": hit["videos"], "video_gmv": round(hit["video_gmv"], 2),
            "live_sessions": hit["sessions"], "live_gmv": round(hit["live_gmv"], 2),
            "suggestions": [],
        }
    scored = sorted(
        ((u, _similarity(h, u)) for u in users),
        key=lambda x: -x[1],
    )
    sugg = [{
        "handle": u, "score": round(s, 3),
        "videos": users[u]["videos"], "video_gmv": round(users[u]["video_gmv"], 2),
        "live_sessions": users[u]["sessions"], "live_gmv": round(users[u]["live_gmv"], 2),
    } for u, s in scored if s >= 0.55][:5]
    return {"handle": h, "status": "not_found", "videos": 0, "video_gmv": 0.0,
            "live_sessions": 0, "live_gmv": 0.0, "suggestions": sugg}


async def fetch_videos(tiktok_get, start: str, end: str,
                       max_pages: int = 50) -> List[Dict[str, Any]]:
    """
    Page through shop_videos/performance for the window — ALL of it.

    The feed cannot sort by post time (allowed sort fields are gmv, sku_orders,
    units_sold, daily_avg_buyers, views, click_through_rate — verified 10 Nov 2026),
    and newly-posted videos earn $0 so they sort LAST under every sort order that
    matters. Stopping early therefore silently drops exactly the videos a retainer
    pays for. Page until next_page_token is empty; max page_size is 100.
    """
    out: List[Dict[str, Any]] = []
    seen: set = set()                     # GMV order can shift between pages; dedupe
    token, pages = "", 0
    while pages < max_pages:
        extra = {
            "start_date_ge": start, "end_date_lt": end,
            "page_size": 100, "sort_field": "gmv", "sort_order": "DESC",
        }
        if token:
            extra["page_token"] = token
        data = await tiktok_get(VIDEOS_PATH, extra)
        d = data.get("data", {}) or {}
        for v in d.get("videos", []) or []:
            vid = str(v.get("id"))
            if vid not in seen:
                seen.add(vid)
                out.append(v)
        token = d.get("next_page_token") or ""
        pages += 1
        if not token:
            break
    return out


async def fetch_lives(tiktok_get, start: str, end: str,
                      max_pages: int = 50) -> List[Dict[str, Any]]:
    """Page through shop_lives/performance (202509 is the valid version stamp).

    Each session carries username, start_time/end_time (unix seconds) and
    sales_performance.gmv — enough to compute LIVE hours per creator.
    """
    out: List[Dict[str, Any]] = []
    seen: set = set()
    token, pages = "", 0
    while pages < max_pages:
        extra = {
            "start_date_ge": start, "end_date_lt": end,
            "page_size": 100, "sort_field": "gmv", "sort_order": "DESC",
        }
        if token:
            extra["page_token"] = token
        data = await tiktok_get(LIVES_PATH, extra)
        d = data.get("data", {}) or {}
        for s in d.get("live_stream_sessions", []) or []:
            sid = str(s.get("id"))
            if sid not in seen:
                seen.add(sid)
                out.append(s)
        token = d.get("next_page_token") or ""
        pages += 1
        if not token:
            break
    return out


def money(v: Any) -> float:
    if isinstance(v, dict):
        try:
            return float(v.get("amount") or 0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def posted_in_window(v: Dict[str, Any], start: str, end: str) -> bool:
    """
    CRITICAL: the analytics feed returns videos ACTIVE in the window, including
    content posted months earlier that is still selling. Retainers pay for posts
    DELIVERED in the period, so delivery must be judged on video_post_time.
    Counting active videos as delivered would massively overpay.
    """
    t = (v.get("video_post_time") or "")[:10]
    return bool(t) and start <= t < end


def is_inactive(r: Dict[str, Any]) -> bool:
    """Only an explicit Inactive is excluded; a blank status still counts."""
    return (r.get("status") or "").strip().lower() == "inactive"


def build(videos: List[Dict[str, Any]], roster: Dict[str, Any],
          start: str, end: str,
          lives: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Aggregate videos + live sessions by creator and score against retainers."""
    lives = lives or []
    by: Dict[str, Dict[str, Any]] = {}
    for v in videos:
        u = (v.get("username") or "").strip().lower()
        if not u:
            continue
        d = by.setdefault(u, {"videos": [], "new": [], "gmv": 0.0, "views": 0,
                              "units": 0, "orders": 0, "new_gmv": 0.0})
        d["videos"].append(v)
        if posted_in_window(v, start, end):
            d["new"].append(v)
            d["new_gmv"] += money(v.get("gmv"))
        d["gmv"] += money(v.get("gmv"))
        d["views"] += int(v.get("views") or 0)
        d["units"] += int(v.get("units_sold") or 0)
        d["orders"] += int(v.get("sku_orders") or 0)

    rows = []
    for r in roster["video"]:
        # handle may be null when the account is unconfirmed (see roster notes).
        # An unresolved creator is still reported, but never matched to API data —
        # guessing an account would mean paying on another creator's numbers.
        h = (r.get("handle") or "").lower()
        d = by.get(h, {"videos": [], "new": [], "gmv": 0.0, "views": 0,
                       "units": 0, "orders": 0, "new_gmv": 0.0}) if h else \
            {"videos": [], "new": [], "gmv": 0.0, "views": 0,
             "units": 0, "orders": 0, "new_gmv": 0.0}
        posted = len(d["new"])          # delivered IN the window — this is what we pay for
        active = len(d["videos"])       # anything still earning, however old
        inactive = is_inactive(r)
        # _raw ignores Active/Inactive so the status layer can re-apply rules
        # without a refetch. The server still returns the roster-correct figures.
        rate = float(r.get("rate") or 0.0)
        committed_videos = int(r.get("videos") or 0)
        earned_raw = round(posted * rate, 2)
        committed_raw = round(committed_videos * rate, 2)
        earned = 0.0 if inactive else earned_raw
        committed = 0.0 if inactive else committed_raw
        vids = sorted(d["videos"], key=lambda x: money(x.get("gmv")), reverse=True)
        rows.append({
            "name": r["name"], "handle": r.get("handle") or "",
            "key": r.get("key") or creator_key("video", r),
            "source": r.get("source", "tracker"),
            "overridden_fields": r.get("overridden_fields", []),
            "perf_retainer": r.get("perf_retainer"),
            "type": "video", "status": r.get("status", ""),
            # resolved=false means the handle is unconfirmed, so every metric on this
            # row is structurally zero and must not be read as "posted nothing".
            "resolved": r.get("resolved", True),
            # 'owned' = brand account; TikTok's affiliate Creator List export reports
            # 0 videos / $0 GMV for these, so only shop video analytics counts them.
            "attribution": r.get("attribution", "affiliate"),
            "note": r.get("note", ""), "handle_note": r.get("handle_note", ""),
            "rate": r["rate"], "commission": r.get("commission", ""),
            "committed_videos": r["videos"], "committed_cost": committed,
            "earned_raw": earned_raw, "committed_raw": committed_raw,
            "posted": posted, "active_videos": active,
            "new_gmv": round(d["new_gmv"], 2),
            "earned": round(earned, 2),
            "pace": round(posted / r["videos"], 3) if r["videos"] else None,
            "gmv": round(d["gmv"], 2), "views": d["views"],
            "units": d["units"], "orders": d["orders"],
            "gmv_per_video": round(d["new_gmv"] / posted, 2) if posted else None,
            "cost_per_gmv": round(earned / d["gmv"], 3) if d["gmv"] else None,
            "roi": round(d["gmv"] / earned, 2) if earned else None,
            "videos": [{
                "new": posted_in_window(x, start, end),
                "id": str(x.get("id")),
                "title": (x.get("title") or "")[:140],
                "url": f"https://www.tiktok.com/@{r['handle']}/video/{x.get('id')}",
                "views": int(x.get("views") or 0),
                "gmv": round(money(x.get("gmv")), 2),
                "units": int(x.get("units_sold") or 0),
                "ctr": x.get("click_through_rate"),
                "posted": x.get("video_post_time"),
            } for x in vids],
        })

    rows.sort(key=lambda x: (-x["gmv"], -x["posted"]))
    # handle can be null for an unresolved creator, so never assume a string here
    on_roster = {(r.get("handle") or "").lower() for r in roster["video"] if r.get("handle")}
    on_roster |= {(r.get("handle") or "").lower() for r in roster["live"] if r.get("handle")}
    off = sorted(
        ({"handle": u, "videos": len(d["new"]), "active": len(d["videos"]),
          "gmv": round(d["gmv"], 2), "views": d["views"], "units": d["units"]}
         for u, d in by.items() if u not in on_roster),
        key=lambda x: -x["gmv"],
    )[:25]

    # ---------------------------------------------------------------- LIVE
    live_by: Dict[str, Dict[str, Any]] = {}
    for s in lives:
        u = (s.get("username") or "").strip().lower()
        if not u:
            continue
        d = live_by.setdefault(u, {"sessions": 0, "hours": 0.0, "gmv": 0.0, "list": []})
        try:
            dur = max(0, int(s.get("end_time") or 0) - int(s.get("start_time") or 0))
        except (TypeError, ValueError):
            dur = 0
        g = money((s.get("sales_performance") or {}).get("gmv"))
        d["sessions"] += 1
        d["hours"] += dur / 3600
        d["gmv"] += g
        d["list"].append({"id": str(s.get("id")), "title": (s.get("title") or "")[:140],
                          "start": s.get("start_time"), "hours": round(dur / 3600, 2),
                          "gmv": round(g, 2)})

    live_rows = []
    for r in roster["live"]:
        h = (r.get("handle") or "").lower()
        d = live_by.get(h, {"sessions": 0, "hours": 0.0, "gmv": 0.0, "list": []})
        inactive = is_inactive(r)
        hourly = r.get("hourly")
        cap = r.get("hours_cap")
        hours = round(d["hours"], 2)
        paid_hours = min(hours, cap) if cap else hours
        earned_raw = round(paid_hours * hourly, 2) if hourly else 0.0
        committed_raw = round(hourly * cap, 2) if (hourly and cap) else 0.0
        earned = 0.0 if inactive else earned_raw
        committed = 0.0 if inactive else committed_raw
        live_rows.append({
            "name": r["name"], "handle": r.get("handle") or "",
            "type": "live", "status": r.get("status", ""),
            "resolved": r.get("resolved", True),
            "key": r.get("key") or creator_key("live", r),
            "source": r.get("source", "tracker"),
            "overridden_fields": r.get("overridden_fields", []),
            "perf_retainer": r.get("perf_retainer"),
            "note": r.get("note", ""), "handle_note": r.get("handle_note", ""),
            "hourly": hourly, "hours_cap": cap,
            "commission": r.get("commission", ""), "notes": r.get("notes", ""),
            "sessions": d["sessions"], "hours": hours, "paid_hours": round(paid_hours, 2),
            "earned": earned, "committed_cost": committed,
            "earned_raw": earned_raw, "committed_raw": committed_raw,
            "gmv": round(d["gmv"], 2),
            "session_list": sorted(d["list"], key=lambda x: -x["gmv"]),
        })
    live_rows.sort(key=lambda x: (-x["hours"], -x["gmv"]))

    live_on = {(r.get("handle") or "").lower() for r in roster["live"] if r.get("handle")}
    live_off = sorted(
        ({"handle": u, "sessions": d["sessions"], "hours": round(d["hours"], 2),
          "gmv": round(d["gmv"], 2)}
         for u, d in live_by.items() if u not in live_on),
        key=lambda x: -x["hours"],
    )[:25]

    return {
        "window": {"start": start, "end": end},
        "generated_at": int(time.time()),
        "totals": {
            "roster_creators": len(rows) + len(live_rows),
            "video_creators": len(rows),
            "live_creators_count": len(live_rows),
            "unresolved": sum(1 for r in rows + live_rows if not r.get("resolved", True)),
            "videos_posted": sum(r["posted"] for r in rows),
            "videos_active": sum(r["active_videos"] for r in rows),
            "videos_committed": sum(r["committed_videos"] for r in rows if r["committed_cost"]),
            "earned": round(sum(r["earned"] for r in rows), 2),
            "committed": round(sum(r["committed_cost"] for r in rows), 2),
            "roster_gmv": round(sum(r["gmv"] for r in rows), 2),
            "offroster_gmv": round(sum(o["gmv"] for o in off), 2),
            "live_hours": round(sum(r["hours"] for r in live_rows), 2),
            "live_gmv": round(sum(r["gmv"] for r in live_rows), 2),
            "live_earned": round(sum(r["earned"] for r in live_rows), 2),
            "live_committed": round(sum(r["committed_cost"] for r in live_rows), 2),
        },
        "creators": rows,
        "off_roster": off,
        "live_creators": live_rows,
        "live_off_roster": live_off,
        "basis_note": ("Posts = videos whose post date falls inside the window, which is "
                       "what a retainer pays for. Active = every video still earning, "
                       "including older content. GMV is from all active videos. "
                       "Inactive creators are excluded from earned AND committed; a blank "
                       "status still counts toward committed."),
        "live_note": ("LIVE hours come from shop_lives/performance: sum of session "
                      "end_time − start_time per creator. Earned = hourly rate × hours, "
                      "capped at the contracted monthly hours where a cap is set."),
    }
