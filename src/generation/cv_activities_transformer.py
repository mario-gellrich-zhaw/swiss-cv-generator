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
from src.generation.metrics_validator import (
    validate_bullet_metrics,
    validate_job_metric_consistency,
    enhance_achievement_prompt,
    get_metric_range_prompt
)
from src.config import get_settings
from src.generation.openai_client import (
    get_openai_client,
    is_openai_available,
    call_openai_chat
)

settings = get_settings()

# Use centralized OpenAI client
OPENAI_AVAILABLE = is_openai_available()
_openai_client = get_openai_client()


def generate_all_jobs_bullets_batch(
    jobs_data: List[Dict[str, Any]],
    occupation_title: str,
    language: str = "de"
) -> Dict[int, List[str]]:
    """
    Generate ALL bullets for ALL jobs in ONE API call.
    
    This is the fastest approach - reduces 4-16 API calls to just 1!
    
    Args:
        jobs_data: List of job dictionaries with keys:
            - job_index: int
            - position: str
            - career_level: str
            - company: str
            - activities: List[str]
            - num_bullets: int
        occupation_title: The base occupation title.
        language: Language (de, fr, it).
    
    Returns:
        Dict mapping job_index to list of bullet points.
    """
    if not jobs_data or not OPENAI_AVAILABLE or not _openai_client:
        return {}
    
    # Build combined prompt for all jobs
    # Use simple 1, 2, 3 numbering (NOT job_index which may have gaps!)
    jobs_prompt_parts = []
    for i, job in enumerate(jobs_data):
        activities_text = "\n".join([f"  - {a}" for a in job.get("activities", [])[:4]])
        jobs_prompt_parts.append(f"""
JOB {i + 1}: {job['position']} bei {job['company']}
Karrierestufe: {job['career_level']}
Anzahl Bullets: {job['num_bullets']}
Tätigkeiten:
{activities_text}""")
    
    all_jobs_text = "\n".join(jobs_prompt_parts)
    total_bullets = sum(job['num_bullets'] for job in jobs_data)
    
    prompt = f"""Du bist ein erfahrener Schweizer Lebenslauf-Autor. 

BERUF: {occupation_title}

Generiere Lebenslauf-Bullets für diese {len(jobs_data)} Stellen:
{all_jobs_text}

REGELN:
1. Bullets SPEZIFISCH für den Beruf "{occupation_title}"
2. Jeder Bullet beginnt mit VERSCHIEDENEM Aktionsverb
3. EINE konkrete Zahl pro Bullet (Projekte, Kunden, CHF, Team-Grösse)
4. KEINE Prozentangaben, KEINE generischen Business-Phrasen
5. Max 18 Wörter pro Bullet
6. Schweizer Deutsch

AUSGABEFORMAT (WICHTIG - genau so!):
JOB 1:
1. [Bullet]
2. [Bullet]
...

JOB 2:
1. [Bullet]
...

usw."""
    
    try:
        # Calculate needed tokens: ~30 tokens per bullet, plus overhead
        total_bullets = sum(job['num_bullets'] for job in jobs_data)
        needed_tokens = max(1200, total_bullets * 50 + 200)
        
        if hasattr(_openai_client, 'chat'):
            response = _openai_client.chat.completions.create(
                model=settings.openai_model_mini,
                messages=[
                    {"role": "system", "content": "Du schreibst professionelle CV-Bullets. Antworte NUR mit den nummerierten Bullets, formatiert genau wie angegeben."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=needed_tokens
            )
            result = response.choices[0].message.content.strip()
        else:
            return {}
        
        # Parse response into job buckets
        bullets_by_job = {}
        current_job = None
        
        for line in result.split("\n"):
            line = line.strip()
            if not line:
                continue
            
            # Check for job header
            if line.upper().startswith("JOB "):
                try:
                    job_num = int(line.split(":")[0].replace("JOB", "").strip())
                    current_job = job_num - 1  # Convert to 0-indexed
                    bullets_by_job[current_job] = []
                except:
                    continue
            elif current_job is not None and re.match(r'^\d+[\.\)]', line):
                # This is a bullet
                bullet = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                if bullet and len(bullet) > 10:
                    # Ensure capital letter
                    bullet = bullet[0].upper() + bullet[1:] if len(bullet) > 1 else bullet.upper()
                    bullets_by_job[current_job].append(bullet)
        
        return bullets_by_job
        
    except Exception as e:
        import warnings
        warnings.warn(f"Ultra-batch generation failed: {e}")
        return {}


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
    
    # Ensure min_val and max_val are integers for random.randint()
    min_val = int(min_val)
    max_val = int(max_val)
    
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
        
        # Create base prompt for AI transformation
        base_prompt = f"""Transform this Swiss occupation activity into an achievement-focused CV bullet.

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
        
        # Enhance prompt with metric range guidance from metrics_validator
        prompt = enhance_achievement_prompt(base_prompt, career_level)

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


def generate_bullets_batch(
    activities: List[str],
    career_level: str,
    company: str,
    industry: str,
    years_in_position: int,
    language: str,
    num_bullets: int,
    occupation_title: str = ""
) -> List[str]:
    """
    Generate all bullets in a SINGLE API call (batch processing).
    
    This is much faster than individual calls (1 API call instead of N).
    
    Args:
        activities: List of activity descriptions.
        career_level: Career level.
        company: Company name.
        industry: Industry type.
        years_in_position: Years in this position.
        language: Language.
        num_bullets: Number of bullets needed.
        occupation_title: The specific occupation title (e.g. "Betonwerker/in EFZ").
    
    Returns:
        List of bullet points, or empty list if failed.
    """
    if not activities or not OPENAI_AVAILABLE or not _openai_client:
        return []
    
    # Build batch prompt
    activities_text = "\n".join([f"- {a}" for a in activities[:num_bullets + 2]])
    
    # Career level specific examples
    level_examples = {
        "junior": """1. Führte Betonierarbeiten an 15 Baustellen durch, hielt alle Sicherheitsstandards ein
2. Unterstützte bei Schalungsaufbau für 8 Fundamente, termingerecht fertiggestellt
3. Bediente Rüttelgeräte und Betonmischer bei 20 Projekten""",
        "mid": """1. Koordinierte Betonarbeiten für 12 Bauprojekte, optimierte Materialverbrauch um CHF 8'000
2. Plante Einsatz von 5 Fachkräften, alle Etappen termingerecht abgeschlossen
3. Überwachte Qualitätskontrolle bei 30 Betonierungen, null Nacharbeiten nötig""",
        "senior": """1. Leitete Betonierteam von 8 Fachkräften auf Grossprojekt mit CHF 2.5 Mio Budget
2. Verantwortete Baustellen-Logistik für 4 parallele Projekte, 15% unter Budget
3. Implementierte neue Betonmischtechnik, reduzierte Materialverlust um CHF 12'000""",
        "lead": """1. Führte Bauabteilung mit 25 Mitarbeitenden, Jahresumsatz CHF 4.8 Mio
2. Etablierte Qualitätsstandards für 40 Bauprojekte, null Mängelrügen
3. Definierte Weiterbildungsprogramm für Team, 95% Mitarbeiterzufriedenheit"""
    }
    
    examples = level_examples.get(career_level, level_examples["mid"])
    
    prompt = f"""Du bist ein erfahrener Schweizer Lebenslauf-Autor. Schreibe {num_bullets} Aufzählungspunkte für einen Lebenslauf.

BERUF: {occupation_title if occupation_title else "Fachperson"}
TÄTIGKEITEN AUS DER PRAXIS:
{activities_text}

KONTEXT:
- Karrierestufe: {career_level}
- Firma: {company}

WICHTIGE REGELN:
1. Bullets müssen SPEZIFISCH für den Beruf "{occupation_title}" sein
2. Verwende KONKRETE Tätigkeiten aus der obigen Liste - keine generischen Business-Phrasen!
3. KEINE Marketing/Strategie/Management-Floskeln für handwerkliche Berufe!
4. Jeder Bullet beginnt mit einem VERSCHIEDENEN Aktionsverb
5. Füge EINE konkrete Zahl hinzu (KEINE Prozente! Stattdessen: Anzahl Projekte, Stunden, Kunden, CHF-Beträge)
6. Maximal 20 Wörter pro Bullet
7. Professionelles Schweizer Deutsch

BEISPIELE für {career_level}-Level:
{examples}

AUSGABEFORMAT:
Genau {num_bullets} Bullets, nummeriert 1-{num_bullets}. Nur die Bullets, keine Erklärung."""

    try:
        messages = [
            {"role": "system", "content": "You are a professional CV writer. Generate varied, metric-focused bullet points. Return ONLY the numbered bullets, nothing else."},
            {"role": "user", "content": prompt}
        ]
        
        if hasattr(_openai_client, 'chat'):
            response = _openai_client.chat.completions.create(
                model=settings.openai_model_mini,
                messages=messages,
                temperature=settings.ai_temperature_creative,
                max_tokens=500
            )
            result = response.choices[0].message.content.strip()
        else:
            return []
        
        # Parse bullets from response
        bullets = []
        for line in result.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Remove numbering (1., 2., etc.)
            import re
            cleaned = re.sub(r'^[\d]+[\.\)]\s*', '', line)
            cleaned = cleaned.strip().strip('-').strip('•').strip()
            if cleaned and len(cleaned) > 10:
                # Ensure capital letter
                cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
                bullets.append(cleaned)
        
        return bullets[:num_bullets]
        
    except Exception as e:
        import warnings
        warnings.warn(f"Batch bullet generation failed: {e}")
        return []


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
    years_in_position: int = 2,
    occupation_title: str = ""
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
        occupation_title: The specific occupation title (e.g. "Betonwerker/in EFZ").
    
    Returns:
        List of responsibility bullet points with metrics.
    """
    responsibilities = []
    
    # Extract activities from CV_DATA and get occupation title if not provided
    activities = extract_activities_from_occupation(job_id)
    
    # Get occupation title from database if not provided
    if not occupation_title and job_id:
        occupation_doc = get_occupation_by_id(job_id)
        if occupation_doc:
            occupation_title = occupation_doc.get("title", "")
    
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
    
    # Try BATCH generation first (1 API call instead of N)
    if OPENAI_AVAILABLE and _openai_client and len(selected_activities) > 1:
        batch_bullets = generate_bullets_batch(
            selected_activities,
            career_level,
            company,
            industry,
            years_in_position,
            language,
            num_bullets,
            occupation_title
        )
        if batch_bullets and len(batch_bullets) >= num_bullets - 1:
            responsibilities = batch_bullets
        else:
            # Fallback to individual generation
            for activity in selected_activities:
                bullet = transform_activity_to_bullet(
                    activity, career_level, company, industry,
                    years_in_position, language, used_verbs, use_ai=True
                )
                if bullet:
                    responsibilities.append(bullet)
    else:
        # Transform each activity to bullet with metrics (individual calls)
        for activity in selected_activities:
            bullet = transform_activity_to_bullet(
                activity, career_level, company, industry,
                years_in_position, language, used_verbs, use_ai=True
            )
            if bullet:
                responsibilities.append(bullet)
    
    # Validate and clean bullets
    validated_responsibilities, issues = validate_and_clean_bullets(
        responsibilities, career_level, max_attempts=3
    )
    
    # Validate metrics with metrics_validator (STRICT)
    validated_with_metrics = []
    rejected_bullets = []
    for bullet in validated_responsibilities:
        is_valid, error_msg, metric = validate_bullet_metrics(bullet, career_level)
        if is_valid:
            validated_with_metrics.append(bullet)
        else:
            # REJECT invalid bullets (strict validation - don't append)
            rejected_bullets.append((bullet, error_msg))
            # Don't append invalid bullets - they will be regenerated if needed
    
    # Validate job metric consistency (STRICT)
    is_consistent, consistency_issues, metric_dist = validate_job_metric_consistency(
        validated_with_metrics, career_level
    )
    
    if not is_consistent and consistency_issues:
        # Warn about consistency issues and track for quality score
        import warnings
        warnings.warn(f"Metric consistency issues: {consistency_issues[:2]}")
        # Continue but track for quality score (don't reject bullets here)
    
    # Ensure progression
    validated_responsibilities = ensure_progression_in_bullets(
        validated_with_metrics,
        career_level,
        is_older_job=not is_current_job
    )
    
    # If we don't have enough bullets, add generic ones with metrics
    while len(validated_responsibilities) < num_bullets:
        generic = generate_generic_responsibility(
            career_level, language, industry
        )
        # Validate generic bullet too
        is_valid, _, _ = validate_bullet_metrics(generic, career_level)
        if is_valid and generic not in validated_responsibilities:
            validated_responsibilities.append(generic)
    
    return validated_responsibilities[:num_bullets]


def generate_generic_responsibilities(
    career_level: str,
    num_bullets: int,
    language: str = "de",
    industry: str = "other",
    occupation_title: str = ""
) -> List[str]:
    """
    Generate responsibilities with metrics when no activities available.
    Uses industry-specific templates for more realistic results.
    
    Args:
        career_level: Career level.
        num_bullets: Number of bullets.
        language: Language.
        industry: Industry type.
        occupation_title: The occupation title for context.
    
    Returns:
        List of responsibility bullets with metrics.
    """
    # Generate bullets using the improved function
    bullets = []
    for _ in range(num_bullets):
        bullet = generate_generic_responsibility(career_level, language, industry, occupation_title)
        bullets.append(bullet)
    
    # Ensure variety - no duplicate starting verbs
    unique_bullets = []
    used_starts = set()
    for bullet in bullets:
        start = bullet.split()[0].lower() if bullet.split() else ""
        if start not in used_starts:
            unique_bullets.append(bullet)
            used_starts.add(start)
    
    # Fill up if needed
    while len(unique_bullets) < num_bullets:
        bullet = generate_generic_responsibility(career_level, language, industry, occupation_title)
        start = bullet.split()[0].lower() if bullet.split() else ""
        if start not in used_starts:
            unique_bullets.append(bullet)
            used_starts.add(start)
    
    return unique_bullets[:num_bullets]


def generate_generic_responsibility(
    career_level: str,
    language: str = "de",
    industry: str = "other",
    occupation_title: str = ""
) -> str:
    """
    Generate a single responsibility with metrics, tailored to industry.
    
    Args:
        career_level: Career level.
        language: Language.
        industry: Industry type.
        occupation_title: The occupation title for context.
    
    Returns:
        Responsibility bullet with metrics.
    """
    # Industry-specific templates
    industry_templates = {
        "construction": {
            "junior": ["Ausführung von Bauarbeiten an {num} Baustellen", "Mitarbeit bei {num} Bauprojekten", "Unterstützung bei Montagearbeiten"],
            "mid": ["Koordination von {num} Bauprojekten", "Überwachung von Arbeiten auf {num} Baustellen", "Planung von Materialeinsatz"],
            "senior": ["Leitung von {num} Bauprojekten", "Verantwortung für Baustellen mit CHF {chf} Budget", "Führung von {team} Mitarbeitenden"],
            "lead": ["Führung der Bauabteilung mit {team} Mitarbeitenden", "Verantwortung für Jahresumsatz CHF {chf}", "Strategische Bauplanung"]
        },
        "technology": {
            "junior": ["Entwicklung von {num} Softwaremodulen", "Bearbeitung von {num} Support-Tickets", "Testing von Applikationen"],
            "mid": ["Umsetzung von {num} IT-Projekten", "Koordination mit {team} Entwicklern", "Implementierung neuer Systeme"],
            "senior": ["Leitung von {num} IT-Projekten", "Architektur für {num} Systeme", "Mentoring von {team} Entwicklern"],
            "lead": ["Führung des IT-Teams mit {team} Mitarbeitenden", "Verantwortung für IT-Budget CHF {chf}", "Strategische IT-Planung"]
        },
        "healthcare": {
            "junior": ["Betreuung von {num} Patienten täglich", "Dokumentation von Behandlungen", "Unterstützung des Pflegeteams"],
            "mid": ["Koordination der Pflege von {num} Patienten", "Anleitung von {team} Auszubildenden", "Qualitätssicherung"],
            "senior": ["Leitung des Pflegeteams mit {team} Mitarbeitenden", "Verantwortung für Station mit {num} Betten", "Schulung von Personal"],
            "lead": ["Führung der Pflegeabteilung", "Verantwortung für {team} Mitarbeitende", "Strategische Personalplanung"]
        },
        "other": {
            "junior": ["Bearbeitung von {num} Aufträgen", "Mitarbeit in {num} Projekten", "Unterstützung des Teams"],
            "mid": ["Koordination von {num} Projekten", "Betreuung von {num} Kunden", "Optimierung von Arbeitsabläufen"],
            "senior": ["Leitung von {num} Projekten", "Führung von {team} Mitarbeitenden", "Verantwortung für Budget CHF {chf}"],
            "lead": ["Führung des Teams mit {team} Mitarbeitenden", "Strategische Planung", "Verantwortung für Umsatz CHF {chf}"]
        }
    }
    
    # Get templates for industry
    templates_by_level = industry_templates.get(industry, industry_templates["other"])
    templates = templates_by_level.get(career_level, templates_by_level["mid"])
    
    # Select random template
    template = random.choice(templates)
    
    # Generate realistic numbers based on career level
    level_scales = {"junior": (5, 15), "mid": (10, 25), "senior": (15, 40), "lead": (25, 60)}
    min_scale, max_scale = level_scales.get(career_level, (10, 25))
    
    num = random.randint(min_scale, max_scale)
    team = random.randint(3, 15) if career_level in ["senior", "lead"] else random.randint(2, 5)
    chf = random.choice([50000, 100000, 250000, 500000, 1000000, 2500000])
    
    # Fill template
    bullet = template.format(num=num, team=team, chf=f"{chf:,}".replace(",", "'"))
    
    # Add action verb
    verbs = ACTION_VERBS.get(career_level, ACTION_VERBS["mid"])
    verb = random.choice(verbs)
    
    # Only add verb if template doesn't already start with one
    if not any(bullet.lower().startswith(v.lower()) for v in ["leitung", "führung", "verantwortung", "koordination"]):
        bullet = f"{verb} {bullet[0].lower()}{bullet[1:]}"
    
    # Ensure capital letter
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
                        # Remove this completely - don't add "Verantwortung für"
                        pass
        
        adjusted_bullets.append(bullet)
    
    return adjusted_bullets
