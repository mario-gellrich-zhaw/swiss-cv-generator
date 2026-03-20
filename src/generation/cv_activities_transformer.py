"""
CV Activities Transformer.

This module transforms occupation activities from CV_DATA into
achievement-focused CV responsibility bullets with metrics and impact.

Run: Used by persona generation pipeline
"""
import logging
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from src.config import get_settings
from src.database.queries import (get_activities_by_occupation,
                                  get_occupation_by_id)
from src.generation.metrics_validator import (enhance_achievement_prompt,
                                              get_metric_range_prompt,
                                              validate_bullet_metrics,
                                              validate_job_metric_consistency)
from src.generation.openai_client import (get_openai_client,
                                          is_openai_available)

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


settings = get_settings()
logger = logging.getLogger(__name__)

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

    # Build combined prompt for all jobs (keep JOB X headers for parsing)
    # Use simple 1, 2, 3 numbering (NOT job_index which may have gaps!)
    jobs_prompt_parts: List[str] = []
    for i, job in enumerate(jobs_data):
        activities_text = "\n".join(
            [f"  - {a}" for a in job.get("activities", [])[:4]])
        jobs_prompt_parts.append(
            f"""
JOB {i + 1}: {job['position']} — {job['company']}
Niveau carrière/Livello carriera: {job['career_level']}
Bullets à générer/Da generare: {job['num_bullets']}
Attività/Tâches (peuvent être en allemand):
{activities_text}"""
        )

    all_jobs_text = "\n".join(jobs_prompt_parts)

    lang = (language or "de")[:2]
    if lang == "fr":
        prompt = f"""Tu es un rédacteur de CV suisse expérimenté.

MÉTIER: {occupation_title}

Génère des puces de CV pour ces {len(jobs_data)} postes:
{all_jobs_text}

RÈGLES:
1. Puces SPÉCIFIQUES au métier "{occupation_title}" (pas de généralités)
2. Chaque puce commence par un verbe d'action DIFFÉRENT
3. UNE valeur chiffrée concrète par puce (projets, clients, CHF, taille d'équipe)
4. Pas de pourcentages; préfère nombres concrets
5. Maximum 18 mots par puce
6. IMPORTANT: Si les tâches/activités ne sont pas en français, TRADUIS tout et ÉCRIS TOUT EN FRANÇAIS

FORMAT DE SORTIE (OBLIGATOIRE - exactement ainsi):
JOB 1:
1. [Puce]
2. [Puce]
...

JOB 2:
1. [Puce]
...
"""
    elif lang == "it":
        prompt = f"""Sei un redattore di CV svizzero esperto.

PROFESSIONE: {occupation_title}

Genera punti elenco di CV per queste {len(jobs_data)} posizioni:
{all_jobs_text}

REGOLE:
1. Punti SPECIFICI per il ruolo "{occupation_title}" (niente frasi generiche)
2. Ogni punto inizia con un verbo d'azione DIVERSO
3. UN numero concreto per punto (progetti, clienti, CHF, dimensione team)
4. Evita percentuali; preferisci numeri concreti
5. Massimo 18 parole per punto
6. IMPORTANTE: Se le attività non sono in italiano, TRADUCI tutto e SCRIVI TUTTO IN ITALIANO

FORMATO DI USCITA (OBBLIGATORIO - esattamente così):
JOB 1:
1. [Punto]
2. [Punto]
...

JOB 2:
1. [Punto]
...
"""
    else:
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
"""

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
        bullets_by_job: dict[int, list[str]] = {}
        current_job = None

        for line in result.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Check for job header
            if line.upper().startswith("JOB "):
                try:
                    job_num = int(line.split(
                        ":")[0].replace("JOB", "").strip())
                    current_job = job_num - 1  # Convert to 0-indexed
                    bullets_by_job[current_job] = []
                except:
                    continue
            elif current_job is not None and re.match(r'^\d+[\.\)]', line):
                # This is a bullet
                bullet = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                if bullet and len(bullet) > 10:
                    # Ensure capital letter
                    bullet = bullet[0].upper(
                    ) + bullet[1:] if len(bullet) > 1 else bullet.upper()
                    bullets_by_job[current_job].append(bullet)

        return bullets_by_job

    except Exception as e:
        logger.debug("Ultra-batch generation failed: %s", e)
        return {}


# Action verbs by career level (for variety)
ACTION_VERBS = {
    "de": {
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
        ],
    },
    "fr": {
        "junior": [
            "A soutenu", "A traité", "A exécuté", "A assisté", "A participé",
            "A contribué", "A appliqué", "A réalisé", "A géré", "A suivi"
        ],
        "mid": [
            "A développé", "A coordonné", "A géré", "A planifié", "A mis en œuvre",
            "A organisé", "A supervisé", "A optimisé", "A analysé", "A implémenté"
        ],
        "senior": [
            "A dirigé", "A optimisé", "A piloté", "A implémenté", "A défini",
            "A établi", "A transformé", "A supervisé", "A développé", "A coordonné"
        ],
        "lead": [
            "A mené", "A défini", "A transformé", "A dirigé", "A orchestré",
            "A élaboré", "A mis en place", "A supervisé", "A déployé", "A piloté"
        ],
    },
    "it": {
        "junior": [
            "Ha supportato", "Ha gestito", "Ha eseguito", "Ha assistito", "Ha partecipato",
            "Ha contribuito", "Ha applicato", "Ha realizzato", "Ha curato", "Ha seguito"
        ],
        "mid": [
            "Ha sviluppato", "Ha coordinato", "Ha gestito", "Ha pianificato", "Ha implementato",
            "Ha organizzato", "Ha supervisionato", "Ha ottimizzato", "Ha analizzato", "Ha introdotto"
        ],
        "senior": [
            "Ha diretto", "Ha ottimizzato", "Ha guidato", "Ha implementato", "Ha definito",
            "Ha istituito", "Ha trasformato", "Ha supervisionato", "Ha sviluppato", "Ha coordinato"
        ],
        "lead": [
            "Ha guidato", "Ha definito", "Ha trasformato", "Ha diretto", "Ha orchestrato",
            "Ha elaborato", "Ha impostato", "Ha supervisionato", "Ha distribuito", "Ha pilotato"
        ],
    },
}


def get_action_verbs(career_level: str, language: str) -> List[str]:
    """Return action verbs for level and language with safe fallbacks."""
    lang_key = (language or "de")[:2]
    return ACTION_VERBS.get(lang_key, ACTION_VERBS["de"]).get(
        career_level, ACTION_VERBS["de"].get("mid", [])
    )


def _localize_metric_unit(unit: str, language: str) -> str:
    """Localize metric units for non-German CVs."""
    lang = (language or "de")[:2]
    if lang != "it":
        return unit

    replacements = {
        "it": {
            "/Tag": "/giorno",
            "/Monat": "/mese",
            "Projekte": "progetti",
            "Personen": "persone",
            "Kunden": "clienti",
            "Benutzer": "utenti",
            "Studierende": "studenti",
            "Kurse": "corsi",
            "Eingriffe": "interventi",
            "Maschinen": "macchine",
            "Einheiten": "unita",
            "Tage": "giorni",
            "Publikationen": "pubblicazioni",
            "Deals": "deal",
        },
    }

    localized = unit
    for key, value in replacements.get(lang, {}).items():
        localized = localized.replace(key, value)

    return localized


def generate_realistic_metrics(
    industry: str,
    career_level: str,
    activity_text: str,
    language: str = "de"
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

    multiplier_min, multiplier_max = scale_multipliers.get(
        career_level, (2, 4))

    # Industry-specific metric types
    industry_metrics: Dict[str, Dict[str, List[Tuple[str, str, float, float]]]] = {
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
    metrics_config: Dict[str, Any] = cast(Dict[str, Any], industry_metrics.get(industry, {
        "types": [
            ("projects", "Projekte", 1, 20),
            ("team_size", "Personen", 3, 30),
            ("efficiency_gain", "%", 5, 25),
            ("satisfaction", "%", 85, 98)
        ]
    }))

    # Select random metric type
    metric_config: List[Tuple[str, str, float, float]
                        ] = metrics_config.get("types", [])
    if not metric_config:
        metric_config = [("projects", "Projekte", 1.0, 20.0)]
    metric_type, unit, min_val, max_val = random.choice(metric_config)

    # Ensure min_val and max_val are integers for random.randint()
    min_val = int(min_val)
    max_val = int(max_val)

    # Calculate value based on career level scale
    base_value = random.randint(min_val, max_val)
    scaled_value = int(
        base_value * random.uniform(multiplier_min, multiplier_max))

    unit_localized = _localize_metric_unit(unit, language)

    return {
        "type": metric_type,
        "value": scaled_value,
        "unit": unit_localized,
        "formatted": f"{scaled_value} {unit_localized}"
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
    use_ai: bool = True,
    occupation_title: str = ""
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
        occupation_title: Occupation title to ground context and fallbacks.

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
            activity_text, career_level, industry, language, used_verbs, occupation_title
        )

    try:
        lang = (language or "de")[:2]

        # Generate realistic metrics
        metrics = generate_realistic_metrics(
            industry, career_level, activity_text, language)

        # Nominalized start suggestions per language
        start_suggestions_by_lang: Dict[str, str] = {
            "de": "Analyse von..., Durchfuehrung von..., Erstellung von..., Planung von..., Koordination von..., Ueberwachung von...",
            "fr": "Analyse de..., Realisation de..., Mise en oeuvre de..., Planification de..., Coordination de..., Suivi de...",
            "it": "Analisi di..., Esecuzione di..., Redazione di..., Pianificazione di..., Coordinamento di..., Monitoraggio di...",
        }
        used_starts = ", ".join(used_verbs[:6]) if used_verbs else "none"
        start_suggestions = start_suggestions_by_lang.get(
            lang, start_suggestions_by_lang["de"])

        # Language-specific examples to anchor the model in the right language
        level_examples_by_lang: Dict[str, Dict[str, str]] = {
            "de": {
                "junior": "1. Bedienung von CNC-Maschinen für 5 Linien mit 99% Verfügbarkeit\n2. Unterstützung beim Schalungsaufbau für 8 Fundamente, termingerecht\n3. Dokumentation von Qualitätsprüfungen für 20 Chargen",
                "mid": "1. Koordination von 8 parallelen Projekten mit Budget CHF 500K, Abschluss pünktlich\n2. Optimierung von Prozesszeiten um 15% ohne Zusatzkosten\n3. Führung eines Teams von 6 Fachkräften, null Sicherheitsvorfälle",
                "senior": "1. Leitung eines 12-köpfigen Teams, Reduktion der Time-to-Market um 30%\n2. Verantwortung für Budget von CHF 1.2 Mio, 12% unter Plan\n3. Implementierung eines QM-Standards, Senkung der Fehlerquote um 18%",
                "lead": "1. Definition einer Roadmap für 45 Mitarbeitende, Kostenreduktion 25%\n2. Steuerung eines Portfolios von 20 Projekten, 95% termintreu\n3. Etablierung eines KPI-Systems, Effizienzsteigerung 22%",
            },
            "fr": {
                "junior": "1. Gestion de 5 lignes CNC avec 99% de disponibilité\n2. Appui au montage de 8 coffrages, livrés à temps\n3. Consignation des contrôles qualité pour 20 lots",
                "mid": "1. Coordination de 8 projets (budget CHF 500K), livrés ponctuellement\n2. Optimisation des temps de processus de 15% sans surcoût\n3. Encadrement d'une équipe de 6 spécialistes, zéro incident sécurité",
                "senior": "1. Direction d'une équipe de 12, réduction du time-to-market de 30%\n2. Gestion d'un budget de CHF 1.2 Mio, 12% sous plan\n3. Mise en place d'une norme qualité, -18% de défauts",
                "lead": "1. Définition de la feuille de route pour 45 collaborateurs, -25% de coûts\n2. Pilotage de 20 projets, 95% livrés à temps\n3. Mise en place de KPI, +22% d'efficacité",
            },
            "it": {
                "junior": "1. Gestione di 5 linee CNC con il 99% di disponibilita\n2. Supporto al montaggio di 8 casseri, consegnati in tempo\n3. Registrazione dei controlli qualita per 20 lotti",
                "mid": "1. Coordinamento di 8 progetti (budget CHF 500K), consegnati puntuali\n2. Ottimizzazione dei tempi di processo del 15% senza costi aggiuntivi\n3. Guida di un team di 6 specialisti, zero incidenti di sicurezza",
                "senior": "1. Direzione di un team di 12, riduzione del time-to-market del 30%\n2. Gestione di un budget di CHF 1.2 Mio, 12% sotto il piano\n3. Introduzione di uno standard qualita, -18% difetti",
                "lead": "1. Definizione della roadmap per 45 collaboratori, -25% di costi\n2. Direzione di un portafoglio di 20 progetti, 95% puntuali\n3. Implementazione di KPI, +22% efficienza",
            },
        }

        examples_for_level = level_examples_by_lang.get(
            lang, level_examples_by_lang["de"]
        ).get(career_level, level_examples_by_lang["de"]["mid"])

        # Create base prompt for AI transformation
        base_prompt = f"""Transform this Swiss occupation activity into an achievement-focused CV bullet.

Activity: {activity_text}
Career Level: {career_level}
Company: {company}
Industry: {industry}
Years in position: {years_in_position}
Occupation: {occupation_title if occupation_title else ""}

CRITICAL REQUIREMENTS:
1. Start with a NOMINALIZED noun phrase (no conjugated verb)
    Examples: {start_suggestions}
    Avoid starting with: {used_starts}
2. Include ONE quantifiable metric:
   - Numbers: team size, customers, projects, hours saved
   - Percentages: efficiency gains, error reduction, satisfaction
   - Scale: budget managed, revenue impact, system users
   Suggested metric: {metrics['formatted']}
3. Show RESULT/IMPACT, not just task description
4. Max 25 words
5. Professional Swiss business language (use {language.upper()} for all text) and translate any non-{language.upper()} input fully
6. Source text may be in German; rewrite the bullet entirely in {language.upper()}
7. Start with CAPITAL letter

Examples for {career_level} level in {language.upper()}:
{examples_for_level}

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
            # Fallback: use the modern client already imported
            try:
                response = _openai_client.chat.completions.create(
                    model=settings.openai_model_mini,
                    messages=messages,
                    temperature=settings.ai_temperature_creative,
                    max_tokens=200
                )
                bullet = response.choices[0].message.content.strip()
            except Exception:
                # If that fails, return empty
                return ""

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
            activity_text, career_level, industry, language, used_verbs, occupation_title
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
    activities_text = "\n".join(
        [f"- {a}" for a in activities[:num_bullets + 2]])

    lang = (language or "de")[:2]

    # Career level specific examples by language
    level_examples_by_lang: Dict[str, Dict[str, str]] = {
        "de": {
            "junior": """1. Durchfuehrung von Betonierarbeiten an 15 Baustellen, Einhaltung aller Sicherheitsstandards
2. Unterstuetzung beim Schalungsaufbau fuer 8 Fundamente, termingerecht fertiggestellt
3. Bedienung von Ruettelgeraeten und Betonmischern bei 20 Projekten""",
            "mid": """1. Koordination von Betonarbeiten fuer 12 Bauprojekte, Materialverbrauch um CHF 8'000 optimiert
2. Planung des Einsatzes von 5 Fachkraeften, alle Etappen termingerecht abgeschlossen
3. Ueberwachung der Qualitaetskontrolle bei 30 Betonierungen, null Nacharbeiten""",
            "senior": """1. Leitung eines Betonierteams von 8 Fachkraeften auf Grossprojekt mit CHF 2.5 Mio Budget
2. Verantwortung fuer Baustellen-Logistik bei 4 parallelen Projekten, 15% unter Budget
3. Implementierung neuer Betonmischtechnik, Materialverlust um CHF 12'000 reduziert""",
            "lead": """1. Fuehrung der Bauabteilung mit 25 Mitarbeitenden, Jahresumsatz CHF 4.8 Mio
2. Etablierung von Qualitaetsstandards fuer 40 Bauprojekte, null Maengelruegen
3. Definition eines Weiterbildungsprogramms, 95% Mitarbeiterzufriedenheit""",
        },
        "fr": {
            "junior": """1. Realisation de travaux de beton sur 15 chantiers, respect de toutes les normes de securite
2. Appui au montage de coffrages pour 8 fondations, livrees dans les delais
3. Utilisation d'aiguilles vibrantes et betonnières sur 20 projets""",
            "mid": """1. Coordination des travaux de beton pour 12 projets, optimisation des materiaux de CHF 8'000
2. Planification de l'affectation de 5 specialistes, toutes les etapes terminees a temps
3. Controle de la qualite sur 30 betonnages, sans reprises""",
            "senior": """1. Direction d'une equipe beton de 8 personnes sur un grand projet (budget CHF 2.5 Mio)
2. Pilotage de la logistique de chantier pour 4 projets paralleles, 15% sous budget
3. Mise en place d'une nouvelle methode de betonage, pertes reduites de CHF 12'000""",
            "lead": """1. Direction du departement construction (25 collaborateurs), chiffre d'affaires CHF 4.8 Mio
2. Etablissement de standards qualite pour 40 projets, zero reclamation
3. Definition d'un programme de formation, 95% de satisfaction""",
        },
        "it": {
            "junior": """1. Esecuzione di lavori di betonaggio in 15 cantieri, rispetto di tutte le norme di sicurezza
2. Supporto al montaggio dei casseri per 8 fondazioni, consegnate puntualmente
3. Utilizzo di vibratori e betoniere in 20 progetti""",
            "mid": """1. Coordinamento di lavori in cemento per 12 progetti, ottimizzazione materiali di CHF 8'000
2. Pianificazione dell'impiego di 5 specialisti, tutte le fasi concluse in tempo
3. Controllo della qualita su 30 gettate, nessun rifacimento""",
            "senior": """1. Direzione di un team di 8 operai su un grande progetto (budget CHF 2.5 Mio)
2. Gestione della logistica di 4 cantieri paralleli, 15% sotto budget
3. Introduzione di una nuova tecnica di betonaggio, riduzione degli sprechi di CHF 12'000""",
            "lead": """1. Direzione del reparto costruzioni (25 collaboratori), fatturato CHF 4.8 Mio
2. Definizione di standard di qualita per 40 progetti, zero contestazioni
3. Creazione di un programma formativo, 95% di soddisfazione""",
        },
    }

    level_examples = level_examples_by_lang.get(
        lang, level_examples_by_lang["de"])
    examples = level_examples.get(career_level, level_examples["mid"])

    prompt_templates = {
        "de": """Du bist ein erfahrener Schweizer Lebenslauf-Autor. Schreibe {num_bullets} Aufzählungspunkte für einen Lebenslauf.

BERUF: {occupation_title}
TÄTIGKEITEN AUS DER PRAXIS:
{activities_text}

KONTEXT:
- Karrierestufe: {career_level}
- Firma: {company}

WICHTIGE REGELN:
1. Bullets müssen SPEZIFISCH für den Beruf "{occupation_title}" sein
2. Verwende KONKRETE Tätigkeiten aus der obigen Liste - keine generischen Business-Phrasen!
3. KEINE Marketing/Strategie/Management-Floskeln für handwerkliche Berufe!
4. Jeder Bullet beginnt mit einer nominalisierten Taetigkeitsform (z. B. Analyse von..., Durchfuehrung von...)
5. Füge EINE konkrete Zahl hinzu (KEINE Prozente! Stattdessen: Anzahl Projekte, Stunden, Kunden, CHF-Beträge)
6. Maximal 20 Wörter pro Bullet
7. Professionelles Schweizer Deutsch

BEISPIELE für {career_level}-Level:
{examples}

AUSGABEFORMAT:
Genau {num_bullets} Bullets, nummeriert 1-{num_bullets}. Nur die Bullets, keine Erklärung.""",
        "fr": """Tu es un rédacteur de CV suisse expérimenté. Rédige {num_bullets} puces pour un CV.

MÉTIER: {occupation_title}
TÂCHES DU QUOTIDIEN:
{activities_text}

CONTEXTE:
- Niveau de carrière: {career_level}
- Entreprise: {company}

RÈGLES IMPORTANTES:
1. Puces spécifiques au métier "{occupation_title}"
2. Utilise les tâches ci-dessus, pas de phrases business génériques
3. Pas de marketing/stratégie pour métiers manuels
4. Chaque puce commence par une forme nominalisee (ex. Analyse de..., Realisation de...)
5. Ajoute UN chiffre concret (pas de pourcentage) : projets, clients, heures, CHF
6. Traduis les tâches si elles ne sont pas en français, écris TOUT en FRANÇAIS
7. Maximum 20 mots par puce
8. Français professionnel suisse

EXEMPLES pour niveau {career_level}:
{examples}

FORMAT DE SORTIE:
Exactement {num_bullets} puces, numérotées 1-{num_bullets}. Uniquement les puces.""",
        "it": """Sei un redattore di CV svizzero esperto. Scrivi {num_bullets} punti elenco per un CV.

PROFESSIONE: {occupation_title}
ATTIVITÀ QUOTIDIANE:
{activities_text}

CONTESTO:
- Livello di carriera: {career_level}
- Azienda: {company}

REGOLE IMPORTANTI:
1. Punti elenco SPECIFICI per il ruolo "{occupation_title}"
2. Usa le attività sopra, niente frasi business generiche
3. Niente marketing/strategia per mestieri manuali
4. Ogni punto inizia con una forma nominale (es. Analisi di..., Esecuzione di...)
5. Aggiungi UN numero concreto (niente percentuali): progetti, clienti, ore, CHF
6. Se le attività non sono in italiano, traducile e scrivi TUTTO in ITALIANO
7. Massimo 20 parole per punto
8. Italiano professionale svizzero

ESEMPI per livello {career_level}:
{examples}

FORMATO DI USCITA:
Esattamente {num_bullets} punti, numerati 1-{num_bullets}. Solo i punti.""",
    }

    prompt = prompt_templates.get(lang, prompt_templates["de"]).format(
        num_bullets=num_bullets,
        occupation_title=occupation_title if occupation_title else "Fachperson",
        activities_text=activities_text,
        career_level=career_level,
        company=company,
        examples=examples
    )

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
                cleaned = cleaned[0].upper(
                ) + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
                bullets.append(cleaned)

        return bullets[:num_bullets]

    except Exception as e:
        logger.debug("Batch bullet generation failed: %s", e)
        return []


def enhanced_transform_activity(
    activity_text: str,
    career_level: str,
    industry: str,
    language: str = "de",
    used_verbs: Optional[List[str]] = None,
    occupation_title: str = ""
) -> str:
    """
    Enhanced transformation without AI, with metrics.

    Args:
        activity_text: Original activity text.
        career_level: Career level.
        industry: Industry type.
        language: Target language code.
        used_verbs: Already used verbs.
        occupation_title: Occupation title for contextual fallbacks.

    Returns:
        Transformed bullet point with metrics.
    """
    if used_verbs is None:
        used_verbs = []

    # For non-German CVs, prefer language-specific generic bullets to avoid leaking German source text
    if language and language.lower() != "de":
        return generate_generic_responsibility(
            career_level, language, industry, occupation_title
        )

    bullet = activity_text.strip()
    bullet_lower = bullet.lower()

    # Remove existing prefixes to avoid duplication
    prefixes_to_remove = ["verantwortung für",
                          "erfolgreich", "verantwortlich für"]
    for prefix in prefixes_to_remove:
        if bullet_lower.startswith(prefix):
            bullet = bullet[len(prefix):].strip()
            bullet_lower = bullet.lower()

    # Nominalized prefixes for fallback phrasing
    prefixes_by_lang: Dict[str, List[str]] = {
        "de": ["Analyse von", "Durchfuehrung von", "Erstellung von", "Planung von", "Koordination von", "Ueberwachung von"],
        "fr": ["Analyse de", "Realisation de", "Mise en oeuvre de", "Planification de", "Coordination de", "Suivi de"],
        "it": ["Analisi di", "Esecuzione di", "Redazione di", "Pianificazione di", "Coordinamento di", "Monitoraggio di"],
    }
    lang_key = (language or "de")[:2]
    available_prefixes = prefixes_by_lang.get(lang_key, prefixes_by_lang["de"])
    prefix = random.choice(available_prefixes)
    used_verbs.append(prefix.split()[0])

    # Generate metrics
    metrics = generate_realistic_metrics(
        industry, career_level, activity_text, language)

    # Construct bullet with nominal prefix and metric
    bullet = f"{prefix} {bullet[0].lower()}{bullet[1:]}" if bullet else prefix

    # Add metric if not already present
    if not re.search(r'\d+', bullet):
        bullet = f"{bullet}, {metrics['formatted']}"

    # Ensure it starts with capital letter
    if bullet:
        bullet = bullet[0].upper() + \
            bullet[1:] if len(bullet) > 1 else bullet.upper()

    return bullet


def validate_and_clean_bullets(
    bullets: List[str],
    career_level: str,
    language: str = "de",
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

    validated: list[str] = []
    issues: list[str] = []
    used_verbs: list[str] = []

    for i, bullet in enumerate(bullets):
        bullet_clean = bullet.strip()
        bullet_lower = bullet_clean.lower()

        # Validation checks
        has_metric = bool(re.search(r'\d+', bullet_clean))
        starts_capital = bullet_clean and bullet_clean[0].isupper()
        no_erfolgreich_spam = bullet_lower.count("erfolgreich") <= 1
        no_verantwortung_spam = bullet_lower.count("verantwortung") <= 1

        # Extract first word (start phrase)
        first_word = bullet_clean.split()[0] if bullet_clean.split() else ""
        start_varies = first_word.lower() not in [
            uv.lower() for uv in used_verbs]

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
            start_varies and
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
            if not start_varies:
                issue_parts.append("repeated start")
            if has_duplicates:
                issue_parts.append("duplicate phrase")

            issues.append(f"Bullet {i+1}: {', '.join(issue_parts)}")

            # Try to fix common issues
            fixed = bullet_clean

            # Fix capitalization
            if not starts_capital:
                fixed = fixed[0].upper() + \
                    fixed[1:] if len(fixed) > 1 else fixed.upper()

            # Remove excessive "Erfolgreich"
            if bullet_lower.count("erfolgreich") > 1:
                fixed = re.sub(r'\berfolgreich\b', '', fixed, flags=re.IGNORECASE,
                               count=bullet_lower.count("erfolgreich") - 1)
                fixed = re.sub(r'\s+', ' ', fixed).strip()

            # If still invalid and we have attempts, mark for regeneration
            if not has_metric and max_attempts > 0:
                # Add a generic metric
                metrics = generate_realistic_metrics(
                    "other", career_level, bullet_clean, language)
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
    filtered_activities = filter_activities_by_career_level(
        activities, career_level)

    # If not enough filtered, use all activities
    if len(filtered_activities) < num_bullets:
        filtered_activities = activities

    # Adjust num_bullets based on job recency
    if not is_current_job:
        # Fewer bullets for previous jobs
        num_bullets = max(2, num_bullets - 1)

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
    used_verbs: list[str] = []

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
                    years_in_position, language, used_verbs, use_ai=True,
                    occupation_title=occupation_title
                )
                if bullet:
                    responsibilities.append(bullet)
    else:
        # Transform each activity to bullet with metrics (individual calls)
        for activity in selected_activities:
            bullet = transform_activity_to_bullet(
                activity, career_level, company, industry,
                years_in_position, language, used_verbs, use_ai=True,
                occupation_title=occupation_title
            )
            if bullet:
                responsibilities.append(bullet)

    # Validate and clean bullets
    validated_responsibilities, issues = validate_and_clean_bullets(
        responsibilities, career_level, language, max_attempts=3
    )

    # Validate metrics with metrics_validator (STRICT)
    validated_with_metrics = []
    rejected_bullets = []
    for bullet in validated_responsibilities:
        is_valid, error_msg, metric = validate_bullet_metrics(
            bullet, career_level)
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
        # Log consistency issues quietly and continue (tracked via quality scoring)
        logger.debug("Metric consistency issues: %s", consistency_issues[:2])

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
        bullet = generate_generic_responsibility(
            career_level, language, industry, occupation_title)
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
        bullet = generate_generic_responsibility(
            career_level, language, industry, occupation_title)
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
    # Industry-specific templates by language to avoid leaking German into FR/IT CVs
    industry_templates_by_lang = {
        "de": {
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
        },
        "fr": {
            "construction": {
                "junior": ["Réalisation de travaux sur {num} chantiers", "Participation à {num} projets de construction", "Soutien aux travaux de montage"],
                "mid": ["Coordination de {num} projets de construction", "Supervision des travaux sur {num} chantiers", "Planification de l'utilisation des matériaux"],
                "senior": ["Direction de {num} projets de construction", "Responsable de chantiers avec budget CHF {chf}", "Encadrement de {team} collaborateurs"],
                "lead": ["Direction du département construction avec {team} collaborateurs", "Responsabilité du chiffre d'affaires annuel CHF {chf}", "Planification stratégique des travaux"]
            },
            "technology": {
                "junior": ["Développement de {num} modules logiciels", "Traitement de {num} tickets de support", "Tests d'applications"],
                "mid": ["Réalisation de {num} projets IT", "Coordination avec {team} développeurs", "Implémentation de nouveaux systèmes"],
                "senior": ["Direction de {num} projets IT", "Architecture pour {num} systèmes", "Mentorat de {team} développeurs"],
                "lead": ["Direction de l'équipe IT avec {team} collaborateurs", "Responsable du budget IT CHF {chf}", "Planification IT stratégique"]
            },
            "healthcare": {
                "junior": ["Prise en charge de {num} patients par jour", "Documentation des soins", "Support à l'équipe soignante"],
                "mid": ["Coordination des soins pour {num} patients", "Encadrement de {team} apprentis", "Assurance qualité"],
                "senior": ["Direction de l'équipe de soins avec {team} collaborateurs", "Responsable d'une unité de {num} lits", "Formation du personnel"],
                "lead": ["Direction du service de soins", "Responsable de {team} collaborateurs", "Planification stratégique du personnel"]
            },
            "other": {
                "junior": ["Traitement de {num} commandes", "Participation à {num} projets", "Soutien à l'équipe"],
                "mid": ["Coordination de {num} projets", "Suivi de {num} clients", "Optimisation des processus"],
                "senior": ["Direction de {num} projets", "Encadrement de {team} collaborateurs", "Responsable d'un budget CHF {chf}"],
                "lead": ["Direction de l'équipe avec {team} collaborateurs", "Planification stratégique", "Responsable du chiffre d'affaires CHF {chf}"]
            }
        },
        "it": {
            "construction": {
                "junior": ["Esecuzione di lavori su {num} cantieri", "Partecipazione a {num} progetti di costruzione", "Supporto alle attività di montaggio"],
                "mid": ["Coordinamento di {num} progetti di costruzione", "Supervisione dei lavori su {num} cantieri", "Pianificazione dell'uso dei materiali"],
                "senior": ["Gestione di {num} progetti di costruzione", "Responsabile di cantieri con budget CHF {chf}", "Guida di {team} collaboratori"],
                "lead": ["Direzione del reparto costruzioni con {team} collaboratori", "Responsabilità fatturato annuo CHF {chf}", "Pianificazione strategica dei lavori"]
            },
            "technology": {
                "junior": ["Sviluppo di {num} moduli software", "Gestione di {num} ticket di supporto", "Test di applicazioni"],
                "mid": ["Realizzazione di {num} progetti IT", "Coordinamento con {team} sviluppatori", "Implementazione di nuovi sistemi"],
                "senior": ["Gestione di {num} progetti IT", "Architettura per {num} sistemi", "Mentoring di {team} sviluppatori"],
                "lead": ["Gestione del team IT con {team} collaboratori", "Responsabile del budget IT CHF {chf}", "Pianificazione IT strategica"]
            },
            "healthcare": {
                "junior": ["Assistenza a {num} pazienti al giorno", "Documentazione delle cure", "Supporto al team sanitario"],
                "mid": ["Coordinamento delle cure per {num} pazienti", "Formazione di {team} apprendisti", "Garanzia della qualità"],
                "senior": ["Gestione del team di cura con {team} collaboratori", "Responsabile di un reparto da {num} posti letto", "Formazione del personale"],
                "lead": ["Direzione del reparto assistenziale", "Responsabile di {team} collaboratori", "Pianificazione strategica del personale"]
            },
            "other": {
                "junior": ["Gestione di {num} ordini", "Partecipazione a {num} progetti", "Supporto al team"],
                "mid": ["Coordinamento di {num} progetti", "Gestione di {num} clienti", "Ottimizzazione dei processi"],
                "senior": ["Gestione di {num} progetti", "Guida di {team} collaboratori", "Responsabile di un budget CHF {chf}"],
                "lead": ["Direzione del team con {team} collaboratori", "Pianificazione strategica", "Responsabile del fatturato CHF {chf}"]
            }
        }
    }

    lang_key = (language or "de")[:2]
    templates_by_industry = industry_templates_by_lang.get(
        lang_key, industry_templates_by_lang["de"])

    templates_by_level = templates_by_industry.get(
        industry, templates_by_industry["other"])
    templates = templates_by_level.get(
        career_level, templates_by_level.get("mid", []))

    # Select random template
    template = random.choice(templates)

    # Generate realistic numbers based on career level
    level_scales = {"junior": (5, 15), "mid": (
        10, 25), "senior": (15, 40), "lead": (25, 60)}
    min_scale, max_scale = level_scales.get(career_level, (10, 25))

    num = random.randint(min_scale, max_scale)
    team = random.randint(3, 15) if career_level in [
        "senior", "lead"] else random.randint(2, 5)
    chf = random.choice([50000, 100000, 250000, 500000, 1000000, 2500000])

    # Fill template
    bullet = template.format(
        num=num, team=team, chf=f"{chf:,}".replace(",", "'"))

    # Ensure capital letter
    bullet = bullet[0].upper() + \
        bullet[1:] if len(bullet) > 1 else bullet.upper()

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
                    bullet = bullet.replace("strategisch", "").replace(
                        "Strategisch", "").strip()
                if "leitung" in bullet_lower and career_level == "junior":
                    bullet = bullet.replace("Leitung", "Unterstützung").replace(
                        "leitung", "unterstützung")

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
