"""
Occupation title lookup from berufsberatung.ch source data.

Provides native multilingual titles (DE/FR/IT/EN) directly from the
official berufsberatung.ch dataset — no AI translation needed.

IDs match the job_id field in MongoDB (string representation of numeric ID).
"""
import json
from pathlib import Path
from typing import Optional, Dict

_SOURCE_FILE = Path(__file__).parent.parent.parent / "data" / "source" / "berufsberatung_occupations_de_fr_it_en.json"

# Cache: {job_id_str: {lang: title}}
_LOOKUP: Optional[Dict[str, Dict[str, str]]] = None


def _load_lookup() -> Dict[str, Dict[str, str]]:
    """Load and cache the multilingual occupation title lookup table."""
    global _LOOKUP
    if _LOOKUP is not None:
        return _LOOKUP

    _LOOKUP = {}
    if not _SOURCE_FILE.exists():
        return _LOOKUP

    with open(_SOURCE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for entry in data:
        job_id = str(entry.get("id", ""))
        if not job_id:
            continue
        languages = entry.get("languages", {})
        _LOOKUP[job_id] = {
            lang: lang_data.get("title", "")
            for lang, lang_data in languages.items()
            if isinstance(lang_data, dict) and lang_data.get("title")
        }

    return _LOOKUP


def get_native_occupation_title(job_id: Optional[str], language: str) -> Optional[str]:
    """
    Return the official occupation title in the requested language.

    Args:
        job_id: Occupation ID (matches MongoDB job_id field).
        language: Target language ('de', 'fr', 'it', 'en').

    Returns:
        Native title string, or None if not found.
    """
    if not job_id:
        return None
    lookup = _load_lookup()
    titles = lookup.get(str(job_id), {})
    return titles.get(language.lower()) or None


def get_german_occupation_title(job_id: Optional[str]) -> Optional[str]:
    """Return the German base title for an occupation ID."""
    return get_native_occupation_title(job_id, "de")
