"""
CV Company Validator.

This module validates companies against occupations with strict industry mapping:
- Occupation-to-Industry mapping (STRICT and FLEXIBLE)
- Company validation for occupation
- Fallback company generation
- Remove "Verschiedene Positionen" entries

Run: Used during job generation, reject early
"""
import sys
import random
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.queries import get_occupation_by_id
from src.database.mongodb_manager import get_db_manager


# STRICT MAPPINGS (NO crossover)
STRICT_OCCUPATION_MAPPINGS = {
    # Gärtner/Landschaftsgärtner → construction or natur (NOT healthcare)
    "gärtner": {"construction", "natur"},
    "landschaftsgärtner": {"construction", "natur"},
    "gartenbau": {"construction", "natur"},
    "gärtnermeister": {"construction", "natur"},
    
    # Informatiker → technology ONLY
    "informatiker": {"technology"},
    "softwareentwickler": {"technology"},
    "programmierer": {"technology"},
    "it-spezialist": {"technology"},
    "systemadministrator": {"technology"},
    "datenbankadministrator": {"technology"},
    
    # Krankenpfleger → healthcare ONLY
    "krankenpfleger": {"healthcare"},
    "krankenpflegerin": {"healthcare"},
    "pflegefachfrau": {"healthcare"},
    "pflegefachmann": {"healthcare"},
    "pfleger": {"healthcare"},
    "pflegerin": {"healthcare"},
    "krankenschwester": {"healthcare"},
    "krankenpfleger": {"healthcare"},
    
    # Mechaniker → manufacturing ONLY
    "mechaniker": {"manufacturing"},
    "maschinenmechaniker": {"manufacturing"},
    "fahrzeugmechaniker": {"manufacturing"},
    "industriemechaniker": {"manufacturing"},
    "werkzeugmacher": {"manufacturing"},
    
    # Rechtsanwalt → legal/finance (NOT hospitality/retail)
    "rechtsanwalt": {"finance", "other"},
    "anwalt": {"finance", "other"},
    "jurist": {"finance", "other"},
    
    # Arzt → healthcare ONLY
    "arzt": {"healthcare"},
    "ärztin": {"healthcare"},
    "mediziner": {"healthcare"},
    "chirurg": {"healthcare"},
    "kardiologe": {"healthcare"},
}

# FLEXIBLE MAPPINGS (can crossover)
FLEXIBLE_OCCUPATION_MAPPINGS = {
    # Kaufmann → finance, retail, education (admin roles everywhere)
    "kaufmann": {"finance", "retail", "education", "healthcare", "other"},
    "kauffrau": {"finance", "retail", "education", "healthcare", "other"},
    "kaufmännischer angestellter": {"finance", "retail", "education", "healthcare", "other"},
    "bürokaufmann": {"finance", "retail", "education", "healthcare", "other"},
    
    # Manager → any industry with "+management" tag
    "manager": {"finance", "retail", "technology", "healthcare", "construction", "manufacturing", "education", "hospitality", "other"},
    "geschäftsführer": {"finance", "retail", "technology", "healthcare", "construction", "manufacturing", "education", "hospitality", "other"},
    "direktor": {"finance", "retail", "technology", "healthcare", "construction", "manufacturing", "education", "hospitality", "other"},
    
    # Sekretär → any industry (support role)
    "sekretär": {"finance", "retail", "technology", "healthcare", "construction", "manufacturing", "education", "hospitality", "other"},
    "sekretärin": {"finance", "retail", "technology", "healthcare", "construction", "manufacturing", "education", "hospitality", "other"},
    "assistent": {"finance", "retail", "technology", "healthcare", "construction", "manufacturing", "education", "hospitality", "other"},
    "assistentin": {"finance", "retail", "technology", "healthcare", "construction", "manufacturing", "education", "hospitality", "other"},
}

# Industries that can have IT departments (for Informatiker)
INDUSTRIES_WITH_IT_DEPARTMENTS = {
    "finance",  # Banks have IT
    "healthcare",  # Hospitals have IT
    "education",  # Universities have IT
    "manufacturing",  # Companies have IT
    "retail",  # Companies have IT
}

# Company name patterns that indicate wrong industry
INVALID_COMPANY_PATTERNS = {
    "healthcare": ["restaurant", "hotel", "gastronomie", "café", "bar"],
    "construction": ["pharma", "swissmedic", "klinik", "spital", "hospital", "apotheke"],
    "technology": ["restaurant", "hotel", "gastronomie", "café"],
    "manufacturing": ["restaurant", "hotel", "klinik", "spital"],
}


def normalize_occupation_name(occupation_name: str) -> str:
    """
    Normalize occupation name for matching.
    
    Args:
        occupation_name: Occupation name or title.
    
    Returns:
        Normalized name (lowercase, no special chars).
    """
    if not occupation_name:
        return ""
    
    normalized = occupation_name.lower()
    # Remove special characters
    normalized = re.sub(r'[^\w\s]', '', normalized)
    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def get_occupation_industry_mapping(
    occupation_doc: Dict[str, Any],
    occupation_title: Optional[str] = None
) -> Tuple[Set[str], bool]:
    """
    Get industry mapping for occupation from CV_DATA + custom rules.
    
    Args:
        occupation_doc: Occupation document from CV_DATA.
        occupation_title: Optional occupation title for additional matching.
    
    Returns:
        Tuple of (allowed_industries, is_strict).
        is_strict=True means NO crossover allowed.
    """
    allowed_industries = set()
    is_strict = False
    
    # Get berufsfeld from occupation document
    berufsfelder = []
    if occupation_doc:
        categories = occupation_doc.get("categories", {})
        if isinstance(categories, dict):
            berufsfelder = categories.get("berufsfelder", [])
            if not isinstance(berufsfelder, list):
                berufsfelder = [berufsfelder] if berufsfelder else []
    
    # Also check occupation title
    title_to_check = occupation_title or occupation_doc.get("title", "") or occupation_doc.get("name_de", "")
    normalized_title = normalize_occupation_name(title_to_check)
    
    # Check STRICT mappings first
    for key, industries in STRICT_OCCUPATION_MAPPINGS.items():
        if key in normalized_title:
            allowed_industries.update(industries)
            is_strict = True
            break
    
    # Check berufsfelder against STRICT mappings
    if not is_strict:
        for berufsfeld in berufsfelder:
            if not isinstance(berufsfeld, str):
                continue
            normalized_bf = normalize_occupation_name(berufsfeld)
            for key, industries in STRICT_OCCUPATION_MAPPINGS.items():
                if key in normalized_bf:
                    allowed_industries.update(industries)
                    is_strict = True
                    break
            if is_strict:
                break
    
    # Check FLEXIBLE mappings if no STRICT match
    if not allowed_industries:
        for key, industries in FLEXIBLE_OCCUPATION_MAPPINGS.items():
            if key in normalized_title:
                allowed_industries.update(industries)
                break
        
        # Check berufsfelder against FLEXIBLE mappings
        if not allowed_industries:
            for berufsfeld in berufsfelder:
                if not isinstance(berufsfeld, str):
                    continue
                normalized_bf = normalize_occupation_name(berufsfeld)
                for key, industries in FLEXIBLE_OCCUPATION_MAPPINGS.items():
                    if key in normalized_bf:
                        allowed_industries.update(industries)
                        break
                if allowed_industries:
                    break
    
    # Special case: Informatiker can work in industries with IT departments
    if "informatiker" in normalized_title or any("informatik" in normalize_occupation_name(str(bf)) for bf in berufsfelder):
        if "technology" in allowed_industries:
            # Also allow industries with IT departments
            allowed_industries.update(INDUSTRIES_WITH_IT_DEPARTMENTS)
    
    return allowed_industries, is_strict


def validate_company_for_occupation(
    company: Dict[str, Any],
    occupation_doc: Dict[str, Any],
    occupation_title: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate company against occupation with strict industry matching.
    
    Args:
        company: Company document.
        occupation_doc: Occupation document from CV_DATA.
        occupation_title: Optional occupation title.
    
    Returns:
        Tuple of (is_valid, rejection_reason).
    """
    if not company:
        return False, "Company is None"
    
    company_name = company.get("name", "").lower()
    company_industry = company.get("industry", "")
    
    # REJECT: "Verschiedene Positionen" is NOT a company
    if "verschiedene positionen" in company_name:
        return False, "Verschiedene Positionen is not a valid company name"
    
    # Get allowed industries for occupation
    allowed_industries, is_strict = get_occupation_industry_mapping(
        occupation_doc, occupation_title
    )
    
    if not allowed_industries:
        # No mapping found, allow any industry
        return True, None
    
    # Check if company industry matches
    if company_industry in allowed_industries:
        # Additional validation: check company name patterns
        invalid_patterns = INVALID_COMPANY_PATTERNS.get(company_industry, [])
        for pattern in invalid_patterns:
            if pattern in company_name:
                return False, f"Company name '{company.get('name')}' contains invalid pattern '{pattern}' for industry {company_industry}"
        
        return True, None
    
    # STRICT mapping: MUST match exactly
    if is_strict:
        return False, f"STRICT mapping violation: Occupation requires {allowed_industries}, but company is {company_industry}"
    
    # FLEXIBLE mapping: check if related industries are acceptable
    # For now, reject if not in allowed set
    return False, f"FLEXIBLE mapping violation: Occupation allows {allowed_industries}, but company is {company_industry}"


def generate_fallback_company(
    occupation_doc: Dict[str, Any],
    canton: str,
    occupation_title: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate realistic fallback company name if no matching company found.
    
    Uses realistic Swiss company naming patterns instead of generic "Services XX".
    
    Args:
        occupation_doc: Occupation document.
        canton: Canton code.
        occupation_title: Optional occupation title.
    
    Returns:
        Generated company dictionary with company_source="fallback".
    """
    # Realistic Swiss company name patterns by industry
    COMPANY_PATTERNS = {
        "technology": [
            "SwissTech", "DigitalHelvetic", "AlpineSoft", "SmartBit", "DataPeak",
            "CodeCraft", "NetAlpin", "TechFlow", "BitMountain", "SwissCode"
        ],
        "healthcare": [
            "MediCare", "HealthPlus", "VitaClinic", "SanaMed", "CarePlus",
            "MedCenter", "HealthFirst", "VitaCare", "SwissMed", "SanaLife"
        ],
        "finance": [
            "FinancePartner", "WealthAdvisor", "CapitalTrust", "InvestSwiss", "BankPartner",
            "AssetPro", "FinanzPro", "TreuhandService", "CapitalPlus", "WealthGuard"
        ],
        "construction": [
            "BauProfi", "ConstructPlus", "BuilderPro", "Baumann", "Bauwerk",
            "SolidBau", "SwissBuild", "ArchiBau", "SteinProfi", "BauMeister"
        ],
        "manufacturing": [
            "TechnikPlus", "PräzisionsTech", "IndustryPro", "MechaTech", "MetallWerk",
            "SwissPrecision", "TechnikWerk", "ProduktionstTech", "IndustriePro", "MaschinenTech"
        ],
        "retail": [
            "HandelPlus", "RetailPro", "KaufhausCenter", "ShopMeister", "MarktPlus",
            "VerkaufsPro", "DetailHandel", "SwissRetail", "MarktPartner", "HandelService"
        ],
        "hospitality": [
            "GastroPlus", "HotelPartner", "RestaurantPro", "CateringService", "GastService",
            "SwissGastro", "HospitalityPro", "GastMeister", "HotelService", "KulinarikPlus"
        ],
        "education": [
            "BildungsPlus", "LernCenter", "AkademiePro", "SchulService", "BildungsMeister",
            "SwissEdu", "LernPartner", "AkademieSwiss", "TrainingPro", "WissenPlus"
        ],
        "other": [
            "ServicePlus", "ProfiPartner", "SwissService", "QualityPro", "ExpertService",
            "MeisterService", "PremiumPro", "SwissExpert", "ProfiService", "QualitätPlus"
        ]
    }
    
    # Get industry from occupation mapping
    allowed_industries, _ = get_occupation_industry_mapping(occupation_doc, occupation_title)
    industry = list(allowed_industries)[0] if allowed_industries else "other"
    
    # Get appropriate patterns for industry
    patterns = COMPANY_PATTERNS.get(industry, COMPANY_PATTERNS["other"])
    base_name = random.choice(patterns)
    
    # Legal forms based on region
    if canton in ["GE", "VD", "NE", "JU", "FR"]:  # French-speaking
        legal_forms = ["SA", "Sàrl"]
    elif canton == "TI":  # Italian-speaking
        legal_forms = ["SA", "Sagl"]
    else:  # German-speaking
        legal_forms = ["AG", "GmbH"]
    
    legal_form = random.choice(legal_forms)
    
    # Generate company name with variation
    name_patterns = [
        f"{base_name} {legal_form}",
        f"{base_name} Schweiz {legal_form}",
        f"{base_name} {canton} {legal_form}",
    ]
    company_name = random.choice(name_patterns)
    
    return {
        "name": company_name,
        "canton_code": canton,
        "industry": industry,
        "size_band": "small",
        "is_real": False,
        "company_source": "fallback"
    }


def get_valid_company_for_occupation(
    occupation_doc: Dict[str, Any],
    canton: str,
    occupation_title: Optional[str] = None,
    max_attempts: int = 5,
    used_companies: Optional[List[str]] = None
) -> Tuple[Dict[str, Any], str]:
    """
    Get valid company for occupation with validation and fallback.
    
    Args:
        occupation_doc: Occupation document.
        canton: Canton code.
        occupation_title: Optional occupation title.
        max_attempts: Maximum attempts to find matching company.
        used_companies: List of already used company names.
    
    Returns:
        Tuple of (company_dict, match_quality).
        match_quality: "perfect", "canton_mismatch", "fallback"
    """
    if used_companies is None:
        used_companies = []
    
    # Get allowed industries
    allowed_industries, is_strict = get_occupation_industry_mapping(
        occupation_doc, occupation_title
    )
    
    db_manager = get_db_manager()
    db_manager.connect()
    companies_col = db_manager.get_target_collection("companies")
    
    # Try to find matching company
    for attempt in range(max_attempts):
        # Priority 1: Strict match (canton + industry)
        if attempt == 0 and allowed_industries:
            for industry in allowed_industries:
                companies = list(companies_col.find({
                    "canton_code": canton,
                    "industry": industry
                }))
                
                companies = [c for c in companies if c.get("name") not in used_companies]
                
                if companies:
                    company = random.choice(companies)
                    is_valid, reason = validate_company_for_occupation(
                        company, occupation_doc, occupation_title
                    )
                    if is_valid:
                        return company, "perfect"
        
        # Priority 2: Industry match, different canton
        if attempt <= 1 and allowed_industries:
            for industry in allowed_industries:
                companies = list(companies_col.find({
                    "industry": industry
                }))
                
                companies = [c for c in companies if c.get("name") not in used_companies]
                
                if companies:
                    company = random.choice(companies)
                    is_valid, reason = validate_company_for_occupation(
                        company, occupation_doc, occupation_title
                    )
                    if is_valid:
                        return company, "canton_mismatch"
        
        # Priority 3: Any company (if flexible mapping)
        if not is_strict and attempt <= 2:
            companies = list(companies_col.find({
                "canton_code": canton
            }))
            
            companies = [c for c in companies if c.get("name") not in used_companies]
            
            if companies:
                company = random.choice(companies)
                is_valid, reason = validate_company_for_occupation(
                    company, occupation_doc, occupation_title
                )
                if is_valid:
                    return company, "flexible_match"
    
    # Fallback: Generate realistic company name
    fallback_company = generate_fallback_company(occupation_doc, canton, occupation_title)
    return fallback_company, "fallback"


def remove_verschiedene_positionen_entries(
    job_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Remove "Verschiedene Positionen" entries from job history.
    
    This is NOT a company - use specific companies OR gap explanation.
    NEVER use as employer name.
    
    Args:
        job_history: List of job entries.
    
    Returns:
        Cleaned job history.
    """
    cleaned = []
    
    for job in job_history:
        company_name = job.get("company", "")
        position = job.get("position", "")
        
        # Check if it's a "Verschiedene Positionen" entry
        if "verschiedene positionen" in company_name.lower() or "verschiedene positionen" in position.lower():
            # Skip this entry
            continue
        
        cleaned.append(job)
    
    return cleaned

