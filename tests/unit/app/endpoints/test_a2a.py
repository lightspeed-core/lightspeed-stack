"""Unit tests for the A2A (Agent-to-Agent) protocol endpoints."""

# pylint: disable=redefined-outer-name
# pylint: disable=protected-access

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request
from pytest_mock import MockerFixture

from a2a.types import (
    AgentCard,
    Artifact,
    Part,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from app.endpoints.a2a import (
    _convert_llama_content_to_a2a_parts,
    get_lightspeed_agent_card,
    LightspeedAgentExecutor,
    TaskResultAggregator,
    _CONTEXT_TO_CONVERSATION,
    _TASK_STORE,
    a2a_health_check,
    get_agent_card,
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
    mocker.patch("app.endpoints.a2a.configuration", cfg)
    return cfg


@pytest.fixture(name="setup_minimal_configuration")
def setup_minimal_configuration_fixture(mocker: MockerFixture) -> AppConfig:
    """Set up minimal configuration without agent_card_config."""
    config_dict: dict[Any, Any] = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {},
        "mcp_servers": [],
        "customization": {},  # Empty customization, no agent_card_config
        "authentication": {"module": "noop"},
        "authorization": {"access_rules": []},
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    mocker.patch("app.endpoints.a2a.configuration", cfg)
    return cfg


# -----------------------------
# Tests for _convert_llama_content_to_a2a_parts
# -----------------------------
class TestConvertLlamaContentToA2AParts:
    """Tests for the content conversion function."""

    def test_convert_none_content(self) -> None:
        """Test converting None content returns empty list."""
        result = _convert_llama_content_to_a2a_parts(None)
        assert not result

    def test_convert_string_content(self) -> None:
        """Test converting string content."""
        result = _convert_llama_content_to_a2a_parts("Hello, world!")
        assert len(result) == 1
        assert result[0].root.text == "Hello, world!"

    def test_convert_text_content_item(self) -> None:
        """Test converting TextContentItem."""
        mock_item = MagicMock()
        mock_item.type = "text"
        mock_item.text = "Test content"

        result = _convert_llama_content_to_a2a_parts(mock_item)
        assert len(result) == 1
        assert result[0].root.text == "Test content"

    def test_convert_list_of_text_items(self) -> None:
        """Test converting list of text items."""
        mock_item1 = MagicMock()
        mock_item1.type = "text"
        mock_item1.text = "First"

        mock_item2 = MagicMock()
        mock_item2.type = "text"
        mock_item2.text = "Second"

        result = _convert_llama_content_to_a2a_parts([mock_item1, mock_item2])
        assert len(result) == 2
        assert result[0].root.text == "First"
        assert result[1].root.text == "Second"

    def test_convert_list_of_strings(self) -> None:
        """Test converting list of strings."""
        result = _convert_llama_content_to_a2a_parts(["Hello", "World"])
        assert len(result) == 2
        assert result[0].root.text == "Hello"
        assert result[1].root.text == "World"

    def test_convert_mixed_list(self) -> None:
        """Test converting mixed list of strings and text items."""
        mock_item = MagicMock()
        mock_item.type = "text"
        mock_item.text = "Text item"

        result = _convert_llama_content_to_a2a_parts(["String", mock_item])
        assert len(result) == 2
        assert result[0].root.text == "String"
        assert result[1].root.text == "Text item"


# -----------------------------
# Tests for TaskResultAggregator
# -----------------------------
class TestTaskResultAggregator:
    """Tests for the TaskResultAggregator class."""

    def test_initial_state_is_working(self) -> None:
        """Test that initial state is working."""
        aggregator = TaskResultAggregator()
        assert aggregator.task_state == TaskState.working
        assert aggregator.task_status_message is None

    def test_process_working_event(self) -> None:
        """Test processing a working status event."""
        aggregator = TaskResultAggregator()
        message = new_agent_text_message("Processing...")
        event = TaskStatusUpdateEvent(
            task_id="task-1",
            context_id="ctx-1",
            status=TaskStatus(state=TaskState.working, message=message),
            final=False,
        )

        aggregator.process_event(event)

        assert aggregator.task_state == TaskState.working
        assert aggregator.task_status_message == message

    def test_process_failed_event_takes_priority(self) -> None:
        """Test that failed state takes priority."""
        aggregator = TaskResultAggregator()

        # First, set to input_required
        event1 = TaskStatusUpdateEvent(
            task_id="task-1",
            context_id="ctx-1",
            status=TaskStatus(state=TaskState.input_required),
            final=False,
        )
        aggregator.process_event(event1)

        # Then set to failed
        failed_message = new_agent_text_message("Error occurred")
        event2 = TaskStatusUpdateEvent(
            task_id="task-1",
            context_id="ctx-1",
            status=TaskStatus(state=TaskState.failed, message=failed_message),
            final=True,
        )
        aggregator.process_event(event2)

        assert aggregator.task_state == TaskState.failed
        assert aggregator.task_status_message == failed_message

    def test_process_auth_required_event(self) -> None:
        """Test processing auth_required status event."""
        aggregator = TaskResultAggregator()

        event = TaskStatusUpdateEvent(
            task_id="task-1",
            context_id="ctx-1",
            status=TaskStatus(state=TaskState.auth_required),
            final=False,
        )
        aggregator.process_event(event)

        assert aggregator.task_state == TaskState.auth_required

    def test_process_input_required_event(self) -> None:
        """Test processing input_required status event."""
        aggregator = TaskResultAggregator()

        event = TaskStatusUpdateEvent(
            task_id="task-1",
            context_id="ctx-1",
            status=TaskStatus(state=TaskState.input_required),
            final=False,
        )
        aggregator.process_event(event)

        assert aggregator.task_state == TaskState.input_required

    def test_failed_cannot_be_overridden(self) -> None:
        """Test that failed state cannot be overridden by other states."""
        aggregator = TaskResultAggregator()

        # Set to failed first
        event1 = TaskStatusUpdateEvent(
            task_id="task-1",
            context_id="ctx-1",
            status=TaskStatus(state=TaskState.failed),
            final=False,
        )
        aggregator.process_event(event1)

        # Try to set to working
        event2 = TaskStatusUpdateEvent(
            task_id="task-1",
            context_id="ctx-1",
            status=TaskStatus(state=TaskState.working),
            final=False,
        )
        aggregator.process_event(event2)

        # Failed should still be the state
        assert aggregator.task_state == TaskState.failed

    def test_non_final_events_show_working(self) -> None:
        """Test that non-final events are set to working state."""
        aggregator = TaskResultAggregator()

        event = TaskStatusUpdateEvent(
            task_id="task-1",
            context_id="ctx-1",
            status=TaskStatus(state=TaskState.input_required),
            final=False,
        )
        aggregator.process_event(event)

        # The event's state should be changed to working for streaming
        assert event.status.state == TaskState.working

    def test_ignores_non_status_events(self) -> None:
        """Test that non-status events are ignored."""
        aggregator = TaskResultAggregator()

        # Process an artifact event
        artifact_event = TaskArtifactUpdateEvent(
            task_id="task-1",
            context_id="ctx-1",
            artifact=Artifact(
                artifact_id="art-1",
                parts=[Part(root=TextPart(text="Result"))],
            ),
            last_chunk=True,
        )
        aggregator.process_event(artifact_event)

        # State should still be working
        assert aggregator.task_state == TaskState.working


# -----------------------------
# Tests for get_lightspeed_agent_card
# -----------------------------
class TestGetLightspeedAgentCard:
    """Tests for the agent card generation."""

    def test_get_agent_card_with_config(
        self, setup_configuration: AppConfig  # pylint: disable=unused-argument
    ) -> None:
        """Test getting agent card with full configuration."""
        agent_card = get_lightspeed_agent_card()

        assert agent_card.name == "Test Agent"
        assert agent_card.description == "A test agent"
        assert agent_card.url == "http://localhost:8080/a2a"
        assert agent_card.protocol_version == "0.2.1"

        # Check provider
        assert agent_card.provider is not None
        assert agent_card.provider.organization == "Test Org"

        # Check skills
        assert len(agent_card.skills) == 1
        assert agent_card.skills[0].id == "test-skill"
        assert agent_card.skills[0].name == "Test Skill"

        # Check capabilities
        assert agent_card.capabilities is not None
        assert agent_card.capabilities.streaming is True

    def test_get_agent_card_without_config_raises_error(
        self,
        setup_minimal_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test that getting agent card without config raises HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            get_lightspeed_agent_card()
        assert exc_info.value.status_code == 500
        assert "Agent card configuration not found" in exc_info.value.detail


# -----------------------------
# Tests for LightspeedAgentExecutor
# -----------------------------
class TestLightspeedAgentExecutor:
    """Tests for the LightspeedAgentExecutor class."""

    def test_executor_initialization(self) -> None:
        """Test executor initialization."""
        executor = LightspeedAgentExecutor(
            auth_token="test-token",
            mcp_headers={"server1": {"header1": "value1"}},
        )

        assert executor.auth_token == "test-token"
        assert executor.mcp_headers == {"server1": {"header1": "value1"}}

    def test_executor_initialization_default_mcp_headers(self) -> None:
        """Test executor initialization with default mcp_headers."""
        executor = LightspeedAgentExecutor(auth_token="test-token")

        assert executor.auth_token == "test-token"
        assert executor.mcp_headers == {}

    @pytest.mark.asyncio
    async def test_execute_without_message_raises_error(self) -> None:
        """Test that execute raises error when message is missing."""
        executor = LightspeedAgentExecutor(auth_token="test-token")

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
        executor = LightspeedAgentExecutor(auth_token="test-token")

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
        mocker.patch("app.endpoints.a2a.new_task", return_value=mock_task)

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
        executor = LightspeedAgentExecutor(auth_token="test-token")

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
        executor = LightspeedAgentExecutor(auth_token="test-token")

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
        executor = LightspeedAgentExecutor(auth_token="test-token")

        context = MagicMock(spec=RequestContext)
        event_queue = AsyncMock(spec=EventQueue)

        with pytest.raises(NotImplementedError):
            await executor.cancel(context, event_queue)


# -----------------------------
# Tests for context to conversation mapping
# -----------------------------
class TestContextToConversationMapping:
    """Tests for the context to conversation ID mapping."""

    def test_context_to_conversation_is_dict(self) -> None:
        """Test that _CONTEXT_TO_CONVERSATION is a dict."""
        assert isinstance(_CONTEXT_TO_CONVERSATION, dict)

    def test_task_store_exists(self) -> None:
        """Test that _TASK_STORE exists."""
        assert _TASK_STORE is not None


# -----------------------------
# Integration-style tests for endpoint handlers
# -----------------------------
class TestA2AEndpointHandlers:
    """Tests for A2A endpoint handler functions."""

    @pytest.mark.asyncio
    async def test_a2a_health_check(self) -> None:
        """Test the health check endpoint."""
        result = await a2a_health_check()

        assert result["status"] == "healthy"
        assert result["service"] == "lightspeed-a2a"
        assert "version" in result
        assert "a2a_sdk_version" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_get_agent_card_endpoint(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test the agent card endpoint."""
        # Mock authorization
        mocker.patch(
            "app.endpoints.a2a.authorize",
            lambda action: lambda f: f,
        )

        result = await get_agent_card(auth=MOCK_AUTH)

        assert isinstance(result, AgentCard)
        assert result.name == "Test Agent"
        assert result.url == "http://localhost:8080/a2a"
