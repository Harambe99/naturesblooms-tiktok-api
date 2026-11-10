"""
Daily Overview — yesterday's trading, modelled on AJ's Raycon daily brief.

SAFETY: read-only. Every TikTok call goes through the caller's tiktok_get, which
is guarded by assert_read_only in app.py. Nothing here writes to TikTok.

Basis note that matters: everything in this module is ORDER/ANALYTICS basis —
GMV is counted when the order is placed. The finance settlement feed used by the
P&L lags ~6 days and is a different basis. Never total the two together.
"""
import datetime as dt
from typing import Any, Dict, List, Optional

PRODUCTS_PATH = "/analytics/202405/shop_products/performance"
SHOP_PATH = "/analytics/202405/shop/performance"

# The seven NB SKUs, with the November COGS card. Bundles are the sum of their
# bottles. Soursop $1.57, Black Seed $1.52, Pineapple Mango $2.55.
SKUS: Dict[str, Dict[str, Any]] = {
    "1729464509762474844": {"name": "Soursop Bitters", "short": "Soursop", "cogs": 1.57},
    "1729761727170319196": {"name": "Black Seed Bitters", "short": "Black Seed", "cogs": 1.52},
    "1732549345172034396": {"name": "Pineapple Mango Bitters", "short": "Pineapple Mango", "cogs": 2.55},
    "1729841947307971420": {"name": "Soursop + Black Seed Bundle", "short": "Soursop + BS", "cogs": 3.09},
    "1732699200709497692": {"name": "Black Seed + Pineapple Mango", "short": "BS + PM", "cogs": 4.07},
    "1732699223071560540": {"name": "Soursop + Pineapple Mango", "short": "Soursop + PM", "cogs": 4.12},
    "1732549409890866012": {"name": "Triple Bloom Bitters", "short": "Triple Bloom", "cogs": 5.64},
}


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


async def fetch_products(tiktok_get, start: str, end: str) -> Dict[str, Any]:
    """Per-SKU GMV / orders / units for a window. Also returns the feed's own
    latest_available_date, which is the authoritative freshness boundary."""
    out: List[Dict[str, Any]] = []
    token, pages, latest = "", 0, None
    while pages < 20:
        extra = {"start_date_ge": start, "end_date_lt": end, "page_size": 100}
        if token:
            extra["page_token"] = token
        data = await tiktok_get(PRODUCTS_PATH, extra)
        d = data.get("data", {}) or {}
        latest = latest or d.get("latest_available_date")
        out.extend(d.get("products", []) or [])
        token = d.get("next_page_token") or ""
        pages += 1
        if not token:
            break
    return {"products": out, "latest_available_date": latest}


async def fetch_shop(tiktok_get, start: str, end: str) -> Dict[str, Any]:
    """Shop-level daily performance: GMV, AOV, buyers and the channel split."""
    data = await tiktok_get(SHOP_PATH, {"start_date_ge": start, "end_date_lt": end})
    return data.get("data", {}) or {}


async def latest_date(tiktok_get) -> Optional[str]:
    """Ask the API how fresh its data actually is, rather than guessing a lag.
    Probes a short recent window; returns YYYY-MM-DD or None."""
    today = dt.date.today()
    d = await fetch_products(tiktok_get,
                             (today - dt.timedelta(days=10)).isoformat(),
                             (today + dt.timedelta(days=1)).isoformat())
    return d.get("latest_available_date")


def sku_table(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Map the feed's product rows onto the NB SKU card. Unknown IDs are kept
    and flagged rather than dropped — a new SKU must not silently vanish."""
    rows, unknown = [], []
    for p in products or []:
        pid = str(p.get("id"))
        perf = p.get("overall_performance") or p            # 202509 nests, 202405 is flat
        gmv = money(perf.get("gmv"))
        units = int(perf.get("units_sold") or perf.get("items_sold") or 0)
        orders = int(perf.get("orders") or 0)
        meta = SKUS.get(pid)
        row = {
            "id": pid,
            "name": (meta or {}).get("name") or f"Unmapped SKU {pid}",
            "short": (meta or {}).get("short") or f"SKU {pid[-6:]}",
            "gmv": round(gmv, 2), "units": units, "orders": orders,
            "cogs_each": (meta or {}).get("cogs"),
            "cogs_total": round(units * meta["cogs"], 2) if meta else None,
            "aov": round(gmv / orders, 2) if orders else None,
            "known": bool(meta),
        }
        rows.append(row)
        if not meta:
            unknown.append(pid)
    # every SKU on the card appears, even at zero, so a dead SKU is visible
    seen = {r["id"] for r in rows}
    for pid, meta in SKUS.items():
        if pid not in seen:
            rows.append({"id": pid, "name": meta["name"], "short": meta["short"],
                         "gmv": 0.0, "units": 0, "orders": 0,
                         "cogs_each": meta["cogs"], "cogs_total": 0.0,
                         "aov": None, "known": True})
    rows.sort(key=lambda r: -r["gmv"])
    return {
        "rows": rows,
        "unknown_ids": unknown,
        "gmv": round(sum(r["gmv"] for r in rows), 2),
        "units": sum(r["units"] for r in rows),
        "orders": sum(r["orders"] for r in rows),
        "cogs": round(sum(r["cogs_total"] or 0 for r in rows), 2),
    }


def shop_summary(shop: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten shop/performance intervals into one summary + the channel split."""
    perf = (shop or {}).get("performance") or {}
    intervals = perf.get("intervals") or []
    gmv = sum(money(i.get("gmv")) for i in intervals)
    buyers = sum(int(i.get("buyers") or 0) for i in intervals)
    visitors = sum(int(i.get("avg_product_page_visitors") or 0) for i in intervals)
    cancels = sum(int(i.get("cancellations_and_returns") or 0) for i in intervals)
    chan: Dict[str, int] = {}
    vis_chan: Dict[str, int] = {}
    for i in intervals:
        for b in i.get("buyer_breakdowns") or []:
            chan[b.get("type", "?")] = chan.get(b.get("type", "?"), 0) + int(b.get("amount") or 0)
        for b in i.get("avg_product_page_visitor_breakdowns") or []:
            vis_chan[b.get("type", "?")] = vis_chan.get(b.get("type", "?"), 0) + int(b.get("amount") or 0)
    return {
        "gmv": round(gmv, 2), "buyers": buyers, "visitors": visitors,
        "cancellations_and_returns": cancels,
        "aov": round(gmv / buyers, 2) if buyers else None,
        "buyers_by_channel": chan, "visitors_by_channel": vis_chan,
        "conversion": round(buyers / visitors, 4) if visitors else None,
        "days": len(intervals),
        "latest_available_date": (shop or {}).get("latest_available_date"),
    }


def video_output(videos: List[Dict[str, Any]], roster: Dict[str, Any],
                 day: str) -> Dict[str, Any]:
    """Videos POSTED on `day`, split retainer vs affiliate.

    Delivery is judged on video_post_time, never on activity — the feed returns
    videos still *earning* in a window, which is a different and much larger set.
    """
    handles: Dict[str, str] = {}
    for typ in ("video", "live"):
        for r in roster.get(typ, []) or []:
            h = (r.get("handle") or "").strip().lower()
            if h:
                handles[h] = r.get("name") or h
    retainer, affiliate = [], []
    for v in videos or []:
        if (v.get("video_post_time") or "")[:10] != day:
            continue
        u = (v.get("username") or "").strip().lower()
        row = {"handle": u, "id": str(v.get("id")),
               "title": (v.get("title") or "")[:120],
               "url": f"https://www.tiktok.com/@{u}/video/{v.get('id')}",
               "gmv": round(money(v.get("gmv")), 2),
               "views": int(v.get("views") or 0),
               "posted_at": v.get("video_post_time")}
        if u in handles:
            row["creator"] = handles[u]
            retainer.append(row)
        else:
            row["creator"] = "External Creator"
            affiliate.append(row)
    retainer.sort(key=lambda r: -r["gmv"])
    affiliate.sort(key=lambda r: -r["gmv"])
    return {
        "retainer": retainer, "affiliate": affiliate,
        "retainer_count": len(retainer), "affiliate_count": len(affiliate),
        "total": len(retainer) + len(affiliate),
        "active_retainer_creators": len({r["handle"] for r in retainer}),
        "active_affiliate_creators": len({r["handle"] for r in affiliate}),
        "names": [r["creator"] for r in retainer] + ["External Creator"] * len(affiliate),
    }


def build(day: str, month_start: str,
          products_day: Dict[str, Any], shop_day: Dict[str, Any],
          products_mtd: Dict[str, Any], shop_mtd: Dict[str, Any],
          videos: List[Dict[str, Any]], roster: Dict[str, Any],
          creator_result: Dict[str, Any],
          goals: Dict[str, Any], onboarding: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the daily brief. `day` is the latest fully-available date."""
    sku_day = sku_table(products_day.get("products", []))
    sku_mtd = sku_table(products_mtd.get("products", []))
    shop_d = shop_summary(shop_day)
    shop_m = shop_summary(shop_mtd)
    out = video_output(videos, roster, day)

    te = creator_result.get("totals_effective") or {}
    counted = [r for r in (creator_result.get("creators") or [])
               if r.get("eff_status") != "Inactive"]
    lcounted = [r for r in (creator_result.get("live_creators") or [])
                if r.get("eff_status") != "Inactive"]
    on_retainer = len(counted) + len(lcounted)
    committed = (te.get("committed") or 0) + (te.get("live_committed") or 0)

    def goal(k):
        v = (goals or {}).get(k)
        try:
            return float(v) if v not in ("", None) else None
        except (TypeError, ValueError):
            return None

    return {
        "day": day, "month_start": month_start,
        "basis": "order/analytics basis — GMV counted when the order was placed",
        "skus_day": sku_day, "skus_mtd": sku_mtd,
        "shop_day": shop_d, "shop_mtd": shop_m,
        "video_output": out,
        "retainers": {
            "creators_on_retainer": on_retainer,
            "total_committed": round(committed, 2),
            "avg_cost_per_creator": round(committed / on_retainer, 2) if on_retainer else None,
            "earned_to_date": round((te.get("earned") or 0) + (te.get("live_earned") or 0), 2),
            "posts_delivered_mtd": te.get("videos_posted"),
            "posts_committed": te.get("videos_committed"),
            "live_hours_mtd": te.get("live_hours"),
        },
        "goals": {
            "gmv_day": goal("gmv_day"), "units_day": goal("units_day"),
            "videos_day": goal("videos_day"),
            "active_creators": goal("active_creators"),
            "active_retainer_creators": goal("active_retainer_creators"),
            "gmv_month": goal("gmv_month"),
        },
        "onboarding": onboarding or {},
        "onboarding_note": ("Creators Waiting for Product and New Creators Onboarded are "
                            "not exposed by any TikTok Shop API — these are manual entries."),
    }
