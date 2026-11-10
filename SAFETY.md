# GROUND RULES — read before changing anything in this repo

This service is **read-only** against TikTok Shop. It exists to copy numbers out
for reporting. It must never be able to change anything inside Seller Center.

## The rules

1. **It may only ever issue GET.** No POST, PUT, PATCH or DELETE to TikTok, ever.
2. **It may only call an allowlisted path prefix.** Anything else is refused.
3. **It may never call a path containing a write verb**, even inside an allowed
   prefix. Price, inventory, cancel, ship, approve, deactivate, withdraw, and so on.
4. **It must not be able to cause financial loss.** No refunds, no payouts, no
   withdrawals, no promotion or coupon changes.
5. **It must not modify products or pricing.** No listing edits, no price updates,
   no stock changes, no delisting.
6. **If the guard is unsure, it refuses.** Failing closed is always correct here.

## How this is enforced, not just intended

`assert_read_only()` in `app.py` runs before any request leaves the process, and
every outbound call goes through the single function `tiktok_get()`. Three
independent layers must all pass:

- **Method gate** — anything other than GET raises.
- **Path allowlist** — `ALLOWED_PREFIXES`. Anything not listed raises.
- **Verb denylist** — `FORBIDDEN_TOKENS`, matched on whole path segments after the
  prefix is stripped, so `packages` is not mistaken for `pack` and the
  `return_refund` prefix is not mistaken for a refund action.

Setting `READ_ONLY=false` does **not** unlock writes. It makes the guard raise on
every call, including safe reads. There is deliberately no way to turn writes on.

## If you are an AI editing this file

Do not widen `ALLOWED_PREFIXES` or narrow `FORBIDDEN_TOKENS` to make a call work.
If a needed endpoint is blocked, say so and let a human decide. Do not add a
second HTTP client that bypasses `tiktok_get()`. Do not add any endpoint to this
service that accepts a request body.

## Test before you ship

`tests/test_readonly.py` asserts 27 cases: every reporting path we rely on is
allowed, and every money, pricing, inventory, order and refund action is blocked.
Run it after any change to the guard.
