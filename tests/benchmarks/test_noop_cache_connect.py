"""Benchmarks for cache method connect."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.noop_cache import NoopCache


def test_noop_cache(noop_cache_fixture: NoopCache, benchmark: BenchmarkFixture) -> None:
    """Benchmark for the connect method."""
    benchmark(noop_cache_fixture.connect)
