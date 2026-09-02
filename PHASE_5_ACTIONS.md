# Phase 5 — Actions You Must Complete

Companion to `AI_BDM_Production_Readiness_Plan.md`. Code changes for Phase 5
(suppression, unsubscribe, bounces, reply threading, email verification) are
done and tested. This file lists the ops work only you can do — DNS records,
bounce webhook wiring, and the domain-warm-up habits that keep your sending
domain out of Gmail's spam bucket.

---

## Status

| Owner | Task | Status |
|---|---|---|
| Claude | `SuppressionList` + `BounceEvent` models + migration `0004` | Done |
| Claude | `EmailService.send()` with full pre-send pipeline | Done |
| Claude | Signed unsubscribe token + `/track/unsubscribe/{token}` endpoint | Done |
| Claude | Auto-injected unsubscribe footer + `List-Unsubscribe` header | Done |
| Claude | Email verification gate (syntax + role-address + blocked-domain) | Done |
| Claude | Message-ID + In-Reply-To on Outreach; IMAP threads by real IDs | Done |
| Claude | Bounce webhook (`POST /webhooks/bounce`) with hard→auto-suppress | Done |
| Claude | Optional tenant daily send quota via `MAX_EMAILS_PER_ORG_PER_DAY` | Done |
| Claude | Scheduler follow-ups routed through the safety pipeline | Done |
| Claude | 8-test email safety suite | **8/8 pass** |
| Claude | Full regression: Phase 1 + 3 + 4 + 5 | **All 43 tests pass** |
| **You** | Publish SPF / DKIM / DMARC records for your sending domain | Pending |
| **You** | Wire your ESP's bounce webhook to `/webhooks/bounce` + secure it | Pending |
| **You** | Verify `List-Unsubscribe` works in your live Gmail/Outlook client | Pending |
| **You** | Warm up any new sending IP / domain gradually | Pending |
| **You** | (Optional) Plug a real verification API (ZeroBounce / Kickbox) | Recommended before high-volume send |

---

## 1. Publish SPF, DKIM, DMARC records

This is DNS-level work, not code. Without these records your outbound mail
lands in spam and Gmail may drop it entirely.

### SPF — TXT record on your sending domain root

Authorizes servers to send FROM your domain. Example for Google Workspace
+ Mailgun:

```
Type:    TXT
Name:    @
Value:   v=spf1 include:_spf.google.com include:mailgun.org -all
TTL:     3600
```

`-all` = hard-fail unauthorized senders. If you're not sure yet, use `~all`
(soft-fail) during warm-up.

### DKIM — TXT record with a public key

Your ESP provides the record. Typical location:

```
Type:    TXT
Name:    <selector>._domainkey.yourdomain.com
Value:   v=DKIM1; k=rsa; p=<long public key from your ESP dashboard>
TTL:     3600
```

Enable DKIM signing in your ESP (Google Workspace, Mailgun, SendGrid, SES —
each has a different setup wizard) and paste the record they give you.

### DMARC — TXT record

Tells receivers what to do when SPF or DKIM fails.

```
Type:    TXT
Name:    _dmarc.yourdomain.com
Value:   v=DMARC1; p=none; rua=mailto:dmarc-reports@yourdomain.com
TTL:     3600
```

Start with `p=none` (monitor only). After 2–4 weeks with clean reports,
progress to `p=quarantine`, then `p=reject`.

### Verify

Use `dig` or MX Toolbox:

```bash
dig TXT yourdomain.com | grep spf
dig TXT _dmarc.yourdomain.com
dig TXT <selector>._domainkey.yourdomain.com
```

---

## 2. Wire your ESP's bounce feed to `/webhooks/bounce`

The endpoint accepts a simple JSON body:

```json
{
  "email": "bounced@example.com",
  "bounce_type": "hard",
  "provider": "ses",
  "provider_message_id": "...",
  "outreach_id": 42,
  "organization_id": 1,
  "diagnostic": "550 5.1.1 mailbox does not exist"
}
```

`bounce_type` must be one of: `hard | soft | complaint | delivered`.
`hard` and `complaint` auto-suppress the recipient in that org.

### Per-provider adapter

Every ESP posts its own JSON shape. You have two options:

**Option A** — add a small translator in front of `/webhooks/bounce`. Write
one endpoint per provider that maps their payload to the schema above, then
posts to `/webhooks/bounce` internally. Cleanest.

**Option B** — extend `backend/main.py:bounce_webhook` to accept the raw
payload plus a `?provider=ses` query param and translate inline. Fewer
files, more branching in one file.

### SECURE the endpoint

`/webhooks/bounce` is currently open (no auth). This is deliberate — every
ESP does auth differently and I don't know which one you'll use. Before
enabling in production, add one of:

- **SES:** verify the SNS signature on incoming notifications.
- **Mailgun:** verify the HMAC-SHA256 signature in `X-Mailgun-Signature`.
- **SendGrid:** verify `X-Twilio-Email-Event-Webhook-Signature`.
- **Postmark:** IP allowlist (Postmark publishes theirs).
- **All others:** shared secret in the URL path (`/webhooks/bounce/<random-secret>`),
  compared with `hmac.compare_digest`.

Never deploy this endpoint publicly without one of the above.

---

## 3. Test `List-Unsubscribe` in your real mail client

Every send now includes:

```
List-Unsubscribe: <https://your-host/track/unsubscribe/TOKEN>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

Gmail and Outlook Web render this as a native "Unsubscribe" link next to
the sender name. Send yourself a test outreach, then look for that native
control (not just the footer link).

If it's missing, check:

- Your ESP isn't stripping the header (Mailgun / SendGrid preserve it by default).
- `TRACKING_BASE_URL` in your env points at your real public host (not `localhost`).
- The token generates against your production `SECRET_KEY` (which must be set — Phase 0).

---

## 4. Warm up new sending IPs / domains

Skip this only if you're sending from an already-warm domain. New IPs get
throttled to a trickle at first.

**Basic warmup schedule (per day):**

| Week | Volume/day | Notes |
|---:|---:|---|
| 1 | 50 | Mostly to your team + engaged contacts |
| 2 | 200 | Add high-intent inbound leads |
| 3 | 500 | Broaden to warm list |
| 4 | 1000+ | Full outreach volume |

Keep bounce rate < 5% and complaint rate < 0.1% throughout. If either climbs,
pause immediately and diagnose.

---

## 5. Optional but recommended — real verification

The built-in `deliverable()` catches syntax garbage and role addresses.
It does NOT check that the mailbox exists. For real-world sending, plug in
one of:

- **ZeroBounce** (~$0.006/email)
- **Kickbox** (~$0.008/email)
- **NeverBounce** (~$0.004/email)

Wire it into `EmailService.deliverable()` — cache the result on
`Contact.verified` so you don't pay to verify the same address twice.
Anything returning `valid` proceeds; `risky` becomes an admin decision;
`invalid` gets auto-suppressed.

Do this before scaling past ~1000/day — hitting even a small % of dead
addresses will tank your sender reputation.

---

## 6. Optional configuration

| Env var | Purpose | Default |
|---|---|---|
| `MAX_EMAILS_PER_ORG_PER_DAY` | Hard tenant cap on `email_send` workflow_runs per day | `0` (off) |
| `TRACKING_BASE_URL` | Public URL where FastAPI lives; used to build unsubscribe links | `http://localhost:8000` |

---

## 7. What Phase 5 does NOT cover

- **Per-provider bounce parsers** — see §2. I built the generic ingestion,
  you (or a follow-up phase) wire the translators.
- **Complaint feedback loop registration** with Gmail Postmaster Tools /
  Microsoft SNDS. Those are one-time signups on each mail provider's site.
- **Rate limiting per recipient / per domain** ("send at most one email
  per week per contact"). Add if your sales motion demands it.
- **AI reply classification** — the plan lists it in Phase 5 but it belongs
  with Phase 6 (AI reliability + structured outputs). Deferred.
- **Domain reputation dashboards** — plug Postmaster Tools and your ESP's
  reputation dashboard into the observability layer in Phase 10.

---

## Done when

- [ ] SPF, DKIM, DMARC published; `dig` confirms all three.
- [ ] Your ESP's bounce feed reaches `/webhooks/bounce` behind auth.
- [ ] A test send to yourself shows the native Unsubscribe link in Gmail.
- [ ] A hard bounce from your ESP results in a row in `suppression_list`.
- [ ] `python tests/test_email_safety.py` shows `Ran 8 tests ... OK`.

When these are checked, Phase 5 is complete and P6 (AI reliability + AI
gateway) is next.

---

## Reference — the pre-send pipeline in order

```
send(to_email, subject, body, smtp_cfg, outreach_id=…)
   ├─ normalize recipient
   ├─ syntax check           → status="undeliverable" if invalid
   ├─ role-address / blocked-domain
   ├─ suppression_list       → status="suppressed" if hit
   ├─ Outreach.unsubscribed_at → status="unsubscribed"
   ├─ Outreach already sent  → status="already_sent" (no-op success)
   ├─ tenant daily quota     → status="quota_exhausted"
   ├─ SMTP credentials       → status="smtp_not_configured"
   ├─ generate Message-ID
   ├─ inject unsubscribe footer + List-Unsubscribe headers
   ├─ SMTP send              → status="smtp_error" on transport failure
   ├─ persist Message-ID + sent_at on Outreach
   └─ return SendResult(ok=True, status="sent", message_id=…)
```

Each step returns a typed `SendResult` — no exceptions for domain outcomes,
only for genuinely unexpected failures (DB down, SMTP down).
