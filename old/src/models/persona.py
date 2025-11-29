from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator
from datetime import date

CANTONS = [
    'ZH','BE','LU','UR','SZ','OW','NW','GL','ZG','FR','SO','BS','BL','SH','AR','AI','SG','GR','AG','TG','TI','VD','VS','NE','GE','JU'
]

LANGS = ['de','fr','it','en']

class ExperienceEntry(BaseModel):
    title: str
    company: Optional[str] = None
    start_year: int
    end_year: Optional[int] = None
    description: Optional[str] = None

    @validator('end_year')
    def validate_years(cls, v, values):
        if v is not None and v < values['start_year']:
            raise ValueError('end_year must be >= start_year')
        return v

class EducationEntry(BaseModel):
    degree: str
    institution: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None

class SwissPersona(BaseModel):
    first_name: str
    last_name: str
    gender: Optional[Literal['male','female','other']] = None
    birth_year: int = Field(..., ge=1900, le=date.today().year)
    canton: str = Field(..., description="Swiss canton 2-letter code")
    language: str = Field('de', description="Primary language code: de/fr/it/en")
    email: Optional[str] = None
    phone: Optional[str] = None
    experiences: List[ExperienceEntry] = []
    education: List[EducationEntry] = []
    skills: List[str] = []
    summary: Optional[str] = None
    metadata: Optional[dict] = {}

    @validator('canton')
    def canton_must_be_valid(cls, v):
        if v not in CANTONS:
            raise ValueError(f'Invalid canton code: {v}')
        return v

    @validator('language')
    def language_must_be_valid(cls, v):
        if v not in LANGS:
            raise ValueError(f'Invalid language code: {v}')
        return v

    @property
    def age(self) -> int:
        return date.today().year - self.birth_year

    def total_experience_years(self) -> int:
        total = 0
        for e in self.experiences:
            if e.end_year is None:
                end = date.today().year
            else:
                end = e.end_year
            total += max(0, end - e.start_year)
        return total

    @validator('experiences', whole=True)
    def experience_vs_age(cls, v, values):
        # best-effort check: total experience should be <= age - 15 (school start)
        birth = values.get('birth_year')
        if birth is None:
            return v
        age = date.today().year - birth
        total = 0
        for e in v:
            end = e.end_year or date.today().year
            total += max(0, end - e.start_year)
        if total > max(0, age - 15):
            raise ValueError('Total experience exceeds plausible bound for given age.')
        return v



