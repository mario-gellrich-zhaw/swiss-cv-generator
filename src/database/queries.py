"""
Database query functions for Swiss CV Generator.

This module provides query functions for:
- Cantons, Occupations, Names, Companies, Skills, Activities (existing)
- Demographic queries (age, gender, career level, portraits)
- Industry-weighted sampling

All functions use MongoDB collections from target_db and source_db.
"""
import random
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict

from .mongodb_manager import get_db_manager
from ..config import get_settings

settings = get_settings()

# Cache for demographic config
_demographic_config_cache: Optional[Dict[str, Any]] = None
_portrait_index_cache: Optional[Dict[str, Any]] = None
_industry_percentages_cache: Optional[Dict[str, float]] = None


def _load_demographic_config() -> Dict[str, Any]:
    """Load demographic configuration from MongoDB or cache."""
    global _demographic_config_cache
    
    if _demographic_config_cache is not None:
        return _demographic_config_cache
    
    db_manager = get_db_manager()
    db_manager.connect()
    
    config_col = db_manager.get_target_collection("demographic_config")
    config_doc = config_col.find_one({"version": "1.0"})
    
    if config_doc and "config" in config_doc:
        _demographic_config_cache = config_doc["config"]
    else:
        # Fallback to JSON file
        config_file = Path(__file__).parent.parent.parent / "data" / "sampling_weights.json"
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                _demographic_config_cache = json.load(f)
        else:
            # Default values
            _demographic_config_cache = {
                "age_groups": {
                    "18-25": {"weight": 7.6},
                    "26-40": {"weight": 18.5},
                    "41-65": {"weight": 31.0}
                },
                "gender_distribution": {
                    "male": {"percentage": 50.1},
                    "female": {"percentage": 49.9}
                }
            }
    
    return _demographic_config_cache


def _load_portrait_index() -> Dict[str, Any]:
    """Load portrait index from JSON file."""
    global _portrait_index_cache
    
    if _portrait_index_cache is not None:
        return _portrait_index_cache
    
    index_file = Path(__file__).parent.parent.parent / "data" / "portraits" / "portrait_index.json"
    
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            _portrait_index_cache = data.get("portrait_index", {})
    else:
        _portrait_index_cache = {
            "male": {"18-25": [], "26-40": [], "41-65": []},
            "female": {"18-25": [], "26-40": [], "41-65": []}
        }
    
    return _portrait_index_cache


def _load_industry_percentages() -> Dict[str, float]:
    """Load industry employment percentages from branch data."""
    global _industry_percentages_cache
    
    if _industry_percentages_cache is not None:
        return _industry_percentages_cache
    
    # Load from demographics.json or Branchenverteilung.json
    demo_file = Path(__file__).parent.parent.parent / "data" / "demographics.json"
    branch_file = Path(__file__).parent.parent.parent / "data" / "source" / "Branchenverteilung.json"
    
    _industry_percentages_cache = {}
    
    # Try demographics.json first
    if demo_file.exists():
        with open(demo_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            branch_data = data.get("branch_distribution", {})
            if isinstance(branch_data, dict):
                _industry_percentages_cache = branch_data
    
    # Fallback to Branchenverteilung.json
    if not _industry_percentages_cache and branch_file.exists():
        with open(branch_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            arbeitsgesellschaft = data.get("arbeitsgesellschaft_branchenverteilung", {})
            daten_list = arbeitsgesellschaft.get("daten_in_prozent", [])
            
            for item in daten_list:
                if isinstance(item, dict):
                    branche = item.get("branche", "")
                    anteil = item.get("anteil_prozent", 0)
                    if branche and anteil:
                        _industry_percentages_cache[branche] = float(anteil)
    
    return _industry_percentages_cache


# ============================================================================
# EXISTING QUERIES: Cantons, Occupations, Names, Companies, Skills
# ============================================================================

def get_canton_by_code(canton_code: str) -> Optional[Dict[str, Any]]:
    """Get canton by code from target_db."""
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_target_collection("cantons")
    return collection.find_one({"code": canton_code})


def sample_canton_weighted() -> Optional[Dict[str, Any]]:
    """Sample canton weighted by population."""
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_target_collection("cantons")
    
    cantons = list(collection.find({}))
    if not cantons:
        return None
    
    weights = [c.get("population", 1) for c in cantons]
    return random.choices(cantons, weights=weights, k=1)[0]


def get_occupation_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    """Get occupation by job_id from source_db."""
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_source_collection(settings.mongodb_collection_occupations)
    return collection.find_one({"job_id": job_id})


# Bildungstyp hierarchy for career levels
BILDUNGSTYP_HIERARCHY = {
    "Grundbildung (Lehre)": 0,  # Junior
    "Berufsfunktion / Spezialisierung": 1,  # Mid
    "Berufsfunktion / Spezialisierung - Weiterbildungsberuf": 1,
    "Weiterbildungsberuf": 2,  # Senior
    "Berufsfunktion / Spezialisierung - Hochschulberuf": 2,
    "Hochschulberuf - Weiterbildungsberuf": 2,
    "Hochschulberuf": 3,  # Lead
}

CAREER_LEVEL_TO_BILDUNG = {
    "junior": 0,
    "mid": 1,
    "senior": 2,
    "lead": 3,
}


def get_related_occupations_by_berufsfeld(
    berufsfelder: List[str],
    target_career_level: str,
    exclude_job_ids: List[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Find related occupations in the same Berufsfeld with appropriate Bildungstyp.
    
    This enables realistic career progression - e.g., a Koch EFZ (Junior) 
    can progress to Küchenchef (Senior) within Gastgewerbe.
    
    Args:
        berufsfelder: List of berufsfelder to search in.
        target_career_level: Target career level (junior, mid, senior, lead).
        exclude_job_ids: Job IDs to exclude (already used).
        limit: Maximum results.
    
    Returns:
        List of related occupation documents.
    """
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_source_collection(settings.mongodb_collection_occupations)
    
    if not berufsfelder:
        return []
    
    # Normalize berufsfelder
    if isinstance(berufsfelder, str):
        berufsfelder = [berufsfelder]
    
    # Get target bildungstyp level
    target_level = CAREER_LEVEL_TO_BILDUNG.get(target_career_level, 1)
    
    # Find bildungstypen for this level
    matching_bildungstypen = [
        bt for bt, level in BILDUNGSTYP_HIERARCHY.items()
        if level == target_level
    ]
    
    # Build query
    query = {
        "categories.berufsfelder": {"$in": berufsfelder},
        "data_completeness.completeness_score": {"$gte": 0.7}
    }
    
    if matching_bildungstypen:
        query["categories.bildungstypen"] = {"$in": matching_bildungstypen}
    
    if exclude_job_ids:
        query["job_id"] = {"$nin": exclude_job_ids}
    
    # Find occupations
    occupations = list(collection.find(query).limit(limit))
    
    return occupations


def get_career_progression_title(
    base_occupation_doc: Dict[str, Any],
    target_career_level: str,
    job_index: int = 0,
    total_jobs: int = 1,
    is_current_job: bool = False,
    used_titles: List[str] = None
) -> Tuple[str, Optional[str]]:
    """
    Get an appropriate job title for a career progression step.
    
    Jobs are ordered chronologically (oldest first, current last).
    Ensures realistic progression within the SAME or closely related Berufsfeld.
    
    Args:
        base_occupation_doc: The base occupation document.
        target_career_level: Target career level for this specific job.
        job_index: Index of job in chronological order (0=oldest, higher=newer).
        total_jobs: Total number of jobs.
        is_current_job: Whether this is the current (most recent) job.
        used_titles: Already used titles to avoid repetition.
    
    Returns:
        Tuple of (title, job_id or None if modified).
    """
    if used_titles is None:
        used_titles = []
    
    base_title = base_occupation_doc.get("title", "Fachperson")
    base_job_id = base_occupation_doc.get("job_id")
    berufsfelder = base_occupation_doc.get("categories", {}).get("berufsfelder", [])
    
    if isinstance(berufsfelder, str):
        berufsfelder = [berufsfelder]
    
    # For CURRENT job (the most recent), always use base title
    if is_current_job:
        title = _add_career_prefix(base_title, target_career_level)
        return title, base_job_id
    
    # For PREVIOUS jobs (older), try to find related occupation in SAME Berufsfeld
    # Priority: Same Berufsfeld > Related Berufsfeld > Base title with prefix
    
    # Try to find strictly related occupations
    related = get_related_occupations_by_berufsfeld(
        berufsfelder,
        target_career_level,
        exclude_job_ids=[base_job_id] if base_job_id else [],
        limit=30
    )
    
    # Filter out already used titles and ensure same Berufsfeld
    available = []
    for occ in related:
        occ_title = occ.get("title", "")
        occ_berufsfelder = occ.get("categories", {}).get("berufsfelder", [])
        if isinstance(occ_berufsfelder, str):
            occ_berufsfelder = [occ_berufsfelder]
        
        # Check if at least one Berufsfeld overlaps
        if not any(bf in berufsfelder for bf in occ_berufsfelder):
            continue
        
        # Check title not already used
        if occ_title.lower() in [t.lower() for t in used_titles]:
            continue
        
        available.append(occ)
    
    if available:
        # Pick a random related occupation from same Berufsfeld
        chosen = random.choice(available)
        title = _add_career_prefix(chosen.get("title", base_title), target_career_level)
        return title, chosen.get("job_id")
    
    # Fallback: use base title with prefix (stay in same field)
    title = _add_career_prefix(base_title, target_career_level)
    return title, base_job_id


def _add_career_prefix(title: str, career_level: str) -> str:
    """Add career level prefix to title if appropriate."""
    title_lower = title.lower()
    
    # Don't add prefix if already present
    if any(prefix in title_lower for prefix in ["senior", "junior", "lead", "leiter", "chef", "meister"]):
        return title
    
    if career_level == "junior":
        # Junior: no prefix, just base title
        return title
    elif career_level == "mid":
        # Mid: no prefix
        return title
    elif career_level == "senior":
        return f"Senior {title}"
    elif career_level == "lead":
        # Vary between Lead/Leiter/Chef
        prefixes = ["Leiter/in", "Lead", "Chef/in"]
        return f"{random.choice(prefixes)} {title}"
    
    return title


def sample_occupation_by_industry(industry: str) -> Optional[Dict[str, Any]]:
    """Sample occupation by industry from source_db."""
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_source_collection(settings.mongodb_collection_occupations)
    
    # Use industry mapping from cv_data_mapping.json
    mapping_file = Path(__file__).parent.parent.parent / "data" / "cv_data_mapping.json"
    industry_mapping = {}
    
    if mapping_file.exists():
        with open(mapping_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            industry_mapping = data.get("industry_mapping", {})
    
    # Find berufsfelder that map to this industry
    matching_berufsfelder = [
        bf for bf, ind in industry_mapping.items() if ind == industry
    ]
    
    if matching_berufsfelder:
        query = {
            "categories.berufsfelder": {"$in": matching_berufsfelder},
            "data_completeness.completeness_score": {"$gte": 0.8}
        }
    else:
        # Fallback: try to find by any field
        query = {"data_completeness.completeness_score": {"$gte": 0.8}}
    
    occupations = list(collection.find(query))
    if not occupations:
        return None
    
    return random.choice(occupations)


def sample_first_name(language: str, gender: str) -> Optional[Dict[str, Any]]:
    """Sample first name by language and gender from target_db."""
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_target_collection("first_names")
    
    names = list(collection.find({
        "language": language,
        "gender": gender
    }))
    
    if not names:
        return None
    
    # Weight by frequency
    weights = [n.get("frequency", 1) for n in names]
    return random.choices(names, weights=weights, k=1)[0]


def sample_last_name(language: str) -> Optional[Dict[str, Any]]:
    """Sample last name by language from target_db."""
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_target_collection("last_names")
    
    names = list(collection.find({"language": language}))
    
    if not names:
        return None
    
    # Weight by frequency
    weights = [n.get("frequency", 1) for n in names]
    return random.choices(names, weights=weights, k=1)[0]


def sample_company_by_canton_and_industry(canton_code: str, industry: str) -> Optional[Dict[str, Any]]:
    """Sample company by canton and industry from target_db."""
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_target_collection("companies")
    
    companies = list(collection.find({
        "canton_code": canton_code,
        "industry": industry
    }))
    
    if not companies:
        # Fallback: try just canton
        companies = list(collection.find({"canton_code": canton_code}))
    
    if not companies:
        # Fallback: any company
        companies = list(collection.find({}))
    
    if not companies:
        return None
    
    return random.choice(companies)


def get_skills_by_occupation(job_id: str) -> List[Dict[str, Any]]:
    """Get skills for an occupation from target_db."""
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_target_collection("occupation_skills")
    
    return list(collection.find({"job_id": job_id}))


def get_activities_by_occupation(job_id: str) -> Optional[List[str]]:
    """Get activities for an occupation from source_db."""
    db_manager = get_db_manager()
    db_manager.connect()
    collection = db_manager.get_source_collection(settings.mongodb_collection_occupations)
    
    occ = collection.find_one({"job_id": job_id})
    if not occ:
        return None
    
    taetigkeiten = occ.get("taetigkeiten", {})
    if isinstance(taetigkeiten, dict):
        kategorien = taetigkeiten.get("kategorien", [])
        if isinstance(kategorien, list):
            return kategorien
    
    return []


# ============================================================================
# NEW: DEMOGRAPHIC QUERIES
# ============================================================================

def sample_age_group() -> str:
    """
    Sample age group weighted by demographic data.
    
    Returns:
        Age group string: "18-25", "26-40", or "41-65"
        Weights: 7.6%, 18.5%, 31.0%
    """
    config = _load_demographic_config()
    age_groups = config.get("age_groups", {})
    
    groups = []
    weights = []
    
    for age_group, data in age_groups.items():
        groups.append(age_group)
        weights.append(data.get("weight", 0))
    
    if not groups:
        # Default fallback
        return random.choice(["18-25", "26-40", "41-65"])
    
    return random.choices(groups, weights=weights, k=1)[0]


def sample_gender() -> str:
    """
    Sample gender weighted by demographic data.
    
    Returns:
        Gender string: "male" or "female"
        Weights: 50.1% male, 49.9% female
    """
    config = _load_demographic_config()
    gender_dist = config.get("gender_distribution", {})
    
    male_pct = gender_dist.get("male", {}).get("percentage", 50.1)
    female_pct = gender_dist.get("female", {}).get("percentage", 49.9)
    
    return random.choices(
        ["male", "female"],
        weights=[male_pct, female_pct],
        k=1
    )[0]


def determine_career_level_by_age(age_group: str, years_experience: int) -> str:
    """
    Determine career level based on age group and years of experience.
    
    Args:
        age_group: Age group string ("18-25", "26-40", "41-65")
        years_experience: Years of work experience
    
    Returns:
        Career level: "junior", "mid", "senior", or "lead"
    """
    config = _load_demographic_config()
    age_groups = config.get("age_groups", {})
    
    if age_group not in age_groups:
        # Fallback logic
        if years_experience < 3:
            return "junior"
        elif years_experience < 7:
            return "mid"
        elif years_experience < 12:
            return "senior"
        else:
            return "lead"
    
    # Get career level distribution for this age group
    career_dist = age_groups[age_group].get("career_level_distribution", {})
    
    # Adjust based on years_experience for edge cases
    if age_group == "18-25":
        # Mostly junior, but consider experience
        if years_experience > 5:
            return random.choices(
                ["junior", "mid"],
                weights=[0.7, 0.3],
                k=1
            )[0]
        return random.choices(
            ["junior", "mid"],
            weights=[career_dist.get("junior", 0.9), career_dist.get("mid", 0.1)],
            k=1
        )[0]
    
    elif age_group == "26-40":
        # Junior to senior, consider experience
        if years_experience < 2:
            return "junior"
        elif years_experience > 10:
            return random.choices(
                ["mid", "senior"],
                weights=[0.3, 0.7],
                k=1
            )[0]
        else:
            return random.choices(
                ["junior", "mid", "senior"],
                weights=[
                    career_dist.get("junior", 0.2),
                    career_dist.get("mid", 0.6),
                    career_dist.get("senior", 0.2)
                ],
                k=1
            )[0]
    
    elif age_group == "41-65":
        # Senior to lead, consider experience
        if years_experience < 5:
            return "mid"
        elif years_experience > 20:
            return random.choices(
                ["senior", "lead"],
                weights=[0.4, 0.6],
                k=1
            )[0]
        else:
            return random.choices(
                ["mid", "senior", "lead"],
                weights=[
                    career_dist.get("mid", 0.05),
                    career_dist.get("senior", 0.60),
                    career_dist.get("lead", 0.35)
                ],
                k=1
            )[0]
    
    # Default fallback
    if years_experience < 3:
        return "junior"
    elif years_experience < 7:
        return "mid"
    elif years_experience < 12:
        return "senior"
    else:
        return "lead"


def get_typical_years_for_age_group(age_group: str) -> Tuple[int, int]:
    """
    Get typical years of experience range for an age group.
    
    Args:
        age_group: Age group string ("18-25", "26-40", "41-65")
    
    Returns:
        Tuple of (min_years, max_years)
    """
    ranges = {
        "18-25": (0, 7),   # Just starting to early career
        "26-40": (2, 18),  # Mid-career range
        "41-65": (5, 40)   # Experienced to very experienced
    }
    
    return ranges.get(age_group, (0, 20))


def sample_portrait_path(gender: str, age_group: str) -> Optional[str]:
    """
    Sample portrait path by gender and age group.
    
    Args:
        gender: Gender string ("male" or "female")
        age_group: Age group string ("18-25", "26-40", "41-65")
    
    Returns:
        Relative path to portrait image (e.g., "male/18-25/image.png")
        or None if no portraits available
    """
    portrait_index = _load_portrait_index()
    
    if gender not in portrait_index:
        return None
    
    if age_group not in portrait_index[gender]:
        return None
    
    portraits = portrait_index[gender][age_group]
    
    if not portraits:
        return None
    
    return random.choice(portraits)


def get_industry_employment_percentage(industry: str) -> float:
    """
    Get industry employment percentage from NOGA branch data.
    
    Args:
        industry: Industry enum value (e.g., "technology", "finance")
    
    Returns:
        Employment percentage (0.0-100.0)
    """
    # Map industry to NOGA branch
    industry_to_branch = {
        "technology": "Informatik",
        "finance": "Wirtschaft, Verwaltung, Tourismus",
        "healthcare": "Gesundheit",
        "construction": "Bau",
        "manufacturing": "Metall, Maschinen, Uhren",
        "education": "Bildung, Soziales",
        "retail": "Verkauf, Einkauf",
        "hospitality": "Gastgewerbe, Hotellerie",
    }
    
    branch = industry_to_branch.get(industry)
    if not branch:
        return 0.0
    
    percentages = _load_industry_percentages()
    return percentages.get(branch, 0.0)


def sample_industry_weighted() -> str:
    """
    Sample industry based on real employment data.
    Higher percentage industries appear more often.
    
    Returns:
        Industry enum value
    """
    percentages = _load_industry_percentages()
    
    # Map NOGA branches to industries
    branch_to_industry = {
        "Informatik": "technology",
        "Wirtschaft, Verwaltung, Tourismus": "finance",
        "Gesundheit": "healthcare",
        "Bau": "construction",
        "Metall, Maschinen, Uhren": "manufacturing",
        "Bildung, Soziales": "education",
        "Verkauf, Einkauf": "retail",
        "Gastgewerbe, Hotellerie": "hospitality",
    }
    
    industries = []
    weights = []
    
    for branch, percentage in percentages.items():
        if branch in branch_to_industry:
            industry = branch_to_industry[branch]
            industries.append(industry)
            weights.append(percentage)
    
    if not industries:
        # Fallback: equal probability
        return random.choice([
            "technology", "finance", "healthcare", "construction",
            "manufacturing", "education", "retail", "hospitality", "other"
        ])
    
    # Add "other" with remaining percentage
    total_weight = sum(weights)
    if total_weight < 100.0:
        industries.append("other")
        weights.append(100.0 - total_weight)
    
    return random.choices(industries, weights=weights, k=1)[0]

