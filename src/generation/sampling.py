# src/generation/sampling.py
import random
import os
import csv
import json
from pathlib import Path
from datetime import date
from typing import List, Dict, Any, Optional
from collections import Counter

from src.data.loader import load_cantons_csv, load_companies_csv, load_occupations_json
from src.data.models import SwissPersona, Language
from src.database.queries import (
    sample_age_group, sample_gender, determine_career_level_by_age,
    get_typical_years_for_age_group, sample_portrait_path,
    get_industry_employment_percentage, sample_industry_weighted,
    sample_canton_weighted, sample_occupation_by_industry,
    sample_first_name, sample_last_name, sample_company_by_canton_and_industry,
    get_skills_by_occupation, get_activities_by_occupation
)


def weighted_choice(items, weights):
    """Weighted random choice."""
    total = sum(weights)
    r = random.random() * total
    upto = 0
    for item, w in zip(items, weights):
        if upto + w >= r:
            return item
        upto += w
    return items[-1] if items else None


def load_name_csv(path):
    """Load names from CSV file."""
    names, weights = [], []
    if not os.path.exists(path):
        return names, weights
    with open(path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            nm = r.get('name') or r.get('Name') or r.get('vorname') or next(iter(r.values()), '')
            freq = r.get('frequency') or r.get('freq') or r.get('anzahl') or r.get('count') or '1'
            try:
                w = int(freq)
            except:
                w = 1
            names.append(nm)
            weights.append(w)
    return names, weights


_FALLBACK_FIRST_NAMES: Dict[str, Dict[str, List[str]]] = {
    "de": {
        "male": ["Luca", "Noah", "Leon", "Liam", "Matteo", "Jan", "David", "Simon", "Samuel", "Nico"],
        "female": ["Sophie", "Mia", "Lena", "Lea", "Emma", "Laura", "Nina", "Alina", "Anna", "Sara"],
    },
    "fr": {
        "male": ["Lucas", "Hugo", "Nathan", "Louis", "Gabriel", "Noah", "Mathis", "Jules", "Adam", "Thomas"],
        "female": ["Emma", "Léa", "Chloé", "Camille", "Manon", "Sarah", "Inès", "Julie", "Alice", "Louise"],
    },
    "it": {
        "male": ["Marco", "Lorenzo", "Matteo", "Alessandro", "Andrea", "Davide", "Simone", "Gabriele", "Luca", "Riccardo"],
        "female": ["Giulia", "Sofia", "Martina", "Chiara", "Francesca", "Alice", "Elisa", "Sara", "Giorgia", "Valentina"],
    },
}


class SamplingEngine:
    def __init__(self, data_dir='data'):
        """Initialize sampling engine with demographic configuration."""
        self.data_dir = data_dir
        self.project_root = Path(__file__).parent.parent.parent
        
        # Load existing data (optional - we use MongoDB now)
        try:
            self.cantons = load_cantons_csv(os.path.join(data_dir, 'cantons.csv'))
        except (FileNotFoundError, IOError):
            self.cantons = []  # Use MongoDB instead
        
        try:
            self.companies = load_companies_csv(os.path.join(data_dir, 'companies.csv'))
        except (FileNotFoundError, IOError):
            self.companies = []  # Use MongoDB instead
        
        try:
            self.occupations = load_occupations_json(os.path.join(data_dir, 'occupations.json'))
        except (FileNotFoundError, IOError, json.JSONDecodeError):
            self.occupations = []  # Use MongoDB instead
        
        try:
            self.surnames, self.surname_weights = load_name_csv(os.path.join(data_dir, 'surnames.csv'))
        except (FileNotFoundError, IOError):
            self.surnames, self.surname_weights = [], []  # Use MongoDB instead
        
        try:
            self.names_de, self.names_de_weights = load_name_csv(os.path.join(data_dir, 'names_de.csv'))
        except (FileNotFoundError, IOError):
            self.names_de, self.names_de_weights = [], []  # Use MongoDB instead
        
        try:
            self.names_fr, self.names_fr_weights = load_name_csv(os.path.join(data_dir, 'names_fr.csv'))
        except (FileNotFoundError, IOError):
            self.names_fr, self.names_fr_weights = [], []  # Use MongoDB instead
        
        try:
            self.names_it, self.names_it_weights = load_name_csv(os.path.join(data_dir, 'names_it.csv'))
        except (FileNotFoundError, IOError):
            self.names_it, self.names_it_weights = [], []  # Use MongoDB instead
        
        # Load demographic configuration
        self._load_demographic_config()
    
    def _load_demographic_config(self):
        """Load demographic configuration from JSON files."""
        # Load sampling_weights.json
        sampling_file = self.project_root / "data" / "sampling_weights.json"
        if sampling_file.exists():
            with open(sampling_file, "r", encoding="utf-8") as f:
                self.sampling_weights = json.load(f)
        else:
            self.sampling_weights = {
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
        
        # Load demographics.json
        demo_file = self.project_root / "data" / "demographics.json"
        if demo_file.exists():
            with open(demo_file, "r", encoding="utf-8") as f:
                self.demographics = json.load(f)
        else:
            self.demographics = {}
    
    def sample_canton(self):
        """Sample canton weighted by population (from MongoDB)."""
        # Use MongoDB query instead of CSV
        canton_doc = sample_canton_weighted()
        if canton_doc:
            # Return a simple object with primary_language
            class Canton:
                def __init__(self, doc):
                    self.code = doc.get("code", "")
                    self.name = doc.get("name_de", "")
                    self.population = doc.get("population", 0)
                    # Determine primary language from canton data
                    lang_de = doc.get("language_de", 0)
                    lang_fr = doc.get("language_fr", 0)
                    lang_it = doc.get("language_it", 0)
                    if lang_de >= lang_fr and lang_de >= lang_it:
                        self.primary_language = "de"
                    elif lang_fr >= lang_it:
                        self.primary_language = "fr"
                    else:
                        self.primary_language = "it"
            return Canton(canton_doc)
        return None
    
    def sample_language_for_canton(self, canton):
        """Sample language based on canton."""
        if canton is None:
            return Language("de")  # Default
        
        probs = {canton.primary_language: 0.9}
        for l in ['de', 'fr', 'it']:
            if l != canton.primary_language:
                probs[l] = probs.get(l, 0.05)
        langs = list(probs.keys())
        weights = list(probs.values())
        return Language(weighted_choice(langs, weights))
    
    def _calculate_age_from_group(self, age_group: str) -> int:
        """Calculate realistic age within age group."""
        if age_group == "18-25":
            return random.randint(18, 25)
        elif age_group == "26-40":
            return random.randint(26, 40)
        elif age_group == "41-65":
            return random.randint(41, 65)
        else:
            return random.randint(20, 65)
    
    def _calculate_years_experience(self, age: int, age_group: str) -> int:
        """Calculate years of experience based on age and age group."""
        min_years, max_years = get_typical_years_for_age_group(age_group)
        
        # Base calculation: age - education_end_age (typically 22)
        education_end_age = 22
        base_experience = max(0, age - education_end_age)
        
        # Add variance
        variance = random.gauss(0, 1.5)
        experience = int(base_experience + variance)
        
        # Clamp to realistic range for age group
        experience = max(min_years, min(max_years, experience))
        
        # Ensure it doesn't exceed age - 16
        experience = min(experience, max(0, age - 16))
        
        return experience
    
    def _derive_industry_from_berufsfeld(self, berufsfeld: str) -> str:
        """Derive industry from berufsfeld using mapping."""
        if not berufsfeld:
            return "other"
        
        bf_lower = berufsfeld.lower()
        
        # Industry mapping based on berufsfeld keywords
        BERUFSFELD_TO_INDUSTRY = {
            "informatik": "technology",
            "technologie": "technology",
            "it": "technology",
            "software": "technology",
            "gesundheit": "healthcare",
            "medizin": "healthcare",
            "pflege": "healthcare",
            "kranken": "healthcare",
            "spital": "healthcare",
            "wirtschaft": "finance",
            "finanz": "finance",
            "bank": "finance",
            "versicherung": "finance",
            "treuhan": "finance",
            "bau": "construction",
            "architektur": "construction",
            "handwerk": "construction",
            "garten": "construction",
            "landschaft": "construction",
            "industrie": "manufacturing",
            "maschinen": "manufacturing",
            "mechanik": "manufacturing",
            "produktion": "manufacturing",
            "metall": "manufacturing",
            "elektro": "manufacturing",
            "bildung": "education",
            "schule": "education",
            "lehrer": "education",
            "pädagog": "education",
            "handel": "retail",
            "verkauf": "retail",
            "detail": "retail",
            "laden": "retail",
            "gastro": "hospitality",
            "hotel": "hospitality",
            "küche": "hospitality",
            "restaurant": "hospitality",
            "tourismus": "hospitality",
        }
        
        for keyword, industry in BERUFSFELD_TO_INDUSTRY.items():
            if keyword in bf_lower:
                return industry
        
        return "other"
    
    def _validate_persona(self, persona_dict: Dict[str, Any]) -> bool:
        """Validate persona data for consistency."""
        age = persona_dict.get("age", 0)
        years_experience = persona_dict.get("years_experience", 0)
        age_group = persona_dict.get("age_group", "")
        career_level = persona_dict.get("career_level", "")
        portrait_path = persona_dict.get("portrait_path")
        
        # Check age is realistic for years_experience
        if years_experience > (age - 16):
            return False
        
        # Check career_level matches age_group (basic check)
        if age_group == "18-25" and career_level == "lead":
            return False
        if age_group == "41-65" and career_level == "junior":
            return False
        
        # Check portrait exists if path provided
        if portrait_path:
            full_path = self.project_root / "data" / "portraits" / portrait_path
            if not full_path.exists():
                return False
        
        return True

    def _fallback_first_name(self, language: str, gender: str) -> str:
        """Return a gender-consistent fallback first name.

        This is used when MongoDB name sampling isn't available.
        """
        lang = (language or "de").lower()[:2]
        g = (gender or "male").lower()
        if g not in ("male", "female"):
            g = "male"

        by_lang = _FALLBACK_FIRST_NAMES.get(lang)
        if by_lang and by_lang.get(g):
            return random.choice(by_lang[g])

        # Final fallback: pick from any language list for the requested gender.
        pool: List[str] = []
        for _lang, by_gender in _FALLBACK_FIRST_NAMES.items():
            pool.extend(by_gender.get(g, []))
        return random.choice(pool) if pool else "Alex"
    
    def sample_persona(self, preferred_canton=None, preferred_industry=None) -> Dict[str, Any]:
        """
        Sample persona with demographic weighting.
        
        Steps:
        1. Sample age_group (weighted)
        2. Sample gender (weighted)
        3. Calculate realistic age within group
        4. Sample years_experience based on age
        5. Determine career_level from age + years_experience
        6. Sample canton (population-weighted)
        7. Sample industry (NOGA-weighted or parameter)
        8. Sample occupation from CV_DATA (filter by industry)
        9. Sample language based on canton
        10. Sample name (language + gender)
        11. Sample company (canton + industry)
        12. Sample portrait path (gender + age_group)
        13. Get skills, activities, requirements from databases
        """
        # Step 1: Sample age_group
        age_group = sample_age_group()
        
        # Step 2: Sample gender
        gender = sample_gender()
        
        # Step 3: Calculate realistic age within group
        age = self._calculate_age_from_group(age_group)
        
        # Step 4: Sample years_experience based on age
        years_experience = self._calculate_years_experience(age, age_group)
        
        # Step 5: Determine career_level
        career_level = determine_career_level_by_age(age_group, years_experience)
        
        # Step 6: Sample canton
        if preferred_canton and preferred_canton != 'all':
            canton = next((c for c in self.cantons if c.code == preferred_canton), None)
            if not canton:
                canton = self.sample_canton()
        else:
            canton_doc = sample_canton_weighted()
            if canton_doc:
                # Find matching canton object
                canton = next((c for c in self.cantons if c.code == canton_doc.get("code")), None)
            if not canton:
                canton = self.sample_canton()
        
        # Step 7+8: Sample occupation FIRST, then derive industry from it
        if preferred_industry:
            occupation_doc = sample_occupation_by_industry(preferred_industry)
            industry = preferred_industry
        else:
            # Sample occupation first, then derive industry
            occupation_doc = sample_occupation_by_industry(sample_industry_weighted())
        
        job_id = occupation_doc.get("job_id") if occupation_doc else None
        occupation_title = occupation_doc.get("title") if occupation_doc else f"{career_level.capitalize()} Worker"
        
        # DERIVE industry FROM occupation to avoid mismatch
        if occupation_doc and not preferred_industry:
            # Get industry from occupation's berufsfelder
            berufsfelder = occupation_doc.get("categories", {}).get("berufsfelder", [])
            if berufsfelder:
                industry = self._derive_industry_from_berufsfeld(berufsfelder[0])
            else:
                industry = "other"
        elif not preferred_industry:
            industry = "other"
        
        industry_employment_pct = get_industry_employment_percentage(industry)
        
        # Step 9: Sample language based on canton
        language = self.sample_language_for_canton(canton)
        language_str = language.value if hasattr(language, 'value') else str(language)
        
        # Step 10: Sample name (language + gender)
        # IMPORTANT: keep first_name consistent with sampled gender so portrait/name don't drift.
        try:
            first_name_doc = sample_first_name(language_str, gender)
        except Exception:
            first_name_doc = None

        try:
            last_name_doc = sample_last_name(language_str)
        except Exception:
            last_name_doc = None

        if first_name_doc:
            first_name = first_name_doc.get("name", "Unknown")
        else:
            # Gender-safe fallback (do not use mixed-gender CSV lists here)
            first_name = self._fallback_first_name(language_str, gender)
        
        if last_name_doc:
            last_name = last_name_doc.get("name", "Unknown")
        else:
            # Fallback to CSV data
            if self.surnames:
                last_name = weighted_choice(self.surnames, self.surname_weights)
            else:
                last_name = random.choice(['Müller', 'Meier', 'Schmid', 'Bianchi'])
        
        # Step 11: Sample company
        company_doc = sample_company_by_canton_and_industry(canton.code, industry)
        company_name = company_doc.get("name") if company_doc else "Acme AG"
        
        # Step 12: Sample portrait path
        portrait_path = sample_portrait_path(gender, age_group)
        
        # Step 13: Get skills, activities, requirements
        skills_list = []
        if job_id:
            skills_docs = get_skills_by_occupation(job_id)
            skills_list = [s.get("skill_name_de", "") for s in skills_docs if s.get("skill_name_de")]
        
        activities_list = []
        if job_id:
            activities_list = get_activities_by_occupation(job_id) or []
        
        # Build persona dictionary
        persona_dict = {
            # Basic info
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}",
            "gender": gender,
            "canton": canton.code,
            "language": language_str,
            
            # Age and experience
            "age": age,
            "birth_year": date.today().year - age,
            "age_group": age_group,
            "years_experience": years_experience,
            "career_level": career_level,
            
            # Professional info
            "industry": industry,
            "industry_employment_pct": industry_employment_pct,
            "current_title": occupation_title,
            "job_id": job_id,
            "occupation": occupation_title,
            
            # Company
            "company": company_name,
            
            # Portrait
            "portrait_path": portrait_path,
            
            # Skills and activities
            "skills": skills_list,
            "activities": activities_list,
            
            # Contact
            "email": f"{first_name.lower()}.{last_name.lower()}@example.ch",
            "phone": f"07{random.randint(60, 99)}{random.randint(100000, 999999)}",
            
            # Career history (simplified)
            "career_history": [{
                "title": occupation_title,
                "company": company_name,
                "start_date": f"{date.today().year - years_experience}-01",
                "end_date": None,
                "desc": "Worked on projects."
            }],
            
            # Additional
            "summary": None,
        }
        
        # Validate persona
        if not self._validate_persona(persona_dict):
            # Retry once if validation fails
            return self.sample_persona(preferred_canton, preferred_industry)
        
        return persona_dict
    
    def sample_batch_with_demographics(self, count: int) -> List[Dict[str, Any]]:
        """
        Generate multiple personas and verify demographic distribution.
        
        Args:
            count: Number of personas to generate.
        
        Returns:
            List of persona dictionaries.
        """
        personas = []
        
        for i in range(count):
            persona = self.sample_persona()
            personas.append(persona)
        
        # Verify demographic distribution
        age_groups = Counter(p.get("age_group") for p in personas)
        genders = Counter(p.get("gender") for p in personas)
        industries = Counter(p.get("industry") for p in personas)
        career_levels = Counter(p.get("career_level") for p in personas)
        
        print(f"\n=== Demographic Distribution for {count} Personas ===")
        print(f"\nAge Groups:")
        for ag in ["18-25", "26-40", "41-65"]:
            count_ag = age_groups.get(ag, 0)
            pct = (count_ag / count * 100) if count > 0 else 0
            expected_pct = self.sampling_weights["age_groups"].get(ag, {}).get("weight", 0)
            print(f"  {ag}: {count_ag} ({pct:.1f}%) [Expected: {expected_pct:.1f}%]")
        
        print(f"\nGender:")
        for g in ["male", "female"]:
            count_g = genders.get(g, 0)
            pct = (count_g / count * 100) if count > 0 else 0
            expected_pct = self.sampling_weights["gender_distribution"].get(g, {}).get("percentage", 50)
            print(f"  {g}: {count_g} ({pct:.1f}%) [Expected: {expected_pct:.1f}%]")
        
        print(f"\nCareer Levels:")
        for cl in ["junior", "mid", "senior", "lead"]:
            count_cl = career_levels.get(cl, 0)
            pct = (count_cl / count * 100) if count > 0 else 0
            print(f"  {cl}: {count_cl} ({pct:.1f}%)")
        
        print(f"\nTop 5 Industries:")
        for ind, count_ind in industries.most_common(5):
            pct = (count_ind / count * 100) if count > 0 else 0
            emp_pct = get_industry_employment_percentage(ind)
            print(f"  {ind}: {count_ind} ({pct:.1f}%) [Employment: {emp_pct:.1f}%]")
        
        return personas
