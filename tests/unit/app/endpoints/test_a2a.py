"""Unit tests for the A2A (Agent-to-Agent) protocol endpoints."""

# pylint: disable=redefined-outer-name
# pylint: disable=protected-access

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException, Request
from llama_stack_client import APIConnectionError
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
    _convert_responses_content_to_a2a_parts,
    get_lightspeed_agent_card,
    A2AAgentExecutor,
    TaskResultAggregator,
    _get_task_store,
    _get_context_store,
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
        "a2a_state": {},  # Empty = in-memory storage (default)
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
        "a2a_state": {},  # Empty = in-memory storage (default)
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    mocker.patch("app.endpoints.a2a.configuration", cfg)
    return cfg


# -----------------------------
# Tests for _convert_responses_content_to_a2a_parts
# -----------------------------
class TestConvertResponsesContentToA2AParts:
    """Tests for the content conversion function."""

    def test_convert_empty_output(self, mocker: MockerFixture) -> None:
        """Test converting empty output returns empty list."""
        mocker.patch(
            "app.endpoints.a2a.extract_text_from_response_output_item",
            return_value=None,
        )
        result = _convert_responses_content_to_a2a_parts([])
        assert not result

    def test_convert_single_output_item(self, mocker: MockerFixture) -> None:
        """Test converting single output item with text."""
        mocker.patch(
            "app.endpoints.a2a.extract_text_from_response_output_item",
            return_value="Hello, world!",
        )
        mock_output_item = MagicMock()
        result = _convert_responses_content_to_a2a_parts([mock_output_item])
        assert len(result) == 1
        assert result[0].root.text == "Hello, world!"

    def test_convert_multiple_output_items(self, mocker: MockerFixture) -> None:
        """Test converting multiple output items."""
        extract_mock = mocker.patch(
            "app.endpoints.a2a.extract_text_from_response_output_item",
        )
        extract_mock.side_effect = ["First", "Second"]

        mock_item1 = MagicMock()
        mock_item2 = MagicMock()

        result = _convert_responses_content_to_a2a_parts([mock_item1, mock_item2])
        assert len(result) == 2
        assert result[0].root.text == "First"
        assert result[1].root.text == "Second"

    def test_convert_output_items_with_none_text(self, mocker: MockerFixture) -> None:
        """Test that output items with no text are filtered out."""
        extract_mock = mocker.patch(
            "app.endpoints.a2a.extract_text_from_response_output_item",
        )
        extract_mock.side_effect = ["Valid text", None, "Another valid"]

        mock_items = [MagicMock(), MagicMock(), MagicMock()]

        result = _convert_responses_content_to_a2a_parts(mock_items)
        assert len(result) == 2
        assert result[0].root.text == "Valid text"
        assert result[1].root.text == "Another valid"


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
        assert agent_card.protocol_version == "0.3.0"  # Default protocol version

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

    def test_get_agent_card_with_custom_protocol_version(
        self, mocker: MockerFixture
    ) -> None:
        """Test getting agent card with custom protocol version."""
        config_dict: dict[Any, Any] = {
            "name": "test",
            "service": {
                "host": "localhost",
                "port": 8080,
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
                    "protocolVersion": "0.2.1",  # Custom protocol version
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
            "a2a_state": {},
        }
        cfg = AppConfig()
        cfg.init_from_dict(config_dict)
        mocker.patch("app.endpoints.a2a.configuration", cfg)

        agent_card = get_lightspeed_agent_card()

        assert agent_card.protocol_version == "0.2.1"  # Custom version used

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
# Tests for A2AAgentExecutor
# -----------------------------
class TestA2AAgentExecutor:
    """Tests for the A2AAgentExecutor class."""

    def test_executor_initialization(self) -> None:
        """Test executor initialization."""
        executor = A2AAgentExecutor(
            auth_token="test-token",
            mcp_headers={"server1": {"header1": "value1"}},
        )

        assert executor.auth_token == "test-token"
        assert executor.mcp_headers == {"server1": {"header1": "value1"}}

    def test_executor_initialization_default_mcp_headers(self) -> None:
        """Test executor initialization with default mcp_headers."""
        executor = A2AAgentExecutor(auth_token="test-token")

        assert executor.auth_token == "test-token"
        assert executor.mcp_headers == {}

    @pytest.mark.asyncio
    async def test_execute_without_message_raises_error(self) -> None:
        """Test that execute raises error when message is missing."""
        executor = A2AAgentExecutor(auth_token="test-token")

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
        executor = A2AAgentExecutor(auth_token="test-token")

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
    async def test_execute_passes_task_ids_to_streaming(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test that execute passes computed task_id and context_id to _process_task_streaming.

        This test verifies the fix for the issue where task_id and context_id
        were computed locally in execute() but not stored in the context object,
        causing _process_task_streaming to fail when trying to read them from context.
        """
        executor = A2AAgentExecutor(auth_token="test-token")

        # Mock the context with empty task_id and context_id (first-turn scenario)
        mock_message = MagicMock()
        mock_message.role = "user"
        mock_message.parts = [Part(root=TextPart(text="Hello"))]
        mock_message.metadata = {}

        context = MagicMock(spec=RequestContext)
        context.message = mock_message
        context.current_task = None
        context.task_id = None  # Empty in context object
        context.context_id = None  # Empty in context object
        context.get_user_input.return_value = "Hello"

        # Mock event queue
        event_queue = AsyncMock(spec=EventQueue)

        # Mock new_task to return a task with specific IDs
        mock_task = MagicMock()
        mock_task.id = "computed-task-id-123"
        mock_task.context_id = "computed-context-id-456"
        mocker.patch("app.endpoints.a2a.new_task", return_value=mock_task)

        # Mock the streaming process
        mock_process_streaming = mocker.patch.object(
            executor,
            "_process_task_streaming",
            new_callable=AsyncMock,
        )

        await executor.execute(context, event_queue)

        # Verify _process_task_streaming was called with the computed IDs
        # NOT the None values from context
        mock_process_streaming.assert_called_once()
        call_args = mock_process_streaming.call_args

        # Check positional arguments: context, task_updater, task_id, context_id
        assert call_args[0][0] == context  # First arg is context
        # Third and fourth args should be the computed IDs
        assert call_args[0][2] == "computed-task-id-123"  # task_id
        assert call_args[0][3] == "computed-context-id-456"  # context_id

    @pytest.mark.asyncio
    async def test_execute_handles_errors_gracefully(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test that execute handles errors and sends failure event."""
        executor = A2AAgentExecutor(auth_token="test-token")

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
        executor = A2AAgentExecutor(auth_token="test-token")

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

        await executor._process_task_streaming(
            context, task_updater, context.task_id, context.context_id
        )

        # Verify input_required status was sent
        task_updater.update_status.assert_called_once()
        call_args = task_updater.update_status.call_args
        assert call_args[0][0] == TaskState.input_required

    @pytest.mark.asyncio
    async def test_process_task_streaming_handles_api_connection_error_on_models_list(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test _process_task_streaming handles APIConnectionError from models.list()."""
        executor = A2AAgentExecutor(auth_token="test-token")

        # Mock the context with valid input
        mock_message = MagicMock()
        mock_message.role = "user"
        mock_message.parts = [Part(root=TextPart(text="Hello"))]
        mock_message.metadata = {}

        context = MagicMock(spec=RequestContext)
        context.task_id = "task-123"
        context.context_id = "ctx-456"
        context.message = mock_message
        context.get_user_input.return_value = "Hello"

        # Mock event queue
        event_queue = AsyncMock(spec=EventQueue)

        # Create task updater mock
        task_updater = MagicMock()
        task_updater.update_status = AsyncMock()
        task_updater.event_queue = event_queue

        # Mock the context store
        mock_context_store = AsyncMock()
        mock_context_store.get.return_value = None
        mocker.patch(
            "app.endpoints.a2a._get_context_store", return_value=mock_context_store
        )

        # Mock the client to raise APIConnectionError on models.list()
        mock_client = AsyncMock()
        # Create a mock httpx.Request for APIConnectionError
        mock_request = httpx.Request("GET", "http://test-llama-stack/models")
        mock_client.models.list.side_effect = APIConnectionError(
            message="Connection refused: unable to reach Llama Stack",
            request=mock_request,
        )
        mocker.patch(
            "app.endpoints.a2a.AsyncLlamaStackClientHolder"
        ).return_value.get_client.return_value = mock_client

        await executor._process_task_streaming(
            context, task_updater, context.task_id, context.context_id
        )

        # Verify failure status was sent
        task_updater.update_status.assert_called_once()
        call_args = task_updater.update_status.call_args
        assert call_args[0][0] == TaskState.failed
        assert call_args[1]["final"] is True
        # Verify error message contains helpful info
        error_message = call_args[1]["message"]
        assert "Unable to connect to Llama Stack backend service" in str(error_message)

    @pytest.mark.asyncio
    async def test_process_task_streaming_handles_api_connection_error_on_retrieve_response(
        self,
        mocker: MockerFixture,
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test _process_task_streaming handles APIConnectionError from retrieve_response()."""
        executor = A2AAgentExecutor(auth_token="test-token")

        # Mock the context with valid input
        mock_message = MagicMock()
        mock_message.role = "user"
        mock_message.parts = [Part(root=TextPart(text="Hello"))]
        mock_message.metadata = {}

        context = MagicMock(spec=RequestContext)
        context.task_id = "task-123"
        context.context_id = "ctx-456"
        context.message = mock_message
        context.get_user_input.return_value = "Hello"

        # Mock event queue
        event_queue = AsyncMock(spec=EventQueue)

        # Create task updater mock
        task_updater = MagicMock()
        task_updater.update_status = AsyncMock()
        task_updater.event_queue = event_queue

        # Mock the context store
        mock_context_store = AsyncMock()
        mock_context_store.get.return_value = None
        mocker.patch(
            "app.endpoints.a2a._get_context_store", return_value=mock_context_store
        )

        # Mock the client to succeed on models.list()
        mock_client = AsyncMock()
        mock_models = MagicMock()
        mock_models.models = []
        mock_client.models.list.return_value = mock_models
        mocker.patch(
            "app.endpoints.a2a.AsyncLlamaStackClientHolder"
        ).return_value.get_client.return_value = mock_client

        # Mock select_model_and_provider_id
        mocker.patch(
            "app.endpoints.a2a.select_model_and_provider_id",
            return_value=("model-id", "model-id", "provider-id"),
        )

        # Mock evaluate_model_hints
        mocker.patch(
            "app.endpoints.a2a.evaluate_model_hints", return_value=(None, None)
        )

        # Mock retrieve_response to raise APIConnectionError
        mock_request = httpx.Request("POST", "http://test-llama-stack/responses")
        mocker.patch(
            "app.endpoints.a2a.retrieve_response",
            side_effect=APIConnectionError(
                message="Connection timeout during streaming", request=mock_request
            ),
        )

        await executor._process_task_streaming(
            context, task_updater, context.task_id, context.context_id
        )

        # Verify failure status was sent
        task_updater.update_status.assert_called_once()
        call_args = task_updater.update_status.call_args
        assert call_args[0][0] == TaskState.failed
        assert call_args[1]["final"] is True
        # Verify error message contains helpful info
        error_message = call_args[1]["message"]
        assert "Unable to connect to Llama Stack backend service" in str(error_message)

    @pytest.mark.asyncio
    async def test_cancel_raises_not_implemented(self) -> None:
        """Test that cancel raises NotImplementedError."""
        executor = A2AAgentExecutor(auth_token="test-token")

        context = MagicMock(spec=RequestContext)
        event_queue = AsyncMock(spec=EventQueue)

        with pytest.raises(NotImplementedError):
            await executor.cancel(context, event_queue)


# -----------------------------
# Tests for context to conversation mapping
# -----------------------------
class TestContextToConversationMapping:
    """Tests for the context to conversation ID mapping."""

    @pytest.mark.asyncio
    async def test_get_context_store_returns_store(
        self,
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test that _get_context_store returns a context store."""
        # pylint: disable=import-outside-toplevel
        # Reset module-level state and factory
        import app.endpoints.a2a as a2a_module
        from a2a_storage import A2AStorageFactory

        a2a_module._context_store = None
        a2a_module._task_store = None
        A2AStorageFactory.reset()

        store = await _get_context_store()
        assert store is not None
        assert store.ready() is True

    @pytest.mark.asyncio
    async def test_get_task_store_returns_store(
        self,
        setup_configuration: AppConfig,  # pylint: disable=unused-argument
    ) -> None:
        """Test that _get_task_store returns a task store."""
        # pylint: disable=import-outside-toplevel
        # Reset module-level state and factory
        import app.endpoints.a2a as a2a_module
        from a2a_storage import A2AStorageFactory

        a2a_module._context_store = None
        a2a_module._task_store = None
        A2AStorageFactory.reset()

        store = await _get_task_store()
        assert store is not None


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
