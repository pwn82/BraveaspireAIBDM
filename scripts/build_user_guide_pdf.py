"""
Build two PDFs:
  1. docs/BraveAspire_User_Guide.pdf       — full illustrated manual (~25 pages)
  2. docs/BraveAspire_Cheat_Sheet.pdf      — 2-page printable quick reference

Run:  python scripts/build_user_guide_pdf.py
"""

import os
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether, Image, Flowable,
)

# ── Output paths ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
os.makedirs(DOCS_DIR, exist_ok=True)
GUIDE_PDF = os.path.join(DOCS_DIR, "BraveAspire_User_Guide.pdf")
CHEAT_PDF = os.path.join(DOCS_DIR, "BraveAspire_Cheat_Sheet.pdf")

# ── Brand colours ─────────────────────────────────────────────────────────────
BRAND_PURPLE  = colors.HexColor("#7C3AED")
BRAND_DARK    = colors.HexColor("#12102A")
BRAND_LIGHT   = colors.HexColor("#F0EEFF")
BRAND_ACCENT  = colors.HexColor("#C4B5FD")
SUCCESS_GREEN = colors.HexColor("#10B981")
WARN_AMBER    = colors.HexColor("#F59E0B")
DANGER_RED    = colors.HexColor("#EF4444")
INK           = colors.HexColor("#1F2937")
MUTED         = colors.HexColor("#6B7280")
SOFT_BG       = colors.HexColor("#F9FAFB")
BORDER        = colors.HexColor("#E5E7EB")

# ── Styles ────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=22, leading=28,
                   textColor=BRAND_PURPLE, spaceAfter=10, spaceBefore=14, fontName="Helvetica-Bold")
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=15, leading=20,
                   textColor=BRAND_PURPLE, spaceAfter=6, spaceBefore=12, fontName="Helvetica-Bold")
H3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=12, leading=16,
                   textColor=INK, spaceAfter=4, spaceBefore=8, fontName="Helvetica-Bold")
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=14,
                     textColor=INK, spaceAfter=6, fontName="Helvetica")
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=8.5, leading=11, textColor=MUTED)
CAPTION = ParagraphStyle("Caption", parent=BODY, fontSize=8, leading=10,
                         textColor=MUTED, alignment=TA_CENTER, fontName="Helvetica-Oblique")
CALLOUT = ParagraphStyle("Callout", parent=BODY, fontSize=9.5, leading=13,
                         textColor=INK, leftIndent=10, rightIndent=10,
                         spaceBefore=6, spaceAfter=6, fontName="Helvetica")
COVER_TITLE = ParagraphStyle("CoverTitle", parent=styles["Title"], fontSize=36, leading=42,
                            textColor=BRAND_PURPLE, alignment=TA_CENTER, fontName="Helvetica-Bold")
COVER_SUB = ParagraphStyle("CoverSub", parent=BODY, fontSize=14, leading=18,
                          textColor=INK, alignment=TA_CENTER, fontName="Helvetica")


# ─────────────────────────────────────────────────────────────────────────────
# Custom flowable: a "screen mockup" — purple-themed app screenshot placeholder
# ─────────────────────────────────────────────────────────────────────────────

class ScreenMockup(Flowable):
    """A stylised app screen mockup drawn directly to canvas."""

    def __init__(self, title, sidebar_active, fields=None, width=16*cm, height=9*cm,
                 buttons=None, badges=None, table_rows=None, note=None):
        Flowable.__init__(self)
        self.title           = title
        self.sidebar_active  = sidebar_active
        self.fields          = fields or []
        self.width           = width
        self.height          = height
        self.buttons         = buttons or []
        self.badges          = badges or []
        self.table_rows      = table_rows or []
        self.note            = note

    def wrap(self, _aw, _ah):
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        w, h = self.width, self.height

        # ── Browser frame ────────────────────────────────────────────────
        c.setFillColor(colors.HexColor("#1F1B3A"))
        c.roundRect(0, 0, w, h, 4, fill=1, stroke=0)

        # Top bar (browser chrome)
        c.setFillColor(colors.HexColor("#0F0D24"))
        c.rect(0, h - 0.7*cm, w, 0.7*cm, fill=1, stroke=0)
        for i, col in enumerate(["#EF4444", "#F59E0B", "#10B981"]):
            c.setFillColor(colors.HexColor(col))
            c.circle(0.3*cm + i*0.35*cm, h - 0.35*cm, 0.08*cm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#2D2556"))
        c.roundRect(2*cm, h - 0.55*cm, w - 4*cm, 0.35*cm, 1, fill=1, stroke=0)
        c.setFillColor(BRAND_ACCENT)
        c.setFont("Helvetica", 6)
        c.drawCentredString(w/2, h - 0.42*cm, "localhost:8501")

        # ── Sidebar ──────────────────────────────────────────────────────
        sb_w = 3.2*cm
        sb_x, sb_y = 0, 0
        sb_h = h - 0.7*cm
        c.setFillColor(colors.HexColor("#0F0D24"))
        c.rect(sb_x, sb_y, sb_w, sb_h, fill=1, stroke=0)

        sidebar_items = [
            "🏠 Home", "🔐 Login", "🏢 Companies", "👥 Contacts",
            "✉️ Outreach", "📅 Followups", "📊 Analytics", "💬 AI Chat",
            "⚙️ Settings", "🔄 Workflow", "💳 Billing", "🔎 Lead Scraper",
            "👤 Users",
        ]
        c.setFont("Helvetica", 6.5)
        for i, item in enumerate(sidebar_items):
            ypos = sb_h - 0.5*cm - i*0.42*cm
            if ypos < 0.3*cm:
                break
            if item == self.sidebar_active:
                c.setFillColor(BRAND_PURPLE)
                c.roundRect(0.15*cm, ypos - 0.05*cm, sb_w - 0.3*cm, 0.35*cm,
                            2, fill=1, stroke=0)
                c.setFillColor(colors.white)
            else:
                c.setFillColor(BRAND_ACCENT)
            c.drawString(sb_x + 0.3*cm, ypos + 0.05*cm, item)

        # ── Main content area ─────────────────────────────────────────────
        ma_x = sb_w + 0.3*cm
        ma_w = w - ma_x - 0.3*cm
        ma_top = h - 0.9*cm

        # Title
        c.setFillColor(BRAND_LIGHT)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(ma_x, ma_top - 0.4*cm, self.title)

        cursor_y = ma_top - 0.85*cm

        # Badges row
        if self.badges:
            bx = ma_x
            for b_text, b_color in self.badges:
                bw = c.stringWidth(b_text, "Helvetica-Bold", 6) + 0.3*cm
                c.setFillColor(colors.HexColor(b_color))
                c.roundRect(bx, cursor_y - 0.05*cm, bw, 0.3*cm, 2, fill=1, stroke=0)
                c.setFillColor(colors.white)
                c.setFont("Helvetica-Bold", 6)
                c.drawString(bx + 0.15*cm, cursor_y + 0.05*cm, b_text)
                bx += bw + 0.15*cm
            cursor_y -= 0.55*cm

        # Form fields
        for label, value, required in self.fields:
            if cursor_y < 1.0*cm:
                break
            # Label
            c.setFillColor(BRAND_ACCENT)
            c.setFont("Helvetica", 6.5)
            label_text = label + (" *" if required else "")
            c.drawString(ma_x, cursor_y, label_text)
            if required:
                c.setFillColor(DANGER_RED)
                c.drawString(ma_x + c.stringWidth(label, "Helvetica", 6.5), cursor_y, " *")
            cursor_y -= 0.3*cm
            # Input box
            c.setFillColor(colors.HexColor("#2D2556"))
            c.setStrokeColor(colors.HexColor("#4C3B8C"))
            c.roundRect(ma_x, cursor_y - 0.05*cm, ma_w - 0.3*cm, 0.35*cm,
                        2, fill=1, stroke=1)
            c.setFillColor(colors.HexColor("#9B8FD4") if not value else BRAND_LIGHT)
            c.setFont("Helvetica-Oblique" if not value else "Helvetica", 6.5)
            c.drawString(ma_x + 0.15*cm, cursor_y + 0.05*cm, value or "(empty)")
            cursor_y -= 0.5*cm

        # Table preview
        if self.table_rows and cursor_y > 2.5*cm:
            c.setFillColor(colors.HexColor("#0F0D24"))
            c.rect(ma_x, cursor_y - 0.05*cm, ma_w - 0.3*cm, 0.35*cm, fill=1, stroke=0)
            headers = self.table_rows[0]
            col_w = (ma_w - 0.3*cm) / len(headers)
            c.setFillColor(BRAND_ACCENT)
            c.setFont("Helvetica-Bold", 6)
            for i, hdr in enumerate(headers):
                c.drawString(ma_x + i*col_w + 0.1*cm, cursor_y + 0.05*cm, hdr)
            cursor_y -= 0.35*cm
            c.setFont("Helvetica", 6)
            for row in self.table_rows[1:]:
                if cursor_y < 1*cm:
                    break
                c.setFillColor(colors.HexColor("#1A1830"))
                c.rect(ma_x, cursor_y - 0.05*cm, ma_w - 0.3*cm, 0.3*cm, fill=1, stroke=0)
                c.setFillColor(BRAND_LIGHT)
                for i, cell in enumerate(row):
                    c.drawString(ma_x + i*col_w + 0.1*cm, cursor_y + 0.03*cm, str(cell)[:18])
                cursor_y -= 0.3*cm

        # Buttons row
        if self.buttons and cursor_y > 0.5*cm:
            bx = ma_x
            for btn_text, primary in self.buttons:
                bw = c.stringWidth(btn_text, "Helvetica-Bold", 7) + 0.5*cm
                c.setFillColor(BRAND_PURPLE if primary else colors.HexColor("#2D2556"))
                c.roundRect(bx, cursor_y - 0.05*cm, bw, 0.45*cm, 3, fill=1, stroke=0)
                c.setFillColor(colors.white)
                c.setFont("Helvetica-Bold", 7)
                c.drawString(bx + 0.25*cm, cursor_y + 0.1*cm, btn_text)
                bx += bw + 0.2*cm

        # Optional note at bottom of mockup
        if self.note:
            c.setFillColor(MUTED)
            c.setFont("Helvetica-Oblique", 6)
            c.drawString(ma_x, 0.2*cm, self.note)


# ─────────────────────────────────────────────────────────────────────────────
# Reusable helpers
# ─────────────────────────────────────────────────────────────────────────────

def info_box(text, kind="info"):
    palette = {
        "info":    (colors.HexColor("#EFF6FF"), colors.HexColor("#3B82F6"), "ℹ️"),
        "warn":    (colors.HexColor("#FFFBEB"), WARN_AMBER, "⚠️"),
        "success": (colors.HexColor("#ECFDF5"), SUCCESS_GREEN, "✓"),
        "danger":  (colors.HexColor("#FEF2F2"), DANGER_RED, "✗"),
    }
    bg, border, icon = palette[kind]
    t = Table([[Paragraph(f"<b>{icon}</b>  {text}", CALLOUT)]], colWidths=[16*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("BOX",        (0,0), (-1,-1), 1, border),
        ("LEFTPADDING",(0,0),(-1,-1), 12),
        ("RIGHTPADDING",(0,0),(-1,-1), 12),
        ("TOPPADDING",(0,0),(-1,-1), 8),
        ("BOTTOMPADDING",(0,0),(-1,-1), 8),
    ]))
    return t


def fields_table(rows, header=("Field", "Required?", "Notes")):
    """Render a 'mandatory fields' table."""
    data = [list(header)] + [[Paragraph(c, BODY) if isinstance(c, str) else c for c in r]
                              for r in rows]
    t = Table(data, colWidths=[5*cm, 2.5*cm, 8.5*cm], repeatRows=1)
    style = [
        ("BACKGROUND", (0,0), (-1,0), BRAND_PURPLE),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,0), 9.5),
        ("FONTSIZE",   (0,1), (-1,-1), 9),
        ("ALIGN",      (1,0), (1,-1), "CENTER"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, SOFT_BG]),
        ("GRID",       (0,0), (-1,-1), 0.4, BORDER),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
    ]
    # Highlight required cells
    for i, row in enumerate(rows, start=1):
        if isinstance(row[1], str) and "✅" in row[1]:
            style.append(("BACKGROUND", (1, i), (1, i), colors.HexColor("#D1FAE5")))
            style.append(("TEXTCOLOR",  (1, i), (1, i), colors.HexColor("#065F46")))
            style.append(("FONTNAME",   (1, i), (1, i), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    return t


def page_decoration(canvas, doc):
    canvas.saveState()
    # Header band
    canvas.setFillColor(BRAND_PURPLE)
    canvas.rect(0, A4[1] - 0.7*cm, A4[0], 0.7*cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(2*cm, A4[1] - 0.45*cm, "BraveAspire AI BDM")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 2*cm, A4[1] - 0.45*cm, "User Guide")
    # Footer
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(A4[0] / 2, 1*cm, f"Page {doc.page}")
    canvas.drawString(2*cm, 1*cm, "© BraveAspire AI BDM")
    canvas.drawRightString(A4[0] - 2*cm, 1*cm, "braveaspire.com")
    canvas.restoreState()


def section_header(num, title, anchor=None):
    """Big numbered section header with a coloured side bar."""
    txt = f'<font color="{BRAND_PURPLE.hexval()}"><b>{num}.</b></font>  {title}'
    return Paragraph(txt, H1)


# ─────────────────────────────────────────────────────────────────────────────
# Build the full guide
# ─────────────────────────────────────────────────────────────────────────────

def build_guide():
    doc = SimpleDocTemplate(
        GUIDE_PDF, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        title="BraveAspire AI BDM — User Guide", author="BraveAspire",
    )
    story = []

    # ── Cover ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 5*cm))
    story.append(Paragraph("BraveAspire", COVER_TITLE))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph("AI BDM Platform", ParagraphStyle(
        "ct2", parent=COVER_TITLE, fontSize=22, textColor=INK)))
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("End-User Guide", ParagraphStyle(
        "ct3", parent=COVER_SUB, fontSize=20, textColor=BRAND_PURPLE,
        fontName="Helvetica-Bold")))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("How to navigate every screen, what fields to fill in,<br/>and the end-to-end workflow", COVER_SUB))
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("Version 2.0  •  May 2026", ParagraphStyle(
        "cv", parent=COVER_SUB, fontSize=11, textColor=MUTED)))
    story.append(PageBreak())

    # ── Table of contents ────────────────────────────────────────────────
    story.append(Paragraph("Table of Contents", H1))
    story.append(Spacer(1, 0.3*cm))
    toc_data = [
        ["1.",  "Quick start (5 minutes from zero to first email)"],
        ["2.",  "Logging in"],
        ["3.",  "Settings — required configuration"],
        ["4.",  "Lead Scraper — discover companies"],
        ["5.",  "Companies — your prospect list"],
        ["6.",  "Contacts — decision-makers"],
        ["7.",  "Outreach — emails, LinkedIn, WhatsApp, proposals"],
        ["8.",  "Follow-ups — automated reminders"],
        ["9.",  "AI Chat assistant"],
        ["10.", "Workflow — autonomous BDM pipeline"],
        ["11.", "Analytics dashboard"],
        ["12.", "User management (admin only)"],
        ["13.", "Troubleshooting"],
        ["14.", "Quick reference — mandatory fields"],
    ]
    toc = Table(toc_data, colWidths=[1.2*cm, 14*cm])
    toc.setStyle(TableStyle([
        ("FONTSIZE",   (0,0), (-1,-1), 11),
        ("TEXTCOLOR",  (0,0), (0,-1),  BRAND_PURPLE),
        ("FONTNAME",   (0,0), (0,-1),  "Helvetica-Bold"),
        ("LEFTPADDING",(0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("LINEBELOW",  (0,0), (-1,-1), 0.3, BORDER),
    ]))
    story.append(toc)
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §1. Quick Start
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(1, "Quick start"))
    story.append(Paragraph(
        "Follow these ten steps to go from a fresh install to your first AI-personalised "
        "cold email — typically under five minutes.", BODY))
    story.append(Spacer(1, 0.2*cm))

    quick_steps = [
        ("1", "Open the app", "Go to http://localhost:8501 in your browser"),
        ("2", "Log in", "Use admin@braveaspire.com / Admin@123! (default super-admin)"),
        ("3", "Configure SMTP", "Settings → 📧 Email → enter Gmail + App Password → Test"),
        ("4", "Configure AI", "Settings → 🤖 AI → paste Groq key or run Ollama locally → Test"),
        ("5", "Add Apify token", "Settings → 🔑 API Keys → paste APIFY_API_TOKEN → Save"),
        ("6", "Scrape leads", "Lead Scraper → enter 'IT companies' + 'Hyderabad' → Start"),
        ("7", "Import to CRM", "Select top 5 results → 💾 Import to CRM"),
        ("8", "Find contacts", "Companies → pick one → 🤖 Find Contacts by AI"),
        ("9", "Personalise email", "Outreach → 🤖 AI Personalize → review draft"),
        ("10","Send", "📤 Send Now — open/click tracking + 3 follow-ups auto-scheduled"),
    ]
    qs_data = [[Paragraph(f"<b><font color='{BRAND_PURPLE.hexval()}'>{n}</font></b>", BODY),
                Paragraph(f"<b>{title}</b>", BODY),
                Paragraph(desc, SMALL)] for n, title, desc in quick_steps]
    qs = Table(qs_data, colWidths=[0.8*cm, 4*cm, 11.2*cm])
    qs.setStyle(TableStyle([
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, SOFT_BG]),
        ("LINEBELOW",  (0,0), (-1,-1), 0.3, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0),(-1,-1), 7),
    ]))
    story.append(qs)
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §2. Login
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(2, "Logging in"))
    story.append(Paragraph(
        "There is no public sign-up — only admins can create accounts. "
        "On a fresh install, the system seeds a default super-admin:", BODY))
    story.append(info_box(
        "<b>Default credentials:</b><br/>"
        "&nbsp;&nbsp;Email: <b>admin@braveaspire.com</b><br/>"
        "&nbsp;&nbsp;Password: <b>Admin@123!</b><br/><br/>"
        "Change this immediately under <b>Settings → 🔒 Security</b>.",
        "warn"))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Screen — Login page", H2))
    story.append(ScreenMockup(
        title="🔐 Login to BraveAspire",
        sidebar_active="🔐 Login",
        fields=[
            ("Email",    "admin@braveaspire.com", True),
            ("Password", "••••••••••",            True),
        ],
        buttons=[("🔓 Login", True), ("📱 Use OTP instead", False)],
        note="* required fields  •  forgotten password? ask your admin",
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Mandatory fields", H3))
    story.append(fields_table([
        ("Email",    "✅ Yes", "Your registered work email"),
        ("Password", "✅ Yes", "Minimum 6 characters"),
    ]))
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("Alternative — passwordless OTP login", H3))
    story.append(fields_table([
        ("Mobile number", "✅ Yes", "E.164 format, e.g. +919876543210"),
        ("6-digit OTP",   "✅ Yes", "Arrives via SMS (Twilio) — or check server logs in dev mode"),
    ]))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §3. Settings
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(3, "Settings — required configuration"))
    story.append(Paragraph(
        "The Settings page has <b>9 tabs</b>. Three of them must be configured "
        "before you can use the app productively: <b>AI</b>, <b>Email/SMTP</b>, "
        "and <b>API Keys</b>. The rest are optional.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="⚙️ Settings",
        sidebar_active="⚙️ Settings",
        badges=[("🤖 AI", "#7C3AED"), ("📧 SMTP", "#3B82F6"),
                ("🔑 API Keys", "#10B981"), ("👤 Profile", "#6B7280"),
                ("🔒 Security", "#EF4444"), ("🗄️ DB", "#F59E0B")],
        fields=[
            ("AI Provider",    "Groq (Cloud)",                        False),
            ("Groq API Key",   "gsk_••••••••••••••••••••••••••••••",  False),
            ("Groq Model",     "llama-3.3-70b-versatile",             False),
        ],
        buttons=[("🔌 Test Connection", True), ("💾 Save to .env", False)],
        note="Tabs across the top — switch with a single click",
    ))
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("🤖 AI tab — required", H2))
    story.append(fields_table([
        ("Provider",        "✅ Yes", "Ollama (local, free) OR Groq (cloud, faster)"),
        ("Ollama URL",      "If Ollama", "Default http://localhost:11434"),
        ("Ollama Model",    "If Ollama", "e.g. llama3, mistral, deepseek-coder"),
        ("Groq API Key",    "If Groq", "From console.groq.com"),
        ("Groq Model",      "If Groq", "Default llama-3.3-70b-versatile"),
    ]))
    story.append(PageBreak())

    story.append(Paragraph("📧 Email / SMTP tab — required", H2))
    story.append(Paragraph(
        "Without this, no outreach emails can be sent.", BODY))
    story.append(fields_table([
        ("SMTP Host",     "✅ Yes", "e.g. smtp.gmail.com"),
        ("SMTP Port",     "✅ Yes", "Usually 587 (TLS)"),
        ("SMTP Email",    "✅ Yes", "Your sending address"),
        ("App Password",  "✅ Yes", "Gmail: enable 2FA then generate an App Password"),
        ("From Email",    "Optional", "Defaults to SMTP Email"),
        ("From Name",     "Optional", "Display name e.g. 'BraveAspire Team'"),
    ]))
    story.append(Spacer(1, 0.3*cm))
    story.append(info_box(
        "<b>Gmail setup:</b> enable 2-Factor Authentication → Google Account → "
        "Security → App Passwords → generate a 16-char password → paste that "
        "into <b>App Password</b> above (NOT your normal Gmail password).",
        "info"))
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("🔑 API Keys tab — recommended", H2))
    story.append(Paragraph(
        "Without at least one of these, the Lead Scraper returns only demo data. "
        "<b>Apify is the easiest single key</b> — it covers Google Maps, LinkedIn, "
        "and Indeed scraping in one subscription.", BODY))
    story.append(fields_table([
        ("Apollo.io key",      "Optional", "Best contact + email data"),
        ("Google Maps key",    "Optional", "Local business search"),
        ("Crunchbase key",     "Optional", "Startup funding firmographics"),
        ("Proxycurl key",      "Optional", "LinkedIn enrichment"),
        ("Apify token",        "✅ Recommended", "Easiest — covers multiple sources"),
        ("Hunter.io key",      "Optional", "Email discovery from domains"),
        ("Twilio SID/Token",   "If SMS OTP", "From console.twilio.com"),
    ]))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §4. Lead Scraper
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(4, "Lead Scraper"))
    story.append(Paragraph(
        "<b>Module 1</b> of the pipeline — discover prospects from Apify, "
        "Apollo, Google Maps, Crunchbase, Clutch.co, Indeed, and Naukri.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="🔎 Lead Scraper — Discover Companies",
        sidebar_active="🔎 Lead Scraper",
        badges=[("✅ Apify", "#10B981"), ("⚙️ Apollo", "#6B7280"),
                ("⚙️ Google Maps", "#6B7280"), ("🆓 Clutch.co", "#3B82F6"),
                ("🆓 Indeed", "#3B82F6")],
        fields=[
            ("Search query",  "IT companies",  True),
            ("Industry",      "Software",      False),
            ("Location",      "Hyderabad",     False),
            ("Max results",   "15",            False),
        ],
        buttons=[("🚀 Start Scraping", True), ("📥 Export CSV", False)],
        note="At least one of query/industry/location must be filled  •  ✅=key set, ⚙️=add key, 🆓=no key needed",
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Mandatory inputs", H3))
    story.append(fields_table([
        ("Search query",       "Either",   "Free-form, e.g. 'SaaS startups hiring Python'"),
        ("Industry",           "Either",   "e.g. Fintech, Healthcare, SaaS"),
        ("Location",           "Either",   "e.g. Hyderabad, Mumbai, San Francisco"),
        ("At least 1 source",  "✅ Yes",   "Check at least one box from Apify / Clutch / Indeed / etc."),
    ], header=("Field", "Required", "Example")))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Optional refinements", H3))
    story.append(fields_table([
        ("Employee size",      "Optional", "e.g. 50-200, 100-500"),
        ("Technology",         "Optional", "e.g. React, Python, Node.js"),
        ("Actively hiring",    "Optional", "Filter to companies posting jobs"),
        ("Has funding",        "Optional", "Only Series A+ etc."),
        ("Outdated tech",      "Optional", "Companies flagged as legacy"),
    ]))
    story.append(Spacer(1, 0.3*cm))
    story.append(info_box(
        "<b>Apify free plan:</b> ~1 Google Maps search per 30 minutes. "
        "If you see a 'TIMED-OUT' warning, wait a few minutes and try again, "
        "or upgrade at apify.com/pricing for unlimited runs.", "warn"))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §5. Companies
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(5, "Companies"))
    story.append(Paragraph(
        "Your CRM database of prospect companies. View, filter, edit, "
        "or add manually.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="🏢 Companies (24)",
        sidebar_active="🏢 Companies",
        badges=[("Total: 24", "#7C3AED"), ("Hiring: 9", "#10B981"),
                ("Hot: 6", "#EF4444")],
        table_rows=[
            ["Name", "Industry", "Loc", "Score", "Status"],
            ["TechNova",      "SaaS",     "SF",   "92", "Interested"],
            ["HealthBridge",  "Health",   "Aus",  "87", "Contacted"],
            ["FinFlow Labs",  "Fintech",  "NY",   "88", "Proposal"],
            ["RetailEdge",    "Ecom",     "Chi",  "79", "New"],
        ],
        buttons=[("➕ Add Company", True), ("🤖 AI Discovery", False),
                 ("📥 Export", False)],
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Add Company dialog", H3))
    story.append(fields_table([
        ("Company Name",      "✅ Yes",     "e.g. Acme Corp"),
        ("Website",           "Optional",   "e.g. acme.com"),
        ("Industry",          "Optional",   "Free text or pick from list"),
        ("Location",          "Optional",   "City, Country"),
        ("Employee Size",     "Optional",   "Integer"),
        ("Revenue",           "Optional",   "e.g. $1M-$5M"),
        ("Status",            "Optional",   "New / Contacted / Interested / Proposal / Won / Lost"),
        ("Hiring?",           "Optional",   "Checkbox"),
        ("Tech Stack",        "Optional",   "Comma-separated"),
        ("Pain Points",       "Optional",   "Free text — AI uses this for personalisation"),
    ]))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §6. Contacts
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(6, "Contacts"))
    story.append(Paragraph(
        "Decision-makers at your target companies. Each contact belongs to a "
        "company.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="👥 Contacts (18)",
        sidebar_active="👥 Contacts",
        table_rows=[
            ["Name", "Company", "Title", "Email", "Verified"],
            ["James Carter",   "TechNova",     "CTO",        "j.carter@…",  "✓"],
            ["Sarah Kim",      "TechNova",     "VP Eng",     "s.kim@…",     "✓"],
            ["Michael Torres", "HealthBridge", "CEO",        "m.torres@…",  "✓"],
            ["Alex Johnson",   "FinFlow",      "Founder",    "alex@…",      "✓"],
        ],
        buttons=[("➕ Add Contact", True), ("🤖 Find by AI", False),
                 ("✉️ Verify Email", False)],
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(fields_table([
        ("Company",        "✅ Yes",     "Pick from your Companies list"),
        ("Name",           "✅ Yes",     "Full name"),
        ("Designation",    "Recommended","Title — used in AI personalisation"),
        ("Email",          "Recommended","Required to actually send outreach"),
        ("LinkedIn URL",   "Optional",   "Full https URL"),
        ("Phone",          "Optional",   "E.164 format"),
        ("Verified",       "Optional",   "Checkbox once email is confirmed"),
    ]))
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("🤖 Find Contacts by AI", H3))
    story.append(Paragraph(
        "From any company's detail view, click <b>Find Contacts by AI</b>. "
        "The system uses GPT/Llama to guess likely decision-makers (CTO, VP "
        "Engineering, Head of Product etc.) and Hunter.io to predict their "
        "email pattern. Review and add the ones that look correct.", BODY))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §7. Outreach
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(7, "Outreach"))
    story.append(Paragraph(
        "Send personalised messages across <b>4 channels</b>: Email, LinkedIn, "
        "WhatsApp, and Proposal. Each has its own tab.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="✉️ Outreach → Email tab",
        sidebar_active="✉️ Outreach",
        badges=[("📧 Email", "#7C3AED"), ("🔗 LinkedIn", "#3B82F6"),
                ("💬 WhatsApp", "#10B981"), ("📄 Proposal", "#F59E0B")],
        fields=[
            ("Contact",  "James Carter — CTO @ TechNova", True),
            ("Subject",  "Partnership — AI-Powered Engineering Solutions", True),
            ("Body",     "Hi James, I noticed TechNova's recent Series B…", True),
        ],
        buttons=[("🤖 AI Personalize", True), ("📤 Send Now", True),
                 ("💾 Save Draft", False)],
        note="Open/click tracking pixel is embedded automatically",
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(fields_table([
        ("Contact",       "✅ Yes", "Pick from your contacts list"),
        ("Subject",       "✅ Yes", "Or use 🤖 AI Personalize to generate"),
        ("Body",          "✅ Yes", "Or use AI Personalize"),
        ("Channel",       "Auto",   "Email / LinkedIn / WhatsApp"),
        ("Schedule for later", "Optional", "Pick date+time, or send immediately"),
    ]))
    story.append(Spacer(1, 0.4*cm))

    status_legend = [
        ("📝 Draft",      "Saved but not sent"),
        ("📤 Sent",       "Email delivered"),
        ("👁️ Opened",    "Recipient opened (tracking pixel fired)"),
        ("💬 Replied",   "Recipient replied (detected by IMAP)"),
        ("⚠️ Bounced",   "Invalid address"),
        ("🕐 Scheduled", "Queued for later"),
    ]
    story.append(Paragraph("Outreach statuses", H3))
    sl = Table([[Paragraph(f"<b>{s}</b>", BODY), Paragraph(d, BODY)]
                for s, d in status_legend], colWidths=[3.5*cm, 12.5*cm])
    sl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, SOFT_BG]),
        ("LINEBELOW",      (0,0), (-1,-1), 0.3, BORDER),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
    ]))
    story.append(sl)
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §8. Follow-ups
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(8, "Follow-ups"))
    story.append(Paragraph(
        "When you send an outreach, the system automatically creates "
        "<b>3 follow-up reminders</b> at +3, +7, and +14 days. You can edit "
        "or cancel any of them.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="📅 Follow-ups (12 pending)",
        sidebar_active="📅 Followups",
        table_rows=[
            ["#", "Contact",      "Original Subject",     "Due",       "Status"],
            ["1", "James Carter", "Partnership Opportunity", "in 2d",  "Scheduled"],
            ["2", "Sarah Kim",    "AI Engineering Solutions","in 5d",  "Scheduled"],
            ["3", "Michael T.",   "Modernizing HealthBridge","tomorrow","Scheduled"],
        ],
        buttons=[("✏️ Edit", False), ("📤 Send Now", True),
                 ("✅ Mark Done", False), ("🤖 AI Suggest Reply", False)],
        note="Statuses auto-update — no mandatory fields, all pre-filled",
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(info_box(
        "Follow-ups have <b>no mandatory fields</b> — subject and body are "
        "auto-generated from the original outreach. You only need to edit "
        "them if you want to customise the wording.", "info"))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §9. AI Chat
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(9, "AI Chat assistant"))
    story.append(Paragraph(
        "Conversational interface to your CRM. Ask questions in plain English — "
        "the AI uses ChromaDB vector search to ground its answers in your "
        "real company and contact data.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="💬 AI Chat",
        sidebar_active="💬 AI Chat",
        fields=[
            ("You",        "Which companies have score > 85 and are hiring?", False),
            ("Assistant",  "I found 6 companies: TechNova (92), CyberShield (90)…", False),
            ("You",        "Draft a cold email for TechNova's CTO",            True),
        ],
        buttons=[("📤 Send", True), ("🔄 Clear chat", False)],
        note="Powered by Ollama or Groq + ChromaDB vector retrieval",
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Example prompts to try", H3))
    examples = [
        "• Show me companies with score above 80",
        "• Which contacts haven't been emailed yet?",
        "• Summarise my pipeline this week",
        "• Draft a follow-up for HealthBridge",
        "• Find similar companies to FinFlow Labs",
    ]
    for ex in examples:
        story.append(Paragraph(ex, BODY))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §10. Workflow
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(10, "Workflow — autonomous BDM pipeline"))
    story.append(Paragraph(
        "Runs all 5 agents end-to-end: <b>Scrape → Find Contacts → Personalise → "
        "Send (with approval) → Track</b>. The pipeline pauses at the Send step "
        "for human approval unless you enable auto-send.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="🔄 Workflow — Autonomous BDM Pipeline",
        sidebar_active="🔄 Workflow",
        fields=[
            ("Target description", "Fintech startups in India hiring backend engineers", True),
            ("Max companies",      "10",                                            True),
            ("☑ Auto-send (HITL)", "Unchecked — you approve each email",            False),
        ],
        buttons=[("▶️ Run Workflow", True), ("⏸ Pause", False),
                 ("📋 View history", False)],
        note="5 agents: Scrape → Find Contacts → Personalise → Send → Track",
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(fields_table([
        ("Target description", "✅ Yes", "Plain-English brief, e.g. 'Fintech in India hiring backend engineers'"),
        ("Max companies",      "✅ Yes", "1–20 (start small, increase later)"),
        ("Auto-send (HITL)",   "Optional", "Off = human approves each email. On = fully autonomous"),
    ]))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §11. Analytics
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(11, "Analytics"))
    story.append(Paragraph("Read-only dashboards — no fields to fill in.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="📊 Analytics",
        sidebar_active="📊 Analytics",
        badges=[("Pipeline: 24", "#7C3AED"), ("Open rate: 42%", "#10B981"),
                ("Reply rate: 11%", "#3B82F6"), ("Won: 3", "#F59E0B")],
        table_rows=[
            ["Week",  "Sent", "Opened", "Replied", "Won"],
            ["W-1",   "12",   "5",      "1",       "0"],
            ["W-2",   "18",   "8",      "2",       "1"],
            ["W-3",   "24",   "11",     "3",       "1"],
            ["W-4",   "31",   "14",     "4",       "1"],
        ],
        buttons=[("📥 Download report", False)],
    ))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §12. User Management
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(12, "User management"))
    story.append(Paragraph(
        "Visible only if your role is <b>admin</b> or <b>super_admin</b>. "
        "Create accounts, assign roles, manage 2FA, lock/unlock.", BODY))
    story.append(Spacer(1, 0.3*cm))

    story.append(ScreenMockup(
        title="👤 Users (admin only)",
        sidebar_active="👤 Users",
        table_rows=[
            ["Email",            "Role",          "2FA",  "Last login"],
            ["admin@brave...",   "super_admin",   "✓",    "today"],
            ["sales@brave...",   "sales_manager", "✓",    "yesterday"],
            ["john@brave...",    "bdm",           "—",    "3 days ago"],
        ],
        buttons=[("➕ Create User", True), ("🔐 Setup TOTP", False),
                 ("🔒 Lock", False), ("🗑️ Delete", False)],
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Create User dialog — mandatory fields", H3))
    story.append(fields_table([
        ("Email",      "✅ Yes",   "Must be unique"),
        ("Full name",  "✅ Yes",   "First + last"),
        ("Role",       "✅ Yes",   "super_admin / admin / sales_manager / bdm / sales_executive / viewer"),
        ("Mobile",     "Optional", "E.164, needed for SMS-OTP login"),
        ("Department", "Optional", "e.g. Sales, Marketing"),
    ]))
    story.append(Spacer(1, 0.3*cm))
    story.append(info_box(
        "A temporary password is auto-generated and emailed to the new user. "
        "They will be forced to change it on first login.", "info"))
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §13. Troubleshooting
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(13, "Troubleshooting"))
    trouble = [
        ("'Start Scraping' does nothing",     "All three query/industry/location fields empty",
         "Fill at least one"),
        ("Lead Scraper returns Demo only",    "No API keys configured",
         "Settings → 🔑 API Keys → add Apify token"),
        ("Apify TIMED-OUT / rate limit",      "Free plan ≈ 1 Google Maps run / 30 min",
         "Wait, or upgrade Apify plan"),
        ("SMTP credentials not configured",   "Gmail App Password empty",
         "Settings → 📧 Email → fill all four fields → Test"),
        ("Account locked",                    "5 failed password attempts",
         "Wait 15 minutes OR ask admin to unlock"),
        ("QR code not showing for 2FA",       "qrcode/PIL libraries missing",
         "pip install qrcode[pil] Pillow pyotp"),
        ("'String would be truncated' on import","Column too small (legacy DB)",
         "Already fixed in v2.x — restart the app"),
        ("OTP not arriving via SMS",          "Twilio not configured",
         "Settings → 🔑 → fill Twilio. Or check logs for OTP in dev mode"),
        ("AI Chat: 'service unavailable'",    "Ollama not running, or bad Groq key",
         "Settings → 🤖 AI → Test Connection"),
    ]
    tdata = [[Paragraph(s, BODY), Paragraph(c, SMALL), Paragraph(f, BODY)] for s, c, f in trouble]
    ttable = Table([[Paragraph("<b>Symptom</b>", BODY),
                     Paragraph("<b>Cause</b>", BODY),
                     Paragraph("<b>Fix</b>", BODY)]] + tdata,
                   colWidths=[5*cm, 5*cm, 6*cm])
    ttable.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0), BRAND_PURPLE),
        ("TEXTCOLOR",      (0,0), (-1,0), colors.white),
        ("FONTNAME",       (0,0), (-1,0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, SOFT_BG]),
        ("GRID",           (0,0), (-1,-1), 0.3, BORDER),
        ("VALIGN",         (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",    (0,0), (-1,-1), 5),
        ("RIGHTPADDING",   (0,0), (-1,-1), 5),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
    ]))
    story.append(ttable)
    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────────
    # §14. Quick Reference card
    # ─────────────────────────────────────────────────────────────────────
    story.append(section_header(14, "Quick reference — mandatory fields"))
    story.append(Paragraph(
        "One-glance summary of every screen and what you must fill in.", BODY))
    story.append(Spacer(1, 0.3*cm))

    qr = [
        ("Login (password)",   "Email, Password"),
        ("Login (OTP)",        "Mobile, OTP"),
        ("Settings — AI",      "Provider; Ollama URL+model OR Groq key+model"),
        ("Settings — SMTP",    "Host, Port, User, App Password"),
        ("Settings — Profile", "(none — but Name/Company recommended)"),
        ("Lead Scraper",       "≥1 of: Query / Industry / Location; ≥1 source"),
        ("Add Company",        "Company Name"),
        ("Add Contact",        "Company, Name"),
        ("Outreach",           "Contact, Subject, Body"),
        ("Workflow",           "Target description, Max companies"),
        ("Create User",        "Email, Full Name, Role"),
    ]
    qrdata = [[Paragraph(f"<b>{p}</b>", BODY),
               Paragraph(f, BODY)] for p, f in qr]
    qrtable = Table([[Paragraph("<b>Screen</b>", BODY),
                      Paragraph("<b>Must fill</b>", BODY)]] + qrdata,
                    colWidths=[5*cm, 11*cm])
    qrtable.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0), BRAND_PURPLE),
        ("TEXTCOLOR",      (0,0), (-1,0), colors.white),
        ("FONTNAME",       (0,0), (-1,0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, SOFT_BG]),
        ("GRID",           (0,0), (-1,-1), 0.3, BORDER),
        ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",    (0,0), (-1,-1), 8),
        ("RIGHTPADDING",   (0,0), (-1,-1), 8),
        ("TOPPADDING",     (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 7),
    ]))
    story.append(qrtable)
    story.append(Spacer(1, 1*cm))
    story.append(info_box(
        "Everything else on every screen is <b>optional</b> and will either "
        "have a sensible default or be auto-generated by the AI.", "success"))

    doc.build(story, onFirstPage=page_decoration, onLaterPages=page_decoration)
    print(f"[OK] Built: {GUIDE_PDF}")


# ─────────────────────────────────────────────────────────────────────────────
# Build the cheat-sheet (2-page landscape printable)
# ─────────────────────────────────────────────────────────────────────────────

def build_cheat_sheet():
    doc = SimpleDocTemplate(
        CHEAT_PDF, pagesize=landscape(A4),
        leftMargin=1*cm, rightMargin=1*cm,
        topMargin=0.8*cm, bottomMargin=0.8*cm,
        title="BraveAspire AI BDM — Cheat Sheet",
    )
    story = []

    # ── Header ───────────────────────────────────────────────────────────
    story.append(Paragraph(
        "<font color='#7C3AED'><b>BraveAspire AI BDM</b></font>  "
        "<font color='#1F2937' size='14'>— Printable Cheat Sheet</font>",
        ParagraphStyle("ch", parent=H1, fontSize=20, alignment=TA_LEFT, spaceAfter=2)
    ))
    story.append(Paragraph(
        "Pin this next to your monitor.  ✅ = mandatory  •  ⚙️ = optional but recommended",
        SMALL))
    story.append(Spacer(1, 0.3*cm))

    # ── Two-column layout: left = mockups, right = field tables ──────────
    # Row 1 — Settings + Lead Scraper
    settings_mock = ScreenMockup(
        title="⚙️ Settings → AI / SMTP / 🔑 API Keys",
        sidebar_active="⚙️ Settings",
        badges=[("🤖", "#7C3AED"), ("📧", "#3B82F6"), ("🔑", "#10B981")],
        fields=[
            ("AI provider", "Groq", True),
            ("SMTP Host",   "smtp.gmail.com", True),
            ("App password","••••••••••••", True),
            ("Apify token", "apify_api_••••", False),
        ],
        buttons=[("💾 Save", True)],
        width=12*cm, height=7*cm,
    )
    scraper_mock = ScreenMockup(
        title="🔎 Lead Scraper",
        sidebar_active="🔎 Lead Scraper",
        badges=[("✅ Apify", "#10B981")],
        fields=[
            ("Query OR Industry OR Location", "IT companies / Hyderabad", True),
            ("Max results", "15", False),
        ],
        buttons=[("🚀 Start", True), ("📥 Export", False)],
        width=12*cm, height=7*cm,
        note="Fill ≥1 input. Check ≥1 source. Apify free = 1 run / 30 min.",
    )

    settings_fields = fields_table([
        ("Provider",     "✅",  "Ollama or Groq"),
        ("SMTP Host",    "✅",  "smtp.gmail.com"),
        ("SMTP Email",   "✅",  "your@gmail.com"),
        ("App Password", "✅",  "Gmail App Pw (not normal pw)"),
        ("Apify token",  "⚙️",  "Recommended for real leads"),
    ], header=("Settings", "Req", "Note"))

    scraper_fields = fields_table([
        ("Query",        "Either", "'IT companies'"),
        ("Industry",     "Either", "'Software'"),
        ("Location",     "Either", "'Hyderabad'"),
        ("Sources",      "✅",     "Pick ≥1 box"),
    ], header=("Lead Scraper", "Req", "Example"))

    row1 = Table(
        [[settings_mock, settings_fields],
         [scraper_mock,  scraper_fields]],
        colWidths=[12.5*cm, 13.5*cm],
        rowHeights=[7.5*cm, 7.5*cm],
    )
    row1.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ]))
    story.append(row1)
    story.append(PageBreak())

    # ── Page 2: Outreach + Companies + Contacts + Workflow ───────────────
    story.append(Paragraph(
        "<font color='#7C3AED'><b>Companies • Contacts • Outreach • Workflow</b></font>",
        ParagraphStyle("ch2", parent=H1, fontSize=18, alignment=TA_LEFT, spaceAfter=2)))
    story.append(Spacer(1, 0.2*cm))

    out_mock = ScreenMockup(
        title="✉️ Outreach — Email tab",
        sidebar_active="✉️ Outreach",
        badges=[("📧", "#7C3AED")],
        fields=[
            ("Contact", "James Carter — CTO @ TechNova", True),
            ("Subject", "Partnership — AI Solutions",     True),
            ("Body",    "Hi James, …",                    True),
        ],
        buttons=[("🤖 Personalize", True), ("📤 Send", True)],
        width=12*cm, height=7*cm,
        note="Use 🤖 AI Personalize to auto-fill subject + body",
    )
    workflow_mock = ScreenMockup(
        title="🔄 Workflow — autonomous pipeline",
        sidebar_active="🔄 Workflow",
        fields=[
            ("Target",        "Fintech India hiring backend", True),
            ("Max companies", "10",                           True),
        ],
        buttons=[("▶️ Run", True)],
        width=12*cm, height=7*cm,
        note="Scrape → Contacts → Personalize → Approve → Track",
    )

    cc_fields = fields_table([
        ("Add Company → Name",       "✅",  "Everything else optional"),
        ("Add Contact → Company",    "✅",  ""),
        ("Add Contact → Name",       "✅",  ""),
        ("Outreach → Contact",       "✅",  ""),
        ("Outreach → Subject",       "✅",  "or click 🤖 Personalize"),
        ("Outreach → Body",          "✅",  "or click 🤖 Personalize"),
        ("Workflow → Target",        "✅",  "Plain English"),
        ("Workflow → Max companies", "✅",  "1–20"),
    ], header=("Field", "Req", "Note"))

    legend_data = [
        ["✅ Mandatory",      "Required — page won't proceed without it"],
        ["⚙️ Recommended",   "Optional but makes the feature work properly"],
        ["📝 Draft",          "Saved, not yet sent"],
        ["📤 Sent",           "Delivered"],
        ["👁️ Opened",        "Tracking pixel fired"],
        ["💬 Replied",        "IMAP detected reply"],
        ["🟢/🟡/🔴 Score",    "≥80 / 60–79 / <60 lead quality"],
    ]
    legend = Table(legend_data, colWidths=[3*cm, 10.5*cm])
    legend.setStyle(TableStyle([
        ("FONTSIZE",       (0,0), (-1,-1), 9),
        ("FONTNAME",       (0,0), (0,-1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, SOFT_BG]),
        ("LINEBELOW",      (0,0), (-1,-1), 0.3, BORDER),
        ("TOPPADDING",     (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 4),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
    ]))

    row2 = Table(
        [[out_mock,      cc_fields],
         [workflow_mock, legend]],
        colWidths=[12.5*cm, 13.5*cm],
        rowHeights=[7.5*cm, 7.5*cm],
    )
    row2.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ]))
    story.append(row2)

    doc.build(story)
    print(f"[OK] Built: {CHEAT_PDF}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    build_guide()
    build_cheat_sheet()
    print()
    print("Output files:")
    print(f"   {GUIDE_PDF}")
    print(f"   {CHEAT_PDF}")
