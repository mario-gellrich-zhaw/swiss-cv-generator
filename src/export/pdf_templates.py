"""
Modern PDF Templates for Swiss CV Generator.

Templates:
1. classic  - Two-column layout with right sidebar (Blue)
2. modern   - Dark sidebar on left (Green)
3. minimal  - Clean single-column (Purple)
4. timeline - Visual timeline for jobs (Pink)

Run: python scripts/generate_cv_parallel.py --template random
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Frame, PageTemplate, FrameBreak,
    Table, TableStyle, Flowable, KeepTogether, Image
)
from reportlab.pdfbase import ttfonts, pdfmetrics
from reportlab.lib.colors import HexColor
from typing import Any, Optional, Dict
import datetime
import os
import base64
import tempfile
import random

# Font configuration
FONT_DIR = os.path.join(os.getcwd(), "assets", "fonts")

def _register_fonts():
    """Register Inter fonts if present, otherwise fall back to Helvetica."""
    try:
        reg = {
            "Inter": os.path.join(FONT_DIR, "Inter-Regular.ttf"),
            "Inter-Bold": os.path.join(FONT_DIR, "Inter-Bold.ttf"),
        }
        any_reg = False
        for name, path in reg.items():
            if os.path.exists(path):
                pdfmetrics.registerFont(ttfonts.TTFont(name, path))
                any_reg = True
        if any_reg:
            return "Inter", "Inter-Bold"
    except Exception:
        pass
    return "Helvetica", "Helvetica-Bold"

FONT_REGULAR, FONT_BOLD = _register_fonts()

# Available templates
TEMPLATES = {
    "classic": {
        "name": "Classic (Two-Column)",
        "description": "Traditional two-column layout with right sidebar",
        "accent": "#0050A4",
    },
    "modern": {
        "name": "Modern (Dark Sidebar)",
        "description": "Contemporary design with dark left sidebar",
        "accent": "#10B981",
    },
    "minimal": {
        "name": "Minimal (Single Column)",
        "description": "Clean, minimal single-column layout",
        "accent": "#6366F1",
    },
    "timeline": {
        "name": "Timeline (Visual History)",
        "description": "Visual timeline for career progression",
        "accent": "#EC4899",
    },
}


def _get(p: Any, key: str, default: Optional[str] = "") -> str:
    """Safely get attribute or dict value."""
    if p is None:
        return default
    if isinstance(p, dict):
        val = p.get(key, default)
        return val if val is not None else default
    val = getattr(p, key, default)
    return val if val is not None else default


def _format_end_date(end_date: Any) -> str:
    """Format end date, ensuring 'Heute' for current jobs."""
    if end_date is None or end_date == "" or str(end_date).lower() == "none":
        return "Heute"
    return str(end_date)


def _labels_for_lang(lang: str) -> Dict[str, str]:
    """Get localized labels."""
    mapping = {
        "de": {
            "profile": "Profil",
            "experience": "Berufserfahrung",
            "education": "Ausbildung",
            "skills": "Kompetenzen",
            "languages": "Sprachen",
            "contact": "Kontakt",
            "hobbies": "Interessen",
        },
        "fr": {
            "profile": "Profil",
            "experience": "Expérience",
            "education": "Formation",
            "skills": "Compétences",
            "languages": "Langues",
            "contact": "Contact",
            "hobbies": "Loisirs",
        },
        "it": {
            "profile": "Profilo",
            "experience": "Esperienza",
            "education": "Formazione",
            "skills": "Competenze",
            "languages": "Lingue",
            "contact": "Contatto",
            "hobbies": "Hobby",
        },
    }
    return mapping.get((lang or "de").lower()[:2], mapping["de"])


def _save_portrait_temp(portrait_base64: str) -> Optional[str]:
    """Save portrait to temp file, return path or None."""
    if not portrait_base64:
        return None
    try:
        if "," in portrait_base64:
            portrait_base64 = portrait_base64.split(",")[1]
        img_data = base64.b64decode(portrait_base64)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(img_data)
            return tmp.name
    except:
        return None


def _cleanup_temp(path: Optional[str]):
    """Clean up temp file."""
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except:
            pass


class ThinDivider(Flowable):
    """A thin horizontal divider line."""
    def __init__(self, width, thickness=0.5, color=HexColor("#E5E7EB")):
        Flowable.__init__(self)
        self.width = width
        self.thickness = thickness
        self.color = color
        self.height = thickness + 6

    def draw(self):
        self.canv.setLineWidth(self.thickness)
        self.canv.setStrokeColor(self.color)
        self.canv.line(0, 3, self.width, 3)


class AccentBar(Flowable):
    """A colored accent bar for section headers."""
    def __init__(self, width, height=3, color=HexColor("#0050A4")):
        Flowable.__init__(self)
        self.width = width
        self.bar_height = height
        self.height = height + 2
        self.color = color

    def draw(self):
        self.canv.setFillColor(self.color)
        self.canv.rect(0, 0, self.width, self.bar_height, fill=1, stroke=0)


class TimelineDot(Flowable):
    """Timeline dot with connector."""
    def __init__(self, color=HexColor("#EC4899"), size=8, show_line=True):
        Flowable.__init__(self)
        self.color = color
        self.size = size
        self.show_line = show_line
        self.width = size + 4
        self.height = size + 2

    def draw(self):
        c = self.canv
        x = self.size / 2 + 2
        y = self.height / 2
        # Dot
        c.setFillColor(self.color)
        c.circle(x, y, self.size/2, fill=1, stroke=0)


# =============================================================================
# TEMPLATE 1: CLASSIC (Two-Column) - Table-based to keep columns together
# =============================================================================
def render_classic(cv_doc: Any, out_path: str):
    """Classic two-column layout with right sidebar using Table layout."""
    accent = "#0050A4"
    
    PAGE_WIDTH, PAGE_HEIGHT = A4
    MARGIN = 18 * mm
    RIGHT_COL_WIDTH = 56 * mm
    GUTTER = 6 * mm
    LEFT_COL_WIDTH = PAGE_WIDTH - 2 * MARGIN - RIGHT_COL_WIDTH - GUTTER
    
    base = getSampleStyleSheet()
    styles = {
        "name": ParagraphStyle("Name", parent=base["Heading1"], fontName=FONT_BOLD, 
                               fontSize=22, leading=26, textColor=HexColor(accent), spaceAfter=2),
        "title": ParagraphStyle("Title", parent=base["Normal"], fontName=FONT_REGULAR, 
                                fontSize=10, leading=13, textColor=HexColor("#555555"), spaceAfter=8),
        "h": ParagraphStyle("H", parent=base["Heading3"], fontName=FONT_BOLD, 
                            fontSize=10, leading=13, textColor=HexColor(accent), spaceBefore=8, spaceAfter=4),
        "h_right": ParagraphStyle("HR", parent=base["Heading3"], fontName=FONT_BOLD, 
                                  fontSize=9, leading=12, textColor=HexColor(accent), spaceBefore=6, spaceAfter=3),
        "normal": ParagraphStyle("Body", parent=base["Normal"], fontName=FONT_REGULAR, 
                                 fontSize=9, leading=12, textColor=HexColor("#333333"), spaceAfter=3),
        "small": ParagraphStyle("Small", parent=base["Normal"], fontName=FONT_REGULAR, 
                                fontSize=8, leading=10, textColor=HexColor("#777777")),
        "bullet": ParagraphStyle("Bullet", parent=base["Normal"], fontName=FONT_REGULAR, 
                                 fontSize=8, leading=11, leftIndent=6, textColor=HexColor("#444444"), spaceAfter=1),
        "bullet_small": ParagraphStyle("BulletS", parent=base["Normal"], fontName=FONT_REGULAR, 
                                       fontSize=8, leading=10, textColor=HexColor("#555555"), spaceAfter=1),
        "job_title": ParagraphStyle("JobTitle", parent=base["Normal"], fontName=FONT_BOLD, 
                                    fontSize=9, leading=12, textColor=HexColor("#222222"), spaceAfter=1),
        "company": ParagraphStyle("Company", parent=base["Normal"], fontName=FONT_REGULAR, 
                                  fontSize=8, leading=11, textColor=HexColor(accent), spaceAfter=3),
    }
    
    language = _get(cv_doc, "language") or "de"
    labels = _labels_for_lang(language)
    
    # Build LEFT column content
    left_content = []
    
    # Header
    name = _get(cv_doc, "full_name") or f"{_get(cv_doc, 'first_name')} {_get(cv_doc, 'last_name')}"
    left_content.append(Paragraph(name, styles["name"]))
    
    current_title = _get(cv_doc, "current_title")
    if current_title:
        left_content.append(Paragraph(current_title, styles["title"]))
    
    # Summary
    summary = _get(cv_doc, "summary")
    if summary:
        left_content.append(AccentBar(LEFT_COL_WIDTH * 0.2, 2, HexColor(accent)))
        left_content.append(Spacer(1, 4))
        left_content.append(Paragraph(labels["profile"], styles["h"]))
        left_content.append(Paragraph(summary, styles["normal"]))
        left_content.append(Spacer(1, 6))
    
    # Experience
    jobs = _get(cv_doc, "jobs") or []
    real_jobs = [j for j in jobs if not (isinstance(j, dict) and j.get("category") == "gap_filler")]
    
    if real_jobs:
        left_content.append(AccentBar(LEFT_COL_WIDTH * 0.2, 2, HexColor(accent)))
        left_content.append(Spacer(1, 4))
        left_content.append(Paragraph(labels["experience"], styles["h"]))
        
        for job in real_jobs:
            position = job.get("position", "") if isinstance(job, dict) else getattr(job, "position", "")
            company = job.get("company", "") if isinstance(job, dict) else getattr(job, "company", "")
            start = job.get("start_date", "") if isinstance(job, dict) else getattr(job, "start_date", "")
            end_raw = job.get("end_date") if isinstance(job, dict) else getattr(job, "end_date", None)
            end = _format_end_date(end_raw)
            resps = job.get("responsibilities", []) if isinstance(job, dict) else getattr(job, "responsibilities", [])
            
            left_content.append(Paragraph(position, styles["job_title"]))
            left_content.append(Paragraph(f"{company}  |  {start} – {end}", styles["company"]))
            
            for r in resps:
                left_content.append(Paragraph(f"• {r}", styles["bullet"]))
            
            left_content.append(Spacer(1, 6))
    
    # Education
    edu = _get(cv_doc, "education") or []
    if edu:
        left_content.append(AccentBar(LEFT_COL_WIDTH * 0.2, 2, HexColor(accent)))
        left_content.append(Spacer(1, 4))
        left_content.append(Paragraph(labels["education"], styles["h"]))
        
        for e in edu:
            degree = e.get("degree", "") if isinstance(e, dict) else getattr(e, "degree", "")
            inst = e.get("institution", "") if isinstance(e, dict) else getattr(e, "institution", "")
            sy = e.get("start_year", "") if isinstance(e, dict) else getattr(e, "start_year", "")
            ey = e.get("end_year", "") if isinstance(e, dict) else getattr(e, "end_year", "")
            
            left_content.append(Paragraph(degree, styles["job_title"]))
            left_content.append(Paragraph(f"{inst}  |  {sy} – {ey}", styles["company"]))
            left_content.append(Spacer(1, 4))
    
    # Build RIGHT column content
    right_content = []
    
    # Portrait
    temp_portrait = _save_portrait_temp(_get(cv_doc, "portrait_base64"))
    if temp_portrait:
        right_content.append(Image(temp_portrait, width=RIGHT_COL_WIDTH - 4, height=RIGHT_COL_WIDTH - 4))
        right_content.append(Spacer(1, 8))
    
    # Contact Card
    email = _get(cv_doc, "email")
    phone = _get(cv_doc, "phone")
    city = _get(cv_doc, "city")
    canton = _get(cv_doc, "canton")
    
    contact_rows = [[Paragraph(f"<b>{labels['contact']}</b>", 
                    ParagraphStyle("CH", parent=styles["h_right"], textColor=colors.white, spaceBefore=0, spaceAfter=0))]]
    if email:
        contact_rows.append([Paragraph(email, styles["small"])])
    if phone:
        contact_rows.append([Paragraph(phone, styles["small"])])
    if city or canton:
        loc = f"{city}, {canton}" if city and canton else city or canton
        contact_rows.append([Paragraph(loc, styles["small"])])
    
    contact_tbl = Table(contact_rows, colWidths=[RIGHT_COL_WIDTH - 4])
    contact_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(accent)),
        ("BACKGROUND", (0, 1), (-1, -1), HexColor("#E8F0F8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    right_content.append(contact_tbl)
    right_content.append(Spacer(1, 10))
    
    # Skills
    skills = _get(cv_doc, "skills") or {}
    all_skills = []
    if isinstance(skills, dict):
        for cat, lst in skills.items():
            if isinstance(lst, list) and cat != "languages":
                all_skills.extend(lst[:2])
    
    if all_skills:
        right_content.append(Paragraph(labels["skills"], styles["h_right"]))
        for s in all_skills[:6]:
            right_content.append(Paragraph(f"• {s}", styles["bullet_small"]))
        right_content.append(Spacer(1, 8))
    
    # Languages
    if isinstance(skills, dict) and "languages" in skills:
        right_content.append(Paragraph(labels["languages"], styles["h_right"]))
        for lang in skills["languages"][:3]:
            right_content.append(Paragraph(f"• {lang}", styles["bullet_small"]))
        right_content.append(Spacer(1, 8))
    
    # Hobbies
    hobbies = _get(cv_doc, "hobbies") or []
    if hobbies:
        right_content.append(Paragraph(labels["hobbies"], styles["h_right"]))
        right_content.append(Paragraph(", ".join(hobbies[:4]), styles["small"]))
    
    # Create main two-column table
    main_table = Table(
        [[left_content, right_content]],
        colWidths=[LEFT_COL_WIDTH, RIGHT_COL_WIDTH]
    )
    main_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), GUTTER),
        ("LEFTPADDING", (1, 0), (1, -1), 0),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    
    # Build document
    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, 
                           topMargin=MARGIN, bottomMargin=MARGIN)
    doc.build([main_table])
    _cleanup_temp(temp_portrait)


# =============================================================================
# TEMPLATE 2: MODERN (Dark Sidebar)
# =============================================================================
def render_modern(cv_doc: Any, out_path: str):
    """Modern design with dark left sidebar."""
    accent = "#10B981"
    sidebar_bg = "#1F2937"
    
    PAGE_WIDTH, PAGE_HEIGHT = A4
    SIDEBAR_WIDTH = 68 * mm
    CONTENT_WIDTH = PAGE_WIDTH - SIDEBAR_WIDTH
    MARGIN = 12 * mm
    
    base = getSampleStyleSheet()
    styles = {
        # Sidebar styles (white text)
        "name_w": ParagraphStyle("NameW", parent=base["Heading1"], fontName=FONT_BOLD, 
                                 fontSize=20, leading=24, textColor=colors.white, spaceAfter=4),
        "title_w": ParagraphStyle("TitleW", parent=base["Normal"], fontName=FONT_REGULAR, 
                                  fontSize=10, leading=13, textColor=HexColor("#9CA3AF"), spaceAfter=16),
        "h_w": ParagraphStyle("HW", parent=base["Heading3"], fontName=FONT_BOLD, 
                              fontSize=10, leading=13, textColor=HexColor(accent), spaceBefore=16, spaceAfter=8),
        "normal_w": ParagraphStyle("BodyW", parent=base["Normal"], fontName=FONT_REGULAR, 
                                   fontSize=9, leading=12, textColor=colors.white, spaceAfter=3),
        "bullet_w": ParagraphStyle("BulletW", parent=base["Normal"], fontName=FONT_REGULAR, 
                                   fontSize=8, leading=11, textColor=HexColor("#D1D5DB"), leftIndent=6, spaceAfter=2),
        # Content styles
        "h": ParagraphStyle("H", parent=base["Heading3"], fontName=FONT_BOLD, 
                            fontSize=12, leading=15, textColor=HexColor("#1F2937"), spaceBefore=16, spaceAfter=10),
        "normal": ParagraphStyle("Body", parent=base["Normal"], fontName=FONT_REGULAR, 
                                 fontSize=10, leading=14, textColor=HexColor("#374151"), spaceAfter=4),
        "bullet": ParagraphStyle("Bullet", parent=base["Normal"], fontName=FONT_REGULAR, 
                                 fontSize=9, leading=12, leftIndent=8, textColor=HexColor("#4B5563"), spaceAfter=2),
        "job_title": ParagraphStyle("JobTitle", parent=base["Normal"], fontName=FONT_BOLD, 
                                    fontSize=10, leading=13, textColor=HexColor("#1F2937"), spaceAfter=1),
        "company": ParagraphStyle("Company", parent=base["Normal"], fontName=FONT_REGULAR, 
                                  fontSize=9, leading=12, textColor=HexColor(accent), spaceAfter=4),
    }
    
    def draw_sidebar(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor(sidebar_bg))
        canvas.rect(0, 0, SIDEBAR_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
        canvas.restoreState()
    
    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=0, rightMargin=0, 
                           topMargin=MARGIN, bottomMargin=MARGIN)
    
    sidebar_frame = Frame(MARGIN, MARGIN, SIDEBAR_WIDTH - 2*MARGIN, PAGE_HEIGHT - 2*MARGIN, id="sidebar")
    content_frame = Frame(SIDEBAR_WIDTH + MARGIN, MARGIN, CONTENT_WIDTH - 2*MARGIN, 
                         PAGE_HEIGHT - 2*MARGIN, id="content")
    
    doc.addPageTemplates([PageTemplate(id="Modern", frames=[sidebar_frame, content_frame], onPage=draw_sidebar)])
    
    flow = []
    language = _get(cv_doc, "language") or "de"
    labels = _labels_for_lang(language)
    
    # === SIDEBAR ===
    # Portrait
    temp_portrait = _save_portrait_temp(_get(cv_doc, "portrait_base64"))
    if temp_portrait:
        flow.append(Image(temp_portrait, width=SIDEBAR_WIDTH - 3*MARGIN, height=SIDEBAR_WIDTH - 3*MARGIN))
        flow.append(Spacer(1, 12))
    
    # Name
    name = _get(cv_doc, "full_name") or f"{_get(cv_doc, 'first_name')} {_get(cv_doc, 'last_name')}"
    flow.append(Paragraph(name, styles["name_w"]))
    
    current_title = _get(cv_doc, "current_title")
    if current_title:
        flow.append(Paragraph(current_title, styles["title_w"]))
    
    # Contact
    flow.append(Paragraph(labels["contact"], styles["h_w"]))
    email = _get(cv_doc, "email")
    phone = _get(cv_doc, "phone")
    city = _get(cv_doc, "city")
    canton = _get(cv_doc, "canton")
    
    if email:
        flow.append(Paragraph(email, styles["normal_w"]))
    if phone:
        flow.append(Paragraph(phone, styles["normal_w"]))
    if city or canton:
        loc = f"{city}, {canton}" if city and canton else city or canton
        flow.append(Paragraph(loc, styles["normal_w"]))
    
    # Skills
    skills = _get(cv_doc, "skills") or {}
    all_skills = []
    if isinstance(skills, dict):
        for cat, lst in skills.items():
            if isinstance(lst, list) and cat != "languages":
                all_skills.extend(lst[:3])
    
    if all_skills:
        flow.append(Paragraph(labels["skills"], styles["h_w"]))
        for s in all_skills[:6]:
            flow.append(Paragraph(f"• {s}", styles["bullet_w"]))
    
    # Languages
    if isinstance(skills, dict) and "languages" in skills:
        flow.append(Paragraph(labels["languages"], styles["h_w"]))
        for lang in skills["languages"][:3]:
            flow.append(Paragraph(f"• {lang}", styles["bullet_w"]))
    
    # Hobbies
    hobbies = _get(cv_doc, "hobbies") or []
    if hobbies:
        flow.append(Paragraph(labels["hobbies"], styles["h_w"]))
        flow.append(Paragraph(", ".join(hobbies[:4]), styles["normal_w"]))
    
    # === CONTENT ===
    flow.append(FrameBreak())
    
    # Summary
    summary = _get(cv_doc, "summary")
    if summary:
        flow.append(Paragraph(labels["profile"], styles["h"]))
        flow.append(Paragraph(summary, styles["normal"]))
    
    # Experience
    jobs = _get(cv_doc, "jobs") or []
    if jobs:
        flow.append(Paragraph(labels["experience"], styles["h"]))
        
        for job in jobs:
            if isinstance(job, dict) and job.get("category") == "gap_filler":
                continue
            
            position = job.get("position", "") if isinstance(job, dict) else getattr(job, "position", "")
            company = job.get("company", "") if isinstance(job, dict) else getattr(job, "company", "")
            start = job.get("start_date", "") if isinstance(job, dict) else getattr(job, "start_date", "")
            end_raw = job.get("end_date") if isinstance(job, dict) else getattr(job, "end_date", None)
            end = _format_end_date(end_raw)
            resps = job.get("responsibilities", []) if isinstance(job, dict) else getattr(job, "responsibilities", [])
            
            flow.append(Paragraph(position, styles["job_title"]))
            flow.append(Paragraph(f"{company}  |  {start} – {end}", styles["company"]))
            
            for r in resps[:3]:
                flow.append(Paragraph(f"• {r}", styles["bullet"]))
            
            flow.append(Spacer(1, 10))
    
    # Education
    edu = _get(cv_doc, "education") or []
    if edu:
        flow.append(Paragraph(labels["education"], styles["h"]))
        
        for e in edu:
            degree = e.get("degree", "") if isinstance(e, dict) else getattr(e, "degree", "")
            inst = e.get("institution", "") if isinstance(e, dict) else getattr(e, "institution", "")
            
            flow.append(Paragraph(f"{degree} — {inst}", styles["normal"]))
            flow.append(Spacer(1, 4))
    
    doc.build(flow)
    _cleanup_temp(temp_portrait)


# =============================================================================
# TEMPLATE 3: MINIMAL (Single Column)
# =============================================================================
def render_minimal(cv_doc: Any, out_path: str):
    """Clean minimal single-column layout."""
    accent = "#6366F1"
    
    PAGE_WIDTH, PAGE_HEIGHT = A4
    MARGIN = 25 * mm
    CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
    
    base = getSampleStyleSheet()
    styles = {
        "name": ParagraphStyle("Name", parent=base["Heading1"], fontName=FONT_BOLD, 
                               fontSize=26, leading=30, textColor=HexColor("#111827"), spaceAfter=2),
        "title": ParagraphStyle("Title", parent=base["Normal"], fontName=FONT_REGULAR, 
                                fontSize=12, leading=15, textColor=HexColor(accent), spaceAfter=6),
        "contact": ParagraphStyle("Contact", parent=base["Normal"], fontName=FONT_REGULAR, 
                                  fontSize=9, leading=12, textColor=HexColor("#6B7280"), spaceAfter=16),
        "h": ParagraphStyle("H", parent=base["Heading3"], fontName=FONT_BOLD, 
                            fontSize=10, leading=13, textColor=HexColor("#111827"), 
                            spaceBefore=18, spaceAfter=10),
        "normal": ParagraphStyle("Body", parent=base["Normal"], fontName=FONT_REGULAR, 
                                 fontSize=10, leading=14, textColor=HexColor("#374151"), spaceAfter=4),
        "bullet": ParagraphStyle("Bullet", parent=base["Normal"], fontName=FONT_REGULAR, 
                                 fontSize=9, leading=13, leftIndent=10, textColor=HexColor("#4B5563"), spaceAfter=2),
        "job_header": ParagraphStyle("JobH", parent=base["Normal"], fontName=FONT_BOLD, 
                                     fontSize=10, leading=13, textColor=HexColor("#111827"), spaceAfter=1),
        "job_meta": ParagraphStyle("JobM", parent=base["Normal"], fontName=FONT_REGULAR, 
                                   fontSize=9, leading=12, textColor=HexColor(accent), spaceAfter=4),
    }
    
    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, 
                           topMargin=MARGIN, bottomMargin=MARGIN)
    flow = []
    language = _get(cv_doc, "language") or "de"
    labels = _labels_for_lang(language)
    
    # Header
    name = _get(cv_doc, "full_name") or f"{_get(cv_doc, 'first_name')} {_get(cv_doc, 'last_name')}"
    temp_portrait = _save_portrait_temp(_get(cv_doc, "portrait_base64"))
    
    if temp_portrait:
        # Header with portrait on right
        title_content = [Paragraph(name, styles["name"])]
        current_title = _get(cv_doc, "current_title")
        if current_title:
            title_content.append(Paragraph(current_title, styles["title"]))
        
        email = _get(cv_doc, "email")
        phone = _get(cv_doc, "phone")
        city = _get(cv_doc, "city")
        canton = _get(cv_doc, "canton")
        contact_parts = [x for x in [email, phone, f"{city}, {canton}" if city else canton] if x]
        title_content.append(Paragraph(" • ".join(contact_parts), styles["contact"]))
        
        header_data = [[title_content, Image(temp_portrait, width=32*mm, height=32*mm)]]
        header = Table(header_data, colWidths=[CONTENT_WIDTH - 38*mm, 38*mm])
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        flow.append(header)
    else:
        flow.append(Paragraph(name, styles["name"]))
        current_title = _get(cv_doc, "current_title")
        if current_title:
            flow.append(Paragraph(current_title, styles["title"]))
        
        email = _get(cv_doc, "email")
        phone = _get(cv_doc, "phone")
        city = _get(cv_doc, "city")
        canton = _get(cv_doc, "canton")
        contact_parts = [x for x in [email, phone, f"{city}, {canton}" if city else canton] if x]
        flow.append(Paragraph(" • ".join(contact_parts), styles["contact"]))
    
    flow.append(ThinDivider(CONTENT_WIDTH, 1, HexColor("#E5E7EB")))
    
    # Summary
    summary = _get(cv_doc, "summary")
    if summary:
        flow.append(Paragraph(labels["profile"].upper(), styles["h"]))
        flow.append(Paragraph(summary, styles["normal"]))
    
    # Experience
    jobs = _get(cv_doc, "jobs") or []
    if jobs:
        flow.append(Paragraph(labels["experience"].upper(), styles["h"]))
        
        for job in jobs:
            if isinstance(job, dict) and job.get("category") == "gap_filler":
                continue
            
            position = job.get("position", "") if isinstance(job, dict) else getattr(job, "position", "")
            company = job.get("company", "") if isinstance(job, dict) else getattr(job, "company", "")
            start = job.get("start_date", "") if isinstance(job, dict) else getattr(job, "start_date", "")
            end_raw = job.get("end_date") if isinstance(job, dict) else getattr(job, "end_date", None)
            end = _format_end_date(end_raw)
            resps = job.get("responsibilities", []) if isinstance(job, dict) else getattr(job, "responsibilities", [])
            
            flow.append(Paragraph(f"{position} — {company}", styles["job_header"]))
            flow.append(Paragraph(f"{start} – {end}", styles["job_meta"]))
            
            for r in resps[:4]:
                flow.append(Paragraph(f"→ {r}", styles["bullet"]))
            
            flow.append(Spacer(1, 10))
    
    # Education
    edu = _get(cv_doc, "education") or []
    if edu:
        flow.append(Paragraph(labels["education"].upper(), styles["h"]))
        
        for e in edu:
            degree = e.get("degree", "") if isinstance(e, dict) else getattr(e, "degree", "")
            inst = e.get("institution", "") if isinstance(e, dict) else getattr(e, "institution", "")
            sy = e.get("start_year", "") if isinstance(e, dict) else getattr(e, "start_year", "")
            ey = e.get("end_year", "") if isinstance(e, dict) else getattr(e, "end_year", "")
            
            flow.append(Paragraph(f"{degree} — {inst}", styles["job_header"]))
            flow.append(Paragraph(f"{sy} – {ey}", styles["job_meta"]))
            flow.append(Spacer(1, 6))
    
    # Skills
    skills = _get(cv_doc, "skills") or {}
    all_skills = []
    if isinstance(skills, dict):
        for cat, lst in skills.items():
            if isinstance(lst, list):
                all_skills.extend(lst[:4])
    
    if all_skills:
        flow.append(Paragraph(labels["skills"].upper(), styles["h"]))
        # Two columns
        mid = (len(all_skills) + 1) // 2
        left = all_skills[:mid]
        right = all_skills[mid:]
        skill_data = []
        for i in range(max(len(left), len(right))):
            l = left[i] if i < len(left) else ""
            r = right[i] if i < len(right) else ""
            skill_data.append([Paragraph(l, styles["normal"]), Paragraph(r, styles["normal"])])
        skill_table = Table(skill_data, colWidths=[CONTENT_WIDTH/2, CONTENT_WIDTH/2])
        flow.append(skill_table)
    
    doc.build(flow)
    _cleanup_temp(temp_portrait)


# =============================================================================
# TEMPLATE 4: TIMELINE
# =============================================================================
def render_timeline(cv_doc: Any, out_path: str):
    """Visual timeline for career progression."""
    accent = "#EC4899"
    
    PAGE_WIDTH, PAGE_HEIGHT = A4
    MARGIN = 20 * mm
    CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
    DATE_COL = 28 * mm
    
    base = getSampleStyleSheet()
    styles = {
        "name": ParagraphStyle("Name", parent=base["Heading1"], fontName=FONT_BOLD, 
                               fontSize=24, leading=28, textColor=HexColor(accent), spaceAfter=2),
        "title": ParagraphStyle("Title", parent=base["Normal"], fontName=FONT_REGULAR, 
                                fontSize=11, leading=14, textColor=HexColor("#6B7280"), spaceAfter=6),
        "contact": ParagraphStyle("Contact", parent=base["Normal"], fontName=FONT_REGULAR, 
                                  fontSize=9, leading=12, textColor=HexColor("#9CA3AF"), spaceAfter=14),
        "h": ParagraphStyle("H", parent=base["Heading3"], fontName=FONT_BOLD, 
                            fontSize=12, leading=15, textColor=HexColor(accent), spaceBefore=16, spaceAfter=10),
        "normal": ParagraphStyle("Body", parent=base["Normal"], fontName=FONT_REGULAR, 
                                 fontSize=10, leading=14, textColor=HexColor("#374151"), spaceAfter=4),
        "bullet": ParagraphStyle("Bullet", parent=base["Normal"], fontName=FONT_REGULAR, 
                                 fontSize=9, leading=12, textColor=HexColor("#4B5563"), spaceAfter=2),
        "date": ParagraphStyle("Date", parent=base["Normal"], fontName=FONT_BOLD, 
                               fontSize=8, leading=10, textColor=HexColor(accent)),
        "job_title": ParagraphStyle("JobTitle", parent=base["Normal"], fontName=FONT_BOLD, 
                                    fontSize=10, leading=13, textColor=HexColor("#1F2937"), spaceAfter=1),
        "company": ParagraphStyle("Company", parent=base["Normal"], fontName=FONT_REGULAR, 
                                  fontSize=9, leading=12, textColor=HexColor("#6B7280"), spaceAfter=4),
    }
    
    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, 
                           topMargin=MARGIN, bottomMargin=MARGIN)
    flow = []
    language = _get(cv_doc, "language") or "de"
    labels = _labels_for_lang(language)
    
    # Header
    temp_portrait = _save_portrait_temp(_get(cv_doc, "portrait_base64"))
    name = _get(cv_doc, "full_name") or f"{_get(cv_doc, 'first_name')} {_get(cv_doc, 'last_name')}"
    
    if temp_portrait:
        title_content = [Paragraph(name, styles["name"])]
        current_title = _get(cv_doc, "current_title")
        if current_title:
            title_content.append(Paragraph(current_title, styles["title"]))
        
        email = _get(cv_doc, "email")
        phone = _get(cv_doc, "phone")
        title_content.append(Paragraph(f"{email} • {phone}", styles["contact"]))
        
        header_data = [[Image(temp_portrait, width=28*mm, height=28*mm), title_content]]
        header = Table(header_data, colWidths=[32*mm, CONTENT_WIDTH - 32*mm])
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        flow.append(header)
    else:
        flow.append(Paragraph(name, styles["name"]))
        current_title = _get(cv_doc, "current_title")
        if current_title:
            flow.append(Paragraph(current_title, styles["title"]))
        email = _get(cv_doc, "email")
        phone = _get(cv_doc, "phone")
        flow.append(Paragraph(f"{email} • {phone}", styles["contact"]))
    
    # Summary
    summary = _get(cv_doc, "summary")
    if summary:
        flow.append(Paragraph(labels["profile"], styles["h"]))
        flow.append(Paragraph(summary, styles["normal"]))
    
    # Experience with timeline
    jobs = _get(cv_doc, "jobs") or []
    if jobs:
        flow.append(Paragraph(labels["experience"], styles["h"]))
        
        for job in jobs:
            if isinstance(job, dict) and job.get("category") == "gap_filler":
                continue
            
            position = job.get("position", "") if isinstance(job, dict) else getattr(job, "position", "")
            company = job.get("company", "") if isinstance(job, dict) else getattr(job, "company", "")
            start = job.get("start_date", "") if isinstance(job, dict) else getattr(job, "start_date", "")
            end_raw = job.get("end_date") if isinstance(job, dict) else getattr(job, "end_date", None)
            end = _format_end_date(end_raw)
            resps = job.get("responsibilities", []) if isinstance(job, dict) else getattr(job, "responsibilities", [])
            
            # Build job content
            job_content = [
                Paragraph(position, styles["job_title"]),
                Paragraph(company, styles["company"])
            ]
            for r in resps[:3]:
                job_content.append(Paragraph(f"• {r}", styles["bullet"]))
            
            # Timeline row: [dot + date | job content]
            date_content = [
                TimelineDot(HexColor(accent), 8),
                Spacer(1, 4),
                Paragraph(start, styles["date"]),
                Paragraph(f"– {end}", styles["date"])
            ]
            
            timeline_data = [[date_content, job_content]]
            timeline_row = Table(timeline_data, colWidths=[DATE_COL, CONTENT_WIDTH - DATE_COL])
            timeline_row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            flow.append(timeline_row)
            flow.append(Spacer(1, 12))
    
    # Education
    edu = _get(cv_doc, "education") or []
    if edu:
        flow.append(Paragraph(labels["education"], styles["h"]))
        
        for e in edu:
            degree = e.get("degree", "") if isinstance(e, dict) else getattr(e, "degree", "")
            inst = e.get("institution", "") if isinstance(e, dict) else getattr(e, "institution", "")
            
            flow.append(Paragraph(f"{degree} — {inst}", styles["normal"]))
            flow.append(Spacer(1, 4))
    
    # Skills
    skills = _get(cv_doc, "skills") or {}
    all_skills = []
    if isinstance(skills, dict):
        for cat, lst in skills.items():
            if isinstance(lst, list):
                all_skills.extend(lst[:3])
    
    if all_skills:
        flow.append(Paragraph(labels["skills"], styles["h"]))
        flow.append(Paragraph(" • ".join(all_skills[:10]), styles["normal"]))
    
    doc.build(flow)
    _cleanup_temp(temp_portrait)


# =============================================================================
# MAIN RENDER FUNCTION
# =============================================================================
RENDER_FUNCTIONS = {
    "classic": render_classic,
    "modern": render_modern,
    "minimal": render_minimal,
    "timeline": render_timeline,
}


def render_cv_with_template(cv_doc: Any, out_path: str, template_name: str = "classic"):
    """
    Render CV with specified template.
    
    Args:
        cv_doc: CVDocument object
        out_path: Output file path
        template_name: Template name or "random"
    """
    if template_name == "random":
        template_name = random.choice(list(RENDER_FUNCTIONS.keys()))
    
    render_func = RENDER_FUNCTIONS.get(template_name, render_classic)
    render_func(cv_doc, out_path)


def get_available_templates() -> Dict[str, str]:
    """Get list of available templates with descriptions."""
    return {key: val["name"] for key, val in TEMPLATES.items()}


def get_random_template() -> str:
    """Get a random template name."""
    return random.choice(list(TEMPLATES.keys()))
