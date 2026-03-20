from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from enum import Enum

class Language(str, Enum):
    de = 'de'
    fr = 'fr'
    it = 'it'
    en = 'en'

class Industry(str, Enum):
    technology = 'technology'
    finance = 'finance'
    healthcare = 'healthcare'
    construction = 'construction'
    manufacturing = 'manufacturing'
    education = 'education'
    retail = 'retail'
    hospitality = 'hospitality'
    other = 'other'

class CareerLevel(str, Enum):
    junior = 'junior'
    mid = 'mid'
    senior = 'senior'
    lead = 'lead'

class CantonInfo(BaseModel):
    code: str = Field(..., description='Canton code, e.g. ZH')
    name: str
    population: int
    workforce: Optional[int] = None
    primary_language: Language

class OccupationCategory(BaseModel):
    id: str
    name_de: str
    name_fr: Optional[str] = None
    name_it: Optional[str] = None
    description_de: str
    berufsfeld: str
    branchen: str
    industry: Industry
    bildungstyp: str
    swissdoc: str
    related_ids: List[str] = []
    
    def get_name(self, language: str = "de") -> str:
        """
        Get the occupation name in the specified language.
        
        Args:
            language: Language code ('de', 'fr', 'it'). Defaults to 'de'.
        
        Returns:
            Name in the specified language, or German name if translation not available.
        """
        if language == "fr" and self.name_fr:
            return self.name_fr
        elif language == "it" and self.name_it:
            return self.name_it
        else:
            return self.name_de

class CompanyInfo(BaseModel):
    name: str
    canton: str
    industry: str
    size_band: Optional[str] = None  # e.g. '1-10','11-50','50-250','250+'

class ExperienceThresholds:
    """
    Defines experience thresholds for career levels across industries.
    
    Thresholds:
    - junior: 0-2 years
    - mid: 3-6 years
    - senior: 7-11 years
    - lead: 12+ years
    """
    
    @classmethod
    def get_level(cls, industry: Industry, years: float) -> CareerLevel:
        """
        Determine career level based on industry and years of experience.
        
        Args:
            industry: Industry enum value
            years: Years of experience (can be float)
        
        Returns:
            CareerLevel enum value
        """
        if years < 0:
            years = 0
        
        if years <= 2:
            return CareerLevel.junior
        elif years <= 6:
            return CareerLevel.mid
        elif years <= 11:
            return CareerLevel.senior
        else:
            return CareerLevel.lead

class SwissPersona(BaseModel):
    first_name: str
    last_name: str
    full_name: str
    canton: str
    language: Language
    age: int
    birth_year: int
    gender: Optional[str]
    experience_years: float
    industry: str
    current_title: str
    career_history: List[dict]  # list of {'title','company','start_date','end_date','desc'}
    email: EmailStr
    phone: str
    skills: List[str]
    summary: Optional[str] = None
    photo_path: Optional[str] = None


