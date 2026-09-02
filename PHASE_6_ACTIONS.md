# Phase 6 — Actions You Must Complete

Companion to `AI_BDM_Production_Readiness_Plan.md`. Code changes for Phase 6
(centralized AI gateway, cost/token tracking, structured outputs, prompt
injection boundaries, per-org quotas) are done and tested.

---

## Status

| Owner | Task | Status |
|---|---|---|
| Claude | `AILog` extended with status / tokens / cost / injection flag; migration `0005` | Done |
| Claude | `AIResult` typed return (no more error-as-string) | Done |
| Claude | `AIGateway` — timeout, retry, cost tracking, quota, audit | Done |
| Claude | `generate_json(schema=…)` with pydantic validation + auto-repair | Done |
| Claude | `wrap_untrusted(text)` prompt-injection fence + safety reminder | Done |
| Claude | Static provider price table + env override (`AI_PRICE_<provider>_<model>=in,out`) | Done |
| Claude | 10-test suite | **10/10 pass** |
| Claude | Full regression: Phase 1 + 3 + 4 + 5 + 6 | **All 53 tests pass** |
| **You** | Migrate agents from raw `AIService` → `AIGateway` (see §3) | Pending |
| **You** | Verify pricing table against your current provider bills (see §4) | Pending |
| **You** | Set `MAX_AI_CALLS_PER_ORG_PER_DAY` / `MAX_AI_TOKENS_PER_ORG_PER_DAY` if desired | Optional |
| **You** | Decide PII redaction policy (see §5) | Pending |

---

## 1. The new `AIResult` contract

Every method on `AIGateway` returns this instead of a bare string:

```python
@dataclass
class AIResult:
    ok: bool                 # convenience — false when status != "ok"
    status: str              # ok | error | timeout | schema_invalid | quota_exhausted
    content: str             # the model's text response (empty on failure)
    parsed: Any = None       # populated by generate_json()
    error: Optional[str]     # human-readable failure reason
    provider, model          # what actually ran
    input_tokens, output_tokens
    cost_micro_usd           # 1_000_000 = $1.00 — never float math on money
    duration_ms
    log_id                   # AILog row id for auditing
    retries                  # how many transient retries were needed
```

**Never** check `if result.startswith("[AI Error"):` any more. Check
`if result.ok:` or route on `result.status`.

---

## 2. Provider pricing

Baked-in defaults (per 1M tokens, USD):

| Provider | Model | In | Out |
|---|---|---:|---:|
| ollama | * | 0.00 | 0.00 |
| groq | llama-3.3-70b-versatile | 0.59 | 0.79 |
| groq | llama-3.1-8b-instant | 0.05 | 0.08 |
| groq | mixtral-8x7b-32768 | 0.24 | 0.24 |
| openai | gpt-4o-mini | 0.15 | 0.60 |
| openai | gpt-4o | 2.50 | 10.00 |
| openai | gpt-4-turbo | 10.00 | 30.00 |
| openai | gpt-3.5-turbo | 0.50 | 1.50 |
| anthropic | claude-haiku-4-5 | 0.80 | 4.00 |
| anthropic | claude-sonnet-5 | 3.00 | 15.00 |
| anthropic | claude-opus-5 | 15.00 | 75.00 |
| *unknown* | *any* | 1.00 | 3.00 |

**Provider prices change.** Verify against your first invoice and override
per model:

```bash
export AI_PRICE_openai_gpt-4o-mini=0.15,0.60
export AI_PRICE_groq_llama-3.3-70b-versatile=0.59,0.79
```

Unknown-model default is deliberately high so an unlogged model doesn't slip
past the quota.

---

## 3. Migrate agents to the gateway

Currently agents call `ai.generate(...)` / `ai.chat(...)` directly. That
path keeps working but returns the legacy error-as-string and does not
track cost / enforce quotas. To pick up all the Phase 6 safety, change:

```python
# BEFORE
result = self.ai.generate(prompt, system=sys)
if result.startswith("[AI Error"):
    return None

# AFTER
from app.services.ai_gateway import AIGateway
gw = AIGateway(organization_id=org_id, ai=self.ai, agent_name="followup_agent")
result = gw.generate(prompt, system=sys)
if not result.ok:
    log.warning("AI call failed: %s", result.error)
    return None
content = result.content
```

For every agent that ingests scraped web / email content, also wrap the
untrusted parts:

```python
from app.services.ai_gateway import AIGateway, wrap_untrusted

gw = AIGateway.from_streamlit(st, agent_name="company_analyzer")
scraped = fetch_company_website(url)              # untrusted
result = gw.generate(
    prompt=f"Analyze this company page:\n{wrap_untrusted(scraped, source_label='website')}",
    system="You are a B2B analyst. Return factual info only.",
    untrusted_input=True,
)
```

Recommended migration order (biggest safety win first):
1. `company_analyzer_agent` — ingests scraped web content
2. `personalization_agent` — ingests contact profiles
3. `inbox_agent` — ingests inbound email bodies (untrusted!)
4. `scraper_agent`, `company_scraping_agent`, `lead_discovery_agent`
5. `followup_agent`, `proposal_agent`

I did not do these migrations in Phase 6 because each agent needs individual
attention — the prompts may need adjustment when wrapped content is fenced.
Small work but not blind sweep.

---

## 4. Cost / quota configuration

Optional env vars:

| Env var | Purpose | Default |
|---|---|---|
| `MAX_AI_CALLS_PER_ORG_PER_DAY` | Refuse further AI calls after this many succeeded today | `0` (off) |
| `MAX_AI_TOKENS_PER_ORG_PER_DAY` | Refuse after this many total tokens today | `0` (off) |
| `AI_PRICE_<provider>_<model>` | Override the built-in pricing table | (see §2) |

Both quotas are enforced per organization. When exceeded, `AIGateway.generate()`
returns `AIResult(ok=False, status="quota_exhausted")` and skips the provider
call entirely — cheap deny, no wasted spend.

To surface cost in the UI, query `AILog` grouped by org / user / model /
day. Recommended addition to the Settings page:

```python
from sqlalchemy import func
from app.database.models import AILog
from app.database.db import get_db

with get_db() as db:
    rows = (
        db.query(AILog.model, func.sum(AILog.cost_micro_usd).label("micro"))
        .filter(AILog.organization_id == org_id)
        .filter(AILog.status == "ok")
        .group_by(AILog.model)
        .all()
    )
for model, micro in rows:
    st.metric(model, f"${(micro or 0) / 1_000_000:.2f}")
```

Small work — not blocking anything, so I did not add the panel this phase.

---

## 5. PII / redaction — decision required

The plan asks "PII handling reviewed." Concretely, the AI Gateway currently
sends contact emails, phone numbers, and any pain-points text to the model
verbatim. In some regulated markets (EU, healthcare, financial) that is a
policy problem.

**Options:**

1. **Do nothing** — acceptable if all your model providers are inside your
   compliance boundary (self-hosted Ollama, Azure OpenAI with a BAA, etc.)
   and your customer contracts allow it.
2. **Redact before send** — replace emails, phones, and other regex-matched
   PII with tokens before calling the model, un-redact in the response.
   Add a `redact()` helper next to `wrap_untrusted()` and call it on any
   scraped/CRM content that goes to a hosted model.
3. **Block hosted models for tenants that opt in to strict mode** — a
   per-org setting "no PII to third-party models" that forces `provider=ollama`.

I did not pick one because the answer depends on your customer contracts
and target market. Once decided, wiring is 20-30 lines.

---

## 6. What Phase 6 does NOT cover

- **Actual token counts from provider responses.** The gateway estimates
  tokens from character count (`chars // 4`). Providers return exact counts
  in `response.usage`. Wiring that is a small ai_service.py change per
  provider — see comments in `_extract_usage` region (currently absent —
  future work). Costs will be within ~15% of actual until that lands.
- **Streaming responses.** All calls are blocking. Streaming would need
  API changes and a separate audit path.
- **Semantic caching** (same prompt → cached answer). Interesting but
  not on the plan's Phase 6 checklist.
- **Per-agent cost budgets** (as opposed to per-org). Also possible via
  the `agent_name` column but not scoped in this phase.

---

## Done when

- [ ] `python tests/test_ai_gateway.py` shows `Ran 10 tests ... OK`.
- [ ] At least one agent migrated to `AIGateway` and observed writing rows
      to `ai_logs` with non-zero cost.
- [ ] Verified the pricing table against your first real provider invoice
      or explicitly overridden via `AI_PRICE_*` env vars.
- [ ] PII policy decided (do-nothing / redact / block hosted) — even if
      the decision is "do nothing for now".

When these are checked, Phase 6 is complete and Phase 7 (billing / quotas)
is next.

---

## Reference — the `AIGateway.generate_json()` pattern

```python
from pydantic import BaseModel, Field
from app.services.ai_gateway import AIGateway

class LeadQualification(BaseModel):
    company_name: str
    is_qualified: bool
    reason: str = Field(description="one-sentence justification")
    fit_score: int = Field(ge=0, le=100)

gw = AIGateway.from_streamlit(st, agent_name="qualifier")
res = gw.generate_json(
    prompt="Qualify this lead: ...",
    schema=LeadQualification,
    system="You are a strict B2B qualifier.",
    repair_attempts=1,
)

if res.ok:
    lead: LeadQualification = res.parsed
    st.write(f"{lead.company_name}: {lead.fit_score}")
else:
    st.error(f"AI failed ({res.status}): {res.error}")
```

The schema is described to the model in the system prompt automatically, and
one repair round-trip is attempted if the response fails to parse.
