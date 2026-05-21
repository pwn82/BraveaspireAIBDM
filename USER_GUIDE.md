# BraveAspire AI BDM — End User Guide

A complete walkthrough of every screen, the mandatory fields you must fill in,
and the typical end-to-end workflow.

---

## Table of Contents

1. [First-time setup](#1-first-time-setup)
2. [Logging in](#2-logging-in)
3. [Settings — configure before you do anything else](#3-settings--configure-before-you-do-anything-else)
4. [Lead Scraper — find new companies](#4-lead-scraper--find-new-companies)
5. [Companies — manage your prospect list](#5-companies--manage-your-prospect-list)
6. [Contacts — manage decision-makers](#6-contacts--manage-decision-makers)
7. [Outreach — send emails & track replies](#7-outreach--send-emails--track-replies)
8. [Follow-ups — automated reminders](#8-followups--automated-reminders)
9. [AI Chat — your assistant](#9-ai-chat--your-assistant)
10. [Workflow — autonomous BDM pipeline](#10-workflow--autonomous-bdm-pipeline)
11. [Analytics — measure performance](#11-analytics--measure-performance)
12. [Users (admin only)](#12-users-admin-only)
13. [End-to-end example](#13-end-to-end-example)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. First-time setup

If this is the very first run on a fresh database, the system seeds a default
super-admin account so you can log in:

| Field | Default value |
|-------|---------------|
| Email | `admin@braveaspire.com` |
| Password | `Admin@123!` |

Change this password immediately under **Settings → Security**.

---

## 2. Logging in

Page: **`0_Login`**

You have two ways to sign in. Pick the one that matches how your account was
created.

### A. Email + password (most common)

| Field | Required? | Notes |
|-------|-----------|-------|
| Email | ✅ Yes | e.g. `you@company.com` |
| Password | ✅ Yes | Minimum 6 characters |

If admin enabled "Force password change" for your account, you'll be asked to
pick a new password on first login.

### B. Mobile + OTP (passwordless)

| Field | Required? | Notes |
|-------|-----------|-------|
| Mobile number | ✅ Yes | E.164 format, e.g. `+919876543210` |
| 6-digit OTP | ✅ Yes | Arrives via SMS (Twilio) or shown in logs if Twilio not configured |

After login, if you set up 2FA, you'll be asked for a 6-digit code from your
authenticator app (Google Authenticator / Authy).

> **There is no public sign-up.** Only admins can create accounts.

---

## 3. Settings — configure before you do anything else

Page: **`7_Settings`** → has 9 tabs

You must configure at least the AI and SMTP tabs before sending any outreach.

### Tab 🤖 AI

| Field | Required? | Notes |
|-------|-----------|-------|
| Provider | ✅ Yes | `Ollama` (local, free) or `Groq` (cloud, faster) |
| **Ollama:** URL | If using Ollama | Default `http://localhost:11434` |
| **Ollama:** Model | If using Ollama | e.g. `llama3` |
| **Groq:** API key | If using Groq | Get from [console.groq.com](https://console.groq.com) |
| **Groq:** Model | If using Groq | Default `llama-3.3-70b-versatile` |

Click **Test AI Connection** to verify, then **Save to .env**.

### Tab 📧 Email / SMTP

You **cannot send emails** without this.

| Field | Required? | Notes |
|-------|-----------|-------|
| SMTP Host | ✅ Yes | e.g. `smtp.gmail.com` |
| SMTP Port | ✅ Yes | Usually `587` |
| SMTP Email | ✅ Yes | Your sending address |
| App Password | ✅ Yes | **Gmail:** generate from Google → Security → App Passwords (NOT your normal password) |
| From Email | Auto-filled | Defaults to SMTP Email |
| From Name | Optional | Display name shown to recipients |

Click **Test SMTP** — you'll get a test email if it works.

**Optional IMAP** (for auto-detecting replies):

| Field | Required? | Notes |
|-------|-----------|-------|
| IMAP Host | If using replies | e.g. `imap.gmail.com` |
| IMAP Port | If using replies | Usually `993` |
| IMAP Email | If using replies | Same as SMTP email |
| IMAP Password | If using replies | Same app password as SMTP |

### Tab 📡 Tracking

| Field | Required? | Notes |
|-------|-----------|-------|
| Tracking Base URL | Optional | Default `http://localhost:8000`. Only needed if running the FastAPI backend for open/click tracking |

### Tab 💳 Billing Keys (admin only)

Stripe integration — leave blank if you're not selling subscriptions.

### Tab 🔑 API Keys *(this is where you set up lead scraping)*

| Field | Required? | Notes |
|-------|-----------|-------|
| Apollo.io API Key | Optional | Best for **contact data + emails**. [app.apollo.io](https://app.apollo.io) → Settings → Integrations |
| Google Maps API Key | Optional | Local business search. [console.cloud.google.com](https://console.cloud.google.com) → Places API |
| Crunchbase API Key | Optional | Funding + firmographics. [data.crunchbase.com](https://data.crunchbase.com) |
| Proxycurl API Key | Optional | LinkedIn enrichment. [nubela.co/proxycurl](https://nubela.co/proxycurl) |
| **Apify API Token** | **Recommended** | **Easiest** — covers Google Maps + LinkedIn. [apify.com](https://apify.com) → Settings → Integrations → API tokens |
| Hunter.io API Key | Optional | Find emails from company domains |
| Twilio SID / Token / From Number | Required for SMS OTP login | [console.twilio.com](https://console.twilio.com) |

**You can use the app without any of these** — but the Lead Scraper will only
return demo data. **Add at minimum the Apify token** for real data.

Click **Save All API Keys** when done.

### Tab 👤 Profile

| Field | Required? | Notes |
|-------|-----------|-------|
| Your Name | Recommended | Used in email signatures |
| Your Company | Recommended | Used in personalization |
| Services Offered | Recommended | AI uses this to craft outreach |

### Tab 🔒 Security

- **Change Password** — current + new (≥ 6 chars). Use this immediately after first login with the default `Admin@123!`.

### Tab 🗄️ Database

- **Load Demo Data** button — populates 8 sample companies with contacts and outreach (good for trying the UI before real data exists).
- **⚠️ Clear All Data** — destroys everything. Use with extreme care.

### Tab 📋 Audit Log

Read-only log of admin actions. Available to admins only.

---

## 4. Lead Scraper — find new companies

Page: **`9_Lead_Scraper`**

This is **Module 1** of the BDM pipeline — it finds companies that might need
your services.

### Mandatory inputs

You must enter **at least one** of these three fields:

| Field | Notes |
|-------|-------|
| What type of companies are you looking for? | Free-form: e.g. `SaaS startups hiring Python engineers` |
| Industry | e.g. `Fintech`, `Healthcare` |
| Location | e.g. `Hyderabad`, `Bangalore`, `San Francisco` |

You must also select **at least one data source** (Apify is recommended).

### Optional refinements

| Field | Notes |
|-------|-------|
| Max results | 5–50, default 15 |
| Employee size | e.g. `50-200` |
| Technology | e.g. `React`, `Python` |
| 🟢 Actively hiring only | Filter to companies posting jobs |
| 💰 Has funding | Only companies with funding stage data |
| 🔴 Outdated tech | Only companies whose stack is flagged as legacy |

### How to use

1. Fill in the search criteria
2. The blue info banner confirms: *"Will search 1 source(s) (apify) for: IT companies Hyderabad"*
3. Check the sources you want (✅ = key configured, ⚙️ = needs key in Settings)
4. Click **🚀 Start Scraping**
5. Wait 20–60 seconds — the spinner shows progress
6. Review the results table with scores (🟢 ≥ 80, 🟡 60–79, 🔴 < 60)
7. Expand any company row to see full details
8. Use the checkboxes to select which to import (results with score ≥ 50 are pre-checked)
9. Click **💾 Import N Selected to CRM** to add them to your Companies list
10. Or click **📥 Export All to CSV** for offline analysis

> **Note on Apify free plan:** ~1 successful Google Maps run per 30 minutes.
> If you see "Apify rate limit hit", wait a few minutes or upgrade your plan.

---

## 5. Companies — manage your prospect list

Page: **`1_Companies`**

This is your CRM database of target companies.

### Adding a company manually

Click **➕ Add Company** and fill in:

| Field | Required? | Notes |
|-------|-----------|-------|
| Company Name | ✅ Yes | e.g. `Acme Corp` |
| Website | Optional | e.g. `acme.com` |
| Industry | Optional | e.g. `Fintech` |
| Location | Optional | e.g. `Mumbai, India` |
| Employee Size | Optional | Number |
| Revenue | Optional | e.g. `$1M-$5M` |
| Status | Optional | `New` / `Contacted` / `Interested` / `Proposal` / `Won` / `Lost` |
| Hiring? | Optional | Checkbox |
| Tech Stack | Optional | Comma-separated |
| Pain Points | Optional | Free text |
| Notes | Optional | Free text |
| Source | Optional | Auto-set to `Manual` |

The system **AI-scores** each company automatically (0–100).

### Other actions on this page

- 🔍 Search by name / industry / pain points
- 🤖 Click "AI Discovery" to have the AI generate prospect leads from a description
- ✏️ Edit any company → updates score
- 🗑️ Delete a company (removes all related contacts + outreach)
- 📥 Export to CSV

---

## 6. Contacts — manage decision-makers

Page: **`2_Contacts`**

Each contact belongs to a company.

### Adding a contact

| Field | Required? | Notes |
|-------|-----------|-------|
| Company | ✅ Yes | Pick from your Companies list |
| Name | ✅ Yes | e.g. `Jane Doe` |
| Designation | Optional | e.g. `CTO`, `VP Engineering` |
| Email | Optional but recommended | Needed to send outreach |
| LinkedIn | Optional | Full URL |
| Phone | Optional | E.164 format |
| Verified | Optional | Checkbox if you've confirmed the email |
| Notes | Optional | Free text |

### Other actions

- 🤖 **Find Contacts by AI** — auto-discovers likely decision-makers for a company using AI + Hunter.io
- ✉️ **Verify Email** — pings the address to check it's valid
- 📥 Export

---

## 7. Outreach — send emails & track replies

Page: **`3_Outreach`** — has tabs for Email, LinkedIn, WhatsApp, Proposal

### Email tab

| Field | Required? | Notes |
|-------|-----------|-------|
| Contact | ✅ Yes | Pick from your Contacts list |
| Subject | ✅ Yes | Or click 🤖 **AI Personalize** to auto-generate |
| Body | ✅ Yes | Or use AI personalize to generate |
| Channel | Auto | `Email` |
| Schedule for later | Optional | Send immediately or pick date/time |

Click **🤖 AI Personalize** to have the AI write a custom message based on:
- The contact's name + designation
- The company's industry, pain points, tech stack
- Your Sender Profile (from Settings)

Click **📤 Send Now** — the email is sent via your SMTP, a tracking pixel is
embedded, and the row appears in your Outreach list with status `Sent`.

### Statuses you'll see

- 📝 Draft — saved but not sent
- 📤 Sent — email delivered
- 👁️ Opened — recipient opened it (tracking pixel)
- 💬 Replied — recipient replied (detected by IMAP)
- ⚠️ Bounced — invalid address
- 🕐 Scheduled — queued for later

### LinkedIn / WhatsApp tabs

Same workflow but the message is generated for that channel. (Actual sending
requires browser automation — see the in-page help for Playwright setup.)

### Proposal tab

| Field | Required? | Notes |
|-------|-----------|-------|
| Company | ✅ Yes | The prospect |
| Project description | ✅ Yes | What you'll build for them |
| Budget range | Optional | e.g. `$10K-$25K` |
| Timeline | Optional | e.g. `8 weeks` |

Click **🤖 Generate Proposal** — AI writes a formatted proposal you can copy
into a PDF.

---

## 8. Follow-ups — automated reminders

Page: **`4_Followups`**

After you send an email with status `Sent`/`Opened`/`Replied`, the system
auto-creates 3 follow-up reminders at **+3 days**, **+7 days**, **+14 days**.

| Action | Notes |
|--------|-------|
| ✏️ Edit follow-up | Change subject/body before it sends |
| 📤 Send Now | Override the schedule |
| ✅ Mark Done | Cancel a follow-up |
| 🤖 AI Suggest Reply | Generate a follow-up message |

No mandatory fields — everything is pre-filled from the original outreach.

---

## 9. AI Chat — your assistant

Page: **`6_AI_Chat`**

Ask the AI anything about your CRM:

- *"Show me companies with score above 80"*
- *"Which contacts haven't been emailed yet?"*
- *"Summarize my pipeline this week"*
- *"Draft a cold email for Acme Corp's CTO"*

| Field | Required? | Notes |
|-------|-----------|-------|
| Message | ✅ Yes | Just type and hit Enter |

The AI uses ChromaDB vector search to ground its answers in your real data.

---

## 10. Workflow — autonomous BDM pipeline

Page: **`8_Workflow`**

Runs a 5-agent LangGraph pipeline end-to-end:

1. 🔍 **Scrape** — finds companies matching your criteria
2. 👥 **Find Contacts** — identifies decision-makers per company
3. ✉️ **Personalize** — drafts outreach emails
4. 📤 **Send** — sends after human approval
5. 📊 **Track** — schedules follow-ups

### Mandatory inputs

| Field | Required? | Notes |
|-------|-----------|-------|
| Target description | ✅ Yes | e.g. `Fintech startups in India hiring backend engineers` |
| Max companies | ✅ Yes | 1–20 |
| Auto-send (HITL) | Optional | If unchecked, you approve each email before send |

Click **▶️ Run Workflow** and watch the live progress. You'll be prompted to
approve each email before it goes out (unless you enabled auto-send).

---

## 11. Analytics — measure performance

Page: **`5_Analytics`**

Read-only dashboards. No fields to fill in.

- Pipeline funnel (New → Contacted → Won)
- Open / click / reply rates by week
- Top performing campaigns
- Lead source breakdown

---

## 12. Users (admin only)

Page: **`10_Users`** — visible only if your role is `admin` or `super_admin`

### Create a new user

| Field | Required? | Notes |
|-------|-----------|-------|
| Email | ✅ Yes | Must be unique |
| Mobile | Optional | E.164 format, needed for SMS OTP login |
| Full name | ✅ Yes | |
| Role | ✅ Yes | `super_admin` / `admin` / `sales_manager` / `bdm` / `sales_executive` / `viewer` |
| Department | Optional | e.g. `Sales`, `Marketing` |

The system generates a temporary password, emails it to the user, and forces
them to change it on first login.

### Other actions

- 🔐 **Setup TOTP** — scan a QR code with Google Authenticator
- 🔒 **Lock / Unlock** account
- 🗑️ Delete user
- 📋 View audit log per user

---

## 13. End-to-end example

The fastest way to go from "nothing" to "sent your first AI-personalized cold
email":

1. **Settings → 📧 Email/SMTP** — add Gmail + App Password, click Test SMTP
2. **Settings → 🤖 AI** — pick Groq (or Ollama), paste API key, Test Connection
3. **Settings → 🔑 API Keys** — paste your Apify token, Save All
4. **Lead Scraper** — type "IT companies", Location "Hyderabad", check ✅ Apify, click Start Scraping
5. After ~20s, select the top 5 companies → **Import to CRM**
6. **Companies** → click any imported company → **🤖 Find Contacts by AI**
7. Pick a contact → click **✉️ Create Outreach**
8. **Outreach** → click **🤖 AI Personalize** → review the AI-generated email
9. Click **📤 Send Now**
10. Wait — open/reply tracking happens automatically; **Follow-ups** auto-creates the +3/+7/+14 day reminders

You've now done a complete BDM cycle in under 5 minutes.

---

## 14. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Start Scraping" button does nothing | All three input fields (query, industry, location) are empty | Fill in at least one |
| Lead Scraper returns "Demo" data only | No API keys configured | Settings → 🔑 API Keys → add Apify token |
| "Apify rate limit hit / TIMED-OUT" | Free plan = ~1 Google Maps run per 30 min | Wait, or upgrade Apify plan |
| "SMTP credentials not configured" | Empty Gmail App Password | Settings → 📧 Email |
| Cannot login — "Account locked" | 5 failed password attempts | Wait 15 min, or ask admin to unlock |
| "QR code not showing" for 2FA | `qrcode[pil]` not installed | `pip install "qrcode[pil]" Pillow pyotp` |
| SQL Server "String or binary data would be truncated" | Address longer than column | Already fixed in v2.x — restart the app |
| OTP not arriving via SMS | Twilio not configured | Settings → 🔑 API Keys → fill Twilio SID/Token/From, or check logs (dev mode prints the OTP) |
| AI Chat says "service unavailable" | Ollama not running, or wrong Groq key | Settings → 🤖 AI → Test Connection |

---

### Quick reference card — fields you MUST fill in

| Page | Mandatory fields |
|------|------------------|
| Login (password) | Email, Password |
| Login (OTP) | Mobile, OTP |
| Settings — AI | Provider; either Ollama URL+model OR Groq key+model |
| Settings — SMTP | Host, Port, User, App Password |
| Lead Scraper | At least one of: Query / Industry / Location; at least one source checked |
| Add Company | Company Name |
| Add Contact | Company, Name |
| Outreach | Contact, Subject, Body |
| Workflow | Target description, Max companies |
| Create User (admin) | Email, Full name, Role |

Everything else is optional and will be filled with sensible defaults or
auto-generated by the AI.
