"""Benchmarks for token estimator."""

from pathlib import Path

from pytest_benchmark.fixture import BenchmarkFixture

from lightspeed_stack.utils.token_estimator import (
    estimate_tokens,
)

LOREM_IPSUM = """
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor
incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis
nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu
fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in
culpa qui officia deserunt mollit anim id est laborum.
"""


def test_estimate_empty_string(benchmark: BenchmarkFixture) -> None:
    """Benchmark for tokenizing empty string.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    input_string = ""
    benchmark(estimate_tokens, input_string)


def test_estimate_hello_world(benchmark: BenchmarkFixture) -> None:
    """Benchmark for tokenizing the string Hello world.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    input_string = "Hello world"
    benchmark(estimate_tokens, input_string)


def test_pangram(benchmark: BenchmarkFixture) -> None:
    """Benchmark for tokenizing known English pangram.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    input_string = "The quick brown fox jumps over the lazy dog."
    benchmark(estimate_tokens, input_string)


def test_lorem_ipsum(benchmark: BenchmarkFixture) -> None:
    """Benchmark for tokenizing Lorem Ipsum text.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    input_string = LOREM_IPSUM
    benchmark(estimate_tokens, input_string)


def test_lorem_ipsum_times_10_times(benchmark: BenchmarkFixture) -> None:
    """Benchmark for tokenizing Lorem Ipsum text repeated ten times.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    input_string = LOREM_IPSUM * 10
    benchmark(estimate_tokens, input_string)


def test_lorem_ipsum_times_100_times(benchmark: BenchmarkFixture) -> None:
    """Benchmark for tokenizing Lorem Ipsum text repeated 100x.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    input_string = LOREM_IPSUM * 100
    benchmark(estimate_tokens, input_string)


def test_lorem_ipsum_times_1000_times(benchmark: BenchmarkFixture) -> None:
    """Benchmark for tokenizing Lorem Ipsum text repeated 1000x.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    input_string = LOREM_IPSUM * 1000
    benchmark(estimate_tokens, input_string)


def test_lorem_ipsum_times_2000_times(benchmark: BenchmarkFixture) -> None:
    """Benchmark for tokenizing Lorem Ipsum text repeated 2000x.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    input_string = LOREM_IPSUM * 2000
    benchmark(estimate_tokens, input_string)


def benchmark_file_tokenization(benchmark: BenchmarkFixture, filename: str) -> None:
    """Read the given file and tokenize it as benchmark.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.
        filename: name of file whose content should be tokenized.

    Returns:
    -------
        None
    """
    data_dir = Path(__file__).parent / "data"
    with (data_dir / filename).open(encoding="utf-8") as fin:
        input_string = fin.read()
        # tokenize the file content
        benchmark(estimate_tokens, input_string)


def test_xml_file_10_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing XML file containing just 10 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "xml_10_lines.xml")


def test_xml_file_100_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing XML file containing just 100 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "xml_100_lines.xml")


def test_xml_file_1000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing XML file containing just 1000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "xml_1000_lines.xml")


def test_xml_file_10000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing XML file containing just 10000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "xml_10000_lines.xml")


def test_yaml_file_10_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing YAML file containing just 10 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "yaml_10_lines.yml")


def test_yaml_file_100_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing YAML file containing just 100 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "yaml_100_lines.yml")


def test_yaml_file_1000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing YAML file containing just 1000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "yaml_1000_lines.yml")


def test_yaml_file_10000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing YAML file containing just 10000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "yaml_10000_lines.yml")


def test_json_file_10_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing JSON file containing just 10 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "json_10_lines.json")


def test_json_file_100_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing JSON file containing just 100 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "json_100_lines.json")


def test_json_file_1000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing JSON file containing just 1000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "json_1000_lines.json")


def test_json_file_10000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing JSON file containing just 10000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "json_10000_lines.json")


def test_python_source_10_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing Python script containing just 10 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "python_10_lines.py")


def test_python_source_100_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing Python script containing just 100 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "python_100_lines.py")


def test_python_source_1000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing Python script containing just 1000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "python_1000_lines.py")


def test_python_source_10000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing Python script containing just 10000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "python_10000_lines.py")


def test_javascript_source_10_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing JavaScript script containing just 10 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "js_10_lines.js")


def test_javascript_source_100_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing JavaScript script containing just 100 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "js_100_lines.js")


def test_javascript_source_1000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing JavaScript script containing just 1000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "js_1000_lines.js")


def test_javascript_source_10000_lines(benchmark: BenchmarkFixture) -> None:
    """Test tokenizing JavaScript script containing just 10000 lines.

    Parameters:
    ----------
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
    -------
        None
    """
    benchmark_file_tokenization(benchmark, "js_10000_lines.js")
