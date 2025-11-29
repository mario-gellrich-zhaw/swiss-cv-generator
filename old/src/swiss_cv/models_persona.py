from pydantic import BaseModel, Field, validator
from typing import List, Optional
from dataclasses import dataclass

class Experience(BaseModel):
    title: str
    company: str
    start_year: int
    end_year: Optional[int]
    description: Optional[str]

class SwissPersona(BaseModel):
    first_name: str
    last_name: str
    age: int
    canton: str
    language: str
    email: str
    phone: str
    summary: Optional[str] = None
    experiences: List[Experience] = Field(default_factory=list)

    @validator('age')
    def age_reasonable(cls, v):
        if v < 16 or v > 80:
            raise ValueError('age out of realistic range')
        return v


