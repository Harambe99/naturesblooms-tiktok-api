"""
Cached read layer. The video feed is ~1,250 rows over 13 pages and takes ~30s,
so tab-switching must not refetch it.

SAFETY: every fetch goes through the tiktok_get passed in by app.py, which is
guarded by assert_read_only. This module adds caching, nothing else — it cannot
reach a write endpoint because it never constructs a path of its own beyond the
analytics paths defined in creators.py / daily.py.
"""
import asyncio
import datetime as dt
import time
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")
TTL_SECONDS = 600                      # 10 minutes; refresh control bypasses it

_cache: Dict[str, Tuple[float, Any]] = {}
_locks: Dict[str, asyncio.Lock] = {}


def est_stamp(ts: Optional[float] = None) -> Dict[str, Any]:
    """Pull-time in US Eastern. zoneinfo handles EST vs EDT, so the label is
    whatever is actually in force on the day rather than a hardcoded 'EST'."""
    t = dt.datetime.fromtimestamp(ts if ts is not None else time.time(), EST)
    return {
        "epoch": int(t.timestamp()),
        "iso": t.isoformat(timespec="seconds"),
        "display": t.strftime("%-d %b %Y, %-I:%M %p"),
        "zone": t.strftime("%Z"),                 # EST or EDT
        "age_seconds": 0,
    }


def _key(name: str, *parts: Any) -> str:
    return name + "|" + "|".join(str(p) for p in parts)


async def cached(name: str, parts, coro_factory, force: bool = False,
                 ttl: int = TTL_SECONDS):
    """Run coro_factory() at most once per TTL per key. Concurrent callers for
    the same key wait on one in-flight fetch rather than stampeding TikTok."""
    k = _key(name, *parts)
    lock = _locks.setdefault(k, asyncio.Lock())
    async with lock:
        hit = _cache.get(k)
        if hit and not force and (time.time() - hit[0]) < ttl:
            return hit[1], hit[0]
        value = await coro_factory()
        now = time.time()
        _cache[k] = (now, value)
        return value, now


def invalidate(prefix: str = "") -> int:
    """Drop cache entries. Called after a store mutation so the UI reflects it."""
    gone = [k for k in _cache if k.startswith(prefix)] if prefix else list(_cache)
    for k in gone:
        _cache.pop(k, None)
    return len(gone)


def stamp_for(fetched_at: float) -> Dict[str, Any]:
    s = est_stamp(fetched_at)
    s["age_seconds"] = max(0, int(time.time() - fetched_at))
    return s
