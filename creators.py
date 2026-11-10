"""Creator retainer tracker — reads the video + LIVE analytics feeds, aggregates by creator."""
import json
import time
from pathlib import Path
from typing import Any, Dict, List

ROSTER_PATH = Path(__file__).parent / "roster.json"

VIDEOS_PATH = "/analytics/202409/shop_videos/performance"
LIVES_PATH = "/analytics/202509/shop_lives/performance"


def load_roster() -> Dict[str, Any]:
    return json.loads(ROSTER_PATH.read_text())


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
        # _raw ignores Active/Inactive so the UI can re-apply a toggle client-side
        # without a refetch. The server still returns the roster-correct figures.
        earned_raw = round(posted * r["rate"], 2)
        committed_raw = round(r["videos"] * r["rate"], 2)
        earned = 0.0 if inactive else earned_raw
        committed = 0.0 if inactive else committed_raw
        vids = sorted(d["videos"], key=lambda x: money(x.get("gmv")), reverse=True)
        rows.append({
            "name": r["name"], "handle": r.get("handle") or "",
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
    on_roster = {r["handle"].lower() for r in roster["video"]}
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
