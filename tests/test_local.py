"""
Tests for the local data layer.

The important one is test_store_cannot_reach_tiktok: the app now has POST routes
so AJ can edit the P&L and the roster. Those writes must be structurally unable
to reach TikTok Shop. If someone later adds an HTTP client to store.py, this
test fails loudly.
"""
import ast
import datetime as dt
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import creators as C  # noqa: E402
import pnl as P  # noqa: E402
import store as S  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_STORE_PATH", str(tmp_path / "appdata.json"))
    yield


# ---------------------------------------------------------------- safety
NETWORK_NAMES = {"httpx", "requests", "urllib", "urllib3", "http", "socket",
                 "aiohttp", "websockets"}


def _code_identifiers_and_strings(path: Path):
    """Identifiers, attributes and string literals that are real CODE — docstrings
    and comments are excluded, so a module may describe its own guarantees in
    prose without tripping the check."""
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docstrings.add(d)
    names, strings, imported = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                strings.add(node.value)
        elif isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return names, strings, imported


def test_store_cannot_reach_tiktok():
    """store.py must import no HTTP client and call nothing TikTok-shaped."""
    names, strings, imported = _code_identifiers_and_strings(
        Path(__file__).resolve().parent.parent / "store.py")
    assert not (imported & NETWORK_NAMES), \
        f"store.py imports network code: {imported & NETWORK_NAMES}"
    for banned in ("tiktok_get", "tiktok_post", "assert_read_only", "APP_SECRET"):
        assert banned not in names, f"store.py calls {banned!r} in code"
    for s in strings:
        low = s.lower()
        assert "tiktok" not in low and "http" not in low, \
            f"store.py has a network-looking literal: {s[:60]!r}"


def test_local_write_modules_are_offline():
    """pnl.py and daily.py must not construct their own TikTok paths beyond the
    documented read-only analytics/finance endpoints."""
    for mod in ("pnl.py", "daily.py"):
        src = (Path(__file__).resolve().parent.parent / mod).read_text()
        assert "httpx" not in src, f"{mod} imports httpx directly"
        for banned in ("/product/", "/order/202", "update", "deactivate"):
            # these modules only ever read; a write verb here is a bug
            assert f'"{banned}' not in src, f"{mod} mentions {banned!r}"


# ---------------------------------------------------------------- status model
def test_four_statuses_only():
    assert C.STATUSES == ("Active", "Paused", "Ended", "Inactive")
    with pytest.raises(ValueError):
        S.set_status("video:x", "Deleted")


def test_ended_requires_a_date():
    with pytest.raises(ValueError):
        S.set_status("video:x", "Ended")
    S.set_status("video:x", "Ended", "2026-11-15")
    assert S.load()["statuses"]["video:x"]["end_date"] == "2026-11-15"


def test_ended_bad_date_rejected():
    with pytest.raises(ValueError):
        S.set_status("video:x", "Ended", "15-11-2026")


def _one_video_roster(rate=100.0, videos=30, status=""):
    return {"video": [{"name": "T", "handle": "t", "videos": videos, "rate": rate,
                       "status": status, "resolved": True}], "live": []}


def _result(rate=100.0, videos=30, posted=2, status=""):
    vids = [{"id": str(i), "username": "t", "gmv": {"amount": "10"},
             "views": 1, "units_sold": 1, "sku_orders": 1,
             "video_post_time": f"2026-11-0{i+1} 10:00:00"} for i in range(posted)]
    roster = C.merge_roster(_one_video_roster(rate, videos, status), {})
    return C.build(vids, roster, "2026-11-01", "2026-11-30", lives=[])


def test_active_counts_full_commitment():
    r = C.apply_statuses(_result(), {}, dt.date(2026, 11, 1))
    row = r["creators"][0]
    assert row["eff_status"] == "Active"
    assert row["earned_eff"] == 200.0          # 2 posts x $100
    assert row["committed_eff"] == 3000.0      # 30 x $100


def test_inactive_removes_cost_but_keeps_posts():
    r = C.apply_statuses(_result(), {"video:t": {"status": "Inactive"}}, dt.date(2026, 11, 1))
    row = r["creators"][0]
    assert row["posted"] == 2                  # still visible
    assert row["earned_eff"] == 0.0
    assert row["retainer_cost"] == 0.0


def test_paused_freezes_commitment_at_earned():
    r = C.apply_statuses(_result(), {"video:t": {"status": "Paused"}}, dt.date(2026, 11, 1))
    row = r["creators"][0]
    assert row["earned_eff"] == 200.0
    assert row["committed_eff"] == 200.0       # frozen, not 3000
    assert row["retainer_cost"] == 200.0


def test_ended_prorates_commitment_by_end_date():
    r = C.apply_statuses(_result(),
                         {"video:t": {"status": "Ended", "end_date": "2026-11-15"}},
                         dt.date(2026, 11, 1))
    row = r["creators"][0]
    assert row["prorata"]["days_engaged"] == 15
    assert row["prorata"]["days_in_month"] == 30
    assert row["committed_eff"] == 1500.0      # half of $3,000
    assert row["retainer_cost"] == 1500.0      # > earned, so pro-rata wins


def test_ended_never_pays_less_than_earned():
    """Ended early but already delivered a lot: cost must not drop below earned."""
    r = C.apply_statuses(_result(rate=100.0, videos=30, posted=2),
                         {"video:t": {"status": "Ended", "end_date": "2026-11-01"}},
                         dt.date(2026, 11, 1))
    row = r["creators"][0]
    assert row["committed_eff"] == 100.0       # 1/30 of 3000
    assert row["retainer_cost"] == 200.0       # earned wins


# ---------------------------------------------------------------- roster merge
def test_roster_override_marks_fields():
    seed = _one_video_roster()
    sdata = {"roster_overrides": {"video:t": {"rate": 50.0}}, "roster_added": []}
    merged = C.merge_roster(seed, sdata)
    assert merged["video"][0]["rate"] == 50.0
    assert merged["video"][0]["overridden_fields"] == ["rate"]
    assert merged["video"][0]["source"] == "tracker"


def test_added_creator_appears_as_custom():
    S.add_creator({"type": "video", "name": "New Person", "handle": "@NewPerson",
                   "videos": 4, "rate": 25})
    merged = C.merge_roster(_one_video_roster(), S.load())
    added = [c for c in merged["video"] if c["name"] == "New Person"]
    assert len(added) == 1
    assert added[0]["handle"] == "newperson"   # normalised, @ stripped
    assert added[0]["source"] == "custom"


def test_add_creator_requires_a_name():
    with pytest.raises(ValueError):
        S.add_creator({"type": "video", "handle": "x"})


def test_real_roster_reproduces_the_sheet_totals():
    """The tracker sheet's own totals: $10,391.45 video + $4,000 hourly."""
    merged = C.merge_roster(C.load_roster(), {})
    out = C.build([], merged, "2026-11-01", "2026-11-30", lives=[])
    out = C.apply_statuses(out, {}, dt.date(2026, 11, 1))
    te = out["totals_effective"]
    assert te["committed"] == 10391.45
    assert te["live_committed"] == 4000.0
    assert len(out["creators"]) + len(out["live_creators"]) == 23


# ---------------------------------------------------------------- handle checks
def _feed():
    vids = [{"id": "1", "username": "juicegyalprncess", "gmv": {"amount": "100"}},
            {"id": "2", "username": "marismyxx", "gmv": {"amount": "50"}}]
    lives = [{"id": "L", "username": "myblackgirlroots",
              "sales_performance": {"gmv": {"amount": "521.84"}}}]
    return vids, lives


def test_handle_found_reports_counts():
    v = C.validate_handle("marismyxx", *_feed())
    assert v["status"] == "ok" and v["videos"] == 1


def test_scrambled_typo_is_suggested():
    """princessjuicegyal -> juicegyalprncess: same letters, different order."""
    v = C.validate_handle("princessjuicegyal", *_feed())
    assert v["status"] == "not_found"
    assert "juicegyalprncess" in [s["handle"] for s in v["suggestions"]]


def test_unknown_handle_has_no_false_match():
    v = C.validate_handle("totallyunrelatedxyz", *_feed())
    assert v["status"] == "not_found"


def test_empty_handle_is_flagged_not_crashed():
    assert C.validate_handle(None, *_feed())["status"] == "empty"


def test_null_handle_does_not_crash_build():
    roster = {"video": [{"name": "Unresolved", "handle": None, "videos": 4,
                         "rate": 175.0, "status": "", "resolved": False}], "live": []}
    out = C.build([], C.merge_roster(roster, {}), "2026-11-01", "2026-11-30", lives=[])
    assert out["creators"][0]["posted"] == 0
    assert out["creators"][0]["resolved"] is False


# ---------------------------------------------------------------- P&L
def test_prorata_explains_itself():
    pr = P.prorata("2026-11", "2026-11-08")
    assert pr["days"] == 8 and pr["days_in_month"] == 30
    assert pr["fraction"] == round(8 / 30, 4)
    assert "8 of 30 days" in pr["explain"]


def test_prorata_clamps_to_month_end():
    pr = P.prorata("2026-11", "2026-12-25")
    assert pr["days"] == 30


def test_manual_cost_prorates_and_can_be_switched_off():
    S.upsert_cost({"month": "2026-11", "description": "Team", "amount": 3000,
                   "pro_rata": True})
    S.upsert_cost({"month": "2026-11", "description": "Software", "amount": 600,
                   "pro_rata": False})
    sku = {"gmv": 1000.0, "units": 10, "orders": 10, "cogs": 20.0}
    out = P.build("2026-11", "2026-11-15", sku, {}, {"totals_effective": {}},
                  S.load()["manual_costs"], {})
    byd = {x["description"]: x for x in out["external_items"]}
    assert byd["Team"]["applied"] == round(3000 * 0.5, 2)
    assert byd["Software"]["applied"] == 600.0


def test_cost_requires_month_and_description():
    with pytest.raises(ValueError):
        S.upsert_cost({"description": "x", "amount": 1})
    with pytest.raises(ValueError):
        S.upsert_cost({"month": "2026-11", "amount": 1})


def test_pnl_cell_override_keeps_the_original():
    sku = {"gmv": 1000.0, "units": 10, "orders": 10, "cogs": 20.0}
    out = P.build("2026-11", "2026-11-15", sku, {}, {"totals_effective": {}}, [],
                  {"2026-11": {"cogs": {"value": -99.0, "note": "corrected"}}})
    row = [r for r in out["rows"] if r["id"] == "cogs"][0]
    assert row["value"] == -99.0
    assert row["original_value"] == -20.0
    assert row["overridden"] is True


def test_net_excludes_settlement_basis_rows():
    """Mixing order basis and settlement basis in one total is the bug that
    produced bad October numbers. The net must use order basis only."""
    sku = {"gmv": 1000.0, "units": 10, "orders": 10, "cogs": 20.0}
    settle = {"settlement": 5000.0, "fees": 300.0, "refunds": 50.0}
    out = P.build("2026-11", "2026-11-15", sku, settle, {"totals_effective": {}}, [], {})
    assert all(r["basis"] != "settlement"
               for r in out["rows"]
               if r["basis"] in ("order", "roster", "manual"))
    # net must not include the 5000 settlement figure
    assert out["net"] < 1000.0


def test_locked_rows_are_reported_not_hidden():
    out = P.build("2026-11", "2026-11-15",
                  {"gmv": 0, "units": 0, "orders": 0, "cogs": 0},
                  {}, {"totals_effective": {}}, [], {})
    ids = {l["id"] for l in out["locked"]}
    assert {"ad_spend", "order_detail", "product_detail"} <= ids
    for l in out["locked"]:
        assert l["reason"] and l["unlocks"]


# ---------------------------------------------------------------- store durability
def test_corrupt_store_falls_back_to_defaults(tmp_path, monkeypatch):
    p = tmp_path / "broken.json"
    p.write_text("{not json at all")
    monkeypatch.setenv("DATA_STORE_PATH", str(p))
    d = S.load()
    assert d["goals"] == {} and d["manual_costs"] == []


def test_missing_store_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_STORE_PATH", str(tmp_path / "nope" / "x.json"))
    assert S.load()["statuses"] == {}


def test_save_is_atomic_and_round_trips():
    S.set_goals({"gmv_day": 3333})
    assert S.load()["goals"]["gmv_day"] == 3333.0
    S.set_goals({"gmv_day": ""})               # blank clears
    assert "gmv_day" not in S.load()["goals"]


def test_fee_estimate_derives_from_settled_rate_and_is_editable():
    """Fees must be estimated onto order-basis GMV, not left at zero, because
    the settlement feed lags ~6 days behind the GMV it would offset."""
    sku = {"gmv": 1000.0, "units": 10, "orders": 10, "cogs": 20.0}
    settle = {"revenue": 500.0, "fees": -100.0, "count": 3, "settlement": 400.0,
              "refunds": 0.0}
    out = P.build("2026-11", "2026-11-15", sku, settle, {"totals_effective": {}}, [], {})
    assert out["fee_rate"] == 0.2                      # 100/500
    row = [r for r in out["rows"] if r["id"] == "fees_est"][0]
    assert row["value"] == -200.0                      # 20% of 1,000 GMV
    assert row["editable"] is True
    assert row["basis"] == "order-est"


def test_net_is_labelled_as_excluding_ad_spend():
    """Calling this a true net would mislead — ad spend is unobtainable."""
    out = P.build("2026-11", "2026-11-15",
                  {"gmv": 100.0, "units": 1, "orders": 1, "cogs": 2.0},
                  {}, {"totals_effective": {}}, [], {})
    assert "ad spend" in out["net_label"].lower()
    assert "AD SPEND IS MISSING" in out["net_caveat"]


def test_fee_estimate_absent_when_no_settled_data():
    out = P.build("2026-11", "2026-11-15",
                  {"gmv": 100.0, "units": 1, "orders": 1, "cogs": 2.0},
                  {"revenue": 0.0, "fees": 0.0}, {"totals_effective": {}}, [], {})
    assert out["fee_rate"] is None
    row = [r for r in out["rows"] if r["id"] == "fees_est"][0]
    assert row["value"] == 0.0
    assert "Could not derive" in row["note"]
