"""Benchmarks for cache method connect."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.in_memory_cache import InMemoryCache


def test_memory_cache(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the connect method."""
    benchmark(memory_cache_fixture.connect)
