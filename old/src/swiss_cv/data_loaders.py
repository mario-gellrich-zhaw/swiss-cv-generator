import os
import json
import random
from typing import List, Dict, Any, Optional

# Data directory is ../data relative to this module (matches existing code expectations)
DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))

def load_json(path: str) -> Any:
    """
    Read a JSON file using utf-8-sig so files with a BOM are accepted.
    """
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def load_cantons() -> List[Dict[str, Any]]:
    path = os.path.join(DATA_DIR, "cantons.json")
    return load_json(path)

def load_occupations() -> List[Dict[str, Any]]:
    path = os.path.join(DATA_DIR, "occupations.json")
    return load_json(path)

def load_companies() -> List[Dict[str, Any]]:
    path = os.path.join(DATA_DIR, "companies.json")
    return load_json(path)

def sample_weighted(items: List[Dict[str, Any]], weight_key: str = "workforce", rnd: Optional[random.Random] = None) -> Dict[str, Any]:
    """
    Sample one item from items, weighted by weight_key if present.
    Returns one item (not a list).
    """
    if not items:
        raise ValueError("items must not be empty")
    if rnd is None:
        rnd = random.Random()
    weights = []
    for it in items:
        w = it.get(weight_key, 1)
        try:
            w = float(w)
        except Exception:
            w = 1.0
        weights.append(max(0.0, w))
    # if all weights are zero, fall back to uniform
    if sum(weights) == 0:
        idx = rnd.randrange(len(items))
        return items[idx]
    # random.choices available in Py3.6+; use it
    chosen = rnd.choices(items, weights=weights, k=1)[0]
    return chosen



