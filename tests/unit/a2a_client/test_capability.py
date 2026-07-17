"""Unit tests for A2ADelegationCapability."""

# pylint: disable=redefined-outer-name

from typing import Any

import pytest
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.types import TextPart as A2ATextPart
from pytest_mock import MockerFixture

from a2a_client.capability import (
    A2ADelegationCapability,
    _extract_text_from_artifact,
    _send_and_collect,
)


@pytest.fixture
def mock_manager(mocker: MockerFixture) -> Any:
    """Create a mock A2AClientManager."""
    manager = mocker.MagicMock()

    card1 = mocker.MagicMock()
    card1.description = "A travel booking agent"
    card1.skills = [mocker.MagicMock(name="book_flight")]
    card1.skills[0].name = "book_flight"

    card2 = mocker.MagicMock()
    card2.description = "A code review agent"
    card2.skills = []

    manager.list_agents.return_value = {
        "travel": card1,
        "reviewer": card2,
    }
    manager.get_client.return_value = mocker.AsyncMock()
    return manager


@pytest.fixture
def capability(mock_manager: Any) -> A2ADelegationCapability:
    """Create an A2ADelegationCapability instance."""
    return A2ADelegationCapability(mock_manager)


class TestA2ADelegationCapability:
    """Tests for the delegation capability."""

    def test_get_toolset_returns_toolset_with_expected_tools(
        self, capability: A2ADelegationCapability
    ) -> None:
        """Test that get_toolset returns a toolset with list_agents and delegate_to_agent."""
        toolset = capability.get_toolset()
        assert toolset is not None
        tool_names = set(toolset.tools)
        assert "list_agents" in tool_names
        assert "delegate_to_agent" in tool_names

    def test_get_instructions_includes_agents(
        self, capability: A2ADelegationCapability
    ) -> None:
        """Test that instructions list available agents."""
        instructions = capability.get_instructions()
        assert instructions is not None
        assert "travel" in instructions
        assert "reviewer" in instructions
        assert "travel booking agent" in instructions.lower()

    def test_get_instructions_none_when_no_agents(self, mocker: MockerFixture) -> None:
        """Test that instructions return None when no agents available."""
        manager = mocker.MagicMock()
        manager.list_agents.return_value = {}
        cap = A2ADelegationCapability(manager)
        assert cap.get_instructions() is None


class TestExtractTextFromArtifact:
    """Tests for artifact text extraction."""

    def test_extracts_text_parts(self) -> None:
        """Test extraction of text from artifact parts."""
        event = TaskArtifactUpdateEvent(
            task_id="t1",
            context_id="c1",
            artifact=Artifact(
                artifact_id="a1",
                parts=[
                    Part(root=A2ATextPart(text="Hello ")),
                    Part(root=A2ATextPart(text="world")),
                ],
            ),
            last_chunk=True,
        )
        assert _extract_text_from_artifact(event) == "Hello world"

    def test_empty_parts(self) -> None:
        """Test extraction with no parts."""
        event = TaskArtifactUpdateEvent(
            task_id="t1",
            context_id="c1",
            artifact=Artifact(artifact_id="a1", parts=[]),
            last_chunk=True,
        )
        assert _extract_text_from_artifact(event) == ""


class TestSendAndCollect:
    """Tests for the _send_and_collect helper."""

    @pytest.mark.asyncio
    async def test_collects_text_from_message_response(
        self, mocker: MockerFixture
    ) -> None:
        """Test collecting text when agent returns a Message."""
        mock_message = Message(
            role=Role.agent,
            parts=[Part(root=A2ATextPart(text="Agent response"))],
            message_id="m1",
        )

        async def _mock_stream(_msg: Any) -> Any:
            yield mock_message

        mock_client = mocker.MagicMock()
        mock_client.send_message = _mock_stream

        result = await _send_and_collect(
            mock_client,
            Message(
                role=Role.user,
                parts=[Part(root=A2ATextPart(text="test"))],
                message_id="m2",
            ),
        )
        assert result == "Agent response"

    @pytest.mark.asyncio
    async def test_collects_text_from_artifact_event(
        self, mocker: MockerFixture
    ) -> None:
        """Test collecting text from TaskArtifactUpdateEvent."""
        artifact_event = TaskArtifactUpdateEvent(
            task_id="t1",
            context_id="c1",
            artifact=Artifact(
                artifact_id="a1",
                parts=[Part(root=A2ATextPart(text="Artifact text"))],
            ),
            last_chunk=True,
        )

        async def _mock_stream(_msg: Any) -> Any:
            yield (mocker.MagicMock(), artifact_event)

        mock_client = mocker.MagicMock()
        mock_client.send_message = _mock_stream

        result = await _send_and_collect(
            mock_client,
            Message(
                role=Role.user,
                parts=[Part(root=A2ATextPart(text="test"))],
                message_id="m1",
            ),
        )
        assert result == "Artifact text"

    @pytest.mark.asyncio
    async def test_handles_failed_task(self, mocker: MockerFixture) -> None:
        """Test that failed task status returns error message."""
        fail_event = TaskStatusUpdateEvent(
            task_id="t1",
            context_id="c1",
            status=TaskStatus(
                state=TaskState.failed,
                message=Message(
                    role=Role.agent,
                    parts=[Part(root=A2ATextPart(text="Something went wrong"))],
                    message_id="m1",
                ),
            ),
            final=True,
        )

        async def _mock_stream(_msg: Any) -> Any:
            yield (mocker.MagicMock(), fail_event)

        mock_client = mocker.MagicMock()
        mock_client.send_message = _mock_stream

        result = await _send_and_collect(
            mock_client,
            Message(
                role=Role.user,
                parts=[Part(root=A2ATextPart(text="test"))],
                message_id="m1",
            ),
        )
        assert "Delegation failed" in result
        assert "Something went wrong" in result

    @pytest.mark.asyncio
    async def test_empty_response(self, mocker: MockerFixture) -> None:
        """Test that empty response returns fallback message."""

        async def _mock_stream(_msg: Any) -> Any:
            return
            yield  # pragma: no cover

        mock_client = mocker.MagicMock()
        mock_client.send_message = _mock_stream

        result = await _send_and_collect(
            mock_client,
            Message(
                role=Role.user,
                parts=[Part(root=A2ATextPart(text="test"))],
                message_id="m1",
            ),
        )
        assert result == "Agent returned no response."
