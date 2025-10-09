# pylint: disable=redefined-outer-name

"""Unit tests for the /conversations REST API endpoints."""

from pydantic import AnyUrl

from app.endpoints.conversations_v2 import transform_chat_message

from models.cache_entry import AdditionalKwargs, CacheEntry
from models.responses import ReferencedDocument


def test_transform_message() -> None:
    """Test the transform_chat_message transformation function."""
    entry = CacheEntry(
        query="query",
        response="response",
        provider="provider",
        model="model",
        started_at="2024-01-01T00:00:00Z",
        completed_at="2024-01-01T00:00:05Z",
    )
    transformed = transform_chat_message(entry)
    assert transformed is not None

    assert "provider" in transformed
    assert transformed["provider"] == "provider"

    assert "model" in transformed
    assert transformed["model"] == "model"

    assert "started_at" in transformed
    assert transformed["started_at"] == "2024-01-01T00:00:00Z"

    assert "completed_at" in transformed
    assert transformed["completed_at"] == "2024-01-01T00:00:05Z"

    assert "messages" in transformed
    assert len(transformed["messages"]) == 2

    message1 = transformed["messages"][0]
    assert message1["type"] == "user"
    assert message1["content"] == "query"

    message2 = transformed["messages"][1]
    assert message2["type"] == "assistant"
    assert message2["content"] == "response"


def test_transform_message_with_additional_kwargs() -> None:
    """Test the transform_chat_message function when additional_kwargs are present."""
    # CacheEntry with referenced documents
    docs = [ReferencedDocument(doc_title="Test Doc", doc_url=AnyUrl("http://example.com"))]
    kwargs_obj = AdditionalKwargs(referenced_documents=docs)
    
    entry = CacheEntry(
        query="query",
        response="response",
        provider="provider",
        model="model",
        started_at="2024-01-01T00:00:00Z",
        completed_at="2024-01-01T00:00:05Z",
        additional_kwargs=kwargs_obj
    )

    transformed = transform_chat_message(entry)
    assert transformed is not None

    assistant_message = transformed["messages"][1]
    
    # Check that the assistant message contains the additional_kwargs field
    assert "additional_kwargs" in assistant_message
    
    # Check the content of the referenced documents
    kwargs = assistant_message["additional_kwargs"]
    assert "referenced_documents" in kwargs
    assert len(kwargs["referenced_documents"]) == 1
    assert kwargs["referenced_documents"][0]["doc_title"] == "Test Doc"
    assert str(kwargs["referenced_documents"][0]["doc_url"]) == "http://example.com/"