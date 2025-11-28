"""
CV Assembler - Complete CV Document Generator.

This module assembles all CV components into a complete document:
- Personal information
- Portrait
- Summary (AI-generated)
- Education history
- Job history
- Skills
- Additional education
- Languages
- Hobbies

Run: Used by persona generation pipeline
"""
import sys
import random
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from PIL import Image
import io
import base64

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.queries import (
    get_occupation_by_id,
    get_canton_by_code,
    sample_portrait_path,
    get_skills_by_occupation
)
from src.generation.cv_education_generator import generate_education_history
from src.generation.cv_job_history_generator import generate_job_history
from src.generation.cv_continuing_education import generate_additional_education
from src.generation.cv_activities_transformer import generate_responsibilities_from_activities
from src.config import get_settings

settings = get_settings()

# OpenAI client setup
OPENAI_AVAILABLE = False
_openai_client = None

try:
    try:
        from openai import OpenAI
        if settings.openai_api_key:
            _openai_client = OpenAI(api_key=settings.openai_api_key)
            OPENAI_AVAILABLE = True
    except ImportError:
        try:
            import openai
            if settings.openai_api_key:
                openai.api_key = settings.openai_api_key
            OPENAI_AVAILABLE = True
        except ImportError:
            pass
except Exception:
    pass


@dataclass
class CVDocument:
    """Complete CV document structure."""
    # Personal
    first_name: str
    last_name: str
    full_name: str
    age: int
    gender: str
    canton: str
    city: Optional[str] = None
    email: str = ""
    phone: str = ""
    address: Optional[str] = None
    portrait_path: Optional[str] = None
    portrait_base64: Optional[str] = None
    
    # Professional
    current_title: str = ""
    industry: str = ""
    career_level: str = ""
    years_experience: int = 0
    
    # Content
    summary: str = ""
    education: List[Dict[str, Any]] = field(default_factory=list)
    jobs: List[Dict[str, Any]] = field(default_factory=list)
    skills: Dict[str, List[str]] = field(default_factory=dict)  # {"technical": [...], "soft": [...], "languages": [...]}
    additional_education: List[Dict[str, Any]] = field(default_factory=list)
    hobbies: List[str] = field(default_factory=list)
    
    # Metadata
    language: str = "de"
    created_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template rendering."""
        return {
            "personal": {
                "first_name": self.first_name,
                "last_name": self.last_name,
                "full_name": self.full_name,
                "age": self.age,
                "gender": self.gender,
                "canton": self.canton,
                "city": self.city,
                "email": self.email,
                "phone": self.phone,
                "address": self.address,
                "portrait_path": self.portrait_path,
                "portrait_base64": self.portrait_base64
            },
            "professional": {
                "current_title": self.current_title,
                "industry": self.industry,
                "career_level": self.career_level,
                "years_experience": self.years_experience
            },
            "content": {
                "summary": self.summary,
                "education": self.education,
                "jobs": self.jobs,
                "skills": self.skills,
                "additional_education": self.additional_education,
                "hobbies": self.hobbies
            },
            "metadata": {
                "language": self.language,
                "created_at": self.created_at
            }
        }


def load_portrait_image(portrait_path: Optional[str], resize: Tuple[int, int] = (150, 150), circular: bool = False) -> Optional[str]:
    """
    Load and process portrait image.
    
    Args:
        portrait_path: Relative path to portrait image.
        resize: Target size (width, height).
        circular: Whether to apply circular crop.
    
    Returns:
        Base64-encoded image string or None.
    """
    if not portrait_path:
        return None
    
    full_path = project_root / "data" / "portraits" / portrait_path
    
    if not full_path.exists():
        return None
    
    try:
        from PIL import Image
        
        # Load image
        img = Image.open(full_path)
        
        # Convert to RGB if necessary
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        # Resize
        img = img.resize(resize, Image.Resampling.LANCZOS)
        
        # Circular crop if requested
        if circular:
            # Create circular mask
            mask = Image.new("L", resize, 0)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(mask)
            draw.ellipse([0, 0, resize[0], resize[1]], fill=255)
            
            # Apply mask
            output = Image.new("RGB", resize, (255, 255, 255))
            output.paste(img, (0, 0), mask)
            img = output
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        return f"data:image/png;base64,{img_base64}"
        
    except Exception as e:
        print(f"Warning: Could not load portrait: {e}")
        return None


def get_age_group(age: int) -> str:
    """Get age group from age."""
    if 18 <= age <= 25:
        return "18-25"
    elif 26 <= age <= 40:
        return "26-40"
    elif 41 <= age <= 65:
        return "41-65"
    else:
        return "other"


def validate_persona_before_assembly(
    persona: Dict[str, Any],
    occupation_doc: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Validate persona before CV assembly.
    
    Args:
        persona: Persona dictionary.
        occupation_doc: Occupation document.
    
    Returns:
        Tuple of (is_valid, fixed_persona, issues).
    """
    issues = []
    fixed_persona = persona.copy()
    
    # 1. Check portrait_path matches age_group
    age = persona.get("age", 25)
    age_group = get_age_group(age)
    gender = persona.get("gender", "male")
    portrait_path = persona.get("portrait_path", "")
    
    if portrait_path:
        # Extract age group from path (e.g., "male/26-40/image.png")
        path_parts = portrait_path.split("/")
        if len(path_parts) >= 2:
            path_age_group = path_parts[1]
            if path_age_group != age_group:
                # Resample portrait from correct age+gender folder
                from src.database.queries import sample_portrait_path
                new_portrait = sample_portrait_path(gender, age_group)
                if new_portrait:
                    fixed_persona["portrait_path"] = new_portrait
                    issues.append(f"Portrait age mismatch: resampled from {age_group}")
                else:
                    issues.append(f"Warning: No portrait available for {gender}/{age_group}")
    
    # 2. Check timeline consistency
    years_experience = persona.get("years_experience", 0)
    education_years = 3  # Approximate
    work_years = years_experience
    
    # Calculate expected total
    expected_total = age - 15
    actual_total = education_years + work_years
    
    discrepancy = abs(actual_total - expected_total)
    if discrepancy > 3:
        issues.append(f"Timeline discrepancy: {discrepancy} years")
        # Try to fix by adjusting years_experience
        if actual_total < expected_total:
            # Increase experience
            fixed_persona["years_experience"] = min(years_experience + discrepancy - 1, age - 18)
        elif actual_total > expected_total:
            # Decrease experience
            fixed_persona["years_experience"] = max(years_experience - discrepancy + 1, 0)
    
    # 3. Validate company-occupation match
    if occupation_doc:
        # Try to get industry from occupation
        categories = occupation_doc.get("categories", {})
        berufsfelder = categories.get("berufsfelder", [])
        
        # Check if persona's companies match industry
        # This is handled in job_history_generator, but we can pre-validate here
        persona_industry = persona.get("industry", "other")
        # Industry matching is complex, so we'll just log a warning if needed
        if not berufsfelder:
            issues.append("Warning: No berufsfelder in occupation document")
    
    is_valid = len([i for i in issues if i.startswith("Error")]) == 0
    
    return is_valid, fixed_persona, issues


def generate_personal_info(
    persona: Dict[str, Any],
    canton: str
) -> Dict[str, str]:
    """
    Generate personalized personal information (email, phone, location).
    
    Args:
        persona: Persona dictionary.
        canton: Canton code.
    
    Returns:
        Dictionary with email, phone, city, address.
    """
    first_name = persona.get("first_name", "").lower()
    last_name = persona.get("last_name", "").lower()
    age = persona.get("age", 25)
    age_group = get_age_group(age)
    
    # Normalize umlauts for email
    def normalize_umlauts(text: str) -> str:
        replacements = {
            "ä": "ae", "ö": "oe", "ü": "ue",
            "à": "a", "è": "e", "é": "e", "ì": "i", "ò": "o", "ù": "u"
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
    
    first_name_clean = normalize_umlauts(first_name)
    last_name_clean = normalize_umlauts(last_name)
    first_initial = first_name_clean[0] if first_name_clean else "x"
    
    # Email generation by age group
    if age_group == "18-25":
        if random.random() < 0.7:
            email = f"{first_name_clean}.{last_name_clean}@gmail.com"
        else:
            email = f"{first_initial}.{last_name_clean}@protonmail.com"
    elif age_group == "26-40":
        if random.random() < 0.4:
            email = f"{first_initial}.{last_name_clean}@bluewin.ch"
        else:
            email = f"{first_name_clean}.{last_name_clean}@gmail.com"
    else:  # 41-65
        if random.random() < 0.6:
            email = f"{first_name_clean}.{last_name_clean}@bluewin.ch"
        else:
            email = f"{first_initial}.{last_name_clean}@sunrise.ch"
    
    # Phone: Swiss mobile 07X XXX XX XX
    if age_group == "18-25":
        prefix = random.choice(["076", "078"])
    elif age_group == "26-40":
        prefix = random.choice(["076", "078", "079"])
    else:  # 41-65
        prefix = random.choice(["079", "077"])
    
    # Generate 7 random digits
    digits = "".join([str(random.randint(0, 9)) for _ in range(7)])
    phone = f"{prefix} {digits[:3]} {digits[3:5]} {digits[5:]}"
    
    # Location: canton.major_city + canton.code
    canton_doc = get_canton_by_code(canton)
    if canton_doc:
        major_city = canton_doc.get("major_city", generate_city_for_canton(canton))
    else:
        major_city = generate_city_for_canton(canton)
    
    address = f"{major_city}, {canton}"
    
    return {
        "email": email,
        "phone": phone,
        "city": major_city,
        "address": address
    }


def generate_personalized_languages(
    canton: str,
    primary_language: str,
    age: int
) -> List[str]:
    """
    Generate personalized languages based on canton and age.
    
    Args:
        canton: Canton code.
        primary_language: Primary language (de, fr, it).
        age: Persona age.
    
    Returns:
        List of language strings with proficiency levels.
    """
    languages = []
    age_group = get_age_group(age)
    
    lang_names = {
        "de": "Deutsch",
        "fr": "Französisch",
        "it": "Italienisch",
        "en": "Englisch",
        "es": "Spanisch",
        "pt": "Portugiesisch"
    }
    
    # Get canton language distribution
    canton_doc = get_canton_by_code(canton)
    if canton_doc:
        lang_de = canton_doc.get("language_de", 0)
        lang_fr = canton_doc.get("language_fr", 0)
        lang_it = canton_doc.get("language_it", 0)
        
        # Primary language (Muttersprache if >70%)
        primary_pct = {
            "de": lang_de,
            "fr": lang_fr,
            "it": lang_it
        }.get(primary_language, 100)
        
        if primary_pct > 70:
            languages.append(f"{lang_names.get(primary_language, primary_language)} (Muttersprache)")
        else:
            languages.append(f"{lang_names.get(primary_language, primary_language)} (Fließend)")
        
        # Add secondary Swiss languages
        if primary_language == "de":
            # Deutschschweiz: +Französisch
            if lang_fr > 10:
                proficiency = random.choice(["Gut", "Grundkenntnisse"])
                languages.append(f"Französisch ({proficiency})")
        elif primary_language == "fr":
            # Romandie: +Deutsch
            if lang_de > 10:
                proficiency = random.choice(["Gut", "Fließend"])
                languages.append(f"Deutsch ({proficiency})")
        elif primary_language == "it":
            # Ticino: +Deutsch, maybe +Französisch
            if lang_de > 10:
                proficiency = random.choice(["Gut", "Fließend"])
                languages.append(f"Deutsch ({proficiency})")
            if lang_fr > 5 and random.random() < 0.5:
                proficiency = random.choice(["Gut", "Grundkenntnisse"])
                languages.append(f"Französisch ({proficiency})")
    else:
        # Fallback
        languages.append(f"{lang_names.get(primary_language, primary_language)} (Muttersprache)")
    
    # English proficiency by age
    if age_group == "18-25":
        if random.random() < 0.8:
            languages.append("Englisch (Fließend)")
        else:
            languages.append("Englisch (Gut)")
    elif age_group == "26-40":
        if random.random() < 0.6:
            proficiency = random.choice(["Fließend", "Gut"])
            languages.append(f"Englisch ({proficiency})")
        else:
            languages.append("Englisch (Grundkenntnisse)")
    else:  # 41-65
        if random.random() < 0.4:
            proficiency = random.choice(["Gut", "Grundkenntnisse"])
            languages.append(f"Englisch ({proficiency})")
    
    # Rare 4th language for 20%
    if random.random() < 0.2:
        fourth_lang = random.choice(["Spanisch", "Italienisch", "Portugiesisch"])
        proficiency = random.choice(["Grundkenntnisse", "Gut"])
        languages.append(f"{fourth_lang} ({proficiency})")
    
    return languages


def generate_personalized_hobbies(
    canton: str,
    language: str,
    age_group: str,
    occupation_type: str = "general"
) -> List[str]:
    """
    Generate personalized hobbies based on region, age, and occupation.
    
    Args:
        canton: Canton code.
        language: Language (de, fr, it).
        age_group: Age group (18-25, 26-40, 41-65).
        occupation_type: Occupation type (technical, creative, social, general).
    
    Returns:
        List of hobby strings (4-6 items).
    """
    hobbies = []
    
    # Regional base hobbies
    regional_hobbies = {
        "de": ["Wandern", "Skifahren", "Jodeln", "Alphornblasen", "Schwingen"],
        "fr": ["Wandern", "Skifahren", "Weinverkostung", "Segeln"],
        "it": ["Wandern", "Skifahren", "Grotto-Besuche", "Mountainbiking"]
    }
    
    # Add 2 common regional hobbies
    lang_hobbies = regional_hobbies.get(language, regional_hobbies["de"])
    hobbies.extend(random.sample(lang_hobbies, min(2, len(lang_hobbies))))
    
    # Age-specific hobbies
    age_hobbies = {
        "18-25": ["Gaming", "Fitness", "Reisen", "Festivals", "Klettern"],
        "26-40": ["Yoga", "Kochen", "Fotografie", "Craft Beer", "Cycling", "Laufen"],
        "41-65": ["Golf", "Gartenarbeit", "Klassische Musik", "Schach", "Wandern", "Lesen"]
    }
    
    age_list = age_hobbies.get(age_group, age_hobbies["26-40"])
    hobbies.extend(random.sample(age_list, min(2, len(age_list))))
    
    # Occupation-specific hobbies
    occupation_hobbies = {
        "technical": ["3D-Druck", "Elektronik", "Open Source", "Programmieren"],
        "creative": ["Malerei", "Fotografie", "Musik", "Design"],
        "social": ["Vereinsarbeit", "Freiwilligenarbeit", "Mentoring"]
    }
    
    if occupation_type in occupation_hobbies:
        occ_list = occupation_hobbies[occupation_type]
        hobbies.extend(random.sample(occ_list, min(1, len(occ_list))))
    
    # Ensure 4-6 hobbies, no duplicates
    unique_hobbies = list(set(hobbies))
    if len(unique_hobbies) < 4:
        # Add more from age list
        remaining = [h for h in age_list if h not in unique_hobbies]
        unique_hobbies.extend(random.sample(remaining, min(4 - len(unique_hobbies), len(remaining))))
    
    return unique_hobbies[:6]


def generate_varied_summary(
    persona: Dict[str, Any],
    occupation_doc: Optional[Dict[str, Any]] = None,
    language: str = "de"
) -> str:
    """
    Generate varied summary with specific details, avoiding templates.
    
    Args:
        persona: Persona dictionary.
        occupation_doc: Occupation document.
        language: Language (de, fr, it).
    
    Returns:
        Varied summary text (2-3 sentences).
    """
    if not OPENAI_AVAILABLE or not settings.openai_api_key:
        return generate_fallback_summary(persona, language)
    
    name = f"{persona.get('first_name')} {persona.get('last_name')}"
    age = persona.get("age", 25)
    years_exp = persona.get("years_experience", 0)
    career_level = persona.get("career_level", "mid")
    industry = persona.get("industry", "")
    occupation_title = persona.get("occupation", persona.get("current_title", ""))
    
    # Get actual skills from occupation
    job_id = persona.get("job_id")
    skills_docs = get_skills_by_occupation(job_id) if job_id else []
    actual_skills = [s.get("skill_name_de", "") for s in skills_docs[:3] if s.get("skill_name_de")]
    
    # Vary tone
    tone_variants = {
        "de": ["erfahrener", "versierter", "kompetenter", "erfolgreicher"],
        "fr": ["expérimenté", "compétent", "expérimenté", "réussi"],
        "it": ["esperto", "competente", "esperto", "di successo"]
    }
    tone = random.choice(tone_variants.get(language, tone_variants["de"]))
    
    # Get description from occupation
    description = ""
    if occupation_doc:
        description = occupation_doc.get("description", "")[:300]
    
    prompts = {
        "de": f"""Erstelle einen professionellen CV-Zusammenfassungstext (2-3 Sätze) für:

Name: {name}
Alter: {age} Jahre
Berufserfahrung: {years_exp} Jahre (EXAKT, nicht "über X Jahren")
Karrierelevel: {career_level}
Branche: {industry}
Beruf: {occupation_title}
Relevante Skills: {', '.join(actual_skills[:2]) if actual_skills else 'verschiedene'}

Berufsbeschreibung: {description}

KRITISCHE ANFORDERUNGEN:
- Verwende EXAKTE Jahre ({years_exp}), nicht "über X Jahren"
- Erwähne 1-2 konkrete Skills: {', '.join(actual_skills[:2]) if actual_skills else 'verschiedene'}
- Erwähne Branchenkontext oder Firmentyp
- Variiere Ton: verwende "{tone}" oder ähnlich
- KEINE AI-Buzzwords: "professioneller Ansatz", "geschätzte Figur"
- Zeige, erzähle nicht: konkrete Details statt generischer Phrasen
- 2-3 Sätze, max 200 Wörter
- Schweizer CV-Stil

Nur den Text zurückgeben, keine Markdown, keine Erklärung.""",
        "fr": f"""Créez un texte de résumé professionnel de CV (2-3 phrases) pour:

Nom: {name}
Âge: {age} ans
Expérience: {years_exp} ans (EXACT, pas "plus de X ans")
Niveau: {career_level}
Secteur: {industry}
Profession: {occupation_title}
Compétences: {', '.join(actual_skills[:2]) if actual_skills else 'diverses'}

Description: {description}

EXIGENCES:
- Utilisez les années EXACTES ({years_exp}), pas "plus de X ans"
- Mentionnez 1-2 compétences concrètes
- Contexte sectoriel
- Ton varié
- Pas de mots-clés AI
- Détails concrets
- 2-3 phrases, max 200 mots

Retournez uniquement le texte.""",
        "it": f"""Crea un testo di riepilogo professionale (2-3 frasi) per:

Nome: {name}
Età: {age} anni
Esperienza: {years_exp} anni (ESATTO, non "oltre X anni")
Livello: {career_level}
Settore: {industry}
Professione: {occupation_title}
Competenze: {', '.join(actual_skills[:2]) if actual_skills else 'varie'}

Descrizione: {description}

REQUISITI:
- Anni ESATTI ({years_exp})
- 1-2 competenze concrete
- Contesto settoriale
- Ton variato
- Dettagli concreti
- 2-3 frasi, max 200 parole

Restituisci solo il testo."""
    }
    
    prompt = prompts.get(language, prompts["de"])
    
    try:
        messages = [
            {
                "role": "system",
                "content": "You are a professional CV writer. Create varied, specific summaries with concrete details, avoiding generic templates and AI buzzwords."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        if _openai_client and hasattr(_openai_client, 'chat'):
            response = _openai_client.chat.completions.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_creative,
                max_tokens=250
            )
            summary = response.choices[0].message.content.strip()
        else:
            summary = generate_fallback_summary(persona, language)
        
        # Clean up
        summary = summary.replace("**", "").replace("*", "").strip()
        return summary
        
    except Exception as e:
        return generate_fallback_summary(persona, language)


def score_cv_quality(cv_doc: CVDocument) -> Dict[str, Any]:
    """
    Score CV quality across multiple dimensions.
    
    Args:
        cv_doc: CVDocument to score.
    
    Returns:
        Dictionary with scores and report.
    """
    scores = {
        "completeness": 0,
        "realism": 0,
        "language": 0,
        "achievement": 0,
        "overall": 0
    }
    
    issues = []
    
    # 1. Completeness (0-100)
    completeness_score = 100
    completeness_issues = []
    
    # Check required sections
    if not cv_doc.summary:
        completeness_score -= 20
        completeness_issues.append("Missing summary")
    if not cv_doc.education:
        completeness_score -= 15
        completeness_issues.append("Missing education")
    if not cv_doc.jobs:
        completeness_score -= 15
        completeness_issues.append("Missing job history")
    if not cv_doc.skills.get("technical"):
        completeness_score -= 10
        completeness_issues.append("Missing technical skills")
    if not cv_doc.skills.get("languages"):
        completeness_score -= 5
        completeness_issues.append("Missing languages")
    
    # Check minimum content
    if cv_doc.jobs:
        current_job = next((j for j in cv_doc.jobs if j.get("is_current")), None)
        if current_job:
            responsibilities = current_job.get("responsibilities", [])
            if len(responsibilities) < 3:
                completeness_score -= 10
                completeness_issues.append("Insufficient responsibilities in current job")
    
    if len(cv_doc.skills.get("technical", [])) < 5:
        completeness_score -= 5
        completeness_issues.append("Insufficient technical skills")
    
    scores["completeness"] = max(0, completeness_score)
    if completeness_issues:
        issues.extend([f"Completeness: {i}" for i in completeness_issues])
    
    # 2. Realism (0-100)
    realism_score = 100
    realism_issues = []
    
    # Check timeline consistency
    age = cv_doc.age
    years_exp = cv_doc.years_experience
    
    if age < 18 + years_exp:
        realism_score -= 20
        realism_issues.append("Age inconsistent with experience")
    
    # Check career level appropriateness
    if cv_doc.career_level == "lead" and age < 30:
        realism_score -= 15
        realism_issues.append("Lead level too young")
    elif cv_doc.career_level == "senior" and age < 25:
        realism_score -= 10
        realism_issues.append("Senior level too young")
    
    # Check job progression
    if len(cv_doc.jobs) > 1:
        job_levels = [j.get("position", "").lower() for j in cv_doc.jobs]
        if "senior" in job_levels[0] and "junior" in job_levels[-1]:
            realism_score -= 15
            realism_issues.append("Illogical career progression")
    
    scores["realism"] = max(0, realism_score)
    if realism_issues:
        issues.extend([f"Realism: {i}" for i in realism_issues])
    
    # 3. Language (0-100)
    language_score = 100
    language_issues = []
    
    # Check for duplicates
    all_text = cv_doc.summary.lower()
    for job in cv_doc.jobs:
        all_text += " " + " ".join(job.get("responsibilities", [])).lower()
    
    words = all_text.split()
    if len(words) > 0:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.7:
            language_score -= 20
            language_issues.append("High word repetition")
    
    # Check for "Erfolgreich" spam
    erfolg_count = all_text.count("erfolgreich")
    if erfolg_count > 3:
        language_score -= 15
        language_issues.append("Too many 'Erfolgreich'")
    
    scores["language"] = max(0, language_score)
    if language_issues:
        issues.extend([f"Language: {i}" for i in language_issues])
    
    # 4. Achievement (0-100)
    achievement_score = 100
    achievement_issues = []
    
    # Check for metrics in responsibilities
    has_metrics = False
    for job in cv_doc.jobs:
        responsibilities = job.get("responsibilities", [])
        for resp in responsibilities:
            # Check for numbers (metrics)
            if re.search(r'\d+', resp):
                has_metrics = True
                break
        if has_metrics:
            break
    
    if not has_metrics:
        achievement_score -= 30
        achievement_issues.append("No metrics in responsibilities")
    
    # Check for impact language
    impact_keywords = ["reduzierte", "steigerte", "optimierte", "verbesserte", "erhöhte"]
    has_impact = any(kw in all_text for kw in impact_keywords)
    if not has_impact:
        achievement_score -= 20
        achievement_issues.append("Missing impact language")
    
    scores["achievement"] = max(0, achievement_score)
    if achievement_issues:
        issues.extend([f"Achievement: {i}" for i in achievement_issues])
    
    # Overall: weighted average (30% completeness, 35% realism, 20% language, 15% achievement)
    scores["overall"] = (
        scores["completeness"] * 0.30 +
        scores["realism"] * 0.35 +
        scores["language"] * 0.20 +
        scores["achievement"] * 0.15
    )
    
    return {
        "scores": scores,
        "issues": issues,
        "passed": scores["overall"] >= 75
    }


def generate_summary(
    persona: Dict[str, Any],
    occupation_doc: Optional[Dict[str, Any]] = None,
    language: str = "de"
) -> str:
    """
    Generate CV summary using AI.
    
    Args:
        persona: Persona dictionary.
        occupation_doc: Occupation document from CV_DATA.
        language: Language (de, fr, it).
    
    Returns:
        Generated summary text (2-3 sentences).
    """
    if not OPENAI_AVAILABLE or not settings.openai_api_key:
        return generate_fallback_summary(persona, language)
    
    # Extract relevant information
    name = f"{persona.get('first_name')} {persona.get('last_name')}"
    age = persona.get("age", 25)
    years_exp = persona.get("years_experience", 0)
    career_level = persona.get("career_level", "mid")
    industry = persona.get("industry", "")
    occupation_title = persona.get("occupation", persona.get("current_title", ""))
    
    # Get description from occupation
    description = ""
    if occupation_doc:
        description = occupation_doc.get("description", "")
        berufsverhaeltnisse = occupation_doc.get("berufsverhaeltnisse", {})
        if isinstance(berufsverhaeltnisse, dict):
            beschreibung = berufsverhaeltnisse.get("beschreibung", "")
            if beschreibung:
                description += " " + beschreibung
    
    # Language-specific prompts
    prompts = {
        "de": f"""Erstelle einen professionellen CV-Zusammenfassungstext (2-3 Sätze) für:

Name: {name}
Alter: {age} Jahre
Berufserfahrung: {years_exp} Jahre
Karrierelevel: {career_level}
Branche: {industry}
Beruf: {occupation_title}

Berufsbeschreibung: {description[:500]}

Anforderungen:
- Professionell und überzeugend
- Zeigt Erfahrung und Kompetenz
- 2-3 Sätze, max 200 Wörter
- Schweizer CV-Stil

Nur den Text zurückgeben, keine Markdown, keine Erklärung.""",
        "fr": f"""Créez un texte de résumé professionnel de CV (2-3 phrases) pour:

Nom: {name}
Âge: {age} ans
Expérience: {years_exp} ans
Niveau de carrière: {career_level}
Secteur: {industry}
Profession: {occupation_title}

Description professionnelle: {description[:500]}

Exigences:
- Professionnel et convaincant
- Montre l'expérience et les compétences
- 2-3 phrases, max 200 mots
- Style CV suisse

Retournez uniquement le texte, pas de markdown, pas d'explication.""",
        "it": f"""Crea un testo di riepilogo professionale del CV (2-3 frasi) per:

Nome: {name}
Età: {age} anni
Esperienza: {years_exp} anni
Livello di carriera: {career_level}
Settore: {industry}
Professione: {occupation_title}

Descrizione professionale: {description[:500]}

Requisiti:
- Professionale e convincente
- Mostra esperienza e competenze
- 2-3 frasi, max 200 parole
- Stile CV svizzero

Restituisci solo il testo, nessun markdown, nessuna spiegazione."""
    }
    
    prompt = prompts.get(language, prompts["de"])
    
    try:
        messages = [
            {
                "role": "system",
                "content": "You are a professional CV writer specializing in Swiss CV formats."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Try modern OpenAI client
        if _openai_client and hasattr(_openai_client, 'chat'):
            response = _openai_client.chat.completions.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_creative,
                max_tokens=200
            )
            summary = response.choices[0].message.content.strip()
        else:
            # Fallback: use simple summary
            summary = generate_fallback_summary(persona, language)
        
        # Clean up
        summary = summary.replace("**", "").replace("*", "").strip()
        
        return summary
        
    except Exception as e:
        print(f"Warning: AI summary generation failed: {e}")
        return generate_fallback_summary(persona, language)


def generate_fallback_summary(persona: Dict[str, Any], language: str = "de") -> str:
    """Generate fallback summary without AI."""
    name = persona.get("first_name", "")
    years_exp = persona.get("years_experience", 0)
    career_level = persona.get("career_level", "mid")
    occupation_title = persona.get("occupation", persona.get("current_title", ""))
    
    summaries = {
        "de": f"{name} ist ein {career_level}-level {occupation_title.lower()} mit {years_exp} Jahren Berufserfahrung. Spezialisiert auf {persona.get('industry', 'verschiedene Bereiche')} mit Fokus auf Qualität und Effizienz.",
        "fr": f"{name} est un {occupation_title.lower()} de niveau {career_level} avec {years_exp} ans d'expérience professionnelle. Spécialisé dans {persona.get('industry', 'divers domaines')} avec un accent sur la qualité et l'efficacité.",
        "it": f"{name} è un {occupation_title.lower()} di livello {career_level} con {years_exp} anni di esperienza professionale. Specializzato in {persona.get('industry', 'vari settori')} con focus su qualità ed efficienza."
    }
    
    return summaries.get(language, summaries["de"])


def generate_hobbies(language: str = "de", use_ai: bool = True) -> List[str]:
    """
    Generate realistic Swiss hobbies.
    
    Args:
        language: Language (de, fr, it).
        use_ai: Whether to use AI generation.
    
    Returns:
        List of hobby strings (3-5 items).
    """
    # Common Swiss hobbies
    swiss_hobbies = {
        "de": [
            "Wandern in den Alpen",
            "Skifahren",
            "Fussball",
            "Velofahren",
            "Lesen",
            "Kochen",
            "Musik",
            "Fotografie",
            "Reisen",
            "Volunteering"
        ],
        "fr": [
            "Randonnée dans les Alpes",
            "Ski",
            "Football",
            "Vélo",
            "Lecture",
            "Cuisine",
            "Musique",
            "Photographie",
            "Voyages",
            "Bénévolat"
        ],
        "it": [
            "Escursioni nelle Alpi",
            "Sci",
            "Calcio",
            "Ciclismo",
            "Lettura",
            "Cucina",
            "Musica",
            "Fotografia",
            "Viaggi",
            "Volontariato"
        ]
    }
    
    if use_ai and OPENAI_AVAILABLE:
        try:
            prompts = {
                "de": "Generiere 4-5 realistische Schweizer Hobbys für einen CV. Rücke nur eine kommagetrennte Liste zurück, keine Erklärung.",
                "fr": "Génère 4-5 loisirs suisses réalistes pour un CV. Retourne uniquement une liste séparée par des virgules, pas d'explication.",
                "it": "Genera 4-5 hobby svizzeri realistici per un CV. Restituisci solo un elenco separato da virgole, nessuna spiegazione."
            }
            
            messages = [
                {"role": "system", "content": "You are a professional CV writer."},
                {"role": "user", "content": prompts.get(language, prompts["de"])}
            ]
            
            if _openai_client and hasattr(_openai_client, 'chat'):
                response = _openai_client.chat.completions.create(
                    model=settings.openai_model_mini,
                    messages=messages,
                    temperature=settings.ai_temperature_creative,
                    max_tokens=100
                )
                hobbies_text = response.choices[0].message.content.strip()
            else:
                # Fallback: use predefined hobbies
                hobbies_text = ""
            
            # Parse hobbies
            hobbies = [h.strip() for h in hobbies_text.split(",") if h.strip()]
            return hobbies[:5] if hobbies else swiss_hobbies.get(language, swiss_hobbies["de"])[:5]
            
        except Exception:
            pass
    
    # Fallback to predefined hobbies
    hobbies_list = swiss_hobbies.get(language, swiss_hobbies["de"])
    return random.sample(hobbies_list, min(5, len(hobbies_list)))


def categorize_skills(skills: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Categorize skills into technical, soft, and languages.
    
    Args:
        skills: List of skill dictionaries from occupation_skills.
    
    Returns:
        Dictionary with categorized skills.
    """
    categorized = {
        "technical": [],
        "soft": [],
        "languages": []
    }
    
    for skill in skills:
        category = skill.get("skill_category", "soft")
        skill_name = skill.get("skill_name_de", "")
        
        if not skill_name:
            continue
        
        if category == "technical":
            categorized["technical"].append(skill_name)
        elif category == "soft":
            categorized["soft"].append(skill_name)
        elif category == "physical":
            # Physical skills can go to technical or soft
            categorized["technical"].append(skill_name)
    
    # Limit to top skills per category
    categorized["technical"] = categorized["technical"][:10]
    categorized["soft"] = categorized["soft"][:8]
    
    return categorized


def get_languages_for_cv(canton: str, primary_language: str) -> List[str]:
    """
    Get languages for CV based on canton and primary language.
    
    Args:
        canton: Canton code.
        primary_language: Primary language (de, fr, it).
    
    Returns:
        List of language strings with proficiency levels.
    """
    languages = []
    
    # Primary language (native or fluent)
    lang_names = {
        "de": "Deutsch",
        "fr": "Französisch",
        "it": "Italienisch",
        "en": "Englisch"
    }
    
    languages.append(f"{lang_names.get(primary_language, primary_language)} (Muttersprache)")
    
    # Add other Swiss languages based on canton
    multilingual_cantons = {
        "BE": ["de", "fr"],
        "VS": ["de", "fr"],
        "FR": ["fr", "de"],
        "GR": ["de", "it", "rm"]
    }
    
    if canton in multilingual_cantons:
        other_langs = multilingual_cantons[canton]
        for lang in other_langs:
            if lang != primary_language:
                proficiency = random.choice(["Fließend", "Gut", "Grundkenntnisse"])
                languages.append(f"{lang_names.get(lang, lang)} ({proficiency})")
    
    # Most Swiss people speak English
    if random.random() < 0.8:  # 80% chance
        english_level = random.choice(["Fließend", "Gut", "Grundkenntnisse"])
        languages.append(f"Englisch ({english_level})")
    
    return languages


def format_date_swiss(date_str: Optional[str], language: str = "de") -> str:
    """
    Format date in Swiss format (DD.MM.YYYY).
    
    Args:
        date_str: Date string (YYYY-MM format).
        language: Language for month names if needed.
    
    Returns:
        Formatted date string.
    """
    if not date_str:
        return ""
    
    try:
        if "-" in date_str:
            parts = date_str.split("-")
            if len(parts) >= 2:
                year = parts[0]
                month = parts[1]
                return f"{month}.{year}"
    except:
        pass
    
    return date_str


def generate_complete_cv(persona: Dict[str, Any]) -> Tuple[Optional[CVDocument], Optional[Dict[str, Any]]]:
    """
    Generate complete CV document from persona with validation and quality scoring.
    
    Args:
        persona: Persona dictionary from sampling.
    
    Returns:
        Tuple of (CVDocument if quality >= 75, quality_report).
        Returns (None, quality_report) if quality < 75.
    """
    # 0. Pre-assembly validation
    job_id = persona.get("job_id")
    occupation_doc = get_occupation_by_id(job_id) if job_id else None
    
    is_valid, fixed_persona, validation_issues = validate_persona_before_assembly(
        persona, occupation_doc
    )
    
    if not is_valid and len([i for i in validation_issues if i.startswith("Error")]) > 0:
        # Critical validation failure
        return None, {
            "scores": {"overall": 0},
            "issues": validation_issues,
            "passed": False
        }
    
    persona = fixed_persona
    
    # Generate all sections
    language = persona.get("language", "de")
    age_group = get_age_group(persona.get("age", 25))
    canton = persona.get("canton", "ZH")
    
    # 1. Personal information (personalized)
    first_name = persona.get("first_name", "")
    last_name = persona.get("last_name", "")
    full_name = persona.get("full_name", f"{first_name} {last_name}")
    
    personal_info = generate_personal_info(persona, canton)
    email = personal_info["email"]
    phone = personal_info["phone"]
    city = personal_info["city"]
    address = personal_info["address"]
    
    # 2. Portrait (validated)
    portrait_path = persona.get("portrait_path")
    portrait_base64 = load_portrait_image(portrait_path, resize=(150, 150), circular=True)
    
    # 3. Summary (varied, specific)
    summary = generate_varied_summary(persona, occupation_doc, language)
    
    # 4. Education history
    education_history = generate_education_history(persona, occupation_doc)
    
    # 5. Job history
    job_history = generate_job_history(persona, occupation_doc)
    
    # Add responsibilities to job history
    for job in job_history:
        if job.get("is_current", False):
            # Generate responsibilities for current job
            responsibilities = generate_responsibilities_from_activities(
                job_id,
                persona.get("career_level", "mid"),
                job.get("company", ""),
                language,
                num_bullets=4,
                is_current_job=True
            )
        else:
            # Fewer responsibilities for previous jobs
            previous_level = "mid" if persona.get("career_level") in ["senior", "lead"] else "junior"
            responsibilities = generate_responsibilities_from_activities(
                job_id,
                previous_level,
                job.get("company", ""),
                language,
                num_bullets=2,
                is_current_job=False
            )
        
        job["responsibilities"] = responsibilities
    
    # 6. Skills (categorized)
    skills_list = persona.get("skills", [])
    if isinstance(skills_list, list) and skills_list and isinstance(skills_list[0], str):
        # Skills are already strings
        from src.database.queries import get_skills_by_occupation
        skills_docs = get_skills_by_occupation(job_id) if job_id else []
        categorized_skills = categorize_skills(skills_docs)
    else:
        # Skills are dictionaries
        categorized_skills = categorize_skills(skills_list)
    
    # Add languages to skills (personalized)
    languages = generate_personalized_languages(canton, language, persona.get("age", 25))
    categorized_skills["languages"] = languages
    
    # 7. Additional education
    base_education_end = None
    if education_history:
        base_education_end = education_history[0].get("end_year")
    
    additional_education = generate_additional_education(
        persona,
        occupation_doc,
        base_education_end_year=base_education_end
    )
    
    # 8. Hobbies (personalized)
    # Determine occupation type
    occupation_type = "general"
    if occupation_doc:
        berufsfelder = occupation_doc.get("categories", {}).get("berufsfelder", [])
        if any("informatik" in bf.lower() or "technik" in bf.lower() for bf in berufsfelder):
            occupation_type = "technical"
        elif any("kunst" in bf.lower() or "design" in bf.lower() for bf in berufsfelder):
            occupation_type = "creative"
        elif any("sozial" in bf.lower() or "pflege" in bf.lower() for bf in berufsfelder):
            occupation_type = "social"
    
    hobbies = generate_personalized_hobbies(canton, language, age_group, occupation_type)
    
    # Create CVDocument
    cv_doc = CVDocument(
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        age=persona.get("age", 25),
        gender=persona.get("gender", ""),
        canton=canton,
        city=city,
        email=email,
        phone=phone,
        address=address,
        portrait_path=portrait_path,
        portrait_base64=portrait_base64,
        current_title=persona.get("current_title", persona.get("occupation", "")),
        industry=persona.get("industry", ""),
        career_level=persona.get("career_level", "mid"),
        years_experience=persona.get("years_experience", 0),
        summary=summary,
        education=education_history,
        jobs=job_history,
        skills=categorized_skills,
        additional_education=additional_education,
        hobbies=hobbies,
        language=language,
        created_at=datetime.now().isoformat()
    )
    
    # Post-assembly quality scoring
    quality_report = score_cv_quality(cv_doc)
    
    # Only return CV if quality >= 75
    if quality_report["passed"]:
        return cv_doc, quality_report
    else:
        return None, quality_report


def generate_city_for_canton(canton: str) -> str:
    """
    Generate realistic city name for canton.
    
    Args:
        canton: Canton code.
    
    Returns:
        City name.
    """
    # Major cities per canton
    canton_cities = {
        "ZH": "Zürich",
        "BE": "Bern",
        "BS": "Basel",
        "GE": "Genève",
        "VD": "Lausanne",
        "AG": "Aarau",
        "SG": "St. Gallen",
        "LU": "Luzern",
        "TI": "Lugano",
        "VS": "Sion",
        "FR": "Fribourg",
        "GR": "Chur",
        "NE": "Neuchâtel",
        "TG": "Frauenfeld",
        "SH": "Schaffhausen",
        "AR": "Herisau",
        "AI": "Appenzell",
        "GL": "Glarus",
        "NW": "Stans",
        "OW": "Sarnen",
        "SZ": "Schwyz",
        "UR": "Altdorf",
        "ZG": "Zug",
        "SO": "Solothurn",
        "BL": "Liestal",
        "JU": "Delémont"
    }
    
    return canton_cities.get(canton, f"City {canton}")


def get_section_headers(language: str) -> Dict[str, str]:
    """
    Get section headers translated for language.
    
    Args:
        language: Language (de, fr, it).
    
    Returns:
        Dictionary with section headers.
    """
    headers = {
        "de": {
            "personal": "Persönliche Angaben",
            "summary": "Zusammenfassung",
            "experience": "Berufserfahrung",
            "education": "Ausbildung",
            "skills": "Kompetenzen",
            "technical_skills": "Technische Kompetenzen",
            "soft_skills": "Persönliche Kompetenzen",
            "languages": "Sprachen",
            "certifications": "Zertifikate & Weiterbildung",
            "hobbies": "Hobbys & Interessen"
        },
        "fr": {
            "personal": "Informations personnelles",
            "summary": "Résumé",
            "experience": "Expérience professionnelle",
            "education": "Formation",
            "skills": "Compétences",
            "technical_skills": "Compétences techniques",
            "soft_skills": "Compétences personnelles",
            "languages": "Langues",
            "certifications": "Certificats & Formation continue",
            "hobbies": "Loisirs & Intérêts"
        },
        "it": {
            "personal": "Informazioni personali",
            "summary": "Riassunto",
            "experience": "Esperienza professionale",
            "education": "Formazione",
            "skills": "Competenze",
            "technical_skills": "Competenze tecniche",
            "soft_skills": "Competenze personali",
            "languages": "Lingue",
            "certifications": "Certificati & Formazione continua",
            "hobbies": "Hobby & Interessi"
        }
    }
    
    return headers.get(language, headers["de"])

