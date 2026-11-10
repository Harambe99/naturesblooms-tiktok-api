"""Creator retainer tracker — reads the video analytics feed, aggregates by creator."""
import json
import time
from pathlib import Path
from typing import Any, Dict, List

ROSTER_PATH = Path(__file__).parent / "roster.json"


def load_roster() -> Dict[str, Any]:
    return json.loads(ROSTER_PATH.read_text())


async def fetch_videos(tiktok_get, start: str, end: str, cap: int = 500) -> List[Dict[str, Any]]:
    """Page through shop_videos/performance for the window."""
    out, token, pages = [], "", 0
    while pages < 10 and len(out) < cap:
        extra = {
            "start_date_ge": start, "end_date_lt": end,
            "page_size": 100, "sort_field": "gmv", "sort_order": "DESC",
        }
        if token:
            extra["page_token"] = token
        data = await tiktok_get("/analytics/202409/shop_videos/performance", extra)
        d = data.get("data", {}) or {}
        out.extend(d.get("videos", []) or [])
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


def build(videos: List[Dict[str, Any]], roster: Dict[str, Any],
          start: str, end: str) -> Dict[str, Any]:
    """Aggregate videos by creator and score them against their retainer."""
    by: Dict[str, Dict[str, Any]] = {}
    for v in videos:
        u = (v.get("username") or "").strip().lower()
        if not u:
            continue
        d = by.setdefault(u, {"videos": [], "gmv": 0.0, "views": 0, "units": 0, "orders": 0})
        d["videos"].append(v)
        d["gmv"] += money(v.get("gmv"))
        d["views"] += int(v.get("views") or 0)
        d["units"] += int(v.get("units_sold") or 0)
        d["orders"] += int(v.get("sku_orders") or 0)

    rows = []
    for r in roster["video"]:
        h = r["handle"].lower()
        d = by.get(h, {"videos": [], "gmv": 0.0, "views": 0, "units": 0, "orders": 0})
        posted = len(d["videos"])
        inactive = r.get("status") == "Inactive"
        earned = 0.0 if inactive else posted * r["rate"]
        committed = r["videos"] * r["rate"]
        vids = sorted(d["videos"], key=lambda x: money(x.get("gmv")), reverse=True)
        rows.append({
            "name": r["name"], "handle": r["handle"], "status": r.get("status", ""),
            "rate": r["rate"], "committed_videos": r["videos"], "committed_cost": committed,
            "posted": posted, "earned": round(earned, 2),
            "pace": round(posted / r["videos"], 3) if r["videos"] else None,
            "gmv": round(d["gmv"], 2), "views": d["views"],
            "units": d["units"], "orders": d["orders"],
            "gmv_per_video": round(d["gmv"] / posted, 2) if posted else None,
            "cost_per_gmv": round(earned / d["gmv"], 3) if d["gmv"] else None,
            "roi": round(d["gmv"] / earned, 2) if earned else None,
            "videos": [{
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
    off = sorted(
        ({"handle": u, "videos": len(d["videos"]), "gmv": round(d["gmv"], 2),
          "views": d["views"], "units": d["units"]} for u, d in by.items() if u not in on_roster),
        key=lambda x: -x["gmv"],
    )[:25]

    return {
        "window": {"start": start, "end": end},
        "generated_at": int(time.time()),
        "totals": {
            "roster_creators": len(rows),
            "videos_posted": sum(r["posted"] for r in rows),
            "videos_committed": sum(r["committed_videos"] for r in rows),
            "earned": round(sum(r["earned"] for r in rows), 2),
            "committed": round(sum(r["committed_cost"] for r in rows), 2),
            "roster_gmv": round(sum(r["gmv"] for r in rows), 2),
            "offroster_gmv": round(sum(o["gmv"] for o in off), 2),
        },
        "creators": rows,
        "off_roster": off,
        "live_note": "LIVE hours are not exposed by the TikTok Open API — add them manually.",
        "live_roster": roster["live"],
    }
