# Nature's Blooms — TikTok Shop connector

Minimal FastAPI service on Render that authorises against TikTok Shop and pulls
orders and settlements. Secrets live in environment variables only.

## Order of operations

The redirect URL and the deployed app depend on each other, so do it in this order.

### 1. Deploy the skeleton first (you need the URL before TikTok will accept it)
```
cd ~/Desktop/nb-tiktok-api
git init && git add -A && git commit -m "NB TikTok connector"
gh repo create naturesblooms-tiktok-api --private --source=. --push
```
On Render: **New → Web Service → connect the repo**. It reads `render.yaml`.
Note the URL it gives you, e.g. `https://nb-tiktok-api.onrender.com`.

The `starter` plan is specified because the **free plan has no persistent disk** and
the refresh token would be wiped on every restart. If you would rather stay free,
delete the `disk:` block and set `TOKEN_STORE_PATH=/tmp/tokens.json`, then expect to
re-run `/connect` after each redeploy.

### 2. Create the app in TikTok Shop Partner Center
Partner Center → **App & Service** → create app.

- **App name** anything, e.g. `Natures Blooms internal`
- **Target sellers** → Add market → **United States**, local sellers
- **Enable API** → on
- **Redirect URL** → `https://YOUR-RENDER-URL.onrender.com/callback`

Save, then **Publish**. Copy the **App key**, **App secret** and **Service ID**
from the Credentials panel.

### 3. Put the secrets into Render
Render → your service → **Environment**. Add:

| Key | Value |
|---|---|
| `TTS_APP_KEY` | from Partner Center |
| `TTS_APP_SECRET` | from Partner Center |
| `TTS_SERVICE_ID` | from Partner Center |
| `TTS_REDIRECT_URI` | `https://YOUR-RENDER-URL.onrender.com/callback` |
| `ADMIN_TOKEN` | a long random string you invent |
| `TOKEN_STORE_PATH` | `/var/data/tokens.json` |

Never commit these. `.env` is gitignored.

### 4. Authorise
1. Open `https://YOUR-RENDER-URL.onrender.com/` — it should say *not connected*
   with nothing missing from config.
2. Go to `/connect?admin=YOUR_ADMIN_TOKEN`, log into Seller Center, approve.
3. You land back on `/callback` with "Connected".
4. Hit `/api/shops?admin=...` once. It stores the **shop cipher**, which every
   later call needs.

### 5. Pull data
```
/api/orders?admin=...&start=1762000000&end=1762600000
/api/settlements?admin=...&start=1762000000&end=1762600000
```
Times are unix seconds. Settlements is the feed the P&L is built on.

## Things that will bite

- **The redirect URL must match exactly** — scheme, host, path, no trailing slash.
  A mismatch gives an opaque TikTok error.
- **Access tokens are short-lived.** The code refreshes automatically when a call
  finds under two minutes left. `/refresh?admin=...` forces it.
- **Refresh tokens expire too** (TikTok has used a ~1 year window). If
  `/api/*` starts returning 409, re-run `/connect`.
- **Verify the endpoint paths** against partner.tiktokshop.com/docv2 before relying
  on them. The host names and version prefixes have changed between API versions
  and the ones here may have moved.
- **Render free tier sleeps.** First request after idle takes ~30 seconds.

## Local run
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # fill it in
set -a && . ./.env && set +a
uvicorn app:app --reload --port 8000
```
