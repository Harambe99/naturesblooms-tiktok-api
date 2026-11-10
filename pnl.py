"""
P&L for the month to date.

SAFETY: read-only against TikTok. Cell overrides and manual costs are stored on
our own disk via store.py; nothing here writes to TikTok Shop.

BASIS — this has burned us before, so it is explicit on every row:
  * GMV, units and COGS come from the ANALYTICS feed: order basis, counted when
    the order is placed. Fresh to `latest_available_date` (~1 day behind).
  * Fees, refunds and net settlement come from the FINANCE feed: settlement
    basis, which lags ~6 days. A 7-day window on settlement basis sees only a
    fraction of the orders placed in it.
These two are never summed into one figure without saying which basis applies.

LOCKED rows are rendered, not hidden: a row we cannot populate because a scope
is missing says so and says what it would unlock.
"""
import calendar
import datetime as dt
from typing import Any, Dict, List, Optional

# Pick & pack is tiered on units per order, not per unit.
PICK_PACK = {1: 2.50, 2: 2.85, 3: 3.50}
PICK_PACK_NOTE = ("Pick & pack is tiered on order quantity: 1 unit $2.50, 2 units $2.85, "
                  "3 units $3.50. Without the Order scope we cannot see units-per-order, "
                  "so this is estimated at the 1-unit tier x orders.")

LOCKED_ROWS = [
    {"id": "ad_spend", "label": "Ad spend (GMV Max / TikTok Ads)",
     "reason": "Not in the TikTok Shop API at all — ad data lives in the TikTok Ads API, "
               "which is a separate app with its own owner approval.",
     "unlocks": "True blended ROAS, cost per acquisition, and organic-vs-paid GMV split."},
    {"id": "order_detail", "label": "Units per order / shipping actuals",
     "reason": "Order scope is not granted (TikTok returns 105005 Access denied).",
     "unlocks": "Exact pick & pack tiers instead of the 1-unit estimate, real per-order "
                "shipping, and sample identification."},
    {"id": "product_detail", "label": "SKU-level cost sync",
     "reason": "Product scope is not granted (105005 Access denied).",
     "unlocks": "COGS pulled from the catalogue instead of the hardcoded November card."},
]


def month_bounds(month: str):
    """'YYYY-MM' -> (first day, days in month)."""
    y, m = int(month[:4]), int(month[5:7])
    return dt.date(y, m, 1), calendar.monthrange(y, m)[1]


def prorata(month: str, through: str) -> Dict[str, Any]:
    """Fraction of the month covered by data, month start -> `through` inclusive.

    AJ described the window as 'start of the month until 2 days prior', but the
    real boundary is the API's own latest_available_date, so that is what we use
    and what we show.
    """
    first, days_in_month = month_bounds(month)
    try:
        last = dt.date.fromisoformat(through)
    except (TypeError, ValueError):
        last = first
    if last < first:
        last = first
    days = min((last - first).days + 1, days_in_month)
    return {"days": days, "days_in_month": days_in_month,
            "fraction": round(days / days_in_month, 4),
            "through": last.isoformat(), "month_start": first.isoformat(),
            "explain": f"{days} of {days_in_month} days = "
                       f"{round(100 * days / days_in_month, 1)}% of the month"}


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


def settlement_summary(statements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll up finance statements. The settlement identity we rely on:
    net sales + shipping - referral - commission - smart promo - refund admin = settlement.
    Smart Promotion is a ROLL-UP: use 'Smart Promotion fee' + 'campaign period fee'.
    """
    agg = {"settlement": 0.0, "revenue": 0.0, "fees": 0.0, "refunds": 0.0,
           "shipping": 0.0, "count": 0, "by_type": {}}
    for s in statements or []:
        agg["count"] += 1
        agg["settlement"] += money(s.get("settlement_amount") or s.get("net_sales_amount"))
        agg["revenue"] += money(s.get("revenue_amount"))
        agg["fees"] += money(s.get("fee_amount")) + money(s.get("fee_tax_amount"))
        agg["refunds"] += money(s.get("adjustment_amount"))
        agg["shipping"] += money(s.get("shipping_cost_amount"))
    for k in ("settlement", "revenue", "fees", "refunds", "shipping"):
        agg[k] = round(agg[k], 2)
    return agg


def build(month: str, through: str,
          sku_mtd: Dict[str, Any],
          settlement: Dict[str, Any],
          creator_result: Dict[str, Any],
          manual_costs: List[Dict[str, Any]],
          overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the P&L. Every row carries its basis and whether it is editable."""
    pr = prorata(month, through)
    rows: List[Dict[str, Any]] = []

    def add(rid, label, value, basis, group, editable=True, note="", kind="cost"):
        rows.append({"id": rid, "label": label, "value": round(float(value or 0), 2),
                     "basis": basis, "group": group, "editable": editable,
                     "note": note, "kind": kind, "locked": False})

    # ---- revenue, order basis
    gmv = sku_mtd.get("gmv") or 0.0
    units = sku_mtd.get("units") or 0
    orders = sku_mtd.get("orders") or 0
    add("gmv", "GMV", gmv, "order", "Revenue", editable=False,
        note="Sum of per-SKU GMV from shop_products/performance.", kind="revenue")
    add("units", "Units sold", units, "order", "Revenue", editable=False, kind="count")
    add("orders", "Orders", orders, "order", "Revenue", editable=False, kind="count")

    # ---- settlement, finance basis (different basis — kept in its own group)
    st = settlement or {}
    add("settled_net", "Settled net (finance feed)", st.get("settlement") or 0.0,
        "settlement", "Settlement", editable=False,
        note="Settlement basis, ~6 days behind order basis. Do NOT add this to GMV.",
        kind="revenue")
    add("tiktok_fees", "TikTok fees", -abs(st.get("fees") or 0.0), "settlement",
        "Settlement", editable=False,
        note="Referral + commission + Smart Promotion (roll-up: Smart Promotion fee + "
             "campaign period fee) + refund admin.")
    add("refunds", "Refunds / adjustments", -abs(st.get("refunds") or 0.0),
        "settlement", "Settlement", editable=False)

    # ---- cost of goods, order basis
    add("cogs", "COGS", -abs(sku_mtd.get("cogs") or 0.0), "order", "Cost of sales",
        note="November card: Soursop $1.57, Black Seed $1.52, Pineapple Mango $2.55; "
             "bundles are the sum of their bottles.")
    add("pick_pack", "Pick & pack (est.)", -abs(orders * PICK_PACK[1]), "order",
        "Cost of sales", note=PICK_PACK_NOTE)

    # ---- creator retainers, from the roster + status rules
    te = (creator_result or {}).get("totals_effective") or {}
    add("retainer_video", "Creator retainers — video", -abs(te.get("retainer_cost_video") or 0.0),
        "roster", "Creators",
        note="Delivered posts x rate per post, with Ended deals pro-rated to their end date.")
    add("retainer_live", "Creator retainers — LIVE", -abs(te.get("retainer_cost_live") or 0.0),
        "roster", "Creators",
        note="LIVE hours x hourly rate, capped at contracted monthly hours.")

    # ---- TikTok fees on an ORDER-basis estimate.
    # Real fees only arrive on settlement basis (~6 days behind), so a month-to-date
    # P&L that used settlement fees alone would understate them badly against
    # order-basis GMV. We derive the effective fee rate actually being charged and
    # apply it to order-basis GMV. It is an ESTIMATE, labelled as one, and editable.
    fee_rate = None
    rev = abs(st.get("revenue") or 0.0)
    if rev > 0 and st.get("fees"):
        fee_rate = round(abs(st["fees"]) / rev, 4)
    est_fees = round(gmv * fee_rate, 2) if fee_rate else 0.0
    add("fees_est", "TikTok fees (estimated)", -abs(est_fees), "order-est",
        "Cost of sales",
        note=(f"No order-basis fee feed exists. Effective rate of {fee_rate*100:.1f}% "
              f"derived from {st.get('count', 0)} settled statements "
              f"(${abs(st.get('fees') or 0):,.2f} of fees on ${rev:,.2f} revenue), "
              f"applied to order-basis GMV. Estimate — edit if you know better."
              if fee_rate else
              "Could not derive a fee rate — no settled statements in this window yet."))

    # ---- manual external costs
    ext_total = 0.0
    ext_rows = []
    for c in manual_costs or []:
        if c.get("month") != month:
            continue
        amt = float(c.get("amount") or 0)
        applied = round(amt * pr["fraction"], 2) if c.get("pro_rata", True) else round(amt, 2)
        ext_total += applied
        ext_rows.append({
            "id": c.get("id"), "description": c.get("description"),
            "category": c.get("category"), "full_amount": round(amt, 2),
            "pro_rata": bool(c.get("pro_rata", True)), "applied": applied,
            "date": c.get("date") or "",
            "explain": (f"{pr['explain']} of ${amt:,.2f}" if c.get("pro_rata", True)
                        else "charged in full, pro-rata off"),
        })
    add("external", "External costs (manual)", -abs(ext_total), "manual", "External",
        editable=False,
        note=f"Pro-rated over {pr['explain']}. Add, edit or switch pro-rata off per line item.")

    # ---- apply cell overrides
    mo = (overrides or {}).get(month, {}) or {}
    for r in rows:
        o = mo.get(r["id"])
        if o:
            r["original_value"] = r["value"]
            r["value"] = round(float(o.get("value") or 0), 2)
            r["overridden"] = True
            r["override_note"] = o.get("note", "")
        else:
            r["overridden"] = False

    # ---- net. Order basis only, so settlement rows are excluded from the total.
    order_rows = [r for r in rows if r["basis"] in ("order", "order-est", "roster", "manual")
                  and r["kind"] in ("revenue", "cost")]
    net = round(sum(r["value"] for r in order_rows), 2)
    gmv_eff = next((r["value"] for r in rows if r["id"] == "gmv"), 0.0)

    return {
        "month": month, "through": through, "prorata": pr,
        "rows": rows, "external_items": ext_rows,
        "locked": LOCKED_ROWS,
        "net": net,
        "net_label": "Net before ad spend",
        "margin": round(net / gmv_eff, 4) if gmv_eff else None,
        "fee_rate": fee_rate,
        "settlement_count": st.get("count", 0),
        # Stated loudly because reading this number as a true net would be wrong:
        # ad spend is the single largest cost at NB and is not obtainable here.
        "net_caveat": ("This is NOT a true bottom line. AD SPEND IS MISSING and cannot be "
                       "pulled — it lives in the TikTok Ads API, which needs its own app and "
                       "owner approval. In October ad spend drove ~72% of GMV at ~1.6 ROAS, "
                       "so the real net will be materially lower than the figure shown. "
                       "TikTok fees here are an estimate derived from settled statements, "
                       "not an order-basis actual."),
        "basis_warning": ("Three bases on this page. Revenue, COGS and retainers are ORDER "
                          "basis (fresh to the data date). TikTok fees are an ORDER-BASIS "
                          "ESTIMATE from the settled fee rate. The Settlement group is "
                          "FINANCE basis and lags ~6 days — it is shown for reconciliation "
                          "and is NOT added into the net."),
        "groups": ["Revenue", "Cost of sales", "Creators", "External", "Settlement"],
    }
