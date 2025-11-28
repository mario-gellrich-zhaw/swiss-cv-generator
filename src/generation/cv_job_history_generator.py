"""
CV Job History Generator.

This module generates realistic job histories for personas with:
- Realistic timeline calculation (fixes Elternzeit problem)
- Company matching with industry validation
- High-quality text generation
- Career progression logic
- Text quality control

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

from src.database.queries import (
    get_occupation_by_id,
    get_skills_by_occupation,
    get_activities_by_occupation,
    sample_company_by_canton_and_industry
)
from src.database.mongodb_manager import get_db_manager
from src.generation.cv_activities_transformer import (
    generate_responsibilities_from_activities,
    filter_activities_by_career_level
)
from src.config import get_settings

settings = get_settings()

# Major Swiss companies by industry (fallback)
MAJOR_COMPANIES = {
    "technology": ["Google Switzerland", "Microsoft Schweiz", "IBM Schweiz", "Swisscom", "UBS Technology"],
    "finance": ["UBS", "Credit Suisse", "Zürcher Kantonalbank", "Raiffeisen", "PostFinance"],
    "healthcare": ["Roche", "Novartis", "Swissmedic", "Universitätsspital Zürich", "Inselspital Bern"],
    "construction": ["Implenia", "Losinger Marazzi", "Hochtief", "Zschokke", "Marti"],
    "manufacturing": ["ABB", "Schindler", "Rieter", "Bühler", "Georg Fischer"],
    "education": ["ETH Zürich", "Universität Zürich", "Universität Bern", "PH Zürich", "FHNW"],
    "retail": ["Migros", "Coop", "Denner", "Manor", "Globus"],
    "hospitality": ["Swissôtel", "Kempinski", "Grand Hotel", "Hotel Schweizerhof", "Baur au Lac"],
    "other": ["Swiss Post", "SBB", "Swisscom", "Swiss Re", "Zurich Insurance"]
}

# Action verbs by career level
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


def calculate_realistic_job_timeline(
    persona_age: int,
    years_experience: int,
    education_end_year: int
) -> List[Dict[str, Any]]:
    """
    Calculate realistic job timeline with proper gap handling.
    
    Args:
        persona_age: Persona's current age.
        years_experience: Total years of work experience.
        education_end_year: Year when education ended.
    
    Returns:
        List of job periods with gaps if needed.
    """
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Calculate number of jobs
    if years_experience <= 2:
        num_jobs = 1
    elif years_experience <= 6:
        num_jobs = 2
    elif years_experience <= 11:
        num_jobs = 3
    else:
        num_jobs = 4
    
    # First job starts: education_end_year + 0 to 6 months
    first_job_start_month = random.randint(1, 6)
    first_job_start_year = education_end_year
    
    # Calculate backwards from current
    periods = []
    remaining_years = years_experience
    current_end_year = current_year
    current_end_month = current_month
    elternzeit_used = False
    
    for job_num in range(num_jobs):
        is_current = (job_num == 0)
        
        if is_current:
            # Current job: 2-5 years (longer for senior/lead)
            duration_years = random.randint(2, 5)
            duration_months = random.randint(0, 11)
        else:
            # Previous jobs: 2-4 years, minimum 1 year
            duration_years = random.randint(2, 4)
            duration_months = random.randint(0, 11)
        
        # Ensure minimum 1 year
        if duration_years == 0 and duration_months < 12:
            duration_years = 1
            duration_months = 0
        
        # Calculate start date
        start_year = current_end_year
        start_month = current_end_month - duration_months
        if start_month <= 0:
            start_month += 12
            start_year -= 1
        start_year -= duration_years
        
        # Adjust for first job
        if job_num == num_jobs - 1:  # Oldest job
            start_year = first_job_start_year
            start_month = first_job_start_month
        
        # Calculate end date
        if is_current:
            end_year = None
            end_month = None
        else:
            end_year = current_end_year
            end_month = current_end_month
        
        periods.append({
            "start_year": start_year,
            "start_month": start_month,
            "end_year": end_year,
            "end_month": end_month,
            "duration_years": duration_years,
            "duration_months": duration_months,
            "is_current": is_current
        })
        
        # Update for next iteration
        if not is_current:
            # Check for gap before next job
            next_start_year = start_year
            next_start_month = start_month
            
            gap_months = (current_end_year - next_start_year) * 12 + (current_end_month - next_start_month)
            
            if gap_months > 6:
                # Insert gap filler
                gap_type = None
                if 6 <= gap_months <= 12:
                    gap_type = random.choice(["weiterbildung", "freelance"])
                elif 12 < gap_months <= 18 and not elternzeit_used:
                    gap_type = "elternzeit"
                    elternzeit_used = True
                elif gap_months > 18:
                    gap_type = "verschiedene_positionen"
                
                if gap_type:
                    gap_duration_months = gap_months - 1  # Leave 1 month buffer
                    gap_start_year = next_start_year
                    gap_start_month = next_start_month
                    
                    # Calculate gap end
                    gap_end_month = current_end_month - 1
                    gap_end_year = current_end_year
                    if gap_end_month <= 0:
                        gap_end_month += 12
                        gap_end_year -= 1
                    
                    periods.append({
                        "start_year": gap_start_year,
                        "start_month": gap_start_month,
                        "end_year": gap_end_year,
                        "end_month": gap_end_month,
                        "duration_years": gap_duration_months // 12,
                        "duration_months": gap_duration_months % 12,
                        "is_current": False,
                        "is_gap": True,
                        "gap_type": gap_type
                    })
            
            current_end_year = next_start_year
            current_end_month = next_start_month - 1
            if current_end_month <= 0:
                current_end_month = 12
                current_end_year -= 1
        
        remaining_years -= duration_years
    
    # Reverse to get chronological order (oldest first)
    periods.reverse()
    
    # Validate: sum of all periods + education ≈ age - 15 (±2 years)
    total_periods_years = sum(p.get("duration_years", 0) for p in periods if not p.get("is_gap", False))
    total_periods_months = sum(p.get("duration_months", 0) for p in periods if not p.get("is_gap", False))
    total_periods = total_periods_years + (total_periods_months / 12.0)
    
    expected_years = persona_age - 15
    discrepancy = abs(total_periods - expected_years)
    
    if discrepancy > 2.0:
        # Adjust first job start if needed
        if periods:
            first_period = periods[0]
            adjustment = expected_years - total_periods
            if abs(adjustment) <= 2:
                first_period["start_year"] = int(first_period.get("start_year", education_end_year) - adjustment)
    
    return periods


def get_realistic_company_for_job(
    canton: str,
    industry: str,
    occupation_industry: str,
    attempt: int = 0,
    used_companies: Optional[List[str]] = None
) -> Tuple[Dict[str, Any], str]:
    """
    Get realistic company for job with industry validation.
    
    Priority order:
    a) Companies in persona.canton + occupation.industry (strict match)
    b) Companies in different canton + occupation.industry
    c) Major Swiss companies in industry
    d) Generate realistic name
    
    Args:
        canton: Persona's canton.
        industry: Persona's industry.
        occupation_industry: Occupation's industry (must match).
        attempt: Current attempt number.
        used_companies: List of already used company names.
    
    Returns:
        Tuple of (company_dict, match_quality).
    """
    if used_companies is None:
        used_companies = []
    
    db_manager = get_db_manager()
    db_manager.connect()
    companies_col = db_manager.get_target_collection("companies")
    
    # Priority 1: Strict match (canton + industry)
    if attempt == 0:
        companies = list(companies_col.find({
            "canton_code": canton,
            "industry": occupation_industry
        }))
        
        # Filter out used companies
        companies = [c for c in companies if c.get("name") not in used_companies]
        
        if companies:
            company = random.choice(companies)
            if company.get("industry") == occupation_industry:
                return company, "perfect"
    
    # Priority 2: Industry match, different canton
    if attempt <= 1:
        companies = list(companies_col.find({
            "industry": occupation_industry
        }))
        
        companies = [c for c in companies if c.get("name") not in used_companies]
        
        if companies:
            company = random.choice(companies)
            if company.get("industry") == occupation_industry:
                return company, "canton_mismatch"
    
    # Priority 3: Major Swiss companies
    if attempt <= 2:
        major_companies = MAJOR_COMPANIES.get(occupation_industry, [])
        if major_companies:
            company_name = random.choice(major_companies)
            if company_name not in used_companies:
                return {
                    "name": company_name,
                    "canton_code": canton,
                    "industry": occupation_industry,
                    "size_band": "large",
                    "is_real": True
                }, "generated"
    
    # Priority 4: Generate realistic name
    industry_terms = {
        "technology": ["Tech", "Solutions", "Systems", "Digital", "IT"],
        "finance": ["Finanz", "Bank", "Vermögen", "Invest", "Capital"],
        "healthcare": ["Medizin", "Gesundheit", "Care", "Health", "Klinik"],
        "construction": ["Bau", "Construction", "Architektur", "Planung"],
        "manufacturing": ["Industrie", "Produktion", "Manufacturing", "Werke"],
        "education": ["Bildung", "Education", "Akademie", "Institut"],
        "retail": ["Retail", "Handel", "Commerce", "Markt"],
        "hospitality": ["Hotel", "Gastronomie", "Tourismus", "Service"],
        "other": ["Services", "AG", "GmbH", "Sàrl"]
    }
    
    legal_forms = ["AG", "GmbH", "Sàrl", "SA"]
    terms = industry_terms.get(occupation_industry, ["Services"])
    term = random.choice(terms)
    legal_form = random.choice(legal_forms)
    
    company_name = f"{canton} {term} {legal_form}"
    
    return {
        "name": company_name,
        "canton_code": canton,
        "industry": occupation_industry,
        "size_band": "small",
        "is_real": False
    }, "generated"


def clean_job_text(text: str, career_level: str) -> str:
    """
    Clean and improve job text quality.
    
    Args:
        text: Raw text.
        career_level: Career level for verb selection.
    
    Returns:
        Cleaned text.
    """
    if not text:
        return ""
    
    # Remove duplicates (case-insensitive)
    words = text.split()
    seen = set()
    cleaned_words = []
    for word in words:
        word_lower = word.lower()
        if word_lower not in seen:
            cleaned_words.append(word)
            seen.add(word_lower)
        elif word[0].isupper():  # Keep capitalized versions
            cleaned_words.append(word)
    
    text = " ".join(cleaned_words)
    
    # Remove duplicate phrases
    text = re.sub(r'\b(\w+(?:\s+\w+){1,3})\s+\1\b', r'\1', text, flags=re.IGNORECASE)
    
    # Ensure capitalization at start
    if text and not text[0].isupper():
        text = text[0].upper() + text[1:]
    
    # Remove generic fillers
    fillers = ["erfolgreich", "professionell", "kompetent"]
    for filler in fillers:
        text = re.sub(rf'\b{filler}\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text)  # Clean up extra spaces
    
    return text.strip()


def ensure_logical_progression(
    job_history: List[Dict[str, Any]],
    career_level: str
) -> List[Dict[str, Any]]:
    """
    Ensure logical career progression in job titles and responsibilities.
    
    Args:
        job_history: List of job entries (oldest first).
        career_level: Current career level.
    
    Returns:
        Job history with logical progression.
    """
    if not job_history:
        return job_history
    
    # Career level progression
    level_progression = {
        "junior": ["junior"],
        "mid": ["junior", "mid"],
        "senior": ["junior", "mid", "senior"],
        "lead": ["junior", "mid", "senior", "lead"]
    }
    
    progression = level_progression.get(career_level, ["mid", "senior"])
    
    # Sort by start_date (oldest first)
    sorted_jobs = sorted(
        job_history,
        key=lambda j: (int(j.get("start_date", "2000-01").split("-")[0]), int(j.get("start_date", "2000-01").split("-")[1]) if "-" in j.get("start_date", "") else 1)
    )
    
    # Assign career levels to jobs
    num_jobs = len(sorted_jobs)
    for i, job in enumerate(sorted_jobs):
        if i < len(progression):
            job_level = progression[i]
        else:
            job_level = progression[0] if i == 0 else progression[-1]
        
        # Update position title if needed
        base_title = job.get("position", "")
        if "Senior" not in base_title and "Lead" not in base_title and "Leiter" not in base_title:
            if job_level == "senior":
                job["position"] = f"Senior {base_title}"
            elif job_level == "lead":
                job["position"] = f"Leiter {base_title}" if random.random() < 0.5 else f"Lead {base_title}"
        
        # Ensure responsibilities increase in complexity
        responsibilities = job.get("responsibilities", [])
        if i == 0:  # Oldest job
            # Simple responsibilities
            job["responsibilities"] = responsibilities[:2] if len(responsibilities) > 2 else responsibilities
        elif i == num_jobs - 1:  # Current job
            # Most complex responsibilities
            job["responsibilities"] = responsibilities[:5] if len(responsibilities) > 5 else responsibilities
        else:
            # Medium complexity
            job["responsibilities"] = responsibilities[:3] if len(responsibilities) > 3 else responsibilities
    
    return sorted_jobs


def generate_job_entry(
    persona: Dict[str, Any],
    occupation_doc: Dict[str, Any],
    period: Dict[str, Any],
    job_index: int,
    total_jobs: int,
    used_companies: List[str],
    language: str = "de"
) -> Dict[str, Any]:
    """
    Generate a single job entry with high quality.
    
    Args:
        persona: Persona dictionary.
        occupation_doc: Occupation document.
        period: Timeline period for this job.
        job_index: Index of this job (0 = oldest, total_jobs-1 = current).
        total_jobs: Total number of jobs.
        used_companies: List of already used company names.
        language: Language (de, fr, it).
    
    Returns:
        Job entry dictionary.
    """
    is_current = period.get("is_current", False)
    is_gap = period.get("is_gap", False)
    gap_type = period.get("gap_type")
    
    # Handle gap fillers
    if is_gap:
        gap_names = {
            "weiterbildung": "Weiterbildung / Fortbildung",
            "freelance": "Freelance-Projekte",
            "elternzeit": "Elternzeit",
            "verschiedene_positionen": f"Verschiedene Positionen in {persona.get('industry', 'verschiedenen Bereichen')}"
        }
        
        return {
            "company": gap_names.get(gap_type, "Weiterbildung"),
            "position": gap_names.get(gap_type, "Weiterbildung"),
            "location": persona.get("canton", ""),
            "start_date": f"{period['start_year']}-{period['start_month']:02d}",
            "end_date": f"{period['end_year']}-{period['end_month']:02d}" if period.get("end_year") else None,
            "is_current": False,
            "responsibilities": [],
            "technologies": [],
            "category": "gap_filler"
        }
    
    # Determine career level for this job
    career_level = persona.get("career_level", "mid")
    if is_current:
        job_career_level = career_level
    else:
        # Previous jobs: show progression
        if total_jobs == 2:
            job_career_level = "junior" if job_index == 0 else career_level
        elif total_jobs == 3:
            if job_index == 0:
                job_career_level = "junior"
            elif job_index == 1:
                job_career_level = "mid"
            else:
                job_career_level = career_level
        else:  # 4 jobs
            if job_index == 0:
                job_career_level = "junior"
            elif job_index == 1:
                job_career_level = "mid"
            elif job_index == 2:
                job_career_level = "senior" if career_level in ["senior", "lead"] else "mid"
            else:
                job_career_level = career_level
    
    # Get company with industry validation
    canton = persona.get("canton", "ZH")
    industry = persona.get("industry", "other")
    occupation_industry = industry  # Assume occupation matches persona industry
    
    # Try to get occupation industry from document
    if occupation_doc:
        # Try to infer industry from berufsfeld
        berufsfelder = occupation_doc.get("categories", {}).get("berufsfelder", [])
        if berufsfelder:
            # Use industry mapping if available
            from src.data.models import Industry
            # For now, use persona industry
            occupation_industry = industry
    
    company, match_quality = get_realistic_company_for_job(
        canton, industry, occupation_industry,
        attempt=0, used_companies=used_companies
    )
    
    company_name = company.get("name", "Company AG")
    used_companies.append(company_name)
    
    # Get position title
    occupation_title = persona.get("occupation", persona.get("current_title", "Engineer"))
    position = get_career_level_title(occupation_title, job_career_level, avoid_repetition=True)
    
    # Get responsibilities
    job_id = persona.get("job_id")
    activities = get_activities_by_occupation(job_id) if job_id else []
    
    # Get industry and years in position
    industry = persona.get("industry", "other")
    years_in_position = period.get("duration_years", 2)
    
    if is_current:
        # Current job: 4-5 bullets
        num_bullets = random.randint(4, 5)
        responsibilities = generate_responsibilities_from_activities(
            job_id, job_career_level, company_name, language,
            num_bullets=num_bullets, is_current_job=True,
            industry=industry, years_in_position=years_in_position
        )
    else:
        # Previous jobs: 2-3 bullets (decreasing for older)
        num_bullets = max(2, 4 - job_index)
        responsibilities = generate_responsibilities_from_activities(
            job_id, job_career_level, company_name, language,
            num_bullets=num_bullets, is_current_job=False,
            industry=industry, years_in_position=years_in_position
        )
    
    # Clean responsibilities
    cleaned_responsibilities = []
    seen_bullets = set()
    for resp in responsibilities:
        cleaned = clean_job_text(resp, job_career_level)
        if cleaned and cleaned.lower() not in seen_bullets:
            cleaned_responsibilities.append(cleaned)
            seen_bullets.add(cleaned.lower())
    
    # Ensure we have enough bullets
    if len(cleaned_responsibilities) < num_bullets:
        # Generate fallback bullets
        verbs = ACTION_VERBS.get(job_career_level, ACTION_VERBS["mid"])
        for i in range(num_bullets - len(cleaned_responsibilities)):
            verb = random.choice(verbs)
            bullet = f"{verb} {occupation_title.lower()}-bezogene Aufgaben"
            if bullet.lower() not in seen_bullets:
                cleaned_responsibilities.append(bullet)
                seen_bullets.add(bullet.lower())
    
    # Get technologies
    if is_current:
        technologies = get_technologies_from_skills(job_id, limit=8)
    else:
        # Older technologies for previous jobs
        years_ago = datetime.now().year - period.get("end_year", datetime.now().year)
        current_techs = get_technologies_from_skills(job_id, limit=8)
        technologies = get_older_technologies(current_techs, years_ago)
    
    return {
        "company": company_name,
        "position": position,
        "location": canton,
        "start_date": f"{period['start_year']}-{period['start_month']:02d}",
        "end_date": None if is_current else f"{period['end_year']}-{period['end_month']:02d}",
        "is_current": is_current,
        "responsibilities": cleaned_responsibilities[:num_bullets],
        "technologies": technologies,
        "category": industry,
        "company_match_quality": match_quality
    }


def get_career_level_title(base_title: str, career_level: str, avoid_repetition: bool = True) -> str:
    """
    Add career level prefix to occupation title, avoiding repetition.
    
    Args:
        base_title: Base occupation title.
        career_level: Career level (junior, mid, senior, lead).
        avoid_repetition: Avoid adding prefix if already present.
    
    Returns:
        Title with career level prefix.
    """
    base_lower = base_title.lower()
    
    if career_level == "junior":
        # Check if already has junior prefix
        if "junior" in base_lower or "trainee" in base_lower:
            return base_title
        return base_title  # Junior typically no prefix
    
    elif career_level == "mid":
        # Check if already has mid/senior/lead prefix
        if any(prefix in base_lower for prefix in ["senior", "lead", "leiter", "manager"]):
            return base_title
        return base_title  # Mid typically no prefix
    
    elif career_level == "senior":
        # Check if already has senior prefix
        if "senior" in base_lower:
            return base_title
        if "lead" in base_lower or "leiter" in base_lower:
            # Already higher level, keep as is
            return base_title
        return f"Senior {base_title}"
    
    elif career_level == "lead":
        # Check if already has lead/leiter prefix
        if "leiter" in base_lower or "lead" in base_lower or "manager" in base_lower:
            return base_title
        if "senior" in base_lower:
            # Replace senior with lead
            return base_title.replace("Senior", "Leiter").replace("Senior", "Lead")
        return f"Leiter {base_title}" if random.random() < 0.5 else f"Lead {base_title}"
    
    return base_title


def get_older_technologies(technologies: List[str], years_ago: int) -> List[str]:
    """
    Get older versions of technologies for historical positions.
    
    Args:
        technologies: Current technologies.
        years_ago: How many years ago.
    
    Returns:
        List of older technology names.
    """
    technology_evolution = {
        "Python": ["Python 2.7", "Python 2"],
        "JavaScript": ["ES5", "jQuery", "JavaScript"],
        "React": ["jQuery", "Backbone.js", "AngularJS"],
        "Vue.js": ["jQuery", "Backbone.js"],
        "TypeScript": ["JavaScript", "ES5"],
        "Docker": ["VirtualBox", "VMware"],
        "Kubernetes": ["Docker", "Docker Compose"],
        "AWS": ["On-premise", "Private Cloud"],
        "Git": ["SVN", "CVS"],
        "PostgreSQL": ["MySQL", "PostgreSQL 9"],
        "MongoDB": ["MySQL", "PostgreSQL"],
    }
    
    older_techs = []
    for tech in technologies[:5]:
        found = False
        for current, older_list in technology_evolution.items():
            if current.lower() in tech.lower():
                if years_ago > 5:
                    older_techs.append(older_list[-1] if older_list else tech)
                else:
                    older_techs.append(older_list[0] if older_list else tech)
                found = True
                break
        if not found:
            older_techs.append(tech)
    
    return older_techs[:5]


def get_technologies_from_skills(job_id: Optional[str], limit: int = 8) -> List[str]:
    """
    Get top technologies from occupation skills.
    
    Args:
        job_id: Occupation job_id.
        limit: Maximum number of technologies.
    
    Returns:
        List of technology names.
    """
    if not job_id:
        return []
    
    skills = get_skills_by_occupation(job_id)
    
    technical_skills = [
        s.get("skill_name_de", "")
        for s in skills
        if s.get("skill_category") == "technical"
    ]
    
    # Sort by importance
    technical_skills.sort(
        key=lambda x: next(
            (s.get("importance", 0) for s in skills if s.get("skill_name_de") == x),
            0
        ),
        reverse=True
    )
    
    return technical_skills[:limit]


def generate_job_history(
    persona: Dict[str, Any],
    occupation_doc: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Generate job history for a persona with realistic timeline and quality.
    
    Args:
        persona: Persona dictionary with age, years_experience, job_id, company, etc.
        occupation_doc: Optional occupation document from CV_DATA.
    
    Returns:
        List of job entries with structure:
        {
            "company": str,
            "position": str,
            "location": str,
            "start_date": str (YYYY-MM),
            "end_date": Optional[str] (YYYY-MM or None for current),
            "is_current": bool,
            "responsibilities": List[str],
            "technologies": List[str],
            "category": str,
            "company_match_quality": str
        }
    """
    persona_age = persona.get("age", 25)
    years_experience = persona.get("years_experience", 0)
    job_id = persona.get("job_id")
    language = persona.get("language", "de")
    
    # Get occupation document if not provided
    if not occupation_doc and job_id:
        occupation_doc = get_occupation_by_id(job_id)
    
    if not occupation_doc:
        # Fallback: minimal job history
        return [{
            "company": persona.get("company", "Company AG"),
            "position": persona.get("occupation", "Engineer"),
            "location": persona.get("canton", "ZH"),
            "start_date": f"{datetime.now().year - years_experience}-01",
            "end_date": None,
            "is_current": True,
            "responsibilities": [],
            "technologies": [],
            "category": persona.get("industry", "other")
        }]
    
    # Calculate education end year (approximate)
    education_end_year = datetime.now().year - years_experience - persona_age + 18
    if education_end_year < 2000:
        education_end_year = 2000
    
    # Calculate realistic timeline
    periods = calculate_realistic_job_timeline(
        persona_age, years_experience, education_end_year
    )
    
    # Generate job entries
    job_history = []
    used_companies = []
    
    for i, period in enumerate(periods):
        if period.get("is_gap", False):
            # Generate gap filler
            gap_names = {
                "weiterbildung": "Weiterbildung / Fortbildung",
                "freelance": "Freelance-Projekte",
                "elternzeit": "Elternzeit",
                "verschiedene_positionen": f"Verschiedene Positionen in {persona.get('industry', 'verschiedenen Bereichen')}"
            }
            gap_type = period.get("gap_type", "weiterbildung")
            
            job_entry = {
                "company": gap_names.get(gap_type, "Weiterbildung"),
                "position": gap_names.get(gap_type, "Weiterbildung"),
                "location": persona.get("canton", ""),
                "start_date": f"{period['start_year']}-{period['start_month']:02d}",
                "end_date": f"{period['end_year']}-{period['end_month']:02d}",
                "is_current": False,
                "responsibilities": [],
                "technologies": [],
                "category": "gap_filler"
            }
        else:
            # Generate real job entry
            job_entry = generate_job_entry(
                persona, occupation_doc, period, i, len(periods),
                used_companies, language
            )
        
        job_history.append(job_entry)
    
    # Ensure logical progression
    job_history = ensure_logical_progression(job_history, persona.get("career_level", "mid"))
    
    # Sort by start_date (most recent first for CV display)
    job_history.sort(
        key=lambda x: (
            int(x.get("start_date", "2000-01").split("-")[0]),
            int(x.get("start_date", "2000-01").split("-")[1]) if "-" in x.get("start_date", "") else 1
        ),
        reverse=True
    )
    
    return job_history


def validate_job_history(
    job_history: List[Dict[str, Any]],
    persona_age: int,
    years_experience: int
) -> List[Dict[str, Any]]:
    """
    Validate job history timeline consistency.
    
    Args:
        job_history: List of job entries.
        persona_age: Persona's current age.
        years_experience: Years of work experience.
    
    Returns:
        Validated job history.
    """
    if not job_history:
        return job_history
    
    current_year = datetime.now().year
    birth_year = current_year - persona_age
    
    validated = []
    
    for job in job_history:
        start_date = job.get("start_date", "")
        end_date = job.get("end_date")
        is_current = job.get("is_current", False)
        
        if start_date:
            try:
                start_year = int(start_date.split("-")[0])
                
                # Check: Job shouldn't start before minimum work age
                if start_year < birth_year + 18:
                    start_year = birth_year + 18
                    job["start_date"] = f"{start_year}-01"
                
                # Check: Job shouldn't start after current year
                if start_year > current_year:
                    start_year = current_year - 1
                    job["start_date"] = f"{start_year}-01"
                
                # Validate end_date
                if end_date:
                    end_year = int(end_date.split("-")[0])
                    if end_year < start_year:
                        end_year = start_year + 1
                    if end_year > current_year:
                        end_year = current_year
                    job["end_date"] = f"{end_year}-12"
                elif not is_current:
                    # Previous job should have end_date
                    start_year = int(job["start_date"].split("-")[0])
                    end_year = min(start_year + 2, current_year - 1)
                    job["end_date"] = f"{end_year}-12"
                
            except (ValueError, IndexError):
                pass
        
        validated.append(job)
    
    return validated


def get_job_history_summary(job_history: List[Dict[str, Any]]) -> str:
    """
    Generate a text summary of job history.
    
    Args:
        job_history: List of job entries.
    
    Returns:
        Formatted job history summary string.
    """
    if not job_history:
        return "Keine Berufserfahrung verfügbar."
    
    summary_parts = []
    
    for job in job_history:
        if job.get("category") == "gap_filler":
            continue
        
        company = job.get("company", "")
        position = job.get("position", "")
        start_date = job.get("start_date", "")
        end_date = job.get("end_date", "heute")
        
        if company and position:
            start_year = start_date.split("-")[0] if start_date else "?"
            end_year = end_date.split("-")[0] if end_date else "heute"
            summary_parts.append(f"{position} bei {company} ({start_year}-{end_year})")
    
    return " | ".join(summary_parts) if summary_parts else "Keine Berufserfahrung verfügbar."
