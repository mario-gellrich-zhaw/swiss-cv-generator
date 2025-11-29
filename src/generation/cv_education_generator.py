"""
CV Education History Generator.

This module generates realistic education histories for personas based on:
- CV_DATA.ausbildung (primary education)
- CV_DATA.weiterbildung (continuing education)
- Persona age and years_experience

Run: Used by persona generation pipeline
"""
import sys
import random
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.queries import get_occupation_by_id
from src.database.mongodb_manager import get_db_manager
from src.config import get_settings

settings = get_settings()


def extract_education_data(occupation_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract education data from occupation document.
    
    Args:
        occupation_doc: Occupation document from CV_DATA.
    
    Returns:
        Dictionary with extracted education data.
    """
    ausbildung = occupation_doc.get("ausbildung", {})
    weiterbildung = occupation_doc.get("weiterbildung", {})
    
    education_data = {
        "primary": {},
        "berufsmaturitaet": None,
        "weiterbildung": []
    }
    
    # Extract primary education
    if isinstance(ausbildung, dict):
        education_data["primary"] = {
            "bildungstyp": ausbildung.get("bildungstyp", ""),
            "dauer_jahre": ausbildung.get("dauer_jahre", 3),
            "abschluss": ausbildung.get("abschluss", ""),
            "schulische_bildung": ausbildung.get("schulische_bildung", ""),
            "institution": ausbildung.get("institution", ""),
            "ort": ausbildung.get("ort", "")
        }
        
        # Check for Berufsmaturität
        if "berufsmaturitaet" in str(ausbildung).lower() or "bm" in str(ausbildung).lower():
            education_data["berufsmaturitaet"] = {
                "type": "Berufsmaturität",
                "dauer_jahre": 1
            }
    
    # Extract continuing education
    if isinstance(weiterbildung, dict):
        career_progression = weiterbildung.get("career_progression", [])
        if isinstance(career_progression, list):
            for item in career_progression:
                if isinstance(item, dict):
                    education_data["weiterbildung"].append({
                        "title": item.get("title", ""),
                        "type": item.get("type", ""),
                        "dauer_jahre": item.get("dauer_jahre", 1),
                        "institution": item.get("institution", "")
                    })
    
    return education_data


def calculate_education_timeline(
    persona_age: int,
    years_experience: int,
    education_duration: int
) -> Tuple[int, int]:
    """
    Calculate education start and end years based on persona age and experience.
    
    Formula:
    - Education end = age - years_experience
    - Education start = end - education_duration
    
    Args:
        persona_age: Persona's current age.
        years_experience: Years of work experience.
        education_duration: Duration of education in years.
    
    Returns:
        Tuple of (start_year, end_year).
    """
    current_year = datetime.now().year
    
    # Education typically ends when work starts
    education_end_age = persona_age - years_experience
    
    # Ensure minimum age (typically 15-16 for apprenticeships)
    if education_end_age < 15:
        education_end_age = 15
    
    education_end_year = current_year - (persona_age - education_end_age)
    education_start_year = education_end_year - education_duration
    
    # Ensure start year is reasonable (not before 1980)
    if education_start_year < 1980:
        education_start_year = 1980
        education_end_year = education_start_year + education_duration
    
    return education_start_year, education_end_year


def generate_education_history(
    persona: Dict[str, Any],
    occupation_doc: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Generate education history for a persona.
    
    Args:
        persona: Persona dictionary with age, years_experience, job_id, etc.
        occupation_doc: Optional occupation document from CV_DATA.
    
    Returns:
        List of education entries with structure:
        {
            "degree": str,
            "institution": str,
            "location": str,
            "start_year": int,
            "end_year": int,
            "type": str  # "primary", "berufsmaturitaet", "weiterbildung"
        }
    """
    education_history = []
    
    persona_age = persona.get("age", 25)
    years_experience = persona.get("years_experience", 0)
    job_id = persona.get("job_id")
    canton = persona.get("canton", "ZH")
    
    # Get occupation document if not provided
    if not occupation_doc and job_id:
        occupation_doc = get_occupation_by_id(job_id)
    
    # Extract education data
    if occupation_doc:
        education_data = extract_education_data(occupation_doc)
    else:
        # Fallback: use default education
        education_data = {
            "primary": {
                "bildungstyp": "EFZ",
                "dauer_jahre": 3,
                "abschluss": "Eidgenössisches Fähigkeitszeugnis",
                "schulische_bildung": "Berufsschule"
            },
            "berufsmaturitaet": None,
            "weiterbildung": []
        }
    
    # 1. Primary education
    primary = education_data.get("primary", {})
    if primary:
        bildungstyp = primary.get("bildungstyp", "EFZ")
        dauer_jahre = primary.get("dauer_jahre", 3)
        abschluss = primary.get("abschluss", "")
        institution = primary.get("institution", "")
        ort = primary.get("ort", "")
        
        # Calculate timeline
        start_year, end_year = calculate_education_timeline(
            persona_age,
            years_experience,
            dauer_jahre
        )
        
        # Format degree name
        if not abschluss:
            if "EFZ" in bildungstyp or "Eidgenössisches Fähigkeitszeugnis" in bildungstyp:
                abschluss = "Eidgenössisches Fähigkeitszeugnis (EFZ)"
            elif "EBA" in bildungstyp or "Eidgenössisches Berufsattest" in bildungstyp:
                abschluss = "Eidgenössisches Berufsattest (EBA)"
            elif "HF" in bildungstyp:
                abschluss = "Höhere Fachschule (HF)"
            elif "FH" in bildungstyp or "Fachhochschule" in bildungstyp:
                abschluss = "Fachhochschule (FH)"
            elif "ETH" in bildungstyp or "Universität" in bildungstyp:
                abschluss = "Universität / ETH"
            else:
                abschluss = bildungstyp
        
        # Get institution name
        if not institution:
            if "FH" in bildungstyp or "Fachhochschule" in bildungstyp:
                institution = f"Fachhochschule {canton}"
            elif "ETH" in bildungstyp or "Universität" in bildungstyp:
                institution = "ETH Zürich" if canton == "ZH" else "Universität"
            else:
                # Use canton-based institution
                institution = f"Berufsschule {canton}"
        
        # Get location
        if not ort:
            ort = canton
        
        education_history.append({
            "degree": abschluss,
            "institution": institution,
            "location": ort,
            "start_year": start_year,
            "end_year": end_year,
            "type": "primary"
        })
    
    # 2. Optional: Berufsmaturität (if completeness_score high and age allows)
    completeness_score = occupation_doc.get("data_completeness", {}).get("completeness_score", 0) if occupation_doc else 0
    age_group = persona.get("age_group", "")
    
    # Berufsmaturität is more common for younger personas and high completeness
    if (completeness_score >= 0.8 and 
        age_group in ["18-25", "26-40"] and
        random.random() < 0.3):  # 30% chance
        
        berufsmaturitaet = education_data.get("berufsmaturitaet")
        if berufsmaturitaet or random.random() < 0.5:  # 50% chance even without explicit data
            # Berufsmaturität typically follows primary education
            primary_end = education_history[0]["end_year"] if education_history else end_year
            bm_start = primary_end
            bm_end = primary_end + 1
            
            education_history.append({
                "degree": "Berufsmaturität",
                "institution": f"Berufsmaturitätsschule {canton}",
                "location": canton,
                "start_year": bm_start,
                "end_year": bm_end,
                "type": "berufsmaturitaet"
            })
    
    # 3. Optional: Weiterbildung (continuing education)
    weiterbildung_list = education_data.get("weiterbildung", [])
    
    if weiterbildung_list and years_experience > 2:
        # Add 1-2 continuing education entries for experienced personas
        num_weiterbildung = min(2, len(weiterbildung_list))
        
        for i, wb in enumerate(weiterbildung_list[:num_weiterbildung]):
            if random.random() < 0.4:  # 40% chance per entry
                wb_title = wb.get("title", "Weiterbildung")
                wb_type = wb.get("type", "Kurs")
                wb_dauer = wb.get("dauer_jahre", 1)
                wb_institution = wb.get("institution", f"Institution {canton}")
                
                # Weiterbildung typically happens during career
                # Place it 1-5 years after primary education
                primary_end = education_history[0]["end_year"] if education_history else end_year
                wb_start = primary_end + random.randint(1, min(5, years_experience - 1))
                wb_end = wb_start + wb_dauer
                
                # Ensure it doesn't extend beyond current year
                current_year = datetime.now().year
                if wb_end > current_year:
                    wb_end = current_year
                    wb_start = wb_end - wb_dauer
                
                education_history.append({
                    "degree": wb_title,
                    "institution": wb_institution,
                    "location": canton,
                    "start_year": wb_start,
                    "end_year": wb_end,
                    "type": "weiterbildung"
                })
    
    # Validate timeline consistency
    education_history = validate_education_timeline(education_history, persona_age, years_experience)
    
    # Sort by start_year
    education_history.sort(key=lambda x: x.get("start_year", 0))
    
    return education_history


def validate_education_timeline(
    education_history: List[Dict[str, Any]],
    persona_age: int,
    years_experience: int
) -> List[Dict[str, Any]]:
    """
    Validate and fix education timeline consistency with persona age.
    
    Args:
        education_history: List of education entries.
        persona_age: Persona's current age.
        years_experience: Years of work experience.
    
    Returns:
        Validated and corrected education history.
    """
    if not education_history:
        return education_history
    
    current_year = datetime.now().year
    birth_year = current_year - persona_age
    
    validated = []
    
    for entry in education_history:
        start_year = entry.get("start_year", 0)
        end_year = entry.get("end_year", 0)
        
        # Check: Education shouldn't start before age 15
        min_start_age = 15
        if start_year < birth_year + min_start_age:
            start_year = birth_year + min_start_age
            end_year = start_year + (end_year - entry.get("start_year", start_year))
        
        # Check: Education shouldn't end after current year
        if end_year > current_year:
            end_year = current_year
            start_year = end_year - (entry.get("end_year", end_year) - entry.get("start_year", start_year))
        
        # Check: Education end should be before work starts
        work_start_year = current_year - years_experience
        if end_year > work_start_year:
            # Adjust: education should end when work starts
            end_year = work_start_year
            start_year = end_year - (entry.get("end_year", end_year) - entry.get("start_year", start_year))
        
        # Check: Start year should be before end year
        if start_year >= end_year:
            # Fix: make it at least 1 year
            end_year = start_year + 1
        
        # Update entry
        entry["start_year"] = start_year
        entry["end_year"] = end_year
        
        # VALIDATION: Skip entries with empty degree or institution
        degree = entry.get("degree", "")
        institution = entry.get("institution", "")
        if not degree or not institution:
            continue  # Skip this entry
        
        validated.append(entry)
    
    return validated


def get_education_summary(education_history: List[Dict[str, Any]]) -> str:
    """
    Generate a text summary of education history.
    
    Args:
        education_history: List of education entries.
    
    Returns:
        Formatted education summary string.
    """
    if not education_history:
        return "Keine Bildungsinformationen verfügbar."
    
    summary_parts = []
    
    for entry in education_history:
        degree = entry.get("degree", "")
        institution = entry.get("institution", "")
        start_year = entry.get("start_year", 0)
        end_year = entry.get("end_year", 0)
        
        if degree and institution:
            summary_parts.append(f"{degree} bei {institution} ({start_year}-{end_year})")
        elif degree:
            summary_parts.append(f"{degree} ({start_year}-{end_year})")
    
    return " | ".join(summary_parts) if summary_parts else "Keine Bildungsinformationen verfügbar."

