# Phase 0 — Actions You Must Complete

Companion to `AI_BDM_Production_Readiness_Plan.md`. Code changes for Phase 0
have already been made in the repo. This file lists the 20% that only you can
do, because it involves your provider accounts, your production environment,
and your git history.

**Why this matters:** `.env` was committed to this repo in commit `8bd28f4`.
Assume every credential inside it is public. Nothing in the code changes buys
you safety until every leaked key is rotated on the provider side.

---

## Status

| Owner | Task | Status |
|---|---|---|
| Claude | Uncomment `.env` in `.gitignore`, add `.env.*` + `!.env.example` | Done |
| Claude | `git rm --cached .env` (untrack, keep local copy) | Done (staged, not committed) |
| Claude | Remove hardcoded default `SECRET_KEY` from `app/services/auth_service.py` | Done |
| Claude | `APP_ENV=production` refuses to boot without a real SECRET_KEY | Done |
| Claude | Document `APP_ENV` + how to generate `SECRET_KEY` in `.env.example` | Done |
| **You** | Rotate every leaked credential | Pending |
| **You** | Generate a new `SECRET_KEY` for local `.env` | Pending |
| **You** | Commit the Phase 0 code changes | Pending |
| **You** | Decide + execute on git history scrub | Pending |
| **You** | Verify the SECRET_KEY guard raises in production mode | Pending |

---

## 1. Rotate every leaked credential

Estimated time: 30–60 min.

For each provider you actually use: **revoke the old key first**, then generate
the new one, then paste into your local `.env`.

| Provider | Where | Env var(s) to replace |
|---|---|---|
| Groq | console.groq.com → API Keys | `GROQ_API_KEY` |
| OpenAI (if used) | platform.openai.com/api-keys | `OPENAI_API_KEY` |
| Anthropic (if used) | console.anthropic.com → Settings → API Keys | `ANTHROPIC_API_KEY` |
| Stripe | dashboard.stripe.com → Developers → API keys | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| Twilio | console.twilio.com → Account → API keys & tokens | `TWILIO_AUTH_TOKEN` (SID is fine to keep) |
| Gmail SMTP | myaccount.google.com/apppasswords | `SMTP_PASSWORD`, `IMAP_PASSWORD` |
| Hunter | hunter.io/api-keys | `HUNTER_API_KEY` |
| Apollo | app.apollo.io → Settings → Integrations | `APOLLO_API_KEY` |
| Proxycurl | nubela.co/proxycurl → account | `PROXYCURL_API_KEY` |
| Google Maps | console.cloud.google.com → Credentials | `GOOGLE_MAPS_API_KEY` |
| Crunchbase | data.crunchbase.com | `CRUNCHBASE_API_KEY` |
| Apify | apify.com → Settings → Integrations | `APIFY_API_TOKEN` |
| Database | your DB admin | Change the SQL Server password if `DATABASE_URL` contained one |

Skip any provider whose key you never actually generated.

---

## 2. Generate a new `SECRET_KEY`

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Paste the output into your local `.env`:

```
SECRET_KEY=<the generated string>
```

**Side effect:** every existing JWT becomes invalid — all users get logged out
on next request. That is the correct behavior; the old key is compromised.

---

## 3. Commit the Phase 0 code changes

Do this only after step 1 is complete (i.e. your local `.env` now holds
freshly rotated values). Commit file-by-file — do **not** run `git add .`,
because `git status` currently also shows unrelated modified files
(`data/bdm.db`, `.claude/settings.local.json`, the OpenAI/Anthropic AIService
additions, etc.) that should go in their own commits.

Bash:

```bash
git add .gitignore .env.example app/services/auth_service.py
git commit -m "P0 security: require SECRET_KEY, ignore .env"
git commit -m "P0 security: stop tracking .env" -- .env
git push
```

PowerShell equivalent (same commands — PowerShell runs them fine):

```powershell
git add .gitignore .env.example app/services/auth_service.py
git commit -m "P0 security: require SECRET_KEY, ignore .env"
git commit -m "P0 security: stop tracking .env" -- .env
git push
```

Verify afterward:

```bash
git ls-files | grep -E "^\.env$"
```

Should print nothing. If it still shows `.env`, the untrack didn't commit — re-run
`git rm --cached .env` and commit again.

---

## 4. Decide about git history

Answer one question first: **is this GitHub repo private or public?**

### Option A — repo is private and only you have access

**Skip the scrub.** Rotation in step 1 has already neutralized the leaked keys.
The old strings live on in history but they no longer unlock anything.

### Option B — repo is public, has collaborators, or was ever public

Scrub `.env` from every commit. This rewrites history.

```bash
pip install git-filter-repo
git filter-repo --path .env --invert-paths
git push --force origin main
```

Then:

- Tell anyone else with a clone to re-clone. Their old clones still contain the
  history and will conflict.
- Do NOT skip step 1 in exchange for this. Scrubbing history does not recover
  keys already scraped by bots — key rotation is what actually stops the leak.
  Scrubbing only prevents future clones from seeing them.

---

## 5. Verify the SECRET_KEY guard works

On Windows PowerShell:

```powershell
$env:APP_ENV="production"; $env:SECRET_KEY=""; python -c "from app.services import auth_service"
```

Expected output: a `RuntimeError` mentioning "SECRET_KEY is missing or set to
the insecure default."

If it does **not** raise, the guard is broken — flag it.

Reset the shell after:

```powershell
Remove-Item Env:APP_ENV; Remove-Item Env:SECRET_KEY
```

---

## Done when

- [ ] New keys pasted into local `.env`; old keys revoked on every provider dashboard
- [ ] New `SECRET_KEY` in local `.env`
- [ ] `.gitignore`, `auth_service.py`, `.env.example` changes committed and pushed
- [ ] `git ls-files | grep .env` on origin returns nothing
- [ ] Decision made on history scrub (private → skip, public → executed)
- [ ] Production guard test raises the expected `RuntimeError`

When all six boxes are ticked, Phase 0 is complete and we can move on to
Phase 1 (multi-tenancy) from `AI_BDM_Production_Readiness_Plan.md`.

---

## What NOT to do

- Do NOT commit real values from your rotated `.env` "just to test". Keep the
  file local; only `.env.example` (fake values) belongs in the repo.
- Do NOT run `git add .` — you have unrelated pending changes that need their
  own commits.
- Do NOT skip step 1 in favor of step 4. History scrub without rotation is
  security theater; rotation without scrub is genuine safety.
- Do NOT set `APP_ENV=production` on your dev machine after testing. Leave it
  `development` or unset locally, so the dev fallback keeps working.
