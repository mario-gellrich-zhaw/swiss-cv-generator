# src/generation/__init__.py
"""
CV Generation Package.

This package provides all CV generation functionality:
- sampling: Persona sampling with demographics
- cv_assembler: Complete CV assembly
- cv_education_generator: Education history generation
- cv_job_history_generator: Job history generation
- cv_activities_transformer: Activity to achievement transformation
- cv_continuing_education: Continuing education generation
- cv_timeline_validator: Timeline validation and auto-fix
- cv_quality_validator: Quality validation and scoring
- company_validator: Company-occupation matching
- metrics_validator: Metric validation and ranges
- openai_client: Centralized OpenAI client
"""

from src.generation.sampling import SamplingEngine
from src.generation.cv_assembler import generate_complete_cv, CVDocument
from src.generation.cv_timeline_validator import validate_cv_timeline
from src.generation.cv_quality_validator import validate_cv_quality
from src.generation.openai_client import (
    call_openai_chat,
    call_openai_json,
    is_openai_available,
    get_openai_client
)

__all__ = [
    # Main classes
    "SamplingEngine",
    "CVDocument",
    
    # Main functions
    "generate_complete_cv",
    "validate_cv_timeline",
    "validate_cv_quality",
    
    # OpenAI utilities
    "call_openai_chat",
    "call_openai_json",
    "is_openai_available",
    "get_openai_client",
]
