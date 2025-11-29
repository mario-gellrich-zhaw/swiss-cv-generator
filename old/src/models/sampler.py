import json
import random
from typing import Optional
from src.data_loaders import bfs_loader

def sample_canton(processed_json_path: str = 'data/processed/pop_by_canton.json', seed: Optional[int]=None) -> str:
    data = bfs_loader.load_processed_population(processed_json_path)
    if not data:
        raise ValueError('No canton population data available.')
    # deterministic RNG if seed provided
    rng = random.Random(seed)
    cantons = list(data.keys())
    weights = [data[c] for c in cantons]
    total = sum(weights)
    if total <= 0:
        raise ValueError('Population weights sum to zero.')
    # sample by cumulative weights
    r = rng.random() * total
    cum = 0.0
    for c, w in zip(cantons, weights):
        cum += w
        if r <= cum:
            return c
    return cantons[-1]



