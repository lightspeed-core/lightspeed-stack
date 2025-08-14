"""Unit tests for utils.metadata module."""

import pytest

from utils.metadata import parse_knowledge_search_metadata, METADATA_PATTERN


def test_metadata_pattern_exists():
    """Test that METADATA_PATTERN is properly defined."""
    assert METADATA_PATTERN is not None
    assert hasattr(METADATA_PATTERN, "findall")


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


def test_parse_knowledge_search_metadata_malformed_json():
    """Test parsing malformed JSON raises ValueError."""
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
