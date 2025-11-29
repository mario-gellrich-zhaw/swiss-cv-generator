import json, random, os
from pathlib import Path
from typing import Tuple, List

BASE_DIR = Path(__file__).resolve().parent.parent
CANTON_FILE = os.path.join(BASE_DIR, 'data', 'cantons_official.json')

_first_names = {
    "de": ["Andreas","Stefan","Laura","Michael","Anna","Lukas","Sofia","Simon","Daniel","Sandra","Nadine","Tobias"],
    "fr": ["Pierre","Luc","Camille","Sophie","Claire","Julien","Marine","Thierry","Nicolas"],
    "it": ["Luca","Giulia","Marco","Lucia","Francesco","Chiara"]
}
_last_names = {
    "de": ["Müller","Meier","Schmid","Keller","Schneider","Frei","Zimmermann"],
    "fr": ["Dubois","Leroy","Martin","Morel"],
    "it": ["Rossi","Bianchi","Ferrari","Bruno"]
}

def load_cantons():
    if not os.path.exists(CANTON_FILE):
        # fallback to a small default
        return [
            {"code":"ZH","name":"Zürich","population":1600000,"language":"de"},
            {"code":"BE","name":"Bern","population":1030000,"language":"de"},
            {"code":"VD","name":"Vaud","population":800000,"language":"fr"},
            {"code":"GE","name":"Genève","population":500000,"language":"fr"},
            {"code":"TI","name":"Ticino","population":350000,"language":"it"}
        ]
    with open(CANTON_FILE,'r',encoding='utf-8') as f:
        return json.load(f)

_cantons = load_cantons()

def sample_canton_language() -> Tuple[str,str]:
    pick = random.choices(_cantons, weights=[c.get('population',1) for c in _cantons], k=1)[0]
    return pick['code'], pick.get('language','de')

def sample_age_and_experience():
    age = int(random.normalvariate(35,9))
    age = max(18, min(age, 65))
    base_start = 22
    exp = max(0, age - base_start - random.randint(0,3))
    return age, exp

def sample_name(language: str) -> Tuple[str,str]:
    lang = language if language in _first_names else 'de'
    first = random.choice(_first_names[lang])
    last = random.choice(_last_names.get(lang, _last_names['de']))
    return first, last

def sample_phone():
    prefix = random.choice(['076','077','078','079'])
    body = ''.join(str(random.randint(0,9)) for _ in range(7))
    return f'+41 {prefix} {body[:3]} {body[3:]}'

def sample_email(first: str, last: str, canton: str):
    domains = ['example.ch','bluewin.ch','gmx.ch','gmail.com']
    safe = f"{first.lower().replace(' ','')}.{last.lower().replace(' ','')}"
    return f"{safe}@{random.choice(domains)}"


