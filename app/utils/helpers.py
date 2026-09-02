import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()


def load_settings(st):
    """Initialize Streamlit session_state settings from .env (only if not already set)."""
    defaults = {
        # AI
        "ai_provider":       os.getenv("AI_PROVIDER",       "ollama"),
        "ollama_model":      os.getenv("OLLAMA_MODEL",      "llama3"),
        "ollama_url":        os.getenv("OLLAMA_BASE_URL",   "http://localhost:11434"),
        "groq_model":        os.getenv("GROQ_MODEL",        "llama-3.3-70b-versatile"),
        "groq_api_key":      os.getenv("GROQ_API_KEY",      ""),
        "openai_model":      os.getenv("OPENAI_MODEL",      "gpt-4o-mini"),
        "openai_api_key":    os.getenv("OPENAI_API_KEY",    ""),
        "anthropic_model":   os.getenv("ANTHROPIC_MODEL",   "claude-haiku-4-5-20251001"),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        # Email / SMTP
        "smtp_host":       os.getenv("SMTP_HOST",          "smtp.gmail.com"),
        "smtp_port":       int(os.getenv("SMTP_PORT",      "587")),
        "smtp_user":       os.getenv("SMTP_USER",          ""),
        "smtp_password":   os.getenv("SMTP_PASSWORD",      ""),
        "from_email":      os.getenv("FROM_EMAIL",         ""),
        "from_name":       os.getenv("FROM_NAME",          "BraveAspire AI BDM"),
        # Profile
        "sender_name":     os.getenv("SENDER_NAME",        "BraveAspire Team"),
        "sender_company":  os.getenv("SENDER_COMPANY",     "BraveAspire"),
        "services_offered":os.getenv("SERVICES",           "custom software development & AI solutions"),
        # Lead Scraping API keys
        "apollo_api_key":        os.getenv("APOLLO_API_KEY",        ""),
        "google_maps_api_key":   os.getenv("GOOGLE_MAPS_API_KEY",   ""),
        "crunchbase_api_key":    os.getenv("CRUNCHBASE_API_KEY",    ""),
        "proxycurl_api_key":     os.getenv("PROXYCURL_API_KEY",     ""),
        "apify_api_token":       os.getenv("APIFY_API_TOKEN",       ""),
        "hunter_api_key":        os.getenv("HUNTER_API_KEY",        ""),
        # SMS / OTP
        "twilio_account_sid":    os.getenv("TWILIO_ACCOUNT_SID",    ""),
        "twilio_auth_token":     os.getenv("TWILIO_AUTH_TOKEN",     ""),
        "twilio_from_number":    os.getenv("TWILIO_FROM_NUMBER",    ""),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_api_key(st_or_key_name, key_name: str = "") -> str:
    """
    Get an API key — first from Streamlit session_state, then from os.environ.
    Usage: get_api_key(st, "apollo_api_key")  OR  get_api_key("APOLLO_API_KEY")
    """
    if key_name:
        # Called with (st, "session_state_key")
        return st_or_key_name.session_state.get(key_name, "") or os.getenv(key_name.upper(), "")
    else:
        # Called with ("ENV_VAR_NAME")
        name = st_or_key_name
        return os.getenv(name, "")


def get_scoped_crm(st):
    """
    Return a CRMService bound to the current user's organization.

    Raises RuntimeError if the caller has no active org membership — that is
    ALWAYS a bug (user must be authenticated with a valid org context before
    reaching a CRM screen). Fail loudly rather than fall back to system mode.
    """
    from .rbac import get_current_org_id
    from ..services.crm_service import CRMService
    org_id = get_current_org_id()
    if org_id is None:
        raise RuntimeError(
            "No organization context. User must be authenticated before "
            "constructing a CRMService."
        )
    return CRMService(organization_id=org_id)


def get_ai_service(st):
    """Build AIService from current session_state settings."""
    from ..services.ai_service import AIService
    return AIService(
        provider=st.session_state.get("ai_provider", "ollama"),
        ollama_model=st.session_state.get("ollama_model", "llama3"),
        ollama_url=st.session_state.get("ollama_url", "http://localhost:11434"),
        groq_model=st.session_state.get("groq_model", "llama-3.3-70b-versatile"),
        groq_api_key=st.session_state.get("groq_api_key", ""),
        openai_model=st.session_state.get("openai_model", "gpt-4o-mini"),
        openai_api_key=st.session_state.get("openai_api_key", ""),
        anthropic_model=st.session_state.get("anthropic_model", "claude-haiku-4-5-20251001"),
        anthropic_api_key=st.session_state.get("anthropic_api_key", ""),
    )


def send_email(to_email: str, subject: str, body: str, settings: dict,
               organization_id: int = None, outreach_id: int = None) -> tuple[bool, str]:
    """
    Send email via SMTP. Returns (success, message).

    Phase 5: prefers the safety-pipeline path (`EmailService.send`) when an
    `organization_id` is supplied — that enforces suppression, unsubscribe,
    daily quota, and stamps a Message-ID for reply threading. Callers that
    still pass only the legacy signature keep working via a raw-SMTP fallback,
    but that path bypasses safety checks and should be migrated.
    """
    if organization_id:
        from ..services.email_service import EmailService
        svc = EmailService(organization_id=organization_id)
        result = svc.send(
            to_email=to_email, subject=subject, body=body,
            smtp_cfg=settings, outreach_id=outreach_id,
        )
        return result.ok, f"{result.status}: {result.reason or ''}".rstrip(": ")

    # Legacy path — no tenant context, no safety checks. Preserved so pages
    # that only test SMTP connectivity from the Settings page keep working.
    if not settings.get("smtp_user") or not settings.get("smtp_password"):
        return False, "SMTP credentials not configured. Go to Settings."
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.get('from_name', 'BraveAspire')} <{settings['from_email'] or settings['smtp_user']}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(settings["smtp_host"], settings["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(settings["smtp_user"], settings["smtp_password"])
            server.sendmail(settings["smtp_user"], to_email, msg.as_string())
        return True, f"Email sent to {to_email}"
    except Exception as e:
        return False, str(e)


def score_color(score: int) -> str:
    if score >= 85:
        return "green"
    elif score >= 70:
        return "orange"
    return "red"


def status_emoji(status: str) -> str:
    return {
        "New": "🆕",
        "Contacted": "📬",
        "Interested": "💡",
        "Proposal": "📋",
        "Won": "✅",
        "Lost": "❌",
        "Draft": "📝",
        "Sent": "📤",
        "Opened": "👁️",
        "Replied": "💬",
        "Bounced": "⚠️",
        "Scheduled": "🕐",
        "Pending Approval": "⏳",
    }.get(status, "•")
