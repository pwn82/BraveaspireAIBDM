# Phase 7 — Actions You Must Complete

Companion to `AI_BDM_Production_Readiness_Plan.md`. Code changes for Phase 7
(plan-based entitlements, quota enforcement, Stripe webhook idempotency,
per-org subscriptions) are done and tested.

---

## Status

| Owner | Task | Status |
|---|---|---|
| Claude | `Organization.plan` + `Subscription.organization_id` + `StripeEvent` — migration `0006` | Done |
| Claude | `entitlements.py` with `PLAN_LIMITS`, `check_quota`, `usage_snapshot` | Done |
| Claude | Quota enforced at `CRMService.add_company`, `add_contact`, `EmailService.send`, `AIGateway` | Done |
| Claude | Stripe webhook idempotent via `stripe_events.event_id` unique constraint | Done |
| Claude | `checkout.session.completed` writes `Organization.plan` (not just `User.plan`) | Done |
| Claude | `customer.subscription.deleted` downgrades org back to `free` | Done |
| Claude | 10-test suite | **10/10 pass** |
| Claude | Full regression: Phases 1 + 3 + 4 + 5 + 6 + 7 | **All 63 tests pass** |
| **You** | Create Stripe products / prices in dashboard + set env vars | Pending |
| **You** | Set `STRIPE_WEBHOOK_SECRET` in production env | Pending |
| **You** | Set `SUCCESS_URL` and `CANCEL_URL` (production hosts, not localhost) | Pending |
| **You** | Wire "Upgrade" button in Streamlit UI → `create_checkout_session` | Pending |
| **You** | (If EU customers) handle tax via Stripe Tax; else document exclusion | Pending |

---

## 1. The plan matrix

Numerical limits live in `app/services/entitlements.py:PLAN_LIMITS`. Human
copy (price, feature bullets) lives in `app/services/billing_service.py:PLANS`.
Change the numbers there, no code changes needed elsewhere.

| Feature | Free | Starter | Pro | Agency |
|---|---:|---:|---:|---:|
| companies | 20 | 500 | 5,000 | ∞ |
| contacts | 50 | 2,000 | 20,000 | ∞ |
| emails/day | 10 | 100 | 500 | ∞ |
| ai_calls/day | 50 | 500 | 5,000 | ∞ |
| ai_tokens/day | 50k | 500k | 5M | ∞ |
| users/org | 3 | 5 | 25 | ∞ |
| scraping_credits/month | 10 | 200 | 1,000 | ∞ |

`-1` in the code = unlimited. `0` = feature disabled for this plan.

---

## 2. Where quotas are enforced

| Operation | Enforcement point | Return on cap |
|---|---|---|
| Create company | `CRMService.add_company` | `None` |
| Create contact | `CRMService.add_contact` | `None` |
| Send email (safety pipeline) | `EmailService.send` → `remaining_daily_quota` | `SendResult(status="quota_exhausted")` |
| Send follow-up (scheduler) | Same path as above | `run_job` marks failed / retry per policy |
| Every AI call | `AIGateway.chat` / `.generate` / `.generate_json` | `AIResult(status="quota_exhausted")` |

**The Streamlit UI still shows write buttons even when quota is exhausted.**
That's intentional for now — the enforcement runs at the data-layer boundary
so any code path (page click, API call, agent) gets the same "None" outcome.
When you add "Upgrade" affordances you can call `check_quota()` yourself and
render "Buy more" instead of the write button.

---

## 3. Stripe setup — the parts only you can do

### Create products + prices in Stripe

For each plan (starter, pro, agency):

1. Stripe dashboard → Products → Add product
2. Name it (e.g. "BraveAspire Starter")
3. Pricing: recurring, monthly, USD (or your currency)
4. Copy the `price_XXX` id from the resulting price

### Env vars for production

| Env var | Purpose |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_live_...` (or `sk_test_...` for staging) |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` — the endpoint's signing secret |
| `STRIPE_PUBLISHABLE_KEY` | `pk_live_...` — used client-side |
| `BILLING_SUCCESS_URL` | e.g. `https://app.braveaspire.com/billing/success` |
| `BILLING_CANCEL_URL` | e.g. `https://app.braveaspire.com/billing/cancel` |

The code accepts these values in `create_checkout_session(success_url=..., cancel_url=...)` — plumb them through your Settings/Billing page.

### Configure the webhook in Stripe

1. Stripe dashboard → Developers → Webhooks → Add endpoint
2. URL: `https://api.braveaspire.com/webhooks/stripe`
3. Events to send (minimum):
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
4. Copy the signing secret → set `STRIPE_WEBHOOK_SECRET`
5. Send a "Test webhook" and confirm it lands (check `stripe_events` table)

### Do NOT skip signature verification

`handle_webhook` refuses to accept unsigned payloads when `APP_ENV=production`.
In development it accepts unsigned so you can `curl` test payloads locally.
Never set `APP_ENV=production` without `STRIPE_WEBHOOK_SECRET` — the code
refuses to boot the handler, but a bad deploy will silently drop billing events.

---

## 4. Test webhook idempotency yourself

Send the same event twice from Stripe's dashboard (or via curl for a dev
test). Confirm:

```sql
SELECT event_id, event_type, status, processed_at
FROM stripe_events
ORDER BY processed_at DESC LIMIT 5;
```

There must be exactly **one** row per event_id. Second delivery returns
`{"status":"ok","idempotent":true}` and does not re-write the org's plan.

Idempotency covers real Stripe retries (network hiccup) AND a mis-configured
webhook that hits your endpoint twice.

---

## 5. Migrate Streamlit pages to show quota state

Recommended (small, not blocking): expose `usage_snapshot()` in the Settings
page so users see their consumption.

```python
from app.services.entitlements import usage_snapshot, get_plan
from app.utils.rbac import get_current_org_id

with tab_billing:
    org_id = get_current_org_id()
    st.caption(f"Current plan: **{get_plan(org_id)}**")
    for feature, stats in usage_snapshot(org_id).items():
        limit_label = "∞" if stats["limit"] == -1 else stats["limit"]
        st.metric(feature.replace("_", " ").title(),
                  f'{stats["used"]} / {limit_label}')
```

I did not add this because the Billing page shape depends on your design
preferences — keep it minimal or add upgrade CTAs, your call.

---

## 6. Tax, invoicing, dunning

The current code doesn't handle:

- **VAT / GST / sales tax**: enable Stripe Tax on each product if you sell
  to EU / UK / Australia / etc. Nothing to code — Stripe handles it once
  turned on in the dashboard.
- **Failed-payment dunning**: `invoice.payment_failed` currently downgrades
  to free. Stripe has its own retry ladder ("smart retries" in the dashboard)
  — you'll likely want to leave the org on their paid plan for 3–7 days
  before actually downgrading. To do that, add a `grace_until` column on
  `Subscription` and skip downgrade if `now < grace_until`.
- **Proration on upgrade / downgrade mid-cycle**: Stripe does this automatically
  if you use `subscription.update` (not implemented — currently only new
  checkouts flow through). For in-app plan changes without a Stripe Portal
  redirect, add a `POST /api/billing/upgrade` endpoint that calls
  `stripe.Subscription.modify(...)`.

None of these are shipped in Phase 7. Add as needed for your commercial
launch.

---

## 7. Rotate leaked Stripe keys before enabling

Phase 0 already flagged that your committed `.env` leaked all keys. Reminder:
if you haven't already, generate new `sk_test_*` / `sk_live_*` keys in the
Stripe dashboard and revoke the old ones **before** wiring production
customers. A leaked live key = someone can create charges under your account.

---

## 8. What Phase 7 does NOT cover

- **Streamlit "Upgrade" UI** — see §5. Small, but design-dependent.
- **In-app plan changes** (as opposed to Stripe-portal-redirect). See §6.
- **Grace period on failed payments** — currently downgrades on first failure.
- **Coupons / discounts** — configure in Stripe, works automatically since
  `checkout.session.completed` reflects the discounted state.
- **Team billing / multiple orgs per user** — the schema supports it via
  `OrganizationUser`, but the UI treats each user as belonging to one org.
- **Usage-based / metered billing** — everything here is seat/tier based.
  Metered would require a `usage_records` table + periodic push to Stripe.

---

## Done when

- [ ] `python tests/test_billing_quotas.py` shows `Ran 10 tests ... OK`.
- [ ] Stripe products + prices created; env vars set in production.
- [ ] `STRIPE_WEBHOOK_SECRET` set; test webhook lands and appears in `stripe_events`.
- [ ] Verified in the DB that a same-event replay produces exactly ONE row.
- [ ] Upgrade path from Streamlit works end-to-end (checkout → webhook → plan raised).
- [ ] Cancellation via Stripe Portal downgrades org to `free` on next webhook.

When these are checked, Phase 7 is complete and Phase 8 (test coverage growth)
is next.

---

## Reference — the enforcement contract

Every enforcement call site follows the same pattern:

```python
from app.services.entitlements import check_quota

gate = check_quota(org_id, "companies", amount=1)
if not gate.allowed:
    # gate.reason is a short human-readable string like:
    # "'companies' quota exhausted on free plan (20/20 used, requested +1)"
    return None   # or a typed error the UI can act on
```

`QuotaResult` fields: `allowed`, `feature`, `plan`, `limit`, `used`,
`remaining` (`None` when unlimited), `reason`.
