"""Unit tests for the Responses A2A (Agent-to-Agent) protocol endpoints."""

# pylint: disable=redefined-outer-name
# pylint: disable=protected-access

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from pytest_mock import MockerFixture

from a2a.types import (
    AgentCard,
    Part,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue

from app.endpoints.responses_a2a import (
    _convert_responses_content_to_a2a_parts,
    get_responses_agent_card,
    ResponsesAgentExecutor,
    _CONTEXT_TO_RESPONSE_ID,
    responses_a2a_health_check,
    get_responses_agent_card_endpoint,
)
from configuration import AppConfig
from models.config import Action


# User ID must be proper UUID
MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)


@pytest.fixture
def dummy_request() -> Request:
    """Dummy request fixture for testing."""
    req = Request(
        scope={
            "type": "http",
        }
    )
    req.state.authorized_actions = set(Action)
    return req


@pytest.fixture(name="setup_configuration")
def setup_configuration_fixture(mocker: MockerFixture) -> AppConfig:
    """Set up configuration for tests."""
    config_dict: dict[Any, Any] = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "base_url": "http://localhost:8080",
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {},
        "mcp_servers": [],
        "customization": {
            "agent_card_config": {
                "name": "Test Agent",
                "description": "A test agent",
                "provider": {
                    "organization": "Test Org",
                    "url": "https://test.org",
                },
                "skills": [
                    {
                        "id": "test-skill",
                        "name": "Test Skill",
                        "description": "A test skill",
                        "tags": ["test"],
                        "inputModes": ["text/plain"],
                        "outputModes": ["text/plain"],
                    }
                ],
                "capabilities": {
                    "streaming": True,
                    "pushNotifications": False,
                    "stateTransitionHistory": False,
                },
            }
        },
        "authentication": {"module": "noop"},
        "authorization": {"access_rules": []},
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    # Patch a2a configuration (responses_a2a uses get_lightspeed_agent_card from a2a)
    mocker.patch("app.endpoints.a2a.configuration", cfg)
    return cfg


# -----------------------------
# Tests for _convert_responses_content_to_a2a_parts
# -----------------------------
class TestConvertResponsesContentToA2AParts:
    """Tests for the Responses API content conversion function."""

    def test_convert_empty_output(self) -> None:
        """Test converting empty output returns empty list."""
        result = _convert_responses_content_to_a2a_parts([])
        assert not result

    def test_convert_message_output_item(self) -> None:
        """Test converting message output item with text content."""
        mock_item = MagicMock()
        mock_item.type = "message"
        mock_item.role = "assistant"
        mock_item.content = "Hello, world!"

        result = _convert_responses_content_to_a2a_parts([mock_item])
        assert len(result) == 1
        assert result[0].root.text == "Hello, world!"

    def test_convert_message_with_content_list(self) -> None:
        """Test converting message with content as list."""
        mock_content_part = MagicMock()
        mock_content_part.text = "Content from list"

        mock_item = MagicMock()
        mock_item.type = "message"
        mock_item.role = "assistant"
        mock_item.content = [mock_content_part]

        result = _convert_responses_content_to_a2a_parts([mock_item])
        assert len(result) == 1
        assert result[0].root.text == "Content from list"

    def test_convert_non_message_item_ignored(self) -> None:
        """Test that non-message items are ignored."""
        mock_item = MagicMock()
        mock_item.type = "function_call"
        mock_item.role = "assistant"

        result = _convert_responses_content_to_a2a_parts([mock_item])
        assert not result

    def test_convert_non_assistant_role_ignored(self) -> None:
        """Test that non-assistant roles are ignored."""
        mock_item = MagicMock()
        mock_item.type = "message"
        mock_item.role = "user"
        mock_item.content = "User message"

        result = _convert_responses_content_to_a2a_parts([mock_item])
        assert not result

    def test_convert_multiple_message_items(self) -> None:
        """Test converting multiple message items."""
        mock_item1 = MagicMock()
        mock_item1.type = "message"
        mock_item1.role = "assistant"
        mock_item1.content = "First message"

        mock_item2 = MagicMock()
        mock_item2.type = "message"
        mock_item2.role = "assistant"
        mock_item2.content = "Second message"

        result = _convert_responses_content_to_a2a_parts([mock_item1, mock_item2])
        assert len(result) == 2
        assert result[0].root.text == "First message"
        assert result[1].root.text == "Second message"


# -----------------------------
# Tests for get_responses_agent_card
# -----------------------------
class TestGetResponsesAgentCard:
    """Tests for the responses agent card generation."""

    def test_get_responses_agent_card_url(
        self, setup_configuration: AppConfig  # pylint: disable=unused-argument
    ) -> None:
        """Test that responses agent card has correct URL."""
        agent_card = get_responses_agent_card()

        # URL should point to /responses/a2a
        assert "/responses/a2a" in agent_card.url
        assert agent_card.name == "Test Agent"

    def test_get_responses_agent_card_inherits_config(
        self, setup_configuration: AppConfig  # pylint: disable=unused-argument
    ) -> None:
        """Test that responses agent card inherits from base config."""
        agent_card = get_responses_agent_card()

        assert agent_card.description == "A test agent"
        assert agent_card.protocol_version == "0.2.1"
        assert len(agent_card.skills) == 1


# -----------------------------
# Tests for ResponsesAgentExecutor
# -----------------------------
class TestResponsesAgentExecutor:
    """Tests for the ResponsesAgentExecutor class."""

    def test_executor_initialization(self) -> None:
        """Test executor initialization."""
        executor = ResponsesAgentExecutor(
            auth_token="test-token",
            mcp_headers={"server1": {"header1": "value1"}},
        )

        assert executor.auth_token == "test-token"
        assert executor.mcp_headers == {"server1": {"header1": "value1"}}

    def test_executor_initialization_default_mcp_headers(self) -> None:
        """Test executor initialization with default mcp_headers."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        assert executor.auth_token == "test-token"
        assert executor.mcp_headers == {}

    @pytest.mark.asyncio
    async def test_execute_without_message_raises_error(self) -> None:
        """Test that execute raises error when message is missing."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        context = MagicMock(spec=RequestContext)
        context.message = None

        event_queue = AsyncMock(spec=EventQueue)

        with pytest.raises(ValueError, match="A2A request must have a message"):
            await executor.execute(context, event_queue)

    @pytest.mark.asyncio
    async def test_execute_creates_new_task(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test that execute creates a new task when current_task is None."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        # Mock the context with a mock message
        mock_message = MagicMock()
        mock_message.role = "user"
        mock_message.parts = [Part(root=TextPart(text="Hello"))]
        mock_message.metadata = {}

        context = MagicMock(spec=RequestContext)
        context.message = mock_message
        context.current_task = None
        context.task_id = None
        context.context_id = None
        context.get_user_input.return_value = "Hello"

        # Mock event queue
        event_queue = AsyncMock(spec=EventQueue)

        # Mock new_task to return a mock Task
        mock_task = MagicMock()
        mock_task.id = "test-task-id"
        mock_task.context_id = "test-context-id"
        mocker.patch("app.endpoints.responses_a2a.new_task", return_value=mock_task)

        # Mock the streaming process to avoid actual LLM calls
        mocker.patch.object(
            executor,
            "_process_task_streaming",
            new_callable=AsyncMock,
        )

        await executor.execute(context, event_queue)

        # Verify a task was created and enqueued
        assert event_queue.enqueue_event.called

    @pytest.mark.asyncio
    async def test_execute_handles_errors_gracefully(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test that execute handles errors and sends failure event."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        # Mock the context with a mock message
        mock_message = MagicMock()
        mock_message.role = "user"
        mock_message.parts = [Part(root=TextPart(text="Hello"))]
        mock_message.metadata = {}

        context = MagicMock(spec=RequestContext)
        context.message = mock_message
        context.current_task = MagicMock()
        context.task_id = "task-123"
        context.context_id = "ctx-456"
        context.get_user_input.return_value = "Hello"

        # Mock event queue
        event_queue = AsyncMock(spec=EventQueue)

        # Mock the streaming process to raise an error
        mocker.patch.object(
            executor,
            "_process_task_streaming",
            side_effect=Exception("Test error"),
        )

        await executor.execute(context, event_queue)

        # Verify failure event was enqueued
        calls = event_queue.enqueue_event.call_args_list
        # Find the failure status update
        failure_sent = False
        for call in calls:
            event = call[0][0]
            if isinstance(event, TaskStatusUpdateEvent):
                if event.status.state == TaskState.failed:
                    failure_sent = True
                    break
        assert failure_sent

    @pytest.mark.asyncio
    async def test_process_task_streaming_no_input(
        self,
        mocker: MockerFixture,  # pylint: disable=unused-argument
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test _process_task_streaming when no input is provided."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        # Mock the context with no input
        mock_message = MagicMock()
        mock_message.role = "user"
        mock_message.parts = []
        mock_message.metadata = {}

        context = MagicMock(spec=RequestContext)
        context.task_id = "task-123"
        context.context_id = "ctx-456"
        context.message = mock_message
        context.get_user_input.return_value = ""

        # Mock event queue
        event_queue = AsyncMock(spec=EventQueue)

        # Create task updater mock
        task_updater = MagicMock()
        task_updater.update_status = AsyncMock()
        task_updater.event_queue = event_queue

        await executor._process_task_streaming(context, task_updater)

        # Verify input_required status was sent
        task_updater.update_status.assert_called_once()
        call_args = task_updater.update_status.call_args
        assert call_args[0][0] == TaskState.input_required

    @pytest.mark.asyncio
    async def test_cancel_raises_not_implemented(self) -> None:
        """Test that cancel raises NotImplementedError."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        context = MagicMock(spec=RequestContext)
        event_queue = AsyncMock(spec=EventQueue)

        with pytest.raises(NotImplementedError):
            await executor.cancel(context, event_queue)


# -----------------------------
# Tests for context to response ID mapping
# -----------------------------
class TestContextToResponseIdMapping:  # pylint: disable=too-few-public-methods
    """Tests for the context to response ID mapping."""

    def test_context_to_response_id_is_dict(self) -> None:
        """Test that _CONTEXT_TO_RESPONSE_ID is a dict."""
        assert isinstance(_CONTEXT_TO_RESPONSE_ID, dict)


# -----------------------------
# Tests for stream event conversion
# -----------------------------
class TestConvertStreamToEvents:
    """Tests for the stream to events conversion."""

    @pytest.mark.asyncio
    async def test_convert_response_created_event(
        self, mocker: MockerFixture  # pylint: disable=unused-argument
    ) -> None:
        """Test converting response.created event extracts response ID."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        # Create mock context
        context = MagicMock(spec=RequestContext)
        context.task_id = "task-123"
        context.context_id = "ctx-456"

        # Create mock stream with response.created event
        mock_response = MagicMock()
        mock_response.id = "resp-789"

        mock_chunk = MagicMock()
        mock_chunk.type = "response.created"
        mock_chunk.response = mock_response

        async def mock_stream() -> AsyncGenerator[Any, None]:
            yield mock_chunk

        # Convert stream to events
        events = []
        async for event in executor._convert_stream_to_events(
            mock_stream(), context, None
        ):
            events.append(event)

        # response.created should not yield events, just update state
        assert len(events) == 0
        # But should have updated the context mapping
        assert _CONTEXT_TO_RESPONSE_ID.get("ctx-456") == "resp-789"

        # Clean up
        _CONTEXT_TO_RESPONSE_ID.pop("ctx-456", None)

    @pytest.mark.asyncio
    async def test_convert_text_delta_event(
        self, mocker: MockerFixture  # pylint: disable=unused-argument
    ) -> None:
        """Test converting response.output_text.delta event."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        # Create mock context
        context = MagicMock(spec=RequestContext)
        context.task_id = "task-123"
        context.context_id = "ctx-456"

        # Create mock stream with text delta event
        mock_chunk = MagicMock()
        mock_chunk.type = "response.output_text.delta"
        mock_chunk.delta = "Hello"

        async def mock_stream() -> AsyncGenerator[Any, None]:
            yield mock_chunk

        # Convert stream to events
        events = []
        async for event in executor._convert_stream_to_events(
            mock_stream(), context, None
        ):
            events.append(event)

        # Should yield a status update event with the text
        assert len(events) == 1
        assert isinstance(events[0], TaskStatusUpdateEvent)
        assert events[0].status.state == TaskState.working

    @pytest.mark.asyncio
    async def test_convert_response_completed_event(
        self, mocker: MockerFixture  # pylint: disable=unused-argument
    ) -> None:
        """Test converting response.completed event yields artifact."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        # Create mock context
        context = MagicMock(spec=RequestContext)
        context.task_id = "task-123"
        context.context_id = "ctx-456"

        # Create mock response with output
        mock_output_item = MagicMock()
        mock_output_item.type = "message"
        mock_output_item.role = "assistant"
        mock_output_item.content = "Final response"

        mock_response = MagicMock()
        mock_response.output = [mock_output_item]

        mock_chunk = MagicMock()
        mock_chunk.type = "response.completed"
        mock_chunk.response = mock_response

        async def mock_stream() -> AsyncGenerator[Any, None]:
            yield mock_chunk

        # Convert stream to events
        events = []
        async for event in executor._convert_stream_to_events(
            mock_stream(), context, None
        ):
            events.append(event)

        # Should yield an artifact update event
        assert len(events) == 1
        assert isinstance(events[0], TaskArtifactUpdateEvent)
        assert events[0].last_chunk is True

    @pytest.mark.asyncio
    async def test_convert_function_call_event(
        self, mocker: MockerFixture  # pylint: disable=unused-argument
    ) -> None:
        """Test converting response.function_call_arguments.done event."""
        executor = ResponsesAgentExecutor(auth_token="test-token")

        # Create mock context
        context = MagicMock(spec=RequestContext)
        context.task_id = "task-123"
        context.context_id = "ctx-456"

        # Create mock chunk for function call
        mock_chunk = MagicMock()
        mock_chunk.type = "response.function_call_arguments.done"
        mock_chunk.item_id = "call-123"

        async def mock_stream() -> AsyncGenerator[Any, None]:
            yield mock_chunk

        # Convert stream to events
        events = []
        async for event in executor._convert_stream_to_events(
            mock_stream(), context, None
        ):
            events.append(event)

        # Should yield a status update about the tool call
        assert len(events) == 1
        assert isinstance(events[0], TaskStatusUpdateEvent)
        assert "Tool call" in str(events[0].status.message)


# -----------------------------
# Integration-style tests for endpoint handlers
# -----------------------------
class TestResponsesA2AEndpointHandlers:
    """Tests for Responses A2A endpoint handler functions."""

    @pytest.mark.asyncio
    async def test_responses_a2a_health_check(
        self, mocker: MockerFixture  # pylint: disable=unused-argument
    ) -> None:
        """Test the health check endpoint."""
        result = await responses_a2a_health_check()

        assert result["status"] == "healthy"
        assert result["service"] == "lightspeed-responses-a2a"
        assert result["api_type"] == "responses"
        assert "version" in result
        assert "a2a_sdk_version" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_get_responses_agent_card_endpoint(
        self,
        mocker: MockerFixture,  # pylint: disable=unused-argument
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test the responses agent card endpoint."""
        result = await get_responses_agent_card_endpoint(auth=MOCK_AUTH)

        assert isinstance(result, AgentCard)
        assert result.name == "Test Agent"
        assert "/responses/a2a" in result.url
