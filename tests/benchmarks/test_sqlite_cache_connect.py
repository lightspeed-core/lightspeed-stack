"""Benchmarks for cache method connect."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.sqlite_cache import SQLiteCache


def test_sqlite_cache(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the connect method."""
    benchmark(sqlite_cache_fixture.connect)
