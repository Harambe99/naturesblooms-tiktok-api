"""
Local persistence for Nature's Blooms app data — goals, roster edits, creator
statuses, P&L overrides and manual costs.

SAFETY: this module writes to OUR disk only. It must never import httpx, call
tiktok_get, or reference the TikTok API in any way. tests/test_local.py enforces
that structurally — do not add network code here.

Storage is a single JSON document, written atomically (temp file + os.replace).
A missing or corrupt file falls back to defaults instead of raising.
"""
import json
import os
import threading
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

_lock = threading.Lock()

DEFAULTS: Dict[str, Any] = {
    # Daily-overview goals. Blank/missing goal -> no RAG colour, just the number.
    "goals": {},                 # {"gmv_day": 3333, "units_day": 20, ...}
    "onboarding": {"waiting": 0, "onboarded": 0, "note": ""},
    # Creator status overrides, keyed "video:handle" / "live:handle" (name when
    # no handle). {"status": "Active|Paused|Ended|Inactive", "end_date": "YYYY-MM-DD"}
    "statuses": {},
    # Roster edits layered over roster.json (the tracker stays source of truth).
    "roster_added": [],          # full creator dicts with "type" video|live
    "roster_overrides": {},      # key -> {field: value} partial overrides
    # P&L cell overrides: {"2026-11": {"row_id": {"value": 123.4, "note": "..", "set_at": ts}}}
    "pnl_overrides": {},
    # Manual external cost line items.
    "manual_costs": [],          # {id, month, description, category, amount, date, pro_rata}
    "_updated_at": 0,
}

VALID_STATUSES = ("Active", "Paused", "Ended", "Inactive")


def store_path() -> Path:
    env = os.getenv("DATA_STORE_PATH", "").strip()
    if env:
        return Path(env)
    if Path("/var/data").is_dir():                 # Render mounted disk
        return Path("/var/data/appdata.json")
    return Path(__file__).parent / "data" / "appdata.json"


def load() -> Dict[str, Any]:
    """Read the store; tolerate a missing or corrupt file by using defaults."""
    p = store_path()
    raw: Dict[str, Any] = {}
    try:
        parsed = json.loads(p.read_text())
        if isinstance(parsed, dict):
            raw = parsed
    except (OSError, json.JSONDecodeError, ValueError):
        raw = {}
    out = deepcopy(DEFAULTS)
    for k, default in DEFAULTS.items():
        v = raw.get(k)
        if v is not None and isinstance(v, type(default)):
            out[k] = v
    return out


def save(data: Dict[str, Any]) -> None:
    """Atomic write: temp file in the same directory, then os.replace."""
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data["_updated_at"] = int(time.time())
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, p)


def _mutate(fn) -> Dict[str, Any]:
    with _lock:
        d = load()
        fn(d)
        save(d)
        return d


# ---------------------------------------------------------------- goals / onboarding
def set_goals(goals: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, float] = {}
    for k, v in (goals or {}).items():
        if v in ("", None):
            continue
        try:
            clean[str(k)[:40]] = float(v)
        except (TypeError, ValueError):
            continue
    return _mutate(lambda d: d.__setitem__("goals", clean))


def set_onboarding(waiting: Any, onboarded: Any, note: str = "") -> Dict[str, Any]:
    def up(d):
        d["onboarding"] = {
            "waiting": int(waiting or 0),
            "onboarded": int(onboarded or 0),
            "note": str(note or "")[:300],
        }
    return _mutate(up)


# ---------------------------------------------------------------- creator status
def set_status(key: str, status: str, end_date: Optional[str] = None) -> Dict[str, Any]:
    status = (status or "").strip().title()
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}")
    if status == "Ended":
        if not end_date:
            raise ValueError("Ended requires an end_date (YYYY-MM-DD)")
        # validate the date shape; raises ValueError if bad
        import datetime as _dt
        _dt.date.fromisoformat(end_date)
    else:
        end_date = None

    def up(d):
        d["statuses"][key] = {"status": status, "end_date": end_date,
                              "set_at": int(time.time())}
    return _mutate(up)


def clear_status(key: str) -> Dict[str, Any]:
    return _mutate(lambda d: d["statuses"].pop(key, None))


# ---------------------------------------------------------------- roster edits
_ROSTER_FIELDS = {"name", "handle", "videos", "rate", "hourly", "hours_cap",
                  "commission", "status", "note"}


def _clean_creator(c: Dict[str, Any]) -> Dict[str, Any]:
    typ = (c.get("type") or "video").strip().lower()
    if typ not in ("video", "live"):
        raise ValueError("type must be 'video' or 'live'")
    name = str(c.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    handle = (c.get("handle") or "").strip().lstrip("@").lower() or None
    out: Dict[str, Any] = {
        "type": typ, "name": name[:80], "handle": handle,
        "commission": str(c.get("commission") or "")[:60],
        "status": str(c.get("status") or "")[:20],
        "note": str(c.get("note") or "")[:400],
        "resolved": bool(handle),
        "custom": True,
        "added_at": int(time.time()),
    }
    def num(k):
        v = c.get(k)
        if v in ("", None):
            return None
        return float(v)
    if typ == "video":
        out["videos"] = int(num("videos") or 0)
        out["rate"] = float(num("rate") or 0.0)
    else:
        out["hourly"] = num("hourly")
        cap = num("hours_cap")
        out["hours_cap"] = int(cap) if cap else None
    return out


def add_creator(c: Dict[str, Any]) -> Dict[str, Any]:
    row = _clean_creator(c)
    def up(d):
        # replace a previous custom row for the same handle/name instead of duping
        key = (row["type"], row["handle"] or row["name"].lower())
        d["roster_added"] = [
            r for r in d["roster_added"]
            if ((r.get("type"), (r.get("handle") or r.get("name", "").lower())) != key)
        ]
        d["roster_added"].append(row)
    return _mutate(up)


def remove_added_creator(typ: str, handle_or_name: str) -> Dict[str, Any]:
    k = (typ, (handle_or_name or "").lower())
    def up(d):
        d["roster_added"] = [
            r for r in d["roster_added"]
            if ((r.get("type"), (r.get("handle") or r.get("name", "").lower())) != k)
        ]
    return _mutate(up)


def set_roster_override(key: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    clean = {k: v for k, v in (fields or {}).items() if k in _ROSTER_FIELDS}
    def up(d):
        if clean:
            cur = d["roster_overrides"].get(key, {})
            cur.update(clean)
            d["roster_overrides"][key] = cur
        else:
            d["roster_overrides"].pop(key, None)
    return _mutate(up)


def clear_roster_override(key: str) -> Dict[str, Any]:
    return _mutate(lambda d: d["roster_overrides"].pop(key, None))


# ---------------------------------------------------------------- P&L overrides
def set_pnl_override(month: str, row_id: str, value: Any, note: str = "") -> Dict[str, Any]:
    val = float(value)
    def up(d):
        m = d["pnl_overrides"].setdefault(month, {})
        m[row_id] = {"value": val, "note": str(note or "")[:200], "set_at": int(time.time())}
    return _mutate(up)


def clear_pnl_override(month: str, row_id: str) -> Dict[str, Any]:
    def up(d):
        m = d["pnl_overrides"].get(month, {})
        m.pop(row_id, None)
        if not m:
            d["pnl_overrides"].pop(month, None)
    return _mutate(up)


# ---------------------------------------------------------------- manual costs
def upsert_cost(c: Dict[str, Any]) -> Dict[str, Any]:
    month = str(c.get("month") or "").strip()
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")
    desc = str(c.get("description") or "").strip()
    if not desc:
        raise ValueError("description is required")
    row = {
        "id": str(c.get("id") or uuid.uuid4().hex[:10]),
        "month": month,
        "description": desc[:200],
        "category": str(c.get("category") or "Other")[:60],
        "amount": float(c.get("amount") or 0),
        "date": str(c.get("date") or "")[:10],
        "pro_rata": bool(c.get("pro_rata", True)),
    }
    def up(d):
        d["manual_costs"] = [x for x in d["manual_costs"] if x.get("id") != row["id"]]
        d["manual_costs"].append(row)
    return _mutate(up)


def delete_cost(cost_id: str) -> Dict[str, Any]:
    return _mutate(lambda d: d.__setitem__(
        "manual_costs", [x for x in d["manual_costs"] if x.get("id") != cost_id]))
