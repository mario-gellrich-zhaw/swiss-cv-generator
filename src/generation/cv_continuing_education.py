"""
CV Continuing Education Generator.

This module generates additional education and certifications for personas:
- Courses (Kurse)
- Professional exams (Berufsprüfung)
- Higher professional exams (Höhere Fachprüfung)
- Certifications (SUVA, language, industry)

Run: Used by persona generation pipeline
"""
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from src.config import get_settings
from src.database.queries import get_occupation_by_id

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


settings = get_settings()


class WeiterbildungData(TypedDict):
    kurse: List[Any]
    berufspruefung: List[Any]
    hoehere_fachpruefung: Optional[str]
    hoehere_fachschule: Optional[str]
    fachhochschule: Optional[str]
    training_providers: List[str]


def extract_weiterbildung_data(occupation_doc: Dict[str, Any]) -> WeiterbildungData:
    """
    Extract continuing education data from occupation document.

    Args:
        occupation_doc: Occupation document from CV_DATA.

    Returns:
        Dictionary with extracted weiterbildung data.
    """
    weiterbildung = occupation_doc.get("weiterbildung", {})
    weitere_info = occupation_doc.get("weitere_informationen", {})

    education_data: WeiterbildungData = {
        "kurse": [],
        "berufspruefung": [],
        "hoehere_fachpruefung": None,
        "hoehere_fachschule": None,
        "fachhochschule": None,
        "training_providers": []
    }

    # Extract Kurse
    kurse_text = weiterbildung.get("kurse", "")
    if isinstance(kurse_text, str) and kurse_text:
        # Parse course text (may contain multiple courses or just description)
        # Try to extract course names from text
        # Common patterns: "Kurse von...", "Angebote von..."
        if "von" in kurse_text or "Angebote" in kurse_text:
            # This is a description, create generic course names
            education_data["kurse"] = [f"Fachkurs {i+1}" for i in range(2)]
        else:
            # Try to split by common delimiters
            education_data["kurse"] = [kurs.strip()
                                       for kurs in kurse_text.split(",") if kurs.strip()]
    elif isinstance(kurse_text, list):
        education_data["kurse"] = kurse_text

    # Extract Berufsprüfung
    berufspruefung_list = weiterbildung.get("berufspruefung", [])
    if isinstance(berufspruefung_list, list):
        education_data["berufspruefung"] = berufspruefung_list

    # Extract Höhere Fachprüfung
    hoehere_fachpruefung = weiterbildung.get("hoehere_fachpruefung", "")
    if hoehere_fachpruefung:
        education_data["hoehere_fachpruefung"] = str(hoehere_fachpruefung)

    # Extract Höhere Fachschule
    hoehere_fachschule = weiterbildung.get("hoehere_fachschule", "")
    if hoehere_fachschule:
        education_data["hoehere_fachschule"] = str(hoehere_fachschule)

    # Extract training providers from weitere_informationen
    adressen = weitere_info.get("adressen", [])
    if isinstance(adressen, list):
        for adresse in adressen:
            if isinstance(adresse, dict):
                name = adresse.get("name", "") or adresse.get(
                    "organisation", "")
                if name and any(keyword in name.lower() for keyword in ["schule", "bildungs", "akademie", "institut", "zentrum"]):
                    education_data["training_providers"].append(name)

    return education_data


def get_suva_safety_courses(berufsfeld: Optional[str] = None) -> List[str]:
    """
    Get SUVA safety courses relevant to occupation.

    Args:
        berufsfeld: Berufsfeld from occupation.

    Returns:
        List of relevant SUVA course names.
    """
    # SUVA courses relevant to different fields
    suva_courses = {
        "Bau": [
            "SUVA Sicherheitskurs Bau",
            "SUVA Gerüstbau-Sicherheit",
            "SUVA Arbeitssicherheit auf Baustellen"
        ],
        "Metall, Maschinen, Uhren": [
            "SUVA Maschinensicherheit",
            "SUVA Arbeitssicherheit in der Produktion"
        ],
        "Gesundheit": [
            "SUVA Ergonomie im Gesundheitswesen",
            "SUVA Arbeitssicherheit im Gesundheitswesen"
        ],
        "Gastgewerbe, Hotellerie": [
            "SUVA Arbeitssicherheit in der Gastronomie",
            "SUVA Küchensicherheit"
        ],
        "default": [
            "SUVA Grundkurs Arbeitssicherheit",
            "SUVA Erste Hilfe",
            "SUVA Brandschutz"
        ]
    }

    if berufsfeld:
        for field, courses in suva_courses.items():
            if field in str(berufsfeld):
                return courses

    return suva_courses["default"]


def get_language_certificates(canton: str, language: str) -> List[str]:
    """
    Get relevant language certificates based on canton and language.

    Args:
        canton: Canton code.
        language: Primary language.

    Returns:
        List of language certificate names.
    """
    # Language certificates
    certificates = {
        "de": [
            "Goethe-Zertifikat B2",
            "Goethe-Zertifikat C1",
            "telc Deutsch B2",
            "telc Deutsch C1"
        ],
        "fr": [
            "DELF B2",
            "DELF C1",
            "DALF C1",
            "DALF C2"
        ],
        "it": [
            "CELI B2",
            "CELI C1",
            "CILS B2",
            "CILS C1"
        ]
    }

    # For multilingual cantons, add additional languages
    multilingual_cantons = ["BE", "VS", "FR", "GR"]
    if canton in multilingual_cantons:
        # Add certificates for other languages
        all_certs = []
        for lang, certs in certificates.items():
            if lang != language:
                # One certificate per additional language
                all_certs.extend(certs[:1])
        return certificates.get(language, []) + all_certs

    return certificates.get(language, [])


def calculate_weiterbildung_timeline(
    base_education_end_year: int,
    years_experience: int,
    education_type: str
) -> int:
    """
    Calculate year for continuing education based on timeline.

    Args:
        base_education_end_year: Year when base education ended.
        years_experience: Years of work experience.
        education_type: Type of education (kurs, berufspruefung, hoehere_fachpruefung).

    Returns:
        Year when education was completed.
    """
    current_year = datetime.now().year

    # Guard against invalid randint ranges when experience is low. Clamp the
    # upper bound to at least the lower bound so we never pass an empty range
    # to random.randint().
    def _clamped_randint(low: int, high: int) -> int:
        safe_high = max(low, high)
        return random.randint(low, safe_high)

    if education_type == "kurs":
        # Courses: distributed throughout career
        # 1-2 per 5 years of experience
        years_after_base = _clamped_randint(1, min(years_experience, 10))
        return base_education_end_year + years_after_base

    elif education_type == "berufspruefung":
        # Berufsprüfung: 5-7 years after base education
        years_after_base = random.randint(5, 7)
        return base_education_end_year + years_after_base

    elif education_type == "hoehere_fachpruefung":
        # Höhere Fachprüfung: 10+ years after base
        years_after_base = _clamped_randint(10, min(years_experience, 15))
        return base_education_end_year + years_after_base

    elif education_type == "zertifikat":
        # Certificates: distributed throughout career
        years_after_base = _clamped_randint(2, min(years_experience, 8))
        return base_education_end_year + years_after_base

    return base_education_end_year + _clamped_randint(1, 5)


def generate_additional_education(
    persona: Dict[str, Any],
    occupation_doc: Optional[Dict[str, Any]] = None,
    base_education_end_year: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Generate additional education and certifications for a persona.

    Args:
        persona: Persona dictionary with age, years_experience, career_level, etc.
        occupation_doc: Optional occupation document from CV_DATA.
        base_education_end_year: Year when base education ended.

    Returns:
        List of additional education entries:
        {
            "title": str,
            "provider": str,
            "year": int,
            "type": str  # "Kurs", "Berufsprüfung", "Höhere Fachprüfung", "Zertifikat"
        }
    """
    additional_education = []

    years_experience = persona.get("years_experience", 0)
    career_level = persona.get("career_level", "mid")
    canton = persona.get("canton", "ZH")
    language = persona.get("language", "de")
    job_id = persona.get("job_id")

    # Get occupation document if not provided
    if not occupation_doc and job_id:
        occupation_doc = get_occupation_by_id(job_id)

    # Calculate base education end year if not provided
    if base_education_end_year is None:
        persona_age = persona.get("age", 25)
        current_year = datetime.now().year
        # Base education typically ends around age 18-22
        education_end_age = persona_age - years_experience
        if education_end_age < 18:
            education_end_age = 18
        base_education_end_year = current_year - \
            (persona_age - education_end_age)

    # Ensure base year is a concrete int for timeline calculations
    assert isinstance(base_education_end_year, int)
    base_year: int = base_education_end_year

    # Extract weiterbildung data
    weiterbildung_data: WeiterbildungData
    if occupation_doc:
        weiterbildung_data = extract_weiterbildung_data(
            occupation_doc)
        berufsfeld = occupation_doc.get(
            "categories", {}).get("berufsfelder", [])
        if isinstance(berufsfeld, list) and berufsfeld:
            berufsfeld = berufsfeld[0]
        else:
            berufsfeld = str(berufsfeld) if berufsfeld else None
    else:
        weiterbildung_data = {
            "kurse": [],
            "berufspruefung": [],
            "hoehere_fachpruefung": None,
            "hoehere_fachschule": None,
            "fachhochschule": None,
            "training_providers": []
        }
        berufsfeld = None

    training_providers: List[str] = weiterbildung_data.get(
        "training_providers", []) or []

    # 1. Generate Kurse (1-2 per 5 years of experience)
    num_kurse = max(0, (years_experience // 5) * random.randint(1, 2))
    num_kurse = min(num_kurse, 4)  # Max 4 courses

    kurse_list = weiterbildung_data.get("kurse", [])
    if kurse_list:
        selected_kurse = random.sample(
            kurse_list, min(num_kurse, len(kurse_list)))
    else:
        # Generate generic courses
        selected_kurse = [f"Fachkurs {i+1}" for i in range(num_kurse)]

    for kurs in selected_kurse:
        if isinstance(kurs, dict):
            kurs_title = kurs.get("title", "") or kurs.get("name", "")
        else:
            kurs_title = str(kurs)

        if not kurs_title:
            continue

        # Select provider
        if training_providers:
            provider = random.choice(training_providers)
        else:
            provider = f"Bildungszentrum {canton}"

        # Calculate year
        year = calculate_weiterbildung_timeline(
            base_year,
            years_experience,
            "kurs"
        )

        additional_education.append({
            "title": kurs_title,
            "provider": provider,
            "year": year,
            "type": "Kurs"
        })

    # 2. Generate Berufsprüfung (if career_level >= "senior")
    if career_level in ["senior", "lead"] and years_experience >= 5:
        berufspruefung_list = weiterbildung_data.get("berufspruefung", [])

        if berufspruefung_list:
            # Select one Berufsprüfung
            bp = random.choice(berufspruefung_list)
            if isinstance(bp, dict):
                bp_title = bp.get("title", "") or bp.get("name", "")
            else:
                bp_title = str(bp)

            if bp_title:
                # Select provider
                if training_providers:
                    provider = random.choice(training_providers)
                else:
                    provider = f"Berufsprüfungskommission {canton}"

                # Calculate year (5-7 years after base)
                year = calculate_weiterbildung_timeline(
                    base_year,
                    years_experience,
                    "berufspruefung"
                )

                additional_education.append({
                    "title": bp_title,
                    "provider": provider,
                    "year": year,
                    "type": "Berufsprüfung"
                })

    # 3. Generate Höhere Fachprüfung (if career_level == "lead")
    if career_level == "lead" and years_experience >= 10:
        hoehere_fachpruefung = weiterbildung_data.get(
            "hoehere_fachpruefung", "")

        if hoehere_fachpruefung:
            # Parse HFP text (may contain examples)
            hfp_text = str(hoehere_fachpruefung)
            hfp_title = None

            # Try to extract title (usually after "zum Beispiel" or similar)
            if "zum Beispiel" in hfp_text.lower():
                parts = hfp_text.lower().split("zum beispiel")[-1]
                # Look for "dipl." pattern
                if "dipl." in parts:
                    # Extract everything from "dipl." to next comma or period
                    dipl_part = parts.split("dipl.")[-1]
                    hfp_title = "dipl. " + \
                        dipl_part.split(",")[0].split(".")[0].strip()
                else:
                    hfp_title = parts.split(",")[0].split(".")[0].strip()
            elif "z.B." in hfp_text or "z. B." in hfp_text:
                parts = hfp_text.split("z.B.")[-1].split("z. B.")[-1]
                if "dipl." in parts.lower():
                    dipl_part = parts.lower().split("dipl.")[-1]
                    hfp_title = "dipl. " + \
                        dipl_part.split(",")[0].split(".")[0].strip()
                else:
                    hfp_title = parts.split(",")[0].split(".")[0].strip()
            elif "dipl." in hfp_text.lower():
                # Direct dipl. pattern
                dipl_part = hfp_text.lower().split("dipl.")[-1]
                hfp_title = "dipl. " + \
                    dipl_part.split(",")[0].split(".")[0].strip()
            else:
                # Fallback: use first sentence
                hfp_title = hfp_text.split(".")[0].strip()

            # Clean up title
            if hfp_title:
                hfp_title = hfp_title.strip()
                # Capitalize first letter
                if hfp_title:
                    hfp_title = hfp_title[0].upper(
                    ) + hfp_title[1:] if len(hfp_title) > 1 else hfp_title.upper()

            if hfp_title and len(hfp_title) > 5:  # Only add if meaningful
                # Select provider
                if training_providers:
                    provider = random.choice(training_providers)
                else:
                    provider = f"Höhere Fachprüfungskommission {canton}"

                # Calculate year (10+ years after base)
                year = calculate_weiterbildung_timeline(
                    base_year,
                    years_experience,
                    "hoehere_fachpruefung"
                )

                additional_education.append({
                    "title": hfp_title,
                    "provider": provider,
                    "year": year,
                    "type": "Höhere Fachprüfung"
                })

    # 4. Add SUVA safety courses (if relevant)
    if berufsfeld and random.random() < 0.4:  # 40% chance
        suva_courses = get_suva_safety_courses(berufsfeld)
        if suva_courses:
            suva_course = random.choice(suva_courses)

            year = calculate_weiterbildung_timeline(
                base_year,
                years_experience,
                "zertifikat"
            )

            additional_education.append({
                "title": suva_course,
                "provider": "SUVA",
                "year": year,
                "type": "Zertifikat"
            })

    # 5. Add language certificates (based on canton)
    if random.random() < 0.3:  # 30% chance
        language_certs = get_language_certificates(canton, language)
        if language_certs:
            cert = random.choice(language_certs)

            year = calculate_weiterbildung_timeline(
                base_year,
                years_experience,
                "zertifikat"
            )

            additional_education.append({
                "title": cert,
                "provider": "Offizielles Prüfungszentrum",
                "year": year,
                "type": "Zertifikat"
            })

    # Sort by year (oldest first)
    additional_education.sort(key=lambda x: x.get("year", 0))

    return additional_education


def validate_education_timeline(
    additional_education: List[Dict[str, Any]],
    persona_age: int,
    base_education_end_year: int
) -> List[Dict[str, Any]]:
    """
    Validate education timeline consistency.

    Args:
        additional_education: List of education entries.
        persona_age: Persona's current age.
        base_education_end_year: Year when base education ended.

    Returns:
        Validated education list.
    """
    current_year = datetime.now().year
    birth_year = current_year - persona_age

    validated = []

    for entry in additional_education:
        year = entry.get("year", 0)

        # Check: Education shouldn't be before base education
        if year < base_education_end_year:
            year = base_education_end_year + 1

        # Check: Education shouldn't be in the future
        if year > current_year:
            year = current_year

        # Check: Education shouldn't be before age 18
        if year < birth_year + 18:
            year = birth_year + 18

        entry["year"] = year
        validated.append(entry)

    return validated


def get_education_summary(additional_education: List[Dict[str, Any]]) -> str:
    """
    Generate a text summary of additional education.

    Args:
        additional_education: List of education entries.

    Returns:
        Formatted education summary string.
    """
    if not additional_education:
        return "Keine zusätzlichen Weiterbildungen."

    summary_parts = []

    for entry in additional_education:
        title = entry.get("title", "")
        year = entry.get("year", 0)
        edu_type = entry.get("type", "")

        if title and year:
            summary_parts.append(f"{title} ({year})")

    return " | ".join(summary_parts) if summary_parts else "Keine zusätzlichen Weiterbildungen."
