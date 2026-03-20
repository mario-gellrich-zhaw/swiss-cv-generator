from src.generation.sampling import SamplingEngine

def test_sampling_canton_distribution():
    engine = SamplingEngine()
    # sample many times and assert we get values (statistical validation to be implemented in CI)
    samples = [engine.sample_canton().code for _ in range(100)]
    assert len(samples) == 100
