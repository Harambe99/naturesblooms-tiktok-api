"""
Nature's Blooms — TikTok Shop API connector.

Three jobs, nothing else:
  1. /connect   send the seller to TikTok to authorise this app
  2. /callback  receive the auth code, swap it for tokens, store the refresh token
  3. /api/*     call TikTok Shop Open API with a valid access token

Secrets come from environment variables only. Nothing is ever hardcoded.
"""
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

APP_KEY = os.getenv("TTS_APP_KEY", "")
APP_SECRET = os.getenv("TTS_APP_SECRET", "")
SERVICE_ID = os.getenv("TTS_SERVICE_ID", "")
REDIRECT_URI = os.getenv("TTS_REDIRECT_URI", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
TOKEN_PATH = Path(os.getenv("TOKEN_STORE_PATH", "/tmp/tokens.json"))
# Paste the last known refresh token here to recover WITHOUT re-authorising if the
# disk is ever lost. The app promotes it to the real store on boot, then ignores it.
TOKEN_BOOTSTRAP = os.getenv("TOKEN_BOOTSTRAP", "").strip()
# Refresh this often (hours) regardless of expiry, so the chain never lapses.
REFRESH_EVERY_H = float(os.getenv("REFRESH_EVERY_HOURS", "6"))
# Optional: POSTed a JSON body if a refresh fails. Slack/Discord webhook works.
ALERT_WEBHOOK = os.getenv("ALERT_WEBHOOK", "").strip()

# TikTok Shop hosts. Verify against partner.tiktokshop.com/docv2 before going live —
# TikTok has changed these between API versions.
AUTH_BASE = os.getenv("TTS_AUTH_BASE", "https://services.tiktokshops.us/open/authorize")
TOKEN_BASE = "https://auth.tiktok-shops.com/api/v2/token"
API_BASE = "https://open-api.tiktokglobalshop.com"

app = FastAPI(title="NB TikTok Shop connector", docs_url=None, redoc_url=None)
_oauth_state: Dict[str, float] = {}
_refresh_log: Dict[str, Any] = {"last_ok": None, "last_error": None, "attempts": 0}


# ---------------------------------------------------------------- token store
def load_tokens() -> Dict[str, Any]:
    if TOKEN_PATH.exists():
        try:
            return json.loads(TOKEN_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_tokens(data: Dict[str, Any]) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(data, indent=2))
    TOKEN_PATH.chmod(0o600)


def require_admin(token: Optional[str]) -> None:
    """Constant-time check so these endpoints are not open to the internet."""
    if not ADMIN_TOKEN or not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="admin token required")


# ---------------------------------------------------------------- SAFETY
# GROUND RULE: this service is READ-ONLY against TikTok Shop. It must never be
# capable of changing a price, editing a product, touching inventory, cancelling
# or shipping an order, issuing a refund, or altering any shop setting.
#
# Three independent layers enforce that. All three must pass before any request
# leaves this process. They are deliberately redundant: a mistake in one is
# caught by the others, including a mistake made by an AI editing this file.

READ_ONLY = os.getenv("READ_ONLY", "true").strip().lower() != "false"

# Layer 1 — only these exact path prefixes may ever be called.
ALLOWED_PREFIXES = (
    "/authorization/",          # which shops authorised us
    "/finance/",                # statements, settlements — the P&L
    "/order/",                  # order search and detail (read verbs only, see layer 2)
    "/product/",                # product and SKU names for COGS
    "/fulfillment/",            # parcel weight
    "/return_refund/",          # returns and cancellations, read only
    "/affiliate_seller/",       # creator performance
    "/analytics/",              # shop, video and LIVE analytics
)

# Layer 2 — any path containing one of these is refused outright, even inside an
# allowed prefix. These are the verbs that change money, stock or listings.
FORBIDDEN_TOKENS = frozenset({
    "create", "add", "update", "edit", "set", "upload", "activate", "deactivate",
    "delete", "remove", "cancel", "reject", "approve", "issue", "confirm",
    "ship", "pack", "fulfil", "fulfill", "price", "prices", "inventory", "stock",
    "publish", "unpublish", "promotion", "promotions", "coupon", "coupons",
    "deduct", "withdraw", "transfer", "pay", "upsert", "modify", "adjust",
})


# NARROW EXCEPTION, approved by AJ on 10 Nov 2026.
# TikTok puts search filters in a request body, so its search endpoints are POST.
# POST is therefore permitted, but ONLY to a path ending in /search, ONLY under an
# allowlisted prefix, and ONLY if it contains no write verb. Search reads rows.
# It cannot create, modify or delete. PUT, PATCH and DELETE remain blocked outright.


class UnsafeCall(Exception):
    """Raised before anything is sent. A bug here fails closed, never open."""


def assert_read_only(method: str, path: str) -> None:
    if not READ_ONLY:
        raise UnsafeCall("READ_ONLY was disabled — refusing to run at all")
    m = method.upper()
    if m == "POST":
        # POST is permitted only for SEARCH. A path that ends in /search under an
        # allowlisted prefix reads rows and returns them; it has no write semantics.
        # The write-verb check below still applies, so /search cannot smuggle one in.
        if not path.rstrip("/").endswith("/search"):
            raise UnsafeCall(
                f"POST {path!r} blocked: POST is only ever allowed to a /search endpoint"
            )
    elif m != "GET":
        raise UnsafeCall(f"{m} blocked: only GET, plus POST to named search endpoints")
    prefix = next((p for p in ALLOWED_PREFIXES if path.startswith(p)), None)
    if prefix is None:
        raise UnsafeCall(f"path {path!r} is not on the allowlist")
    # Match whole words, not substrings, so "packages" is not mistaken for "pack".
    # Split on the separators TikTok uses in paths: / _ - and version digits.
    # Scan only what follows the allowlisted prefix, so a prefix like
    # "/return_refund/" is not mistaken for a write verb.
    tail = path[len(prefix):].lower()
    words = {w for w in re.split(r"[/_\-]+", tail) if w and not w.isdigit()}
    hit = words & set(FORBIDDEN_TOKENS)
    if hit:
        raise UnsafeCall(f"path {path!r} contains a write verb ({sorted(hit)[0]!r})")


# ---------------------------------------------------------------- signing
def sign(path: str, params: Dict[str, Any], body: str = "") -> str:
    """
    TikTok Shop request signature.

    Sort every query param except `sign` and `access_token`, concatenate
    key+value, wrap the whole thing in the API path and the app secret,
    then HMAC-SHA256 with the secret.
    """
    excluded = {"sign", "access_token"}
    pairs = sorted((k, v) for k, v in params.items() if k not in excluded)
    base = "".join(f"{k}{v}" for k, v in pairs)
    payload = f"{path}{base}{body}"
    wrapped = f"{APP_SECRET}{payload}{APP_SECRET}"
    return hmac.new(APP_SECRET.encode(), wrapped.encode(), hashlib.sha256).hexdigest()


async def tiktok_get(path: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Signed GET against the Open API. Every call passes the safety gate first."""
    try:
        assert_read_only("GET", path)
    except UnsafeCall as e:
        raise HTTPException(status_code=403, detail=f"blocked by read-only guard: {e}")
    tokens = load_tokens()
    access = tokens.get("access_token")
    if not access:
        raise HTTPException(status_code=409, detail="not connected — visit /connect first")
    if tokens.get("access_token_expire_in", 0) < time.time() + 120:
        tokens = await do_refresh()
        access = tokens["access_token"]

    params: Dict[str, Any] = {
        "app_key": APP_KEY,
        "timestamp": int(time.time()),
        "shop_cipher": tokens.get("shop_cipher", ""),
    }
    params.update(extra or {})
    params = {k: v for k, v in params.items() if v not in ("", None)}
    params["sign"] = sign(path, params)

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{API_BASE}{path}",
            params=params,
            headers={"x-tts-access-token": access, "content-type": "application/json"},
        )
    try:
        data = r.json()
    except ValueError:
        raise HTTPException(status_code=502, detail=f"non-JSON from TikTok: {r.text[:300]}")
    if data.get("code") not in (0, None):
        raise HTTPException(status_code=502, detail=data)
    return data


async def alert(msg: str) -> None:
    """Best-effort shout if the token chain is in trouble. Never raises."""
    if not ALERT_WEBHOOK:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(ALERT_WEBHOOK, json={"content": f"NB TikTok connector: {msg}",
                                              "text": f"NB TikTok connector: {msg}"})
    except Exception:
        pass


def bootstrap_from_env() -> None:
    """
    Disk wiped? Set TOKEN_BOOTSTRAP to the last refresh token and redeploy.
    The next refresh mints a fresh pair and normal service resumes — no re-auth.
    """
    if not TOKEN_BOOTSTRAP:
        return
    t = load_tokens()
    if t.get("refresh_token"):
        return                                  # real store wins
    save_tokens({"refresh_token": TOKEN_BOOTSTRAP, "bootstrapped_at": int(time.time())})


async def refresh_loop() -> None:
    """
    Keeps the chain alive on a timer so nothing depends on traffic arriving.
    Each successful refresh reissues both tokens, so refreshing often is what
    makes this a once-off authorisation rather than a recurring chore.
    """
    await asyncio.sleep(10)                     # let the app finish booting
    while True:
        try:
            t = load_tokens()
            if t.get("refresh_token"):
                exp = t.get("access_token_expire_in", 0)
                due = (not exp) or exp - time.time() < REFRESH_EVERY_H * 3600
                if due:
                    await do_refresh()
                    _refresh_log["last_ok"] = int(time.time())
                    _refresh_log["last_error"] = None
        except Exception as e:                  # never let the loop die
            _refresh_log["last_error"] = f"{type(e).__name__}: {e}"
            _refresh_log["attempts"] += 1
            if _refresh_log["attempts"] in (3, 10, 30):
                await alert(f"refresh failing ({_refresh_log['attempts']}x): {e}")
        await asyncio.sleep(max(REFRESH_EVERY_H, 0.25) * 3600)


@app.on_event("startup")
async def _startup() -> None:
    bootstrap_from_env()
    asyncio.create_task(refresh_loop())


async def tiktok_post(path: str, body: Optional[Dict[str, Any]] = None,
                      extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Signed POST — only ever reaches the allowlisted search endpoints."""
    try:
        assert_read_only("POST", path)
    except UnsafeCall as e:
        raise HTTPException(status_code=403, detail=f"blocked by read-only guard: {e}")

    tokens = load_tokens()
    access = tokens.get("access_token")
    if not access:
        raise HTTPException(status_code=409, detail="not connected — visit /connect first")
    if tokens.get("access_token_expire_in", 0) < time.time() + 120:
        tokens = await do_refresh()
        access = tokens["access_token"]

    payload = json.dumps(body or {}, separators=(",", ":"))
    params: Dict[str, Any] = {
        "app_key": APP_KEY,
        "timestamp": int(time.time()),
        "shop_cipher": tokens.get("shop_cipher", ""),
    }
    params.update(extra or {})
    params = {k: v for k, v in params.items() if v not in ("", None)}
    params["sign"] = sign(path, params, payload)

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{API_BASE}{path}", params=params, content=payload,
            headers={"x-tts-access-token": access, "content-type": "application/json"},
        )
    try:
        data = r.json()
    except ValueError:
        raise HTTPException(status_code=502, detail=f"non-JSON from TikTok: {r.text[:300]}")
    if data.get("code") not in (0, None):
        raise HTTPException(status_code=502, detail=data)
    return data


# ---------------------------------------------------------------- oauth
@app.get("/connect")
async def connect(admin: str = Query(..., description="ADMIN_TOKEN")):
    """Step 1 — send the seller to TikTok to authorise."""
    require_admin(admin)
    for k, v in list(_oauth_state.items()):          # drop stale state
        if v < time.time() - 900:
            _oauth_state.pop(k, None)
    state = secrets.token_urlsafe(24)
    _oauth_state[state] = time.time()
    url = f"{AUTH_BASE}?service_id={SERVICE_ID}&state={state}"
    return RedirectResponse(url, status_code=302)


@app.get("/callback")
async def callback(code: str = "", state: str = "", app_key: str = ""):
    """
    Step 2 — TikTok sends the seller back here with ?code=...
    This URL must match the Redirect URL saved in Partner Center exactly.
    """
    if not code:
        raise HTTPException(status_code=400, detail="no auth code in callback")
    if state and state not in _oauth_state:
        raise HTTPException(status_code=400, detail="unknown or expired state")
    _oauth_state.pop(state, None)

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{TOKEN_BASE}/get",
            params={
                "app_key": APP_KEY,
                "app_secret": APP_SECRET,
                "auth_code": code,
                "grant_type": "authorized_code",
            },
        )
    payload = r.json()
    if payload.get("code") not in (0, None):
        raise HTTPException(status_code=502, detail=payload)

    data = payload.get("data", payload)
    data["connected_at"] = int(time.time())
    save_tokens(data)
    return HTMLResponse(
        "<h2>Connected.</h2><p>Nature&rsquo;s Blooms is now authorised. "
        "You can close this tab.</p>"
    )


async def do_refresh() -> Dict[str, Any]:
    tokens = load_tokens()
    rt = tokens.get("refresh_token")
    if not rt:
        raise HTTPException(status_code=409, detail="no refresh token — visit /connect")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{TOKEN_BASE}/refresh",
            params={
                "app_key": APP_KEY,
                "app_secret": APP_SECRET,
                "refresh_token": rt,
                "grant_type": "refresh_token",
            },
        )
    payload = r.json()
    if payload.get("code") not in (0, None):
        raise HTTPException(status_code=502, detail=payload)
    data = payload.get("data", payload)
    data["connected_at"] = tokens.get("connected_at")
    data["refreshed_at"] = int(time.time())
    save_tokens(data)
    _refresh_log["last_ok"] = int(time.time())
    _refresh_log["attempts"] = 0
    return data


@app.get("/refresh")
async def refresh(admin: str = Query(...)):
    require_admin(admin)
    d = await do_refresh()
    return {"ok": True, "expires_at": d.get("access_token_expire_in")}


# ---------------------------------------------------------------- data pulls
@app.get("/api/shops")
async def shops(admin: str = Query(...)):
    """Call this once after connecting — it returns the shop_cipher you need."""
    require_admin(admin)
    data = await tiktok_get("/authorization/202309/shops")
    shops_list = data.get("data", {}).get("shops", [])
    if shops_list:                                    # cache the cipher for later calls
        t = load_tokens()
        t["shop_cipher"] = shops_list[0].get("cipher", "")
        t["shop_name"] = shops_list[0].get("name", "")
        save_tokens(t)
    return data


@app.get("/api/orders")
async def orders(
    admin: str = Query(...),
    start: int = Query(..., description="unix seconds"),
    end: int = Query(..., description="unix seconds"),
    page_size: int = 50,
):
    require_admin(admin)
    return await tiktok_post(
        "/order/202309/orders/search",
        body={"create_time_ge": start, "create_time_lt": end},
        extra={"page_size": page_size},
    )


@app.get("/api/settlements")
async def settlements(
    admin: str = Query(...),
    start: int = Query(...),
    end: int = Query(...),
    page_size: int = 50,
    sort_field: str = "statement_time",
    sort_order: str = "DESC",
):
    """The settlement feed — this is what the P&L is built on."""
    require_admin(admin)
    return await tiktok_get(
        "/finance/202309/statements",
        {
            "page_size": page_size,
            "statement_time_ge": start,
            "statement_time_lt": end,
            "sort_field": sort_field,
            "sort_order": sort_order,
        },
    )


@app.get("/api/probe")
async def probe(admin: str = Query(...), path: str = Query(...), method: str = "GET",
                body: str = "{}", extra: str = "{}"):
    """Diagnostic. Still passes the same guard — it cannot reach a write endpoint."""
    require_admin(admin)
    try:
        ex = json.loads(extra); bd = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"bad JSON: {e}")
    if method.upper() == "POST":
        return await tiktok_post(path, body=bd, extra=ex)
    return await tiktok_get(path, ex)


# ---------------------------------------------------------------- creator tracker
@app.get("/api/creators")
async def api_creators(admin: str = Query(...),
                       start: str = Query(..., description="YYYY-MM-DD"),
                       end: str = Query(..., description="YYYY-MM-DD, exclusive")):
    require_admin(admin)
    import creators as C
    vids, lives = await asyncio.gather(
        C.fetch_videos(tiktok_get, start, end),
        C.fetch_lives(tiktok_get, start, end),
    )
    return C.build(vids, C.load_roster(), start, end, lives=lives)


# TikTok's creator/video exports lag ~2 days, and the analytics feed behind this
# tracker settles on the same delay. Anything newer than this reads as a partial
# day and under-reports posts, so the picker refuses to go past it.
DATA_LAG_DAYS = 2


def last_complete_day():
    """Most recent date whose creator data is fully settled (today - lag)."""
    import datetime as _dt
    return _dt.date.today() - _dt.timedelta(days=DATA_LAG_DAYS)


@app.get("/creators", response_class=HTMLResponse)
async def creators_page(admin: str = Query(""), start: str = "", end: str = ""):
    """Creator retainer tracker. Pick a creator from the dropdown."""
    import datetime as _dt
    last = last_complete_day()
    max_end = last + _dt.timedelta(days=1)          # end is exclusive

    def clamp(s, default):
        try:
            d = _dt.date.fromisoformat(s)
        except (TypeError, ValueError):
            return default
        return min(d, max_end)

    end_d = clamp(end, max_end)
    start_d = clamp(start, end_d - _dt.timedelta(days=7))
    if start_d >= end_d:
        start_d = end_d - _dt.timedelta(days=7)

    return HTMLResponse(TRACKER_HTML
                        .replace("__START__", start_d.isoformat())
                        .replace("__END__", end_d.isoformat())
                        .replace("__MAXSTART__", last.isoformat())
                        .replace("__MAXEND__", max_end.isoformat())
                        .replace("__LASTDAY__", last.strftime("%-d %b %Y"))
                        .replace("__ADMIN__", admin))


TRACKER_HTML = """
<title>NB creator tracker</title>
<style>
 :root{--ink:#15202b;--mut:#5c6b70;--line:#e3e8ee;--acc:#0e6e5e;--bg:#f7f9fa;
       --good:#2f7d3c;--warn:#9a6400;--bad:#a32c2c}
 *{box-sizing:border-box}
 body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;color:var(--ink);background:#fff}
 .wrap{max-width:70rem;margin:0 auto;padding:2rem 1.5rem 5rem}
 h1{font-size:1.45rem;margin:0 0 .2rem}
 .sub{color:var(--mut);font-size:.9rem;margin:0 0 1.5rem}
 .bar{display:flex;gap:.6rem;flex-wrap:wrap;align-items:end;background:var(--bg);
      border:1px solid var(--line);border-radius:4px;padding:.9rem 1rem;margin-bottom:1.5rem}
 label{display:block;font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;
       color:var(--mut);margin-bottom:.25rem}
 input,select,button{font:inherit;padding:.45rem .6rem;border:1px solid #c9d2da;
       border-radius:3px;background:#fff}
 select{min-width:17rem}
 button{background:var(--acc);color:#fff;border-color:var(--acc);cursor:pointer}
 button:disabled{opacity:.5;cursor:default}
 .cards{display:grid;gap:.7rem;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));margin-bottom:1.5rem}
 .card{border:1px solid var(--line);border-radius:4px;padding:.75rem .9rem;background:var(--bg)}
 .card h4{margin:0 0 .25rem;font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;
          color:var(--mut);font-weight:600}
 .card .v{font-size:1.3rem;font-variant-numeric:tabular-nums}
 table{border-collapse:collapse;width:100%;font-size:.86rem}
 th,td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid var(--line);vertical-align:top}
 th{font-size:.66rem;text-transform:uppercase;letter-spacing:.07em;color:var(--mut);
    border-bottom:1px solid #9aa7b0;cursor:pointer;white-space:nowrap}
 td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
 tr.sel{background:#e3eeeb}
 tbody tr:hover{background:#f2f6f9}
 .pill{font-size:.66rem;padding:.1rem .4rem;border-radius:2px;text-transform:uppercase;letter-spacing:.05em}
 .ok{background:#e6f0e7;color:var(--good)} .no{background:#f6e5e5;color:var(--bad)}
 .mid{background:#f5ebd9;color:var(--warn)}
 a{color:var(--acc)} .scroll{overflow-x:auto}
 .note{font-size:.82rem;color:var(--mut);background:#fdf7e6;border-left:3px solid var(--warn);
       padding:.6rem .8rem;border-radius:0 3px 3px 0;margin:1rem 0}
 h2{font-size:1rem;margin:2rem 0 .5rem;padding-top:1rem;border-top:1px solid var(--line)}
</style>
<div class="wrap">
  <h1>Nature&rsquo;s Blooms &middot; creator tracker</h1>
  <p class="sub">Retainer performance, live from TikTok Shop video analytics.
     TikTok data settles ~2 days late, so the window stops at <b>__LASTDAY__</b> —
     picking anything newer would under-count posts.</p>

  <div class="bar">
    <div><label>admin token</label><input id="adm" value="__ADMIN__" size="30" placeholder="paste token"></div>
    <div><label>from</label><input id="s" type="date" value="__START__" max="__MAXSTART__"></div>
    <div><label>to (exclusive)</label><input id="e" type="date" value="__END__" max="__MAXEND__"></div>
    <div><button id="go">Load</button></div>
    <div style="flex:1"></div>
    <div><label>creator</label><select id="sel"><option value="">— all creators —</option></select></div>
  </div>

  <div id="status" class="sub">Pick a window and press Load.</div>
  <div id="cards" class="cards"></div>
  <div id="body"></div>
</div>
<script>
let DATA=null, SORT={k:'gmv',d:-1};
const $=i=>document.getElementById(i);
const m=n=>'$'+(n||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const n0=n=>(n||0).toLocaleString();

async function load(){
  const a=$('adm').value.trim(); if(!a){$('status').textContent='Enter the admin token.';return;}
  // belt-and-braces: the max= attributes stop the picker, this stops a typed date
  const MAXE='__MAXEND__';
  if($('e').value>MAXE){$('e').value=MAXE;}
  if($('s').value>='__MAXEND__'){$('status').textContent='Start must be before '+MAXE+' — TikTok data is not settled yet.';return;}
  $('go').disabled=true; $('status').textContent='Loading from TikTok…';
  try{
    const r=await fetch(`/api/creators?admin=${encodeURIComponent(a)}&start=${$('s').value}&end=${$('e').value}`);
    if(!r.ok){$('status').textContent='Error '+r.status+' — '+(await r.text()).slice(0,200);return;}
    DATA=await r.json(); fillSelect(); render();
    $('status').textContent=`${DATA.totals.videos_posted} roster videos in ${DATA.window.start} → ${DATA.window.end}`;
  }catch(err){$('status').textContent='Failed: '+err}
  finally{$('go').disabled=false}
}
function fillSelect(){
  const s=$('sel'); s.innerHTML='<option value="">— all creators —</option>';
  DATA.creators.forEach(c=>{
    const o=document.createElement('option'); o.value=c.handle;
    o.textContent=`${c.name} (@${c.handle}) — ${c.posted}/${c.committed_videos} posts`;
    s.appendChild(o);
  });
}
function statusPill(c){
  if(c.status==='Inactive') return '<span class="pill no">inactive</span>';
  if(c.posted===0) return '<span class="pill no">no posts</span>';
  if(c.pace>=0.9) return '<span class="pill ok">on pace</span>';
  if(c.pace>=0.4) return '<span class="pill mid">behind</span>';
  return '<span class="pill no">well behind</span>';
}
function render(){
  const pick=$('sel').value;
  const t=DATA.totals;
  $('cards').innerHTML=[
    ['Posts delivered',`${n0(t.videos_posted)} <span style="font-size:.8rem;color:#5c6b70">/ ${n0(t.videos_committed)}</span>`],
    ['Videos still earning',n0(t.videos_active)],
    ['Earned',m(t.earned)],['Committed',m(t.committed)],
    ['Roster GMV',m(t.roster_gmv)],
    ['Cost per $ GMV', t.roster_gmv? (t.earned/t.roster_gmv).toFixed(2):'—'],
    ['Off-roster GMV',m(t.offroster_gmv)],
    ['LIVE hours',(t.live_hours||0).toFixed(1)],
    ['LIVE earned',m(t.live_earned)],
    ['LIVE GMV',m(t.live_gmv)],
  ].map(([k,v])=>`<div class="card"><h4>${k}</h4><div class="v">${v}</div></div>`).join('');

  if(pick){ renderOne(DATA.creators.find(c=>c.handle===pick)); return; }
  const rows=[...DATA.creators].sort((a,b)=>((a[SORT.k]??-1)-(b[SORT.k]??-1))*SORT.d);
  $('body').innerHTML=`<div class="scroll"><table><thead><tr>
    <th data-k="name">Creator</th><th data-k="posted" class="n">Posts<br><span style="font-weight:400;text-transform:none">in window</span></th>
    <th class="n">Committed</th><th data-k="active_videos" class="n">Still<br><span style="font-weight:400;text-transform:none">earning</span></th><th data-k="pace" class="n">Pace</th>
    <th data-k="earned" class="n">Earned</th><th data-k="gmv" class="n">GMV</th>
    <th data-k="views" class="n">Views</th><th data-k="units" class="n">Units</th>
    <th data-k="roi" class="n">GMV / $1</th><th>Status</th></tr></thead><tbody>
    ${rows.map(c=>`<tr data-h="${c.handle}">
      <td><b>${c.name}</b>${c.attribution==='owned'?' <span class="pill mid" title="'+(c.note||'')+'">brand acct</span>':''}<br><span style="color:#5c6b70;font-size:.78rem">@${c.handle}</span></td>
      <td class="n">${c.posted}</td><td class="n" style="color:#5c6b70">${c.committed_videos}</td>
      <td class="n" style="color:#5c6b70">${c.active_videos}</td>
      <td class="n">${c.pace==null?'—':(c.pace*100).toFixed(0)+'%'}</td>
      <td class="n">${m(c.earned)}</td><td class="n">${m(c.gmv)}</td>
      <td class="n">${n0(c.views)}</td><td class="n">${n0(c.units)}</td>
      <td class="n">${c.roi==null?'—':c.roi.toFixed(2)}</td>
      <td>${statusPill(c)}</td></tr>`).join('')}
    </tbody></table></div>
    <div class="note"><b>How posts are counted.</b> ${DATA.basis_note}</div>
    <h2>LIVE creators</h2>
    <div class="scroll"><table><thead><tr><th>Creator</th><th class="n">Sessions</th>
      <th class="n">Hours</th><th class="n">Cap</th><th class="n">Hourly</th>
      <th class="n">Earned</th><th class="n">Committed</th><th class="n">LIVE GMV</th>
      <th>Commission</th><th>Status</th></tr></thead><tbody>
      ${(DATA.live_creators||[]).map(c=>`<tr>
        <td><b>${c.name}</b><br><span style="color:#5c6b70;font-size:.78rem">${c.handle?'@'+c.handle:'no handle on file'}</span>
          ${c.notes?`<br><span style="color:#9a6400;font-size:.74rem">${c.notes}</span>`:''}</td>
        <td class="n">${c.sessions}</td><td class="n">${c.hours.toFixed(2)}</td>
        <td class="n">${c.hours_cap??'—'}</td><td class="n">${c.hourly==null?'—':m(c.hourly)}</td>
        <td class="n">${m(c.earned)}</td><td class="n">${m(c.committed_cost)}</td>
        <td class="n">${m(c.gmv)}</td><td>${c.commission||'—'}</td>
        <td>${c.status==='Inactive'?'<span class="pill no">inactive</span>':(c.sessions?'<span class="pill ok">live</span>':'<span class="pill mid">no lives</span>')}</td>
      </tr>`).join('')}</tbody></table></div>
    <div class="note">${DATA.live_note}</div>
    <h2>Off-roster creators driving GMV</h2>
    <div class="scroll"><table><thead><tr><th>Handle</th><th class="n">Videos</th>
      <th class="n">GMV</th><th class="n">Views</th><th class="n">Units</th></tr></thead><tbody>
      ${DATA.off_roster.map(o=>`<tr><td>@${o.handle}</td><td class="n">${o.videos}</td>
        <td class="n">${m(o.gmv)}</td><td class="n">${n0(o.views)}</td>
        <td class="n">${n0(o.units)}</td></tr>`).join('')}</tbody></table></div>
    <h2>Off-roster LIVE sellers</h2>
    <div class="scroll"><table><thead><tr><th>Handle</th><th class="n">Sessions</th>
      <th class="n">Hours</th><th class="n">GMV</th></tr></thead><tbody>
      ${(DATA.live_off_roster||[]).map(o=>`<tr><td>@${o.handle}</td><td class="n">${o.sessions}</td>
        <td class="n">${o.hours.toFixed(2)}</td><td class="n">${m(o.gmv)}</td></tr>`).join('')}
      </tbody></table></div>`;
  document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k; SORT = SORT.k===k?{k,d:-SORT.d}:{k,d:-1}; render();});
  document.querySelectorAll('tbody tr[data-h]').forEach(tr=>tr.onclick=()=>{
    $('sel').value=tr.dataset.h; render();});
}
function renderOne(c){
  if(!c){$('body').innerHTML='';return;}
  $('body').innerHTML=`
   <h2>${c.name} &middot; @${c.handle} ${statusPill(c)}</h2>
   ${c.note?`<p class="sub" style="border-left:3px solid #c9a227;padding-left:.6rem">${c.note}</p>`:''}
   <div class="cards">
     ${[['Posts',`${c.posted} / ${c.committed_videos}`],['Rate',m(c.rate)],
        ['Earned',m(c.earned)],['Committed',m(c.committed_cost)],
        ['GMV',m(c.gmv)],['GMV per video',c.gmv_per_video==null?'—':m(c.gmv_per_video)],
        ['GMV per $1 paid',c.roi==null?'—':c.roi.toFixed(2)],['Views',n0(c.views)]]
       .map(([k,v])=>`<div class="card"><h4>${k}</h4><div class="v">${v}</div></div>`).join('')}
   </div>
   ${c.videos.length?`<div class="scroll"><table><thead><tr><th>Posted</th><th></th><th>Video</th>
     <th class="n">Views</th><th class="n">GMV</th><th class="n">Units</th><th class="n">CTR</th>
     <th>Link</th></tr></thead><tbody>
     ${c.videos.map(v=>`<tr><td style="white-space:nowrap">${(v.posted||'').slice(0,10)}</td>
       <td>${v.new?'<span class="pill ok">new</span>':'<span class="pill mid">older</span>'}</td>
       <td>${(v.title||'').replace(/</g,'&lt;')||'<i>no title</i>'}</td>
       <td class="n">${n0(v.views)}</td><td class="n">${m(v.gmv)}</td>
       <td class="n">${v.units}</td><td class="n">${v.ctr??'—'}</td>
       <td><a href="${v.url}" target="_blank" rel="noopener">open</a></td></tr>`).join('')}
     </tbody></table></div>`:'<p class="sub">No videos in this window.</p>'}`;
}
$('go').onclick=load; $('sel').onchange=render;
['s','e'].forEach(i=>$(i).onchange=()=>{if(DATA)load()});
if($('adm').value.trim()) load();
</script>
"""


# ---------------------------------------------------------------- status
@app.get("/status")
async def status(admin: str = Query(...)):
    """Everything you need to confirm the connection is self-sustaining."""
    require_admin(admin)
    t = load_tokens()
    now = time.time()
    rt_exp = t.get("refresh_token_expire_in")
    return {
        "connected": bool(t.get("refresh_token")),
        "shop": t.get("shop_name"),
        "access_token_expires_in_hours": round((t.get("access_token_expire_in", 0) - now) / 3600, 1)
        if t.get("access_token_expire_in") else None,
        "refresh_token_expires_in_days": round((rt_exp - now) / 86400, 1) if rt_exp else None,
        "auto_refresh_every_hours": REFRESH_EVERY_H,
        "last_successful_refresh": _refresh_log["last_ok"],
        "last_error": _refresh_log["last_error"],
        "consecutive_failures": _refresh_log["attempts"],
        "read_only_enforced": READ_ONLY,
        "http_methods_permitted": ["GET"],
        "write_verbs_blocked": len(FORBIDDEN_TOKENS),
        "recovery_hint": "copy refresh_token_tail into TOKEN_BOOTSTRAP if the disk is ever lost",
        "refresh_token_tail": (t.get("refresh_token") or "")[-8:],
    }


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    t = load_tokens()
    connected = bool(t.get("access_token"))
    exp = t.get("access_token_expire_in")
    left = f"{int((exp - time.time()) // 60)} min" if exp else "—"
    missing = [
        n for n, v in (
            ("TTS_APP_KEY", APP_KEY), ("TTS_APP_SECRET", APP_SECRET),
            ("TTS_SERVICE_ID", SERVICE_ID), ("TTS_REDIRECT_URI", REDIRECT_URI),
            ("ADMIN_TOKEN", ADMIN_TOKEN),
        ) if not v
    ]
    rows = "".join(
        f"<tr><td>{k}</td><td><b>{v}</b></td></tr>"
        for k, v in (
            ("Status", "connected" if connected else "not connected"),
            ("Shop", t.get("shop_name") or "—"),
            ("Access token expires in", left),
            ("Config missing", ", ".join(missing) if missing else "nothing"),
        )
    )
    return f"""
    <title>NB TikTok connector</title>
    <style>
      body{{font-family:system-ui,-apple-system,sans-serif;max-width:46rem;
            margin:3rem auto;padding:0 1.5rem;color:#15202b;line-height:1.6}}
      h1{{font-size:1.5rem;margin-bottom:.25rem}}
      table{{border-collapse:collapse;width:100%;margin:1.5rem 0;font-size:.95rem}}
      td{{padding:.5rem .7rem;border-bottom:1px solid #e3e8ee}}
      td:first-child{{color:#5c6b70;width:14rem}}
      code{{background:#f2f5f8;padding:.15rem .4rem;border-radius:3px;font-size:.88rem}}
      .warn{{background:#fdf2d0;border-left:3px solid #9a6400;padding:.8rem 1rem;
             border-radius:0 3px 3px 0;font-size:.92rem}}
    </style>
    <h1>Nature&rsquo;s Blooms &middot; TikTok Shop connector</h1>
    <p style="color:#5c6b70">Pulls orders and settlements straight from Seller Center.</p>
    <table>{rows}</table>
    <p><a href="/creators">&rarr; Creator retainer tracker</a></p>
    <p>Connect or reconnect: <code>/connect?admin=YOUR_ADMIN_TOKEN</code><br>
       Then once: <code>/api/shops?admin=...</code> to capture the shop cipher.</p>
    <div class="warn">Every endpoint except this page and <code>/health</code> needs
    <code>?admin=</code>. Without it the shop data would be public.</div>
    <div class="warn" style="background:#e6f0e7;border-left-color:#2f7d3c">
      <b>Read-only.</b> This service can only issue GET requests, only to an allowlist
      of reporting endpoints, and refuses any path containing a write verb. It cannot
      change a price, edit a product, touch inventory, cancel or ship an order, or
      issue a refund &mdash; the code has no path to do so.
    </div>
    """
