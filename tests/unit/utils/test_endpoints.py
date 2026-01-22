"""Unit tests for endpoints utility functions."""

# pylint: disable=too-many-lines

import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import AnyUrl
from pytest_mock import MockerFixture

import constants
from configuration import AppConfig
from models.config import Action, CustomProfile
from models.requests import QueryRequest
from models.responses import ReferencedDocument
from tests.unit import config_dict
from utils import endpoints

CONFIGURED_SYSTEM_PROMPT = "This is a configured system prompt"


@pytest.fixture(name="input_file")
def input_file_fixture(tmp_path: Path) -> str:
    """Create file manually using the tmp_path fixture."""
    filename = os.path.join(tmp_path, "prompt.txt")
    with open(filename, "wt", encoding="utf-8") as fout:
        fout.write("this is prompt!")
    return filename


@pytest.fixture(name="config_without_system_prompt")
def config_without_system_prompt_fixture() -> AppConfig:
    """Configuration w/o custom system prompt set."""
    test_config = config_dict.copy()

    # no customization provided
    test_config["customization"] = None

    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(name="config_with_custom_system_prompt")
def config_with_custom_system_prompt_fixture() -> AppConfig:
    """Configuration with custom system prompt set."""
    test_config = config_dict.copy()

    # system prompt is customized
    test_config["customization"] = {
        "system_prompt": CONFIGURED_SYSTEM_PROMPT,
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(name="config_with_custom_system_prompt_and_disable_query_system_prompt")
def config_with_custom_system_prompt_and_disable_query_system_prompt_fixture() -> (
    AppConfig
):
    """Configuration with custom system prompt and disabled query system prompt set."""
    test_config = config_dict.copy()

    # system prompt is customized and query system prompt is disabled
    test_config["customization"] = {
        "system_prompt": CONFIGURED_SYSTEM_PROMPT,
        "disable_query_system_prompt": True,
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(
    name="config_with_custom_profile_prompt_and_enabled_query_system_prompt"
)
def config_with_custom_profile_prompt_and_enabled_query_system_prompt_fixture() -> (
    AppConfig
):
    """Configuration with custom profile loaded for prompt and disabled query system prompt set."""
    test_config = config_dict.copy()

    test_config["customization"] = {
        "profile_path": "tests/profiles/test/profile.py",
        "system_prompt": CONFIGURED_SYSTEM_PROMPT,
        "disable_query_system_prompt": False,
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(
    name="config_with_custom_profile_prompt_and_disable_query_system_prompt"
)
def config_with_custom_profile_prompt_and_disable_query_system_prompt_fixture() -> (
    AppConfig
):
    """Configuration with custom profile loaded for prompt and disabled query system prompt set."""
    test_config = config_dict.copy()

    test_config["customization"] = {
        "profile_path": "tests/profiles/test/profile.py",
        "system_prompt": CONFIGURED_SYSTEM_PROMPT,
        "disable_query_system_prompt": True,
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(name="query_request_without_system_prompt")
def query_request_without_system_prompt_fixture() -> QueryRequest:
    """Fixture for query request without system prompt."""
    return QueryRequest(
        query="query", system_prompt=None
    )  # pyright: ignore[reportCallIssue]


@pytest.fixture(name="query_request_with_system_prompt")
def query_request_with_system_prompt_fixture() -> QueryRequest:
    """Fixture for query request with system prompt."""
    return QueryRequest(
        query="query", system_prompt="System prompt defined in query"
    )  # pyright: ignore[reportCallIssue]


@pytest.fixture(name="setup_configuration")
def setup_configuration_fixture() -> AppConfig:
    """Set up configuration for tests."""
    test_config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "transcripts_enabled": False,
        },
        "mcp_servers": [],
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config_dict)
    return cfg


def test_get_default_system_prompt(
    config_without_system_prompt: AppConfig,
    query_request_without_system_prompt: QueryRequest,
) -> None:
    """Test that default system prompt is returned when other prompts are not provided."""
    system_prompt = endpoints.get_system_prompt(
        query_request_without_system_prompt, config_without_system_prompt
    )
    assert system_prompt == constants.DEFAULT_SYSTEM_PROMPT


def test_get_customized_system_prompt(
    config_with_custom_system_prompt: AppConfig,
    query_request_without_system_prompt: QueryRequest,
) -> None:
    """Test that customized system prompt is used when system prompt is not provided in query."""
    system_prompt = endpoints.get_system_prompt(
        query_request_without_system_prompt, config_with_custom_system_prompt
    )
    assert system_prompt == CONFIGURED_SYSTEM_PROMPT


def test_get_query_system_prompt(
    config_without_system_prompt: AppConfig,
    query_request_with_system_prompt: QueryRequest,
) -> None:
    """Test that system prompt from query is returned."""
    system_prompt = endpoints.get_system_prompt(
        query_request_with_system_prompt, config_without_system_prompt
    )
    assert system_prompt == query_request_with_system_prompt.system_prompt


def test_get_query_system_prompt_not_customized_one(
    config_with_custom_system_prompt: AppConfig,
    query_request_with_system_prompt: QueryRequest,
) -> None:
    """Test that system prompt from query is returned even when customized one is specified."""
    system_prompt = endpoints.get_system_prompt(
        query_request_with_system_prompt, config_with_custom_system_prompt
    )
    assert system_prompt == query_request_with_system_prompt.system_prompt


def test_get_system_prompt_with_disable_query_system_prompt(
    config_with_custom_system_prompt_and_disable_query_system_prompt: AppConfig,
    query_request_with_system_prompt: QueryRequest,
) -> None:
    """Test that query system prompt is disallowed when disable_query_system_prompt is True."""
    with pytest.raises(HTTPException) as exc_info:
        endpoints.get_system_prompt(
            query_request_with_system_prompt,
            config_with_custom_system_prompt_and_disable_query_system_prompt,
        )
    assert exc_info.value.status_code == 422


def test_get_system_prompt_with_disable_query_system_prompt_and_non_system_prompt_query(
    config_with_custom_system_prompt_and_disable_query_system_prompt: AppConfig,
    query_request_without_system_prompt: QueryRequest,
) -> None:
    """Test that query without system prompt is allowed when disable_query_system_prompt is True."""
    system_prompt = endpoints.get_system_prompt(
        query_request_without_system_prompt,
        config_with_custom_system_prompt_and_disable_query_system_prompt,
    )
    assert system_prompt == CONFIGURED_SYSTEM_PROMPT


def test_get_profile_prompt_with_disable_query_system_prompt(
    config_with_custom_profile_prompt_and_disable_query_system_prompt: AppConfig,
    query_request_without_system_prompt: QueryRequest,
) -> None:
    """Test that system prompt is set if profile enabled and query system prompt disabled."""
    custom_profile = CustomProfile(path="tests/profiles/test/profile.py")
    prompts = custom_profile.get_prompts()
    system_prompt = endpoints.get_system_prompt(
        query_request_without_system_prompt,
        config_with_custom_profile_prompt_and_disable_query_system_prompt,
    )
    assert system_prompt == prompts.get("default")


def test_get_profile_prompt_with_enabled_query_system_prompt(
    config_with_custom_profile_prompt_and_enabled_query_system_prompt: AppConfig,
    query_request_with_system_prompt: QueryRequest,
) -> None:
    """Test that profile system prompt is overridden by query system prompt enabled."""
    system_prompt = endpoints.get_system_prompt(
        query_request_with_system_prompt,
        config_with_custom_profile_prompt_and_enabled_query_system_prompt,
    )
    assert system_prompt == query_request_with_system_prompt.system_prompt


def test_validate_model_provider_override_allowed_with_action() -> None:
    """Ensure no exception when caller has MODEL_OVERRIDE and request includes model/provider."""
    query_request = QueryRequest(
        query="q", model="m", provider="p"
    )  # pyright: ignore[reportCallIssue]
    authorized_actions = {Action.MODEL_OVERRIDE}
    endpoints.validate_model_provider_override(query_request, authorized_actions)


def test_validate_model_provider_override_rejected_without_action() -> None:
    """Ensure HTTP 403 when request includes model/provider and caller lacks permission."""
    query_request = QueryRequest(
        query="q", model="m", provider="p"
    )  # pyright: ignore[reportCallIssue]
    authorized_actions: set[Action] = set()
    with pytest.raises(HTTPException) as exc_info:
        endpoints.validate_model_provider_override(query_request, authorized_actions)
    assert exc_info.value.status_code == 403


def test_validate_model_provider_override_no_override_without_action() -> None:
    """No exception when request does not include model/provider regardless of permission."""
    query_request = QueryRequest(query="q")  # pyright:ignore[reportCallIssue]
    endpoints.validate_model_provider_override(query_request, set())


def test_get_topic_summary_system_prompt_default(
    setup_configuration: AppConfig,
) -> None:
    """Test that default topic summary system prompt is returned when no custom
    profile is configured.
    """
    topic_summary_prompt = endpoints.get_topic_summary_system_prompt(
        setup_configuration
    )
    assert topic_summary_prompt == constants.DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT


def test_get_topic_summary_system_prompt_with_custom_profile() -> None:
    """Test that custom profile topic summary prompt is returned when available."""
    test_config = config_dict.copy()
    test_config["customization"] = {
        "profile_path": "tests/profiles/test/profile.py",
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    # Mock the custom profile to return a topic_summary prompt
    custom_profile = CustomProfile(path="tests/profiles/test/profile.py")
    prompts = custom_profile.get_prompts()

    topic_summary_prompt = endpoints.get_topic_summary_system_prompt(cfg)
    assert topic_summary_prompt == prompts.get("topic_summary")


def test_get_topic_summary_system_prompt_with_custom_profile_no_topic_summary(
    mocker: MockerFixture,
) -> None:
    """Test that default topic summary prompt is returned when custom profile has
    no topic_summary prompt.
    """
    test_config = config_dict.copy()
    test_config["customization"] = {
        "profile_path": "tests/profiles/test/profile.py",
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    # Mock the custom profile to return None for topic_summary prompt
    mock_profile = mocker.Mock()
    mock_profile.get_prompts.return_value = {
        "default": "some prompt"
    }  # No topic_summary key

    # Patch the custom_profile property to return our mock
    mocker.patch.object(cfg.customization, "custom_profile", mock_profile)

    topic_summary_prompt = endpoints.get_topic_summary_system_prompt(cfg)
    assert topic_summary_prompt == constants.DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT


def test_get_topic_summary_system_prompt_no_customization() -> None:
    """Test that default topic summary prompt is returned when customization is None."""
    test_config = config_dict.copy()
    test_config["customization"] = None
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    topic_summary_prompt = endpoints.get_topic_summary_system_prompt(cfg)
    assert topic_summary_prompt == constants.DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT


# Tests for unified create_referenced_documents function
class TestCreateReferencedDocuments:
    """Test cases for the unified create_referenced_documents function."""

    def test_create_referenced_documents_empty_chunks(self) -> None:
        """Test that empty chunks list returns empty result."""
        result = endpoints.create_referenced_documents([])
        assert not result

    def test_create_referenced_documents_http_urls_referenced_document_format(
        self,
    ) -> None:
        """Test HTTP URLs with ReferencedDocument format."""

        mock_chunk1 = type("MockChunk", (), {"source": "https://example.com/doc1"})()
        mock_chunk2 = type("MockChunk", (), {"source": "https://example.com/doc2"})()

        result = endpoints.create_referenced_documents([mock_chunk1, mock_chunk2])

        # two referenced documents are expected
        assert len(result) == 2
        # results must exist
        assert result[0] is not None
        assert result[1] is not None
        # results must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert isinstance(result[1], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "doc1"
        assert result[1].doc_url == AnyUrl("https://example.com/doc2")
        assert result[1].doc_title == "doc2"
        # Verify new fields are present (HTTP sources use URL as document_id)
        assert result[0].document_id == "https://example.com/doc1"
        assert result[0].product_name is None
        assert result[0].product_version is None
        assert result[0].source_path is None
        assert result[0].score is None
        assert result[0].chunk_metadata is None

    def test_create_referenced_documents_document_ids_with_metadata(self) -> None:
        """Test document IDs with metadata enrichment including product fields."""

        mock_chunk1 = type("MockChunk", (), {"source": "doc_id_1", "score": 0.95})()
        mock_chunk2 = type("MockChunk", (), {"source": "doc_id_2", "score": 0.87})()

        metadata_map = {
            "doc_id_1": {
                "docs_url": "https://example.com/doc1",
                "title": "Document 1",
                "product_name": "Red Hat OpenShift",
                "product_version": "4.15",
                "source_path": "/docs/openshift/install.md",
            },
            "doc_id_2": {
                "docs_url": "https://example.com/doc2",
                "title": "Document 2",
                "product_name": "Red Hat OpenStack",
                "product_version": "17.1",
            },
        }

        result = endpoints.create_referenced_documents(
            [mock_chunk1, mock_chunk2], metadata_map
        )

        # two referenced documents are expected
        assert len(result) == 2
        # results must exist
        assert result[0] is not None
        assert result[1] is not None
        # results must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert isinstance(result[1], ReferencedDocument)
        # Verify existing fields
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "Document 1"
        assert result[1].doc_url == AnyUrl("https://example.com/doc2")
        assert result[1].doc_title == "Document 2"
        # Verify new metadata fields
        assert result[0].document_id == "doc_id_1"
        assert result[0].product_name == "Red Hat OpenShift"
        assert result[0].product_version == "4.15"
        assert result[0].source_path == "/docs/openshift/install.md"
        assert result[0].score == 0.95
        assert result[1].document_id == "doc_id_2"
        assert result[1].product_name == "Red Hat OpenStack"
        assert result[1].product_version == "17.1"
        assert result[1].source_path is None
        assert result[1].score == 0.87

    def test_create_referenced_documents_skips_tool_names(self) -> None:
        """Test that tool names like 'knowledge_search' are skipped."""

        mock_chunk1 = type("MockChunk", (), {"source": "knowledge_search"})()
        mock_chunk2 = type("MockChunk", (), {"source": "https://example.com/doc1"})()

        result = endpoints.create_referenced_documents([mock_chunk1, mock_chunk2])

        # one referenced document is expected
        assert len(result) == 1
        # result must exist
        assert result[0] is not None
        # result must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "doc1"

    def test_create_referenced_documents_skips_empty_sources(self) -> None:
        """Test that chunks with empty or None sources are skipped."""

        mock_chunk1 = type("MockChunk", (), {"source": None})()
        mock_chunk2 = type("MockChunk", (), {"source": ""})()
        mock_chunk3 = type("MockChunk", (), {"source": "https://example.com/doc1"})()

        result = endpoints.create_referenced_documents(
            [mock_chunk1, mock_chunk2, mock_chunk3]
        )

        # one referenced document is expected
        assert len(result) == 1
        # result must exist
        assert result[0] is not None
        # result must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "doc1"

    def test_create_referenced_documents_deduplication(self) -> None:
        """Test that duplicate sources are deduplicated."""

        mock_chunk1 = type("MockChunk", (), {"source": "https://example.com/doc1"})()
        mock_chunk2 = type(
            "MockChunk", (), {"source": "https://example.com/doc1"}
        )()  # Duplicate
        mock_chunk3 = type("MockChunk", (), {"source": "doc_id_1"})()
        mock_chunk4 = type("MockChunk", (), {"source": "doc_id_1"})()  # Duplicate

        result = endpoints.create_referenced_documents(
            [mock_chunk1, mock_chunk2, mock_chunk3, mock_chunk4]
        )

        # two referenced documents are expected
        assert len(result) == 2
        # results must exist
        assert result[0] is not None
        assert result[1] is not None
        # results must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert isinstance(result[1], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[1].doc_title == "doc_id_1"

    def test_create_referenced_documents_invalid_urls(self) -> None:
        """Test handling of invalid URLs."""

        mock_chunk1 = type("MockChunk", (), {"source": "not-a-valid-url"})()
        mock_chunk2 = type("MockChunk", (), {"source": "https://example.com/doc1"})()

        result = endpoints.create_referenced_documents([mock_chunk1, mock_chunk2])

        # two referenced documents are expected
        assert len(result) == 2
        # results must exist
        assert result[0] is not None
        assert result[1] is not None
        # results must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert isinstance(result[1], ReferencedDocument)
        assert result[0].doc_url is None
        assert result[0].doc_title == "not-a-valid-url"
        assert result[1].doc_url == AnyUrl("https://example.com/doc1")
        assert result[1].doc_title == "doc1"

    def test_create_referenced_documents_with_full_metadata(self) -> None:
        """Test document creation with complete metadata including scores and custom fields."""

        # Mock chunks with scores
        mock_chunk1 = type("MockChunk", (), {"source": "doc_id_1", "score": 0.95})()
        mock_chunk2 = type("MockChunk", (), {"source": "doc_id_2", "score": 0.87})()

        metadata_map = {
            "doc_id_1": {
                "docs_url": "https://example.com/doc1",
                "title": "Product Documentation",
                "document_id": "doc_id_1",
                "product_name": "Red Hat OpenShift",
                "product_version": "4.15",
                "source_path": "/docs/openshift/4.15/install.md",
                "author": "Red Hat",
                "creation_date": "2024-01-01",
            },
            "doc_id_2": {
                "docs_url": "https://example.com/doc2",
                "title": "Configuration Guide",
                "document_id": "doc_id_2",
                "product_name": "Red Hat OpenShift",
                "product_version": "4.14",
                "category": "configuration",
            },
        }

        result = endpoints.create_referenced_documents(
            [mock_chunk1, mock_chunk2], metadata_map
        )

        assert len(result) == 2

        # Verify first document with full metadata
        assert isinstance(result[0], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "Product Documentation"
        assert result[0].document_id == "doc_id_1"
        assert result[0].product_name == "Red Hat OpenShift"
        assert result[0].product_version == "4.15"
        assert result[0].source_path == "/docs/openshift/4.15/install.md"
        assert result[0].score == 0.95
        assert result[0].chunk_metadata is not None
        assert result[0].chunk_metadata["author"] == "Red Hat"
        assert result[0].chunk_metadata["creation_date"] == "2024-01-01"

        # Verify second document
        assert isinstance(result[1], ReferencedDocument)
        assert result[1].doc_url == AnyUrl("https://example.com/doc2")
        assert result[1].doc_title == "Configuration Guide"
        assert result[1].document_id == "doc_id_2"
        assert result[1].product_name == "Red Hat OpenShift"
        assert result[1].product_version == "4.14"
        assert result[1].source_path is None
        assert result[1].score == 0.87
        assert result[1].chunk_metadata is not None
        assert result[1].chunk_metadata["category"] == "configuration"

    def test_create_referenced_documents_backward_compatibility(self) -> None:
        """Test that new fields default to None for backward compatibility."""

        mock_chunk = type("MockChunk", (), {"source": "https://example.com/doc1"})()

        result = endpoints.create_referenced_documents([mock_chunk])

        assert len(result) == 1
        assert isinstance(result[0], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "doc1"
        # HTTP sources use URL as document_id
        assert result[0].document_id == "https://example.com/doc1"
        # Other new fields should be None
        assert result[0].product_name is None
        assert result[0].product_version is None
        assert result[0].source_path is None
        assert result[0].score is None
        assert result[0].chunk_metadata is None

    def test_create_referenced_documents_dict_format_with_metadata(self) -> None:
        """Test dictionary format return with all metadata fields."""

        mock_chunk = type("MockChunk", (), {"source": "doc_id_1", "score": 0.92})()

        metadata_map = {
            "doc_id_1": {
                "docs_url": "https://example.com/doc1",
                "title": "Test Document",
                "product_name": "Test Product",
                "product_version": "1.0",
            }
        }

        result = endpoints.create_referenced_documents(
            [mock_chunk], metadata_map, return_dict_format=True
        )

        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["doc_url"] == "https://example.com/doc1"
        assert result[0]["doc_title"] == "Test Document"
        assert result[0]["document_id"] == "doc_id_1"
        assert result[0]["product_name"] == "Test Product"
        assert result[0]["product_version"] == "1.0"
        assert result[0]["score"] == 0.92
        assert result[0]["source_path"] is None
        assert result[0]["chunk_metadata"] is None


@pytest.mark.asyncio
async def test_cleanup_after_streaming_generate_topic_summary_default_true(
    mocker: MockerFixture,
) -> None:
    """Test that topic summary is generated by default for new conversations."""
    mock_is_transcripts_enabled = mocker.Mock(return_value=False)
    mock_get_topic_summary = mocker.AsyncMock(return_value="Generated topic")
    mock_store_transcript = mocker.Mock()
    mock_persist_conversation = mocker.Mock()
    mock_client = mocker.AsyncMock()
    mock_config = mocker.Mock()

    mock_session = mocker.Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session.__enter__ = mocker.Mock(return_value=mock_session)
    mock_session.__exit__ = mocker.Mock(return_value=None)
    mocker.patch("utils.endpoints.get_session", return_value=mock_session)

    mocker.patch(
        "utils.endpoints.create_referenced_documents_with_metadata", return_value=[]
    )
    mocker.patch("utils.endpoints.store_conversation_into_cache")

    query_request = QueryRequest(query="test query")  # pyright: ignore[reportCallIssue]

    await endpoints.cleanup_after_streaming(
        user_id="test_user",
        conversation_id="test_conv_id",
        model_id="test_model",
        provider_id="test_provider",
        llama_stack_model_id="test_llama_model",
        query_request=query_request,
        summary=mocker.Mock(
            llm_response="test response", tool_calls=[], tool_results=[]
        ),
        metadata_map={},
        started_at="2024-01-01T00:00:00Z",
        client=mock_client,
        config=mock_config,
        skip_userid_check=False,
        get_topic_summary_func=mock_get_topic_summary,
        is_transcripts_enabled_func=mock_is_transcripts_enabled,
        store_transcript_func=mock_store_transcript,
        persist_user_conversation_details_func=mock_persist_conversation,
    )

    mock_get_topic_summary.assert_called_once_with(
        "test query", mock_client, "test_llama_model"
    )

    mock_persist_conversation.assert_called_once()
    assert mock_persist_conversation.call_args[1]["topic_summary"] == "Generated topic"


@pytest.mark.asyncio
async def test_cleanup_after_streaming_generate_topic_summary_explicit_false(
    mocker: MockerFixture,
) -> None:
    """Test that topic summary is NOT generated when explicitly set to False."""
    mock_is_transcripts_enabled = mocker.Mock(return_value=False)
    mock_get_topic_summary = mocker.AsyncMock(return_value="Generated topic")
    mock_store_transcript = mocker.Mock()
    mock_persist_conversation = mocker.Mock()
    mock_client = mocker.AsyncMock()
    mock_config = mocker.Mock()

    mock_session = mocker.Mock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session.__enter__ = mocker.Mock(return_value=mock_session)
    mock_session.__exit__ = mocker.Mock(return_value=None)
    mocker.patch("utils.endpoints.get_session", return_value=mock_session)

    mocker.patch(
        "utils.endpoints.create_referenced_documents_with_metadata", return_value=[]
    )
    mocker.patch("utils.endpoints.store_conversation_into_cache")

    query_request = QueryRequest(
        query="test query", generate_topic_summary=False
    )  # pyright: ignore[reportCallIssue]

    await endpoints.cleanup_after_streaming(
        user_id="test_user",
        conversation_id="test_conv_id",
        model_id="test_model",
        provider_id="test_provider",
        llama_stack_model_id="test_llama_model",
        query_request=query_request,
        summary=mocker.Mock(
            llm_response="test response", tool_calls=[], tool_results=[]
        ),
        metadata_map={},
        started_at="2024-01-01T00:00:00Z",
        client=mock_client,
        config=mock_config,
        skip_userid_check=False,
        get_topic_summary_func=mock_get_topic_summary,
        is_transcripts_enabled_func=mock_is_transcripts_enabled,
        store_transcript_func=mock_store_transcript,
        persist_user_conversation_details_func=mock_persist_conversation,
    )

    mock_get_topic_summary.assert_not_called()

    mock_persist_conversation.assert_called_once()
    assert mock_persist_conversation.call_args[1]["topic_summary"] is None
