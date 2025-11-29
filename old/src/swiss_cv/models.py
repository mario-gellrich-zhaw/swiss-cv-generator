from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field

class CantonInfo(BaseModel):
    code: str
    name: str
    population: Optional[int]
    workforce: Optional[int]
    languages: Optional[List[str]] = []

class OccupationCategory(BaseModel):
    code: str
    title: str
    translations: Optional[dict] = {}

class CompanyInfo(BaseModel):
    name: str
    canton: Optional[str]
    industry: Optional[str]

class CareerEntry(BaseModel):
    title: str
    company: Optional[str]
    period: Optional[str]
    bullets: Optional[List[str]] = []

class SwissPersona(BaseModel):
    first_name: str
    last_name: str
    age: Optional[int]
    years_experience: Optional[int] = Field(None, alias='years_experience')
    gender: Optional[str]
    primary_language: Optional[str]
    canton: Optional[str]
    city: Optional[str]
    phone: Optional[str]
    email: Optional[EmailStr]
    title: Optional[str]
    industry: Optional[str]
    summary: Optional[str]
    career_history: Optional[List[CareerEntry]] = []


