"""Unit tests for utils.metadata module."""

import pytest

from utils.metadata import parse_knowledge_search_metadata, METADATA_LABEL_PATTERN


def test_metadata_pattern_exists():
    """Test that METADATA_LABEL_PATTERN is properly defined and captures labels correctly."""
    assert METADATA_LABEL_PATTERN is not None
    assert hasattr(METADATA_LABEL_PATTERN, "finditer")

    # Test that the pattern captures metadata labels case-insensitively
    sample = "Foo\nMetadata: {'a': 1}\nMETADATA: {'b': 2}\nBar"
    matches = list(METADATA_LABEL_PATTERN.finditer(sample))
    assert len(matches) == 2

    # Check that the matches are at the expected positions
    assert sample[matches[0].start() : matches[0].end()] == "Metadata: "
    assert sample[matches[1].start() : matches[1].end()] == "METADATA: "


def test_parse_knowledge_search_metadata_valid_single():
    """Test parsing valid metadata with single entry."""
    text = """Result 1
Content: Some content
Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1', 'document_id': 'doc-1'}
"""
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 1
    assert "doc-1" in result
    assert result["doc-1"]["docs_url"] == "https://example.com/doc1"
    assert result["doc-1"]["title"] == "Doc1"
    assert result["doc-1"]["document_id"] == "doc-1"


def test_parse_knowledge_search_metadata_valid_multiple():
    """Test parsing valid metadata with multiple entries."""
    text = """Result 1
Content: Some content
Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1', 'document_id': 'doc-1'}

Result 2
Content: More content
Metadata: {'docs_url': 'https://example.com/doc2', 'title': 'Doc2', 'document_id': 'doc-2'}
"""
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 2
    assert "doc-1" in result
    assert "doc-2" in result
    assert result["doc-1"]["title"] == "Doc1"
    assert result["doc-2"]["title"] == "Doc2"


def test_parse_knowledge_search_metadata_no_metadata():
    """Test parsing text with no metadata."""
    text = """Result 1
Content: Some content without metadata
"""
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 0


def test_parse_knowledge_search_metadata_missing_document_id():
    """Test parsing metadata without document_id is ignored."""
    text = """Result 1
Content: Some content
Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1'}
"""
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 0


def test_parse_knowledge_search_metadata_malformed_literal():
    """Test parsing malformed Python literal raises ValueError."""
    text = """Result 1
Content: Some content
Metadata: {'docs_url': 'https://example.com/doc1' 'title': 'Doc1', 'document_id': 'doc-1'}
"""
    with pytest.raises(ValueError) as exc_info:
        parse_knowledge_search_metadata(text)

    assert "Failed to parse metadata" in str(exc_info.value)


def test_parse_knowledge_search_metadata_invalid_syntax():
    """Test parsing invalid Python syntax raises ValueError."""
    text = """Result 1
Content: Some content
Metadata: {func_call(): 'value', 'title': 'Doc1', 'document_id': 'doc-1'}
"""
    with pytest.raises(ValueError) as exc_info:
        parse_knowledge_search_metadata(text)

    assert "Failed to parse metadata" in str(exc_info.value)


def test_parse_knowledge_search_metadata_non_dict():
    """Test parsing non-dict metadata is ignored."""
    text = """Result 1
Content: Some content
Metadata: "just a string"
"""
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 0


def test_parse_knowledge_search_metadata_mixed_valid_invalid():
    """Test parsing text with both valid and invalid metadata."""
    text = """Result 1
Content: Some content
Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1', 'document_id': 'doc-1'}

Result 2
Content: Bad content
Metadata: {'docs_url': 'https://example.com/doc2' 'title': 'Doc2', 'document_id': 'doc-2'}
"""
    with pytest.raises(ValueError) as exc_info:
        parse_knowledge_search_metadata(text)

    assert "Failed to parse metadata" in str(exc_info.value)


def test_parse_knowledge_search_metadata_whitespace_handling():
    """Test parsing metadata with various whitespace patterns."""
    text = """Result 1
Content: Some content
   Metadata:   {'docs_url': 'https://example.com/doc1', 'title': 'Doc1', 'document_id': 'doc-1'}   
"""
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 1
    assert "doc-1" in result
    assert result["doc-1"]["title"] == "Doc1"


def test_parse_metadata_duplicate_document_id_last_wins():
    """Test that duplicate document_id entries overwrite (last wins)."""
    text = (
        "Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1a', "
        "'document_id': 'dup'}\n"
        "Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1b', "
        "'document_id': 'dup'}"
    )
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 1
    assert set(result.keys()) == {"dup"}
    assert result["dup"]["title"] == "Doc1b"


def test_parse_knowledge_search_metadata_non_strict_mode():
    """Test non-strict mode skips invalid blocks and continues parsing."""
    text = """Result 1
Content: Valid content
Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1', 'document_id': 'doc-1'}

Result 2
Content: Bad content
Metadata: {'docs_url': 'https://example.com/doc2' 'title': 'Doc2', 'document_id': 'doc-2'}

Result 3
Content: More valid content
Metadata: {'docs_url': 'https://example.com/doc3', 'title': 'Doc3', 'document_id': 'doc-3'}
"""
    result = parse_knowledge_search_metadata(text, strict=False)

    # Should have 2 valid documents, skipping the malformed one
    assert len(result) == 2
    assert "doc-1" in result
    assert "doc-3" in result
    assert "doc-2" not in result  # malformed entry should be skipped
    assert result["doc-1"]["title"] == "Doc1"
    assert result["doc-3"]["title"] == "Doc3"


def test_parse_knowledge_search_metadata_strict_mode_default():
    """Test that strict mode is the default behavior."""
    text = """Result 1
Content: Valid content
Metadata: {'docs_url': 'https://example.com/doc1', 'title': 'Doc1', 'document_id': 'doc-1'}

Result 2
Content: Bad content
Metadata: {'docs_url': 'https://example.com/doc2' 'title': 'Doc2', 'document_id': 'doc-2'}
"""
    # Should raise ValueError in strict mode (default)
    with pytest.raises(ValueError) as exc_info:
        parse_knowledge_search_metadata(text)

    assert "Failed to parse metadata" in str(exc_info.value)

    # Explicitly setting strict=True should behave the same
    with pytest.raises(ValueError) as exc_info:
        parse_knowledge_search_metadata(text, strict=True)

    assert "Failed to parse metadata" in str(exc_info.value)


def test_metadata_pattern_case_insensitive_and_nested():
    """Test case-insensitive matching and nested payloads."""
    text = """Result
Content
METADATA: {'document_id': 'doc-1', 'nested': {'k': [1, 2, 3]}, 'title': 'Nested Doc'}
Another result
metadata: {'document_id': 'doc-2', 'complex': {'a': {'b': {'c': 42}}, 'list': [{'x': 1}, {'y': 2}]}, 'title': 'Complex Doc'}
"""
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 2
    assert "doc-1" in result
    assert "doc-2" in result

    # Verify the nested structure was parsed correctly
    assert result["doc-1"]["nested"]["k"] == [1, 2, 3]
    assert result["doc-1"]["title"] == "Nested Doc"

    assert result["doc-2"]["complex"]["a"]["b"]["c"] == 42
    assert result["doc-2"]["complex"]["list"][0]["x"] == 1
    assert result["doc-2"]["complex"]["list"][1]["y"] == 2
    assert result["doc-2"]["title"] == "Complex Doc"


def test_metadata_pattern_various_case_variations():
    """Test different case variations of metadata label."""
    text = """
Metadata: {'document_id': 'doc-1', 'title': 'Standard'}
METADATA: {'document_id': 'doc-2', 'title': 'Uppercase'}
metadata: {'document_id': 'doc-3', 'title': 'Lowercase'}  
MetaData: {'document_id': 'doc-4', 'title': 'Mixed Case'}
"""
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 4
    assert result["doc-1"]["title"] == "Standard"
    assert result["doc-2"]["title"] == "Uppercase"
    assert result["doc-3"]["title"] == "Lowercase"
    assert result["doc-4"]["title"] == "Mixed Case"


def test_balanced_braces_with_nested_dicts_and_strings():
    """Test balanced brace parsing with complex nested structures."""
    text = """
Metadata: {'document_id': 'doc-1', 'data': {'nested': 'value with {braces} in string'}, 'array': [{'inner': 'val'}]}
"""
    result = parse_knowledge_search_metadata(text)

    assert len(result) == 1
    assert result["doc-1"]["data"]["nested"] == "value with {braces} in string"
    assert result["doc-1"]["array"][0]["inner"] == "val"


def test_unmatched_braces_handling():
    """Test handling of unmatched braces in strict and non-strict modes."""
    text = """
Metadata: {'document_id': 'doc-1', 'incomplete': 'missing brace'
Valid after: some text
Metadata: {'document_id': 'doc-2', 'title': 'Valid Doc'}
"""
    # Strict mode should raise error
    with pytest.raises(ValueError) as exc_info:
        parse_knowledge_search_metadata(text, strict=True)

    assert "Failed to parse metadata" in str(exc_info.value)

    # Non-strict mode should skip the invalid entry and parse the valid one
    result = parse_knowledge_search_metadata(text, strict=False)
    assert len(result) == 1
    assert "doc-2" in result
    assert result["doc-2"]["title"] == "Valid Doc"


def test_no_opening_brace_after_metadata_label():
    """Test handling when no opening brace follows metadata label."""
    text = """
Metadata: not a dict
Some other content
Metadata: {'document_id': 'doc-1', 'title': 'Valid'}
"""
    result = parse_knowledge_search_metadata(text)

    # Should only find the valid metadata entry
    assert len(result) == 1
    assert "doc-1" in result
    assert result["doc-1"]["title"] == "Valid"


@pytest.mark.parametrize(
    "text, strict, expected_ids, description",
    [
        # Valid cases
        (
            "Metadata: {'document_id': 'a', 'title': 'Doc A'}",
            True,
            {"a"},
            "single valid metadata",
        ),
        (
            "Metadata: {'document_id': 'a', 'title': 'Doc A'}\n"
            "Metadata: {'document_id': 'b', 'title': 'Doc B'}",
            True,
            {"a", "b"},
            "multiple valid metadata",
        ),
        (
            "METADATA: {'document_id': 'upper', 'title': 'Upper'}\n"
            "metadata: {'document_id': 'lower', 'title': 'Lower'}",
            True,
            {"upper", "lower"},
            "case-insensitive labels",
        ),
        # Error handling - strict mode
        (
            "Metadata: {'document_id': 'a', 'title': 'Doc A'}\n"
            "Metadata: {'document_id': 'b' 'oops': 1}",
            False,
            {"a"},
            "malformed metadata skipped in non-strict mode",
        ),
        (
            "Metadata: not_a_dict\nMetadata: {'document_id': 'valid', 'title': 'Valid'}",
            True,
            {"valid"},
            "non-dict content ignored",
        ),
        # No metadata cases
        (
            "Some text without metadata",
            True,
            set(),
            "no metadata found",
        ),
        (
            "Metadata: {'title': 'No ID'}",
            True,
            set(),
            "metadata without document_id ignored",
        ),
    ],
)
def test_parse_metadata_parametrized(text, strict, expected_ids, description):
    """Parametrized test for various metadata parsing scenarios."""
    if strict and "malformed" in description:
        # Should raise in strict mode for malformed content
        with pytest.raises(ValueError):
            parse_knowledge_search_metadata(text, strict=strict)
    else:
        result = parse_knowledge_search_metadata(text, strict=strict)
        assert set(result.keys()) == expected_ids, f"Failed for: {description}"


@pytest.mark.parametrize(
    "metadata_label, expected_matches",
    [
        ("Metadata:", 1),
        ("METADATA:", 1),
        ("metadata:", 1),
        ("MetaData:", 1),
        ("MetaDaTa:", 1),
        ("  Metadata:  ", 1),  # with whitespace
        ("NotMetadata:", 0),  # should not match
        ("metadata", 0),  # missing colon
    ],
)
def test_label_pattern_matching(metadata_label, expected_matches):
    """Test that the label pattern matches various case variations correctly."""
    sample = f"Some text\n{metadata_label} {{'document_id': 'test'}}\nMore text"
    matches = list(METADATA_LABEL_PATTERN.finditer(sample))
    assert len(matches) == expected_matches
