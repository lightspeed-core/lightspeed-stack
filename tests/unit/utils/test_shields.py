"""Unit tests for utils/shields.py functions."""

import pytest
from fastapi import HTTPException, status
from llama_stack_api.openai_responses import (
    OpenAIResponseMessage,
    OpenAIResponseOutputMessageFileSearchToolCall,
)
from pytest_mock import MockerFixture

from utils.shields import (
    DEFAULT_VIOLATION_MESSAGE,
    append_refused_turn_to_conversation,
    append_turn_to_conversation,
    detect_shield_violations,
    get_available_shields,
    run_shield_moderation,
)


class TestGetAvailableShields:
    """Tests for get_available_shields function."""

    @pytest.mark.asyncio
    async def test_returns_shield_identifiers(self, mocker: MockerFixture) -> None:
        """Test that get_available_shields returns list of shield identifiers."""
        mock_client = mocker.Mock()
        shield1 = mocker.Mock()
        shield1.identifier = "shield-1"
        shield2 = mocker.Mock()
        shield2.identifier = "shield-2"
        mock_client.shields.list = mocker.AsyncMock(return_value=[shield1, shield2])

        result = await get_available_shields(mock_client)

        assert result == ["shield-1", "shield-2"]
        mock_client.shields.list.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_shields(
        self, mocker: MockerFixture
    ) -> None:
        """Test that get_available_shields returns empty list when no shields available."""
        mock_client = mocker.Mock()
        mock_client.shields.list = mocker.AsyncMock(return_value=[])

        result = await get_available_shields(mock_client)

        assert result == []


class TestDetectShieldViolations:
    """Tests for detect_shield_violations function."""

    def test_detects_violation_when_refusal_present(
        self, mocker: MockerFixture
    ) -> None:
        """Test that detect_shield_violations returns True when refusal is present."""
        mock_metric = mocker.patch(
            "utils.shields.metrics.llm_calls_validation_errors_total"
        )

        output_item = mocker.Mock(type="message", refusal="Content blocked")
        output_items = [output_item]

        result = detect_shield_violations(output_items)

        assert result is True
        mock_metric.inc.assert_called_once()

    def test_returns_false_when_no_violation(self, mocker: MockerFixture) -> None:
        """Test that detect_shield_violations returns False when no refusal."""
        mock_metric = mocker.patch(
            "utils.shields.metrics.llm_calls_validation_errors_total"
        )

        output_item = mocker.Mock(type="message", refusal=None)
        output_items = [output_item]

        result = detect_shield_violations(output_items)

        assert result is False
        mock_metric.inc.assert_not_called()

    def test_returns_false_for_non_message_items(self, mocker: MockerFixture) -> None:
        """Test that detect_shield_violations ignores non-message items."""
        mock_metric = mocker.patch(
            "utils.shields.metrics.llm_calls_validation_errors_total"
        )

        output_item = mocker.Mock(type="tool_call", refusal="Content blocked")
        output_items = [output_item]

        result = detect_shield_violations(output_items)

        assert result is False
        mock_metric.inc.assert_not_called()

    def test_returns_false_for_empty_list(self, mocker: MockerFixture) -> None:
        """Test that detect_shield_violations returns False for empty list."""
        mock_metric = mocker.patch(
            "utils.shields.metrics.llm_calls_validation_errors_total"
        )

        result = detect_shield_violations([])

        assert result is False
        mock_metric.inc.assert_not_called()


class TestRunShieldModeration:
    """Tests for run_shield_moderation function."""

    @pytest.mark.asyncio
    async def test_returns_not_blocked_when_no_shields(
        self, mocker: MockerFixture
    ) -> None:
        """Test that run_shield_moderation returns not blocked when no shields."""
        mock_client = mocker.Mock()
        mock_client.shields.list = mocker.AsyncMock(return_value=[])
        mock_client.models.list = mocker.AsyncMock(return_value=[])

        result = await run_shield_moderation(mock_client, "test input")

        assert result.blocked is False
        assert result.shield_model is None

    @pytest.mark.asyncio
    async def test_returns_not_blocked_when_moderation_passes(
        self, mocker: MockerFixture
    ) -> None:
        """Test that run_shield_moderation returns not blocked when content is safe."""
        mock_client = mocker.Mock()

        # Setup shield
        shield = mocker.Mock()
        shield.identifier = "test-shield"
        shield.provider_resource_id = "moderation-model"
        mock_client.shields.list = mocker.AsyncMock(return_value=[shield])

        # Setup model
        model = mocker.Mock()
        model.id = "moderation-model"
        mock_client.models.list = mocker.AsyncMock(return_value=[model])

        # Setup moderation result (not flagged)
        moderation_result = mocker.Mock()
        moderation_result.results = [mocker.Mock(flagged=False)]
        mock_client.moderations.create = mocker.AsyncMock(
            return_value=moderation_result
        )

        result = await run_shield_moderation(mock_client, "safe input")

        assert result.blocked is False
        assert result.shield_model is None
        mock_client.moderations.create.assert_called_once_with(
            input="safe input", model="moderation-model"
        )

    @pytest.mark.asyncio
    async def test_returns_blocked_when_content_flagged(
        self, mocker: MockerFixture
    ) -> None:
        """Test that run_shield_moderation returns blocked when content is flagged."""
        mock_metric = mocker.patch(
            "utils.shields.metrics.llm_calls_validation_errors_total"
        )
        mock_client = mocker.Mock()

        # Setup shield
        shield = mocker.Mock()
        shield.identifier = "test-shield"
        shield.provider_resource_id = "moderation-model"
        mock_client.shields.list = mocker.AsyncMock(return_value=[shield])

        # Setup model
        model = mocker.Mock()
        model.id = "moderation-model"
        mock_client.models.list = mocker.AsyncMock(return_value=[model])

        # Setup moderation result (flagged)
        flagged_result = mocker.Mock()
        flagged_result.flagged = True
        flagged_result.categories = ["violence"]
        flagged_result.user_message = "Content blocked for violence"
        moderation_result = mocker.Mock()
        moderation_result.results = [flagged_result]
        mock_client.moderations.create = mocker.AsyncMock(
            return_value=moderation_result
        )

        result = await run_shield_moderation(mock_client, "violent content")

        assert result.blocked is True
        assert result.message == "Content blocked for violence"
        assert result.shield_model == "moderation-model"
        mock_metric.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_blocked_with_default_message_when_no_user_message(
        self, mocker: MockerFixture
    ) -> None:
        """Test that run_shield_moderation uses default message when user_message is None."""
        mocker.patch("utils.shields.metrics.llm_calls_validation_errors_total")
        mock_client = mocker.Mock()

        # Setup shield
        shield = mocker.Mock()
        shield.identifier = "test-shield"
        shield.provider_resource_id = "moderation-model"
        mock_client.shields.list = mocker.AsyncMock(return_value=[shield])

        # Setup model
        model = mocker.Mock()
        model.id = "moderation-model"
        mock_client.models.list = mocker.AsyncMock(return_value=[model])

        # Setup moderation result (flagged, no user_message)
        flagged_result = mocker.Mock()
        flagged_result.flagged = True
        flagged_result.categories = ["spam"]
        flagged_result.user_message = None
        moderation_result = mocker.Mock()
        moderation_result.results = [flagged_result]
        mock_client.moderations.create = mocker.AsyncMock(
            return_value=moderation_result
        )

        result = await run_shield_moderation(mock_client, "spam content")

        assert result.blocked is True
        assert result.message == DEFAULT_VIOLATION_MESSAGE
        assert result.shield_model == "moderation-model"

    @pytest.mark.asyncio
    async def test_raises_http_exception_when_shield_model_not_found(
        self, mocker: MockerFixture
    ) -> None:
        """Test that run_shield_moderation raises HTTPException when shield model not in models."""
        mock_client = mocker.Mock()

        # Setup shield with provider_resource_id
        shield = mocker.Mock()
        shield.identifier = "test-shield"
        shield.provider_resource_id = "missing-model"
        mock_client.shields.list = mocker.AsyncMock(return_value=[shield])

        # Setup models (doesn't include the shield's model)
        model = mocker.Mock()
        model.id = "other-model"
        mock_client.models.list = mocker.AsyncMock(return_value=[model])

        with pytest.raises(HTTPException) as exc_info:
            await run_shield_moderation(mock_client, "test input")

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "missing-model" in exc_info.value.detail["cause"]  # type: ignore

    @pytest.mark.asyncio
    async def test_raises_http_exception_when_shield_has_no_provider_resource_id(
        self, mocker: MockerFixture
    ) -> None:
        """Test that run_shield_moderation raises HTTPException when no provider_resource_id."""
        mock_client = mocker.Mock()

        # Setup shield without provider_resource_id
        shield = mocker.Mock()
        shield.identifier = "test-shield"
        shield.provider_resource_id = None
        mock_client.shields.list = mocker.AsyncMock(return_value=[shield])

        mock_client.models.list = mocker.AsyncMock(return_value=[])

        with pytest.raises(HTTPException) as exc_info:
            await run_shield_moderation(mock_client, "test input")

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_returns_blocked_on_bad_request_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test that run_shield_moderation returns blocked when ValueError is raised."""
        mock_metric = mocker.patch(
            "utils.shields.metrics.llm_calls_validation_errors_total"
        )
        mock_client = mocker.Mock()

        # Setup shield
        shield = mocker.Mock()
        shield.identifier = "test-shield"
        shield.provider_resource_id = "moderation-model"
        mock_client.shields.list = mocker.AsyncMock(return_value=[shield])

        # Setup model
        model = mocker.Mock()
        model.id = "moderation-model"
        mock_client.models.list = mocker.AsyncMock(return_value=[model])

        # Setup moderation to raise ValueError (known Llama Stack bug)
        mock_client.moderations.create = mocker.AsyncMock(
            side_effect=ValueError("Bad request")
        )

        result = await run_shield_moderation(mock_client, "test input")

        assert result.blocked is True
        assert result.message == DEFAULT_VIOLATION_MESSAGE
        assert result.shield_model == "moderation-model"
        mock_metric.inc.assert_called_once()


class TestAppendTurnToConversation:  # pylint: disable=too-few-public-methods
    """Tests for append_turn_to_conversation function."""

    @pytest.mark.asyncio
    async def test_appends_user_and_assistant_messages(
        self, mocker: MockerFixture
    ) -> None:
        """Test that append_turn_to_conversation creates conversation items correctly."""
        mock_client = mocker.Mock()
        mock_client.conversations.items.create = mocker.AsyncMock(return_value=None)

        await append_turn_to_conversation(
            mock_client,
            conversation_id="conv-123",
            user_message="Hello",
            assistant_message="I cannot help with that",
        )

        mock_client.conversations.items.create.assert_called_once_with(
            "conv-123",
            items=[
                {"type": "message", "role": "user", "content": "Hello"},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": "I cannot help with that",
                },
            ],
        )


class TestAppendRefusedTurnToConversation:
    """Tests for append_refused_turn_to_conversation function."""

    @pytest.mark.asyncio
    async def test_appends_string_input(self, mocker: MockerFixture) -> None:
        """Test that append_refused_turn_to_conversation handles string input."""
        mock_client = mocker.Mock()
        mock_client.conversations.items.create = mocker.AsyncMock(return_value=None)

        refusal_message = OpenAIResponseMessage(
            type="message",
            role="assistant",
            content="I cannot help with that",
        )

        await append_refused_turn_to_conversation(
            mock_client,
            conversation_id="conv-123",
            user_input="Hello",
            refusal_message=refusal_message,
        )

        mock_client.conversations.items.create.assert_called_once()
        call_args = mock_client.conversations.items.create.call_args
        assert call_args[0][0] == "conv-123"
        items = call_args[1]["items"]
        assert len(items) == 2
        assert items[0]["type"] == "message"
        assert items[0]["role"] == "user"
        assert items[0]["content"] == "Hello"
        assert items[1]["type"] == "message"
        assert items[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_appends_list_input(self, mocker: MockerFixture) -> None:
        """Test that append_refused_turn_to_conversation handles list input."""
        mock_client = mocker.Mock()
        mock_client.conversations.items.create = mocker.AsyncMock(return_value=None)

        user_message = OpenAIResponseMessage(
            type="message",
            role="user",
            content="Search for files",
        )
        file_search_call = OpenAIResponseOutputMessageFileSearchToolCall(
            id="call_123",
            type="file_search_call",
            queries=["search query"],
            status="completed",
        )

        refusal_message = OpenAIResponseMessage(
            type="message",
            role="assistant",
            content="I cannot help with that",
        )

        await append_refused_turn_to_conversation(
            mock_client,
            conversation_id="conv-123",
            user_input=[user_message, file_search_call],
            refusal_message=refusal_message,
        )

        mock_client.conversations.items.create.assert_called_once()
        call_args = mock_client.conversations.items.create.call_args
        assert call_args[0][0] == "conv-123"
        items = call_args[1]["items"]
        # Should have 2 user items (message + file_search_call) + 1 refusal message
        assert len(items) == 3
        assert items[0]["type"] == "message"
        assert items[0]["role"] == "user"
        assert items[1]["type"] == "file_search_call"
        assert items[2]["type"] == "message"
        assert items[2]["role"] == "assistant"
