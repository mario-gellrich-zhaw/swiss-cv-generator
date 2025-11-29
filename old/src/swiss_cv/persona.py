import random
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class SwissPersona:
    first_name: str
    last_name: str
    gender: str
    age: int
    years_experience: int
    canton: str
    canton_name: str
    language: str
    occupation: str
    employer: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    summary: Optional[str] = None

    def to_dict(self):
        return asdict(self)



