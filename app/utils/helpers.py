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
        "ai_provider":     os.getenv("AI_PROVIDER",       "ollama"),
        "ollama_model":    os.getenv("OLLAMA_MODEL",       "llama3"),
        "ollama_url":      os.getenv("OLLAMA_BASE_URL",    "http://localhost:11434"),
        "groq_model":      os.getenv("GROQ_MODEL",         "llama-3.3-70b-versatile"),
        "groq_api_key":    os.getenv("GROQ_API_KEY",       ""),
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


def get_ai_service(st):
    """Build AIService from current session_state settings."""
    from ..services.ai_service import AIService
    return AIService(
        provider=st.session_state.get("ai_provider", "ollama"),
        ollama_model=st.session_state.get("ollama_model", "llama3"),
        ollama_url=st.session_state.get("ollama_url", "http://localhost:11434"),
        groq_model=st.session_state.get("groq_model", "llama3-70b-8192"),
        groq_api_key=st.session_state.get("groq_api_key", ""),
    )


def send_email(to_email: str, subject: str, body: str, settings: dict) -> tuple[bool, str]:
    """Send email via SMTP. Returns (success, message)."""
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
