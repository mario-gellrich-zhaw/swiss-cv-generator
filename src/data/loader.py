import csv
import json
from typing import List, Dict, Optional
from .models import CantonInfo, OccupationCategory, CompanyInfo

def _normalize_dictreader_row(row: Dict[str, str]) -> Dict[str, str]:
    """Return a dict with keys normalized (strip BOM and whitespace)."""
    new: Dict[str, str] = {}
    for k, v in row.items():
        if k is None:
            continue
        nk = k.lstrip('\ufeff').strip()
        new[nk] = v
    return new

def _safe_int(val: Optional[str], default: Optional[int] = None) -> Optional[int]:
    if val is None:
        return default
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if s == "":
        return default
    # remove thousand separators commonly used (commas / spaces)
    s = s.replace(" ", "").replace(",", "")
    return int(s) if s.isdigit() else default

def load_cantons_csv(path: str) -> List[CantonInfo]:
    cants: List[CantonInfo] = []
    with open(path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        # Defensive: normalize fieldnames if a BOM sneaked into the first header
        if reader.fieldnames:
            reader.fieldnames = [fn.lstrip('\ufeff').strip() if fn else fn for fn in reader.fieldnames]
        for r in reader:
            rr = _normalize_dictreader_row(r)
            # Accept common header variants to be tolerant of various CSV sources
            code = rr.get('code') or rr.get('Code') or rr.get('kanton') or rr.get('Kanton')
            name = rr.get('name') or rr.get('Name')
            population = rr.get('population') or rr.get('Population') or rr.get('pop') or '0'
            workforce = rr.get('workforce') or rr.get('Workforce') or rr.get('work') or None
            primary_language = rr.get('primary_language') or rr.get('Primary_language') or rr.get('language') or rr.get('Language') or 'de'
            cants.append(CantonInfo(
                code=code,
                name=name,
                population=_safe_int(population, 0) or 0,
                workforce=_safe_int(workforce, None),
                primary_language=primary_language or 'de'
            ))
    return cants

def load_companies_csv(path: str) -> List[CompanyInfo]:
    comps: List[CompanyInfo] = []
    with open(path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames:
            reader.fieldnames = [fn.lstrip('\ufeff').strip() if fn else fn for fn in reader.fieldnames]
        for r in reader:
            rr = _normalize_dictreader_row(r)
            comps.append(CompanyInfo(
                name=rr.get('name') or rr.get('Name') or '',
                canton=rr.get('canton') or rr.get('Kanton') or rr.get('Canton') or '',
                industry=rr.get('industry') or rr.get('Industry') or '',
                size_band=rr.get('size_band') or rr.get('size') or rr.get('sizeBand') or ''
            ))
    return comps

def load_occupations_json(path: str) -> List[OccupationCategory]:
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    occs = [OccupationCategory(**o) for o in data.get('occupations', [])]
    return occs

# NOTE: For production, replace any sample files in data/ with official SFSO exports.
