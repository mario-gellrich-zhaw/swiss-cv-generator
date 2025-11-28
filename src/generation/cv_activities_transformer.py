"""
CV Activities Transformer.

This module transforms occupation activities from CV_DATA into
achievement-focused CV responsibility bullets with metrics and impact.

Run: Used by persona generation pipeline
"""
import sys
import random
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.queries import get_activities_by_occupation, get_occupation_by_id
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

# Action verbs by career level (for variety)
ACTION_VERBS = {
    "junior": [
        "Unterstützte", "Bearbeitete", "Führte durch", "Erledigte", "Hilfte bei",
        "Mitarbeitete an", "Assistierte bei", "Durchführte", "Erstellte", "Wartete"
    ],
    "mid": [
        "Entwickelte", "Koordinierte", "Verwaltete", "Plante", "Umsetzte",
        "Organisierte", "Betreute", "Optimierte", "Analysierte", "Implementierte"
    ],
    "senior": [
        "Leitete", "Optimierte", "Verantwortete", "Implementierte", "Strategierte",
        "Etablierte", "Transformierte", "Steuerte", "Entwickelte", "Koordinierte"
    ],
    "lead": [
        "Führte", "Etablierte", "Definierte", "Transformierte", "Visionierte",
        "Leitete", "Strategierte", "Entwickelte", "Implementierte", "Steuerte"
    ]
}


def generate_realistic_metrics(
    industry: str,
    career_level: str,
    activity_text: str
) -> Dict[str, Any]:
    """
    Generate realistic metrics based on industry and career level.
    
    Args:
        industry: Industry type (technology, finance, healthcare, etc.).
        career_level: Career level (junior, mid, senior, lead).
        activity_text: Activity text for context.
    
    Returns:
        Dictionary with metric type and value suggestions.
    """
    # Scale by career level
    scale_multipliers = {
        "junior": (1, 1.5),
        "mid": (2, 4),
        "senior": (5, 10),
        "lead": (10, 20)
    }
    
    multiplier_min, multiplier_max = scale_multipliers.get(career_level, (2, 4))
    
    # Industry-specific metric types
    industry_metrics = {
        "technology": {
            "types": [
                ("uptime", "%", 95, 99.9),
                ("deployments", "/Monat", 5, 50),
                ("team_size", "Personen", 3, 30),
                ("lines_of_code", "Zeilen", 10000, 500000),
                ("projects", "Projekte", 1, 20),
                ("users", "Benutzer", 100, 100000),
                ("response_time", "ms", 50, 500)
            ]
        },
        "finance": {
            "types": [
                ("accounts", "Konten", 50, 5000),
                ("transactions", "/Tag", 100, 10000),
                ("assets", "CHF", 100000, 50000000),
                ("compliance_rate", "%", 95, 100),
                ("clients", "Kunden", 20, 500),
                ("revenue", "CHF", 50000, 5000000)
            ]
        },
        "healthcare": {
            "types": [
                ("patients", "/Tag", 5, 100),
                ("satisfaction", "%", 85, 99),
                ("wait_time_reduction", "%", 10, 50),
                ("procedures", "Eingriffe", 50, 2000),
                ("team_size", "Personen", 3, 25),
                ("efficiency_gain", "%", 5, 30)
            ]
        },
        "construction": {
            "types": [
                ("projects", "Projekte", 1, 15),
                ("team_size", "Personen", 5, 50),
                ("safety_record", "Tage", 100, 1000),
                ("m2_built", "m²", 500, 50000),
                ("budget", "CHF", 100000, 10000000),
                ("efficiency_gain", "%", 5, 25)
            ]
        },
        "manufacturing": {
            "types": [
                ("units", "Einheiten", 1000, 100000),
                ("error_rate", "%", 0.1, 5),
                ("efficiency_gain", "%", 5, 30),
                ("machines", "Maschinen", 1, 20),
                ("team_size", "Personen", 3, 40),
                ("uptime", "%", 90, 99)
            ]
        },
        "sales": {
            "types": [
                ("quota_achievement", "%", 80, 150),
                ("customers", "/Monat", 5, 50),
                ("revenue", "CHF", 50000, 2000000),
                ("deals_closed", "Deals", 5, 100),
                ("satisfaction", "%", 85, 99),
                ("growth", "%", 10, 50)
            ]
        },
        "education": {
            "types": [
                ("students", "Studierende", 20, 500),
                ("courses", "Kurse", 2, 20),
                ("satisfaction", "%", 85, 98),
                ("team_size", "Personen", 3, 30),
                ("publications", "Publikationen", 1, 20)
            ]
        },
        "retail": {
            "types": [
                ("customers", "/Tag", 50, 1000),
                ("revenue", "CHF", 10000, 500000),
                ("inventory_turnover", "x", 2, 12),
                ("satisfaction", "%", 85, 98),
                ("team_size", "Personen", 2, 20)
            ]
        },
        "hospitality": {
            "types": [
                ("guests", "/Tag", 20, 500),
                ("satisfaction", "%", 85, 98),
                ("occupancy", "%", 60, 95),
                ("revenue", "CHF", 50000, 2000000),
                ("team_size", "Personen", 5, 50)
            ]
        }
    }
    
    # Get metrics for industry or use generic
    metrics_config = industry_metrics.get(industry, {
        "types": [
            ("projects", "Projekte", 1, 20),
            ("team_size", "Personen", 3, 30),
            ("efficiency_gain", "%", 5, 25),
            ("satisfaction", "%", 85, 98)
        ]
    })
    
    # Select random metric type
    metric_type, unit, min_val, max_val = random.choice(metrics_config["types"])
    
    # Calculate value based on career level scale
    base_value = random.randint(min_val, max_val)
    scaled_value = int(base_value * random.uniform(multiplier_min, multiplier_max))
    
    return {
        "type": metric_type,
        "value": scaled_value,
        "unit": unit,
        "formatted": f"{scaled_value} {unit}"
    }


def filter_activities_by_career_level(
    activities: List[str],
    career_level: str
) -> List[str]:
    """
    Filter activities based on career level focus.
    
    Args:
        activities: List of activity strings.
        career_level: Career level (junior, mid, senior, lead).
    
    Returns:
        Filtered list of activities matching career level.
    """
    if not activities:
        return []
    
    # Keywords for different career levels
    level_keywords = {
        "junior": [
            "durchführen", "unterstützen", "erstellen", "bearbeiten",
            "ausführen", "mitarbeiten", "helfen", "assistieren"
        ],
        "mid": [
            "planen", "organisieren", "koordinieren", "durchführen",
            "entwickeln", "umsetzen", "verantworten"
        ],
        "senior": [
            "leiten", "entwickeln", "planen", "koordinieren",
            "verantworten", "optimieren", "strategisch"
        ],
        "lead": [
            "leiten", "führen", "strategisch", "entwickeln",
            "verantworten", "management", "team"
        ]
    }
    
    keywords = level_keywords.get(career_level, level_keywords["mid"])
    
    # Score activities based on keyword matches
    scored_activities = []
    for activity in activities:
        activity_lower = activity.lower()
        score = sum(1 for kw in keywords if kw in activity_lower)
        if score > 0:
            scored_activities.append((activity, score))
    
    # Sort by score (highest first)
    scored_activities.sort(key=lambda x: x[1], reverse=True)
    
    # Return top activities
    filtered = [act for act, score in scored_activities]
    
    # If no matches, return all activities
    if not filtered:
        return activities
    
    return filtered


def transform_activity_to_bullet(
    activity_text: str,
    career_level: str,
    company: str,
    industry: str = "other",
    years_in_position: int = 2,
    language: str = "de",
    used_verbs: Optional[List[str]] = None,
    use_ai: bool = True
) -> str:
    """
    Transform activity text to achievement-focused CV bullet with metrics.
    
    Args:
        activity_text: Original activity text.
        career_level: Career level for context.
        company: Company name for context.
        industry: Industry type.
        years_in_position: Years in this position.
        language: Language (de, fr, it).
        used_verbs: List of already used action verbs (to avoid repetition).
        use_ai: Whether to use AI transformation.
    
    Returns:
        Polished bullet point with metrics.
    """
    if not activity_text:
        return ""
    
    if used_verbs is None:
        used_verbs = []
    
    # If AI not available or disabled, use enhanced transformation
    if not use_ai or not OPENAI_AVAILABLE:
        return enhanced_transform_activity(
            activity_text, career_level, industry, used_verbs
        )
    
    try:
        # Generate realistic metrics
        metrics = generate_realistic_metrics(industry, career_level, activity_text)
        
        # Get available verbs (excluding already used)
        available_verbs = [
            v for v in ACTION_VERBS.get(career_level, ACTION_VERBS["mid"])
            if v.lower() not in [uv.lower() for uv in used_verbs]
        ]
        if not available_verbs:
            available_verbs = ACTION_VERBS.get(career_level, ACTION_VERBS["mid"])
        
        suggested_verb = random.choice(available_verbs)
        
        # Create enhanced prompt for AI transformation
        prompt = f"""Transform this Swiss occupation activity into an achievement-focused CV bullet.

Activity: {activity_text}
Career Level: {career_level}
Company: {company}
Industry: {industry}
Years in position: {years_in_position}

CRITICAL REQUIREMENTS:
1. Start with VARIED action verb (NOT 'Erfolgreich', rotate verbs)
   Suggested verb: {suggested_verb}
2. Include ONE quantifiable metric:
   - Numbers: team size, customers, projects, hours saved
   - Percentages: efficiency gains, error reduction, satisfaction
   - Scale: budget managed, revenue impact, system users
   Suggested metric: {metrics['formatted']}
3. Show RESULT/IMPACT, not just task description
4. Max 25 words
5. Professional Swiss business language
6. Start with CAPITAL letter

Verb suggestions by level:
- Junior: Unterstützte, Bearbeitete, Führte durch
- Mid: Entwickelte, Koordinierte, Optimierte
- Senior: Leitete, Implementierte, Verantwortete
- Lead: Führte, Etablierte, Transformierte

Examples by career level:

Junior (0-2y):
BAD: 'Erfolgreich maschinen bedienen'
GOOD: 'Bediente CNC-Maschinen für 5 Produktionslinien mit 99% Verfügbarkeit'

Mid (3-6y):
BAD: 'Projekte koordinieren'
GOOD: 'Koordinierte 8 parallele Projekte mit Budget von CHF 500K, Abschluss pünktlich'

Senior (7-11y):
BAD: 'Team leiten'
GOOD: 'Leitete 12-köpfiges Entwicklerteam, reduzierte Time-to-Market um 30%'

Lead (12+y):
BAD: 'Verantwortung für strategie'
GOOD: 'Definierte Technologie-Roadmap für Abteilung (45 Mitarbeiter), Kostenreduktion 25%'

Language: {language}

Return only the bullet point text, no markdown, no explanation, no quotes."""

        messages = [
            {
                "role": "system",
                "content": "You are a professional CV writer specializing in achievement-focused bullet points with quantifiable metrics. Always start with varied action verbs, include metrics, and show impact."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Try modern OpenAI client
        if hasattr(_openai_client, 'chat') and callable(getattr(_openai_client, 'chat', None)):
            response = _openai_client.chat.completions.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_creative,
                max_tokens=200
            )
            bullet = response.choices[0].message.content.strip()
        else:
            # Fallback to legacy client
            import openai
            response = openai.ChatCompletion.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_creative,
                max_tokens=200
            )
            bullet = response.choices[0].message.content.strip()
        
        # Clean up bullet (remove markdown, quotes, ensure proper format)
        bullet = bullet.replace("*", "").replace("-", "").strip()
        bullet = bullet.strip('"').strip("'").strip()
        if bullet.startswith("•"):
            bullet = bullet[1:].strip()
        
        # Extract verb for tracking
        first_word = bullet.split()[0] if bullet.split() else ""
        if first_word:
            used_verbs.append(first_word)
        
        return bullet
        
    except Exception as e:
        # Fallback to enhanced transformation
        return enhanced_transform_activity(
            activity_text, career_level, industry, used_verbs
        )


def enhanced_transform_activity(
    activity_text: str,
    career_level: str,
    industry: str,
    used_verbs: Optional[List[str]] = None
) -> str:
    """
    Enhanced transformation without AI, with metrics.
    
    Args:
        activity_text: Original activity text.
        career_level: Career level.
        industry: Industry type.
        used_verbs: Already used verbs.
    
    Returns:
        Transformed bullet point with metrics.
    """
    if used_verbs is None:
        used_verbs = []
    
    bullet = activity_text.strip()
    bullet_lower = bullet.lower()
    
    # Remove existing prefixes to avoid duplication
    prefixes_to_remove = ["verantwortung für", "erfolgreich", "verantwortlich für"]
    for prefix in prefixes_to_remove:
        if bullet_lower.startswith(prefix):
            bullet = bullet[len(prefix):].strip()
            bullet_lower = bullet.lower()
    
    # Get available verbs
    available_verbs = [
        v for v in ACTION_VERBS.get(career_level, ACTION_VERBS["mid"])
        if v.lower() not in [uv.lower() for uv in used_verbs]
    ]
    if not available_verbs:
        available_verbs = ACTION_VERBS.get(career_level, ACTION_VERBS["mid"])
    
    # Add action verb
    verb = random.choice(available_verbs)
    used_verbs.append(verb)
    
    # Generate metrics
    metrics = generate_realistic_metrics(industry, career_level, activity_text)
    
    # Construct bullet with verb and metric
    if verb.lower() not in bullet_lower:
        bullet = f"{verb} {bullet.lower()}"
    
    # Add metric if not already present
    if not re.search(r'\d+', bullet):
        bullet = f"{bullet}, {metrics['formatted']}"
    
    # Ensure it starts with capital letter
    if bullet:
        bullet = bullet[0].upper() + bullet[1:] if len(bullet) > 1 else bullet.upper()
    
    return bullet


def validate_and_clean_bullets(
    bullets: List[str],
    career_level: str,
    max_attempts: int = 3
) -> Tuple[List[str], List[str]]:
    """
    Validate and clean bullets, regenerate if needed.
    
    Args:
        bullets: List of bullet points.
        career_level: Career level.
        max_attempts: Maximum regeneration attempts.
    
    Returns:
        Tuple of (validated_bullets, issues).
    """
    if not bullets:
        return [], []
    
    validated = []
    issues = []
    used_verbs = []
    
    for i, bullet in enumerate(bullets):
        bullet_clean = bullet.strip()
        bullet_lower = bullet_clean.lower()
        
        # Validation checks
        has_metric = bool(re.search(r'\d+', bullet_clean))
        starts_capital = bullet_clean and bullet_clean[0].isupper()
        no_erfolgreich_spam = bullet_lower.count("erfolgreich") <= 1
        no_verantwortung_spam = bullet_lower.count("verantwortung") <= 1
        
        # Extract first word (verb)
        first_word = bullet_clean.split()[0] if bullet_clean.split() else ""
        verb_varies = first_word.lower() not in [uv.lower() for uv in used_verbs]
        
        # Check for duplicate phrases
        has_duplicates = False
        for other_bullet in validated:
            # Check if more than 50% of words match
            words1 = set(bullet_lower.split())
            words2 = set(other_bullet.lower().split())
            if len(words1) > 0 and len(words2) > 0:
                overlap = len(words1 & words2) / max(len(words1), len(words2))
                if overlap > 0.5:
                    has_duplicates = True
                    break
        
        # Validate
        is_valid = (
            has_metric and
            starts_capital and
            no_erfolgreich_spam and
            no_verantwortung_spam and
            verb_varies and
            not has_duplicates
        )
        
        if is_valid:
            validated.append(bullet_clean)
            if first_word:
                used_verbs.append(first_word)
        else:
            # Track issues
            issue_parts = []
            if not has_metric:
                issue_parts.append("missing metric")
            if not starts_capital:
                issue_parts.append("no capital start")
            if not no_erfolgreich_spam:
                issue_parts.append("too many 'Erfolgreich'")
            if not verb_varies:
                issue_parts.append("repeated verb")
            if has_duplicates:
                issue_parts.append("duplicate phrase")
            
            issues.append(f"Bullet {i+1}: {', '.join(issue_parts)}")
            
            # Try to fix common issues
            fixed = bullet_clean
            
            # Fix capitalization
            if not starts_capital:
                fixed = fixed[0].upper() + fixed[1:] if len(fixed) > 1 else fixed.upper()
            
            # Remove excessive "Erfolgreich"
            if bullet_lower.count("erfolgreich") > 1:
                fixed = re.sub(r'\berfolgreich\b', '', fixed, flags=re.IGNORECASE, count=bullet_lower.count("erfolgreich") - 1)
                fixed = re.sub(r'\s+', ' ', fixed).strip()
            
            # If still invalid and we have attempts, mark for regeneration
            if not has_metric and max_attempts > 0:
                # Add a generic metric
                metrics = generate_realistic_metrics("other", career_level, bullet_clean)
                if not re.search(r'\d+', fixed):
                    fixed = f"{fixed}, {metrics['formatted']}"
            
            validated.append(fixed)
            if first_word:
                used_verbs.append(first_word)
    
    return validated, issues


def extract_activities_from_occupation(job_id: Optional[str]) -> List[str]:
    """
    Extract activities from occupation document.
    
    Args:
        job_id: Occupation job_id.
    
    Returns:
        List of activity strings.
    """
    if not job_id:
        return []
    
    occupation_doc = get_occupation_by_id(job_id)
    if not occupation_doc:
        return []
    
    activities = []
    taetigkeiten = occupation_doc.get("taetigkeiten", {})
    kategorien = taetigkeiten.get("kategorien", {})
    
    if isinstance(kategorien, dict):
        # kategorien is a dict with category names as keys
        for category_name, activity_list in kategorien.items():
            if isinstance(activity_list, list):
                activities.extend(activity_list)
    elif isinstance(kategorien, list):
        # kategorien is a list
        activities = kategorien
    
    # Also try get_activities_by_occupation as fallback
    if not activities:
        activities = get_activities_by_occupation(job_id) or []
    
    return activities


def generate_responsibilities_from_activities(
    job_id: Optional[str],
    career_level: str,
    company: str,
    language: str = "de",
    num_bullets: int = 4,
    is_current_job: bool = True,
    industry: str = "other",
    years_in_position: int = 2
) -> List[str]:
    """
    Generate responsibility bullets from CV_DATA activities with metrics.
    
    Args:
        job_id: Occupation job_id.
        career_level: Career level (junior, mid, senior, lead).
        company: Company name.
        language: Language (de, fr, it).
        num_bullets: Number of bullets to generate.
        is_current_job: Whether this is the current job.
        industry: Industry type.
        years_in_position: Years in this position.
    
    Returns:
        List of responsibility bullet points with metrics.
    """
    responsibilities = []
    
    # Extract activities from CV_DATA
    activities = extract_activities_from_occupation(job_id)
    
    if not activities:
        # Fallback: generate generic responsibilities with metrics
        return generate_generic_responsibilities(
            career_level, num_bullets, language, industry
        )
    
    # Filter activities by career level
    filtered_activities = filter_activities_by_career_level(activities, career_level)
    
    # If not enough filtered, use all activities
    if len(filtered_activities) < num_bullets:
        filtered_activities = activities
    
    # Adjust num_bullets based on job recency
    if not is_current_job:
        num_bullets = max(2, num_bullets - 1)  # Fewer bullets for previous jobs
    
    # Select activities
    selected_activities = []
    if len(filtered_activities) >= num_bullets:
        selected_activities = random.sample(
            filtered_activities,
            min(num_bullets, len(filtered_activities))
        )
    else:
        selected_activities = filtered_activities
    
    # Track used verbs to ensure variety
    used_verbs = []
    
    # Transform each activity to bullet with metrics
    for activity in selected_activities:
        bullet = transform_activity_to_bullet(
            activity,
            career_level,
            company,
            industry,
            years_in_position,
            language,
            used_verbs,
            use_ai=True
        )
        
        if bullet:
            responsibilities.append(bullet)
    
    # Validate and clean bullets
    validated_responsibilities, issues = validate_and_clean_bullets(
        responsibilities, career_level, max_attempts=3
    )
    
    # Ensure progression
    validated_responsibilities = ensure_progression_in_bullets(
        validated_responsibilities,
        career_level,
        is_older_job=not is_current_job
    )
    
    # If we don't have enough bullets, add generic ones with metrics
    while len(validated_responsibilities) < num_bullets:
        generic = generate_generic_responsibility(
            career_level, language, industry
        )
        if generic not in validated_responsibilities:
            validated_responsibilities.append(generic)
    
    return validated_responsibilities[:num_bullets]


def generate_generic_responsibilities(
    career_level: str,
    num_bullets: int,
    language: str = "de",
    industry: str = "other"
) -> List[str]:
    """
    Generate generic responsibilities with metrics when no activities available.
    
    Args:
        career_level: Career level.
        num_bullets: Number of bullets.
        language: Language.
        industry: Industry type.
    
    Returns:
        List of generic responsibility bullets with metrics.
    """
    generic_templates = {
        "junior": [
            "Durchführung von operativen Aufgaben",
            "Unterstützung bei Projekten",
            "Mitarbeit in Teams",
            "Erstellung von Dokumentationen"
        ],
        "mid": [
            "Planung und Durchführung von Projekten",
            "Koordination von Arbeitsabläufen",
            "Entwicklung von Lösungen",
            "Zusammenarbeit mit Partnern"
        ],
        "senior": [
            "Leitung von komplexen Projekten",
            "Strategische Planung",
            "Mentoring von Team-Mitgliedern",
            "Optimierung von Prozessen"
        ],
        "lead": [
            "Strategische Führung",
            "Leitung von Teams",
            "Verantwortung für Budget",
            "Entwicklung von Strategien"
        ]
    }
    
    templates = generic_templates.get(career_level, generic_templates["mid"])
    selected = random.sample(templates, min(num_bullets, len(templates)))
    
    # Add metrics to each template
    bullets_with_metrics = []
    used_verbs = []
    
    for template in selected:
        # Get verb
        available_verbs = [
            v for v in ACTION_VERBS.get(career_level, ACTION_VERBS["mid"])
            if v.lower() not in [uv.lower() for uv in used_verbs]
        ]
        if not available_verbs:
            available_verbs = ACTION_VERBS.get(career_level, ACTION_VERBS["mid"])
        
        verb = random.choice(available_verbs)
        used_verbs.append(verb)
        
        # Generate metrics
        metrics = generate_realistic_metrics(industry, career_level, template)
        
        # Construct bullet
        bullet = f"{verb} {template.lower()}, {metrics['formatted']}"
        bullet = bullet[0].upper() + bullet[1:] if len(bullet) > 1 else bullet.upper()
        
        bullets_with_metrics.append(bullet)
    
    return bullets_with_metrics


def generate_generic_responsibility(
    career_level: str,
    language: str = "de",
    industry: str = "other"
) -> str:
    """
    Generate a single generic responsibility with metrics.
    
    Args:
        career_level: Career level.
        language: Language.
        industry: Industry type.
    
    Returns:
        Generic responsibility bullet with metrics.
    """
    generic = {
        "junior": "Durchführung von operativen Aufgaben",
        "mid": "Planung und Durchführung von Projekten",
        "senior": "Leitung von komplexen Projekten",
        "lead": "Strategische Führung und Entwicklung"
    }
    
    template = generic.get(career_level, generic["mid"])
    
    # Get verb
    verbs = ACTION_VERBS.get(career_level, ACTION_VERBS["mid"])
    verb = random.choice(verbs)
    
    # Generate metrics
    metrics = generate_realistic_metrics(industry, career_level, template)
    
    # Construct bullet
    bullet = f"{verb} {template.lower()}, {metrics['formatted']}"
    bullet = bullet[0].upper() + bullet[1:] if len(bullet) > 1 else bullet.upper()
    
    return bullet


def ensure_progression_in_bullets(
    bullets: List[str],
    career_level: str,
    is_older_job: bool = False
) -> List[str]:
    """
    Ensure bullets show appropriate progression (newer = more complex/impactful).
    
    Args:
        bullets: List of bullet points.
        career_level: Career level.
        is_older_job: Whether this is an older position.
    
    Returns:
        Adjusted bullets showing progression.
    """
    if not bullets:
        return bullets
    
    adjusted_bullets = []
    
    for bullet in bullets:
        bullet_lower = bullet.lower()
        
        # For older jobs, simplify language
        if is_older_job:
            # Remove complex/leadership terms if career level was lower
            if career_level in ["junior", "mid"]:
                # Simplify to basic execution language
                if "strategisch" in bullet_lower:
                    bullet = bullet.replace("strategisch", "").replace("Strategisch", "").strip()
                if "leitung" in bullet_lower and career_level == "junior":
                    bullet = bullet.replace("Leitung", "Unterstützung").replace("leitung", "unterstützung")
        
        # For recent jobs, ensure complexity matches career level
        else:
            if career_level in ["senior", "lead"]:
                # Ensure leadership/strategic language if not present
                if "leiten" not in bullet_lower and "führen" not in bullet_lower:
                    if "planen" in bullet_lower or "entwickeln" in bullet_lower:
                        # Already has some complexity
                        pass
                    else:
                        # Add leadership context (but avoid "Erfolgreich" spam)
                        if "verantwortung" not in bullet_lower:
                            bullet = f"Verantwortung für {bullet.lower()}"
        
        adjusted_bullets.append(bullet)
    
    return adjusted_bullets
