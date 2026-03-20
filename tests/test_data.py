import pytest
from src.data.loader import load_cantons_csv

def test_load_cantons():
    c = load_cantons_csv('data/cantons.csv')
    assert len(c) > 0
    assert any(ci.code == 'ZH' for ci in c)
