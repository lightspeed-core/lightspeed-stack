"""Unit tests for utils/query.py functions."""

# pylint: disable=too-many-lines

import sqlite3
from typing import Any

import psycopg2
import pytest
from fastapi import HTTPException
from llama_stack_client import APIConnectionError, APIStatusError
from llama_stack_client.types import ModelListResponse
from pytest_mock import MockerFixture
from sqlalchemy.exc import SQLAlchemyError

from cache.cache_error import CacheError
from configuration import AppConfig
from models.cache_entry import CacheEntry
from models.config import Action
from models.database.conversations import UserConversation, UserTurn
from models.requests import Attachment, QueryRequest
from models.responses import (
    InternalServerErrorResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
)

from tests.unit import config_dict
from utils.query import (
    consume_query_tokens,
    evaluate_model_hints,
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    is_input_shield,
    is_output_shield,
    is_transcripts_enabled,
    persist_user_conversation_details,
    prepare_input,
    select_model_and_provider_id,
    store_conversation_into_cache,
    store_query_results,
    update_azure_token,
    validate_attachments_metadata,
    validate_model_provider_override,
)
from utils.token_counter import TokenCounter
from utils.types import TurnSummary


@pytest.fixture(name="mock_config")
def mock_config_fixture() -> AppConfig:
    """Create a mock configuration for tests."""
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    return cfg


@pytest.fixture(name="mock_models")
def mock_models_fixture() -> ModelListResponse:
    """Create mock models list."""
    model1 = type(
        "Model",
        (),
        {
            "id": "provider1/model1",
            "custom_metadata": {"model_type": "llm", "provider_id": "provider1"},
        },
    )()
    model2 = type(
        "Model",
        (),
        {
            "id": "provider2/model2",
            "custom_metadata": {"model_type": "llm", "provider_id": "provider2"},
        },
    )()
    return [model1, model2]


class TestStoreConversationIntoCache:
    """Tests for store_conversation_into_cache function."""

    def test_store_with_cache_configured(self, mocker: MockerFixture) -> None:
        """Test storing conversation when cache is configured."""
        mock_config = mocker.Mock(spec=AppConfig)
        mock_cache = mocker.Mock()
        mock_config.conversation_cache = mock_cache
        mock_config.conversation_cache_configuration = mocker.Mock()
        mock_config.conversation_cache_configuration.type = "sqlite"

        cache_entry = CacheEntry(
            query="test query",
            response="test response",
            provider="test_provider",
            model="test_model",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
        )

        store_conversation_into_cache(
            config=mock_config,
            user_id="test_user",
            conversation_id="test_conv",
            cache_entry=cache_entry,
            _skip_userid_check=False,
            topic_summary="Test topic",
        )

        mock_cache.insert_or_append.assert_called_once_with(
            "test_user", "test_conv", cache_entry, False
        )
        mock_cache.set_topic_summary.assert_called_once_with(
            "test_user", "test_conv", "Test topic", False
        )

    def test_store_without_topic_summary(self, mocker: MockerFixture) -> None:
        """Test storing conversation without topic summary."""
        mock_config = mocker.Mock(spec=AppConfig)
        mock_cache = mocker.Mock()
        mock_config.conversation_cache = mock_cache
        mock_config.conversation_cache_configuration = mocker.Mock()
        mock_config.conversation_cache_configuration.type = "sqlite"

        cache_entry = CacheEntry(
            query="test query",
            response="test response",
            provider="test_provider",
            model="test_model",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
        )

        store_conversation_into_cache(
            config=mock_config,
            user_id="test_user",
            conversation_id="test_conv",
            cache_entry=cache_entry,
            _skip_userid_check=False,
            topic_summary=None,
        )

        mock_cache.insert_or_append.assert_called_once()
        mock_cache.set_topic_summary.assert_not_called()

    def test_store_with_cache_not_initialized(self, mocker: MockerFixture) -> None:
        """Test storing when cache is configured but not initialized."""
        mock_config = mocker.Mock(spec=AppConfig)
        mock_config.conversation_cache = None
        mock_config.conversation_cache_configuration = mocker.Mock()
        mock_config.conversation_cache_configuration.type = "sqlite"

        cache_entry = CacheEntry(
            query="test query",
            response="test response",
            provider="test_provider",
            model="test_model",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
        )

        # Should not raise an exception, just log a warning
        store_conversation_into_cache(
            config=mock_config,
            user_id="test_user",
            conversation_id="test_conv",
            cache_entry=cache_entry,
            _skip_userid_check=False,
            topic_summary=None,
        )


class TestSelectModelAndProviderId:
    """Tests for select_model_and_provider_id function."""

    def test_select_from_request(self, mock_models: ModelListResponse) -> None:
        """Test selecting model and provider from request."""
        result = select_model_and_provider_id(
            models=mock_models,
            model_id="model1",
            provider_id="provider1",
        )
        assert result == ("provider1/model1", "model1", "provider1")

    def test_select_first_available_llm(self, mock_models: ModelListResponse) -> None:
        """Test selecting first available LLM when no model specified."""
        result = select_model_and_provider_id(
            models=mock_models,
            model_id=None,
            provider_id=None,
        )
        assert result[0] in ("provider1/model1", "provider2/model2")
        assert result[1] in ("model1", "model2")
        assert result[2] in ("provider1", "provider2")

    def test_select_model_not_found(self, mock_models: ModelListResponse) -> None:
        """Test selecting non-existent model raises HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            select_model_and_provider_id(
                models=mock_models,
                model_id="nonexistent",
                provider_id="provider1",
            )
        assert exc_info.value.status_code == 404

    def test_select_model_no_llm_models_available(self, mocker: MockerFixture) -> None:
        """Test selecting model when no LLM models are available raises HTTPException."""
        # Mock configuration to have no default model/provider
        mocker.patch("utils.query.configuration.inference.default_model", None)
        mocker.patch("utils.query.configuration.inference.default_provider", None)

        # Empty models list
        empty_models: ModelListResponse = []
        with pytest.raises(HTTPException) as exc_info:
            select_model_and_provider_id(
                models=empty_models,
                model_id=None,
                provider_id=None,
            )
        assert exc_info.value.status_code == 404
        # Verify it's a NotFoundResponse for model resource
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail.get("response") == "Model not found"
        assert "Model with ID" in detail.get("cause", "")

    def test_select_model_no_llm_models_with_non_llm_only(
        self, mocker: MockerFixture
    ) -> None:
        """Test selecting model when only non-LLM models are available raises HTTPException."""
        # Mock configuration to have no default model/provider
        mocker.patch("utils.query.configuration.inference.default_model", None)
        mocker.patch("utils.query.configuration.inference.default_provider", None)

        # Models list with only non-LLM models
        non_llm_models = [
            type(
                "Model",
                (),
                {
                    "id": "provider1/model1",
                    "custom_metadata": {
                        "model_type": "embeddings",
                        "provider_id": "provider1",
                    },
                },
            )(),
        ]
        with pytest.raises(HTTPException) as exc_info:
            select_model_and_provider_id(
                models=non_llm_models,
                model_id=None,
                provider_id=None,
            )
        assert exc_info.value.status_code == 404
        # Verify it's a NotFoundResponse for model resource
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail.get("response") == "Model not found"
        assert "Model with ID" in detail.get("cause", "")

    def test_select_model_attribute_error(self, mocker: MockerFixture) -> None:
        """Test selecting model when model lacks custom_metadata raises HTTPException."""
        # Mock configuration to have no default model/provider
        mocker.patch("utils.query.configuration.inference.default_model", None)
        mocker.patch("utils.query.configuration.inference.default_provider", None)

        # Models list with model that has no custom_metadata attribute
        models_without_metadata = [
            type("Model", (), {"id": "provider1/model1"})(),
        ]
        with pytest.raises(HTTPException) as exc_info:
            select_model_and_provider_id(
                models=models_without_metadata,
                model_id=None,
                provider_id=None,
            )
        assert exc_info.value.status_code == 404
        # Verify it's a NotFoundResponse for model resource
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail.get("response") == "Model not found"
        assert "Model with ID" in detail.get("cause", "")


class TestValidateModelProviderOverride:
    """Tests for validate_model_provider_override function."""

    def test_allowed_with_action(self) -> None:
        """Test that override is allowed when user has MODEL_OVERRIDE action."""
        query_request = QueryRequest(
            query="test", model="model1", provider="provider1"
        )  # pyright: ignore[reportCallIssue]
        validate_model_provider_override(query_request, {Action.MODEL_OVERRIDE})

    def test_rejected_without_action(self) -> None:
        """Test that override is rejected when user lacks MODEL_OVERRIDE action."""
        query_request = QueryRequest(
            query="test", model="model1", provider="provider1"
        )  # pyright: ignore[reportCallIssue]
        with pytest.raises(HTTPException) as exc_info:
            validate_model_provider_override(query_request, set())
        assert exc_info.value.status_code == 403

    def test_no_override_allowed(self) -> None:
        """Test that request without override is allowed regardless of permissions."""
        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]
        validate_model_provider_override(query_request, set())


class TestShieldFunctions:
    """Tests for shield-related functions."""

    def test_is_output_shield_output_prefix(self) -> None:
        """Test is_output_shield returns True for output_ prefix."""
        shield = type("Shield", (), {"identifier": "output_test"})()
        assert is_output_shield(shield) is True

    def test_is_output_shield_inout_prefix(self) -> None:
        """Test is_output_shield returns True for inout_ prefix."""
        shield = type("Shield", (), {"identifier": "inout_test"})()
        assert is_output_shield(shield) is True

    def test_is_output_shield_other(self) -> None:
        """Test is_output_shield returns False for other prefixes."""
        shield = type("Shield", (), {"identifier": "input_test"})()
        assert is_output_shield(shield) is False

    def test_is_input_shield_input_prefix(self) -> None:
        """Test is_input_shield returns True for input prefix."""
        shield = type("Shield", (), {"identifier": "input_test"})()
        assert is_input_shield(shield) is True

    def test_is_input_shield_inout_prefix(self) -> None:
        """Test is_input_shield returns True for inout_ prefix."""
        shield = type("Shield", (), {"identifier": "inout_test"})()
        assert is_input_shield(shield) is True

    def test_is_input_shield_output_prefix(self) -> None:
        """Test is_input_shield returns False for output_ prefix."""
        shield = type("Shield", (), {"identifier": "output_test"})()
        assert is_input_shield(shield) is False


class TestEvaluateModelHints:
    """Tests for evaluate_model_hints function."""

    def test_with_user_conversation_no_request_hints(self) -> None:
        """Test using hints from user conversation when request has none."""
        user_conv = UserConversation(
            id="conv1",
            user_id="user1",
            last_used_model="model1",
            last_used_provider="provider1",
        )
        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        model_id, provider_id = evaluate_model_hints(user_conv, query_request)
        assert model_id == "model1"
        assert provider_id == "provider1"

    def test_with_user_conversation_and_request_hints(self) -> None:
        """Test request hints take precedence over conversation hints."""
        user_conv = UserConversation(
            id="conv1",
            user_id="user1",
            last_used_model="model1",
            last_used_provider="provider1",
        )
        query_request = QueryRequest(
            query="test", model="model2", provider="provider2"
        )  # pyright: ignore[reportCallIssue]

        model_id, provider_id = evaluate_model_hints(user_conv, query_request)
        assert model_id == "model2"
        assert provider_id == "provider2"

    def test_without_user_conversation(self) -> None:
        """Test without user conversation returns request hints or None."""
        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        model_id, provider_id = evaluate_model_hints(None, query_request)
        assert model_id is None
        assert provider_id is None


class TestPrepareInput:
    """Tests for prepare_input function."""

    def test_prepare_input_without_attachments(self) -> None:
        """Test preparing input without attachments."""
        query_request = QueryRequest(
            query="test query"
        )  # pyright: ignore[reportCallIssue]
        result = prepare_input(query_request)
        assert result == "test query"

    def test_prepare_input_with_attachments(self) -> None:
        """Test preparing input with attachments."""
        attachment = Attachment(
            attachment_type="text",
            content="attachment content",
            content_type="text/plain",
        )
        query_request = QueryRequest(
            query="test query", attachments=[attachment]
        )  # pyright: ignore[reportCallIssue]
        result = prepare_input(query_request)
        assert "test query" in result
        assert "[Attachment: text]" in result
        assert "attachment content" in result


class TestExtractProviderAndModelFromModelId:
    """Tests for extract_provider_and_model_from_model_id function."""

    def test_extract_with_provider(self) -> None:
        """Test extracting provider and model from full model ID."""
        provider, model = extract_provider_and_model_from_model_id("provider1/model1")
        assert provider == "provider1"
        assert model == "model1"

    def test_extract_without_provider(self) -> None:
        """Test extracting when model ID has no provider."""
        provider, model = extract_provider_and_model_from_model_id("model1")
        assert provider == ""
        assert model == "model1"


class TestHandleKnownApistatusErrors:
    """Tests for handle_known_apistatus_errors function."""

    def test_context_length_exceeded(self) -> None:
        """Test handling context length exceeded error."""
        error = type(
            "APIStatusError",
            (),
            {"status_code": 400, "message": "context_length_exceeded: prompt too long"},
        )()
        result = handle_known_apistatus_errors(error, "model1")
        assert isinstance(result, PromptTooLongResponse)
        detail = result.model_dump()["detail"]
        assert detail["response"] == "Prompt is too long"
        assert "model1" in detail["cause"]
        assert "context window size" in detail["cause"]

    def test_quota_exceeded(self) -> None:
        """Test handling quota exceeded error."""
        error = type(
            "APIStatusError", (), {"status_code": 429, "message": "Rate limit exceeded"}
        )()
        result = handle_known_apistatus_errors(error, "model1")
        assert isinstance(result, QuotaExceededResponse)
        detail = result.model_dump()["detail"]
        assert "quota" in detail["response"].lower()

    def test_generic_error(self) -> None:
        """Test handling generic error."""
        error = type(
            "APIStatusError",
            (),
            {"status_code": 500, "message": "Internal server error"},
        )()
        result = handle_known_apistatus_errors(error, "model1")
        assert isinstance(result, InternalServerErrorResponse)
        detail = result.model_dump()["detail"]
        assert detail["response"] == "Internal server error"


class TestValidateAttachmentsMetadata:
    """Tests for validate_attachments_metadata function."""

    def test_valid_attachment(self) -> None:
        """Test validation passes for valid attachment."""
        attachment = Attachment(
            attachment_type="log",
            content="content",
            content_type="text/plain",
        )
        validate_attachments_metadata([attachment])

    def test_invalid_attachment_type(self) -> None:
        """Test validation fails for invalid attachment type."""
        attachment = Attachment(
            attachment_type="invalid",
            content="content",
            content_type="text/plain",
        )
        with pytest.raises(HTTPException) as exc_info:
            validate_attachments_metadata([attachment])
        assert exc_info.value.status_code == 422

    def test_invalid_content_type(self) -> None:
        """Test validation fails for invalid content type."""
        # Use valid attachment_type to ensure we hit the content_type check
        attachment = Attachment(
            attachment_type="log",
            content="content",
            content_type="invalid/type",
        )
        with pytest.raises(HTTPException) as exc_info:
            validate_attachments_metadata([attachment])
        assert exc_info.value.status_code == 422
        assert "Invalid attachment content type" in str(exc_info.value.detail)


class TestIsTranscriptsEnabled:
    """Tests for is_transcripts_enabled function."""

    def test_transcripts_enabled(self, mocker: MockerFixture) -> None:
        """Test when transcripts are enabled."""
        mocker.patch(
            "utils.query.configuration.user_data_collection_configuration.transcripts_enabled",
            True,
        )
        assert is_transcripts_enabled() is True

    def test_transcripts_disabled(self, mocker: MockerFixture) -> None:
        """Test when transcripts are disabled."""
        mocker.patch(
            "utils.query.configuration.user_data_collection_configuration.transcripts_enabled",
            False,
        )
        assert is_transcripts_enabled() is False


class TestPersistUserConversationDetails:
    """Tests for persist_user_conversation_details function."""

    def test_create_new_conversation(self, mocker: MockerFixture) -> None:
        """Test creating a new conversation."""
        mock_session = mocker.Mock()

        # Mock the UserConversation query
        mock_conv_query = mocker.Mock()
        mock_conv_query.filter_by.return_value.first.return_value = None

        # Mock the max turn number query
        mock_filtered_query = mocker.Mock()
        mock_filtered_query.scalar.return_value = None
        mock_max_query = mocker.Mock()
        mock_max_query.filter_by.return_value = mock_filtered_query

        def query_side_effect(*args: Any) -> Any:
            """Route queries based on the argument type."""
            if args and args[0] is UserConversation:
                return mock_conv_query
            return mock_max_query

        mock_session.query.side_effect = query_side_effect
        mock_session.__enter__ = mocker.Mock(return_value=mock_session)
        mock_session.__exit__ = mocker.Mock(return_value=None)
        mocker.patch("utils.query.get_session", return_value=mock_session)

        persist_user_conversation_details(
            user_id="user1",
            conversation_id="conv1",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
            model_id="model1",
            provider_id="provider1",
            topic_summary="Topic",
        )

        mock_session.add.assert_called()
        mock_session.commit.assert_called_once()

    def test_update_existing_conversation(self, mocker: MockerFixture) -> None:
        """Test updating an existing conversation."""
        existing_conv = UserConversation(
            id="conv1",
            user_id="user1",
            last_used_model="old_model",
            last_used_provider="old_provider",
            message_count=5,
        )
        mock_session = mocker.Mock()

        # Mock the UserConversation query
        mock_conv_query = mocker.Mock()
        mock_conv_query.filter_by.return_value.first.return_value = existing_conv

        # Mock the max turn number query
        # The query chain is: session.query(func.max(...)).filter_by(...).scalar()
        mock_filtered_query = mocker.Mock()
        mock_filtered_query.scalar.return_value = None
        mock_max_query = mocker.Mock()
        mock_max_query.filter_by.return_value = mock_filtered_query

        def query_side_effect(*args: Any) -> Any:
            """Route queries based on the argument type."""
            if args and args[0] is UserConversation:
                return mock_conv_query
            # func.max(UserTurn.turn_number) doesn't match UserTurn type, falls through
            return mock_max_query

        mock_session.query.side_effect = query_side_effect
        mock_session.__enter__ = mocker.Mock(return_value=mock_session)
        mock_session.__exit__ = mocker.Mock(return_value=None)
        mocker.patch("utils.query.get_session", return_value=mock_session)

        persist_user_conversation_details(
            user_id="user1",
            conversation_id="conv1",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
            model_id="new_model",
            provider_id="new_provider",
            topic_summary=None,
        )

        assert existing_conv.last_used_model == "new_model"
        assert existing_conv.last_used_provider == "new_provider"
        assert existing_conv.message_count == 6
        mock_session.commit.assert_called_once()

    def test_create_new_conversation_with_existing_turns(
        self, mocker: MockerFixture
    ) -> None:
        """Test creating a new conversation when there are existing turns."""
        mock_session = mocker.Mock()

        # Mock the UserConversation query
        mock_conv_query = mocker.Mock()
        mock_conv_query.filter_by.return_value.first.return_value = None

        # Mock the max turn number query - return existing turn number
        mock_filtered_query = mocker.Mock()
        mock_filtered_query.scalar.return_value = 5  # Existing max turn number
        mock_max_query = mocker.Mock()
        mock_max_query.filter_by.return_value = mock_filtered_query

        def query_side_effect(*args: Any) -> Any:
            """Route queries based on the argument type."""
            if args and args[0] is UserConversation:
                return mock_conv_query
            # func.max(UserTurn.turn_number) doesn't match UserTurn type, falls through
            return mock_max_query

        mock_session.query.side_effect = query_side_effect
        mock_session.__enter__ = mocker.Mock(return_value=mock_session)
        mock_session.__exit__ = mocker.Mock(return_value=None)
        mocker.patch("utils.query.get_session", return_value=mock_session)

        persist_user_conversation_details(
            user_id="user1",
            conversation_id="conv1",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
            model_id="model1",
            provider_id="provider1",
            topic_summary="Topic",
        )

        # Verify that the turn number is incremented correctly
        add_calls = mock_session.add.call_args_list
        assert len(add_calls) == 2  # Conversation and UserTurn

        # Find the UserTurn object in the add calls
        turn_added = None
        for call in add_calls:
            obj = call[0][0]
            if isinstance(obj, UserTurn):
                turn_added = obj
                break

        assert turn_added is not None, "UserTurn should have been added"
        assert (
            turn_added.turn_number == 6
        ), "Turn number should be incremented from 5 to 6"
        mock_session.commit.assert_called_once()


class TestConsumeQueryTokens:
    """Tests for consume_query_tokens function."""

    def test_consume_tokens_success(
        self, mock_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test successful token consumption."""
        mock_consume = mocker.patch("utils.query.consume_tokens")

        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        consume_query_tokens(
            user_id="user1",
            model_id="provider1/model1",
            token_usage=token_usage,
            configuration=mock_config,
        )

        # Verify consume_tokens was called
        mock_consume.assert_called_once()

    def test_consume_tokens_database_error(
        self, mock_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test token consumption raises HTTPException on database error."""
        mocker.patch(
            "utils.query.consume_tokens", side_effect=sqlite3.Error("DB error")
        )

        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        with pytest.raises(HTTPException) as exc_info:
            consume_query_tokens(
                user_id="user1",
                model_id="provider1/model1",
                token_usage=token_usage,
                configuration=mock_config,
            )
        assert exc_info.value.status_code == 500


class TestUpdateAzureToken:
    """Tests for update_azure_token function."""

    @pytest.mark.asyncio
    async def test_update_with_library_client(self, mocker: MockerFixture) -> None:
        """Test updating token with library client."""
        mock_client_holder = mocker.Mock()
        mock_client_holder.is_library_client = True
        mock_client_holder.reload_library_client = mocker.AsyncMock(
            return_value="client"
        )
        mocker.patch(
            "utils.query.AsyncLlamaStackClientHolder", return_value=mock_client_holder
        )

        mock_client = mocker.Mock()
        result = await update_azure_token(mock_client)
        assert result == "client"
        mock_client_holder.reload_library_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_with_remote_client(self, mocker: MockerFixture) -> None:
        """Test updating token with remote client."""
        mock_client_holder = mocker.Mock()
        mock_client_holder.is_library_client = False
        mock_client_holder.update_provider_data = mocker.Mock(
            return_value="updated_client"
        )
        mocker.patch(
            "utils.query.AsyncLlamaStackClientHolder", return_value=mock_client_holder
        )

        mock_provider = type(
            "Provider",
            (),
            {
                "provider_type": "remote::azure",
                "config": {"api_base": "https://api.example.com"},
            },
        )()
        mock_client = mocker.AsyncMock()
        mock_client.providers.list = mocker.AsyncMock(return_value=[mock_provider])

        mocker.patch(
            "utils.query.AzureEntraIDManager",
            return_value=mocker.Mock(
                access_token=mocker.Mock(
                    get_secret_value=mocker.Mock(return_value="token")
                )
            ),
        )

        result = await update_azure_token(mock_client)
        assert result == "updated_client"

    @pytest.mark.asyncio
    async def test_update_with_connection_error(self, mocker: MockerFixture) -> None:
        """Test updating token raises HTTPException on connection error."""
        mock_client_holder = mocker.Mock()
        mock_client_holder.is_library_client = False
        mocker.patch(
            "utils.query.AsyncLlamaStackClientHolder", return_value=mock_client_holder
        )

        mock_client = mocker.AsyncMock()
        mock_client.providers.list = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed", request=mocker.Mock()
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_azure_token(mock_client)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_update_with_api_status_error(self, mocker: MockerFixture) -> None:
        """Test updating token raises HTTPException on API status error."""
        mock_client_holder = mocker.Mock()
        mock_client_holder.is_library_client = False
        mocker.patch(
            "utils.query.AsyncLlamaStackClientHolder", return_value=mock_client_holder
        )

        mock_client = mocker.AsyncMock()
        # Create a mock exception that will be caught by except APIStatusError
        mock_error = APIStatusError(
            message="API error", response=mocker.Mock(request=None), body=None
        )
        mock_client.providers.list = mocker.AsyncMock(side_effect=mock_error)

        with pytest.raises(HTTPException) as exc_info:
            await update_azure_token(mock_client)
        assert exc_info.value.status_code == 500


class TestStoreQueryResults:
    """Tests for store_query_results function."""

    def test_store_query_results_success(
        self, mock_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test successful storage of query results."""
        mocker.patch("utils.query.is_transcripts_enabled", return_value=False)
        mock_persist = mocker.patch("utils.query.persist_user_conversation_details")
        mock_store_cache = mocker.patch("utils.query.store_conversation_into_cache")

        summary = TurnSummary()
        summary.llm_response = "response"
        summary.rag_chunks = []

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        store_query_results(
            user_id="user1",
            conversation_id="conv1",
            model="provider1/model1",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:00:05Z",
            summary=summary,
            query_request=query_request,
            configuration=mock_config,
            skip_userid_check=False,
            topic_summary="Topic",
        )

        # Verify functions were called
        mock_persist.assert_called_once()
        mock_store_cache.assert_called_once()

    def test_store_query_results_transcript_error(
        self, mock_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test storage raises HTTPException on transcript error."""
        mocker.patch("utils.query.is_transcripts_enabled", return_value=True)
        mocker.patch("utils.query.store_transcript", side_effect=IOError("IO error"))

        summary = TurnSummary()
        summary.llm_response = "response"
        summary.rag_chunks = []

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        with pytest.raises(HTTPException) as exc_info:
            store_query_results(
                user_id="user1",
                conversation_id="conv1",
                model="provider1/model1",
                started_at="2024-01-01T00:00:00Z",
                completed_at="2024-01-01T00:00:05Z",
                summary=summary,
                query_request=query_request,
                configuration=mock_config,
                skip_userid_check=False,
                topic_summary=None,
            )
        assert exc_info.value.status_code == 500

    def test_store_query_results_sqlalchemy_error(
        self, mock_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test storage raises HTTPException on SQLAlchemy error."""
        mocker.patch("utils.query.is_transcripts_enabled", return_value=False)
        mocker.patch(
            "utils.query.persist_user_conversation_details",
            side_effect=SQLAlchemyError("Database error", None, None),
        )

        summary = TurnSummary()
        summary.llm_response = "response"
        summary.rag_chunks = []

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        with pytest.raises(HTTPException) as exc_info:
            store_query_results(
                user_id="user1",
                conversation_id="conv1",
                model="provider1/model1",
                started_at="2024-01-01T00:00:00Z",
                completed_at="2024-01-01T00:00:05Z",
                summary=summary,
                query_request=query_request,
                configuration=mock_config,
                skip_userid_check=False,
                topic_summary=None,
            )
        assert exc_info.value.status_code == 500

    def test_store_query_results_cache_error(
        self, mock_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test storage raises HTTPException on cache error."""
        mocker.patch("utils.query.is_transcripts_enabled", return_value=False)
        mocker.patch("utils.query.persist_user_conversation_details")
        mocker.patch(
            "utils.query.store_conversation_into_cache",
            side_effect=CacheError("Cache error"),
        )

        summary = TurnSummary()
        summary.llm_response = "response"
        summary.rag_chunks = []

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        with pytest.raises(HTTPException) as exc_info:
            store_query_results(
                user_id="user1",
                conversation_id="conv1",
                model="provider1/model1",
                started_at="2024-01-01T00:00:00Z",
                completed_at="2024-01-01T00:00:05Z",
                summary=summary,
                query_request=query_request,
                configuration=mock_config,
                skip_userid_check=False,
                topic_summary=None,
            )
        assert exc_info.value.status_code == 500

    def test_store_query_results_value_error(
        self, mock_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test storage raises HTTPException on ValueError."""
        mocker.patch("utils.query.is_transcripts_enabled", return_value=False)
        mocker.patch("utils.query.persist_user_conversation_details")
        mocker.patch(
            "utils.query.store_conversation_into_cache",
            side_effect=ValueError("Invalid value"),
        )

        summary = TurnSummary()
        summary.llm_response = "response"
        summary.rag_chunks = []

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        with pytest.raises(HTTPException) as exc_info:
            store_query_results(
                user_id="user1",
                conversation_id="conv1",
                model="provider1/model1",
                started_at="2024-01-01T00:00:00Z",
                completed_at="2024-01-01T00:00:05Z",
                summary=summary,
                query_request=query_request,
                configuration=mock_config,
                skip_userid_check=False,
                topic_summary=None,
            )
        assert exc_info.value.status_code == 500

    def test_store_query_results_psycopg2_error(
        self, mock_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test storage raises HTTPException on psycopg2 error."""
        mocker.patch("utils.query.is_transcripts_enabled", return_value=False)
        mocker.patch("utils.query.persist_user_conversation_details")
        mocker.patch(
            "utils.query.store_conversation_into_cache",
            side_effect=psycopg2.Error("PostgreSQL error"),
        )

        summary = TurnSummary()
        summary.llm_response = "response"
        summary.rag_chunks = []

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        with pytest.raises(HTTPException) as exc_info:
            store_query_results(
                user_id="user1",
                conversation_id="conv1",
                model="provider1/model1",
                started_at="2024-01-01T00:00:00Z",
                completed_at="2024-01-01T00:00:05Z",
                summary=summary,
                query_request=query_request,
                configuration=mock_config,
                skip_userid_check=False,
                topic_summary=None,
            )
        assert exc_info.value.status_code == 500

    def test_store_query_results_sqlite_error(
        self, mock_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test storage raises HTTPException on sqlite3 error."""
        mocker.patch("utils.query.is_transcripts_enabled", return_value=False)
        mocker.patch("utils.query.persist_user_conversation_details")
        mocker.patch(
            "utils.query.store_conversation_into_cache",
            side_effect=sqlite3.Error("SQLite error"),
        )

        summary = TurnSummary()
        summary.llm_response = "response"
        summary.rag_chunks = []

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        with pytest.raises(HTTPException) as exc_info:
            store_query_results(
                user_id="user1",
                conversation_id="conv1",
                model="provider1/model1",
                started_at="2024-01-01T00:00:00Z",
                completed_at="2024-01-01T00:00:05Z",
                summary=summary,
                query_request=query_request,
                configuration=mock_config,
                skip_userid_check=False,
                topic_summary=None,
            )
        assert exc_info.value.status_code == 500
