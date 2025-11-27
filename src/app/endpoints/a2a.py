"""Handler for A2A (Agent-to-Agent) protocol endpoints."""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from datetime import timezone
from typing import Annotated, Any, AsyncIterator, MutableMapping

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.responses import Response, StreamingResponse

from a2a.types import (
    AgentCard,
    AgentSkill,
    AgentProvider,
    AgentCapabilities,
    Artifact,
    Message,
    Part,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.server.apps import A2AStarletteApplication
from a2a.utils import new_agent_text_message, new_task

from authentication.interface import AuthTuple
from authentication import get_auth_dependency
from authorization.middleware import authorize
from configuration import configuration
from models.config import Action
from models.requests import QueryRequest
from app.endpoints.query import (
    select_model_and_provider_id,
    evaluate_model_hints,
)
from app.endpoints.streaming_query import retrieve_response
from client import AsyncLlamaStackClientHolder
from utils.mcp_headers import mcp_headers_dependency
from version import __version__

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["a2a"])

auth_dependency = get_auth_dependency()


# -----------------------------
# Persistent State (multi-turn)
# -----------------------------
# Keep a single TaskStore instance so tasks persist across requests and
# previous messages remain connected to the current request.
_TASK_STORE = InMemoryTaskStore()

# Map A2A contextId -> Llama Stack conversationId to preserve history across turns
_CONTEXT_TO_CONVERSATION: dict[str, str] = {}


def _convert_llama_content_to_a2a_parts(content: Any) -> list[Part]:
    """
    Convert Llama Stack InterleavedContent to A2A Parts.

    Args:
        content: Llama Stack content (str, TextContentItem, ImageContentItem, or list)

    Returns:
        List of A2A Part objects
    """
    parts: list[Part] = []

    if content is None:
        return parts

    if isinstance(content, str):
        parts.append(Part(root=TextPart(text=content)))
    elif isinstance(content, list):
        for item in content:
            if hasattr(item, "type"):
                if item.type == "text":
                    parts.append(Part(root=TextPart(text=item.text)))
                # Note: image content is not yet handled; extend this branch if needed.
            elif isinstance(item, str):
                parts.append(Part(root=TextPart(text=item)))
    elif hasattr(content, "type") and content.type == "text":
        parts.append(Part(root=TextPart(text=content.text)))

    return parts


class TaskResultAggregator:
    """Aggregates the task status updates and provides the final task state."""

    def __init__(self) -> None:
        """Initialize the task result aggregator with default state."""
        self._task_state: TaskState = TaskState.working
        self._task_status_message: Message | None = None

    def process_event(
        self, event: TaskStatusUpdateEvent | TaskArtifactUpdateEvent | Any
    ) -> None:
        """
        Process an event from the agent run and detect signals about the task status.

        Priority of task state (highest to lowest):
        - failed
        - auth_required
        - input_required
        - working

        Args:
            event: The event to process
        """
        if isinstance(event, TaskStatusUpdateEvent):
            if event.status.state == TaskState.failed:
                self._task_state = TaskState.failed
                self._task_status_message = event.status.message
            elif (
                event.status.state == TaskState.auth_required
                and self._task_state != TaskState.failed
            ):
                self._task_state = TaskState.auth_required
                self._task_status_message = event.status.message
            elif (
                event.status.state == TaskState.input_required
                and self._task_state not in (TaskState.failed, TaskState.auth_required)
            ):
                self._task_state = TaskState.input_required
                self._task_status_message = event.status.message
            elif self._task_state == TaskState.working:
                # Keep tracking the working message/status
                self._task_status_message = event.status.message

            # Ensure the stream always sees "working" state for intermediate updates
            # unless it's already terminal in the event flow (which we control via
            # generator). This prevents premature terminationby clients listening to the stream.
            if not event.final:
                event.status.state = TaskState.working

    @property
    def task_state(self) -> TaskState:
        """Return the current task state."""
        return self._task_state

    @property
    def task_status_message(self) -> Any:
        """Return the current task status message."""
        return self._task_status_message


# -----------------------------
# Agent Executor Implementation
# -----------------------------
class LightspeedAgentExecutor(AgentExecutor):
    """
    Lightspeed Agent Executor for OpenShift Assisted Chat Installer.

    This executor implements the A2A AgentExecutor interface and handles
    routing queries to the appropriate LLM backend.
    """

    def __init__(
        self, auth_token: str, mcp_headers: dict[str, dict[str, str]] | None = None
    ):
        """
        Initialize the Lightspeed agent executor.

        Args:
            auth_token: Authentication token for the request
            mcp_headers: MCP headers for context propagation
        """
        self.auth_token: str = auth_token
        self.mcp_headers: dict[str, dict[str, str]] = mcp_headers or {}

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute the agent with the given context and send results to the event queue.

        Args:
            context: The request context containing user input and metadata
            event_queue: Queue for sending response events
        """
        # Get or create task
        if not context.message:
            raise ValueError("A2A request must have a message")

        task_id = context.task_id or ""
        context_id = context.context_id or ""
        # for new task, create a task submitted event
        if not context.current_task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
            # await task_updater.update_status(
            #     TaskState.submitted,
            #     message=context.message,
            #    final=False,
            # )
            task_id = task.id
            context_id = task.context_id
        task_updater = TaskUpdater(event_queue, task_id, context_id)

        # Process the task with streaming
        try:
            await self._process_task_streaming(context, task_updater)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error handling A2A request: %s", e, exc_info=True)
            # Publish failure event
            try:
                await task_updater.update_status(
                    TaskState.failed,
                    message=new_agent_text_message(str(e)),
                    final=True,
                )
            except Exception as enqueue_error:  # pylint: disable=broad-exception-caught
                logger.error(
                    "Failed to publish failure event: %s", enqueue_error, exc_info=True
                )

    async def _process_task_streaming(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self,
        context: RequestContext,
        task_updater: TaskUpdater,
    ) -> None:
        """
        Process the task with streaming updates.

        Args:
            context: The request context
            task_updater: Task updater for sending events
        """
        # Validate IDs
        task_id = context.task_id
        context_id = context.context_id
        if not task_id or not context_id:
            raise ValueError("Task ID and Context ID are required")

        # Extract user input using SDK utility
        user_input = context.get_user_input()
        if not user_input:
            await task_updater.update_status(
                TaskState.input_required,
                message=new_agent_text_message(
                    "No input received. Please provide your input.",
                    context_id=context_id,
                    task_id=task_id,
                ),
                final=True,
            )
            return

        preview = user_input[:200] + ("..." if len(user_input) > 200 else "")
        logger.info("Processing A2A request: %s", preview)

        # Extract routing metadata from context
        metadata = context.message.metadata if context.message else {}
        model = metadata.get("model") if metadata else None
        provider = metadata.get("provider") if metadata else None

        # Resolve conversation_id from A2A contextId to preserve multi-turn history
        a2a_context_id = context_id
        conversation_id_hint = _CONTEXT_TO_CONVERSATION.get(a2a_context_id)
        logger.info(
            "A2A contextId %s maps to conversation_id %s",
            a2a_context_id,
            conversation_id_hint,
        )

        # Build internal query request with conversation_id for history
        query_request = QueryRequest(
            query=user_input,
            conversation_id=conversation_id_hint,
            model=model,
            provider=provider,
            system_prompt=None,
            attachments=None,
            no_tools=False,
            generate_topic_summary=True,
            media_type=None,
        )

        # Get LLM client and select model
        client = AsyncLlamaStackClientHolder().get_client()
        llama_stack_model_id, _model_id, _provider_id = select_model_and_provider_id(
            await client.models.list(),
            *evaluate_model_hints(user_conversation=None, query_request=query_request),
        )

        # Stream response from LLM with status updates
        stream, conversation_id = await retrieve_response(
            client,
            llama_stack_model_id,
            query_request,
            self.auth_token,
            mcp_headers=self.mcp_headers,
        )

        # Persist conversationId for next turn in same A2A context
        if conversation_id:
            _CONTEXT_TO_CONVERSATION[a2a_context_id] = conversation_id
            logger.info(
                "Persisted conversation_id %s for A2A contextId %s",
                conversation_id,
                a2a_context_id,
            )

        # Initialize result aggregator
        aggregator = TaskResultAggregator()
        event_queue = task_updater.event_queue

        # Emit working status with metadata before processing stream
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                status=TaskStatus(
                    state=TaskState.working,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
                context_id=context_id,
                final=False,
                metadata={
                    "model": llama_stack_model_id,
                    "conversation_id": conversation_id or "",
                },
            )
        )

        # Process stream using generator and aggregator pattern
        async for a2a_event in self._convert_stream_to_events(
            stream, context, conversation_id
        ):
            aggregator.process_event(a2a_event)
            await event_queue.enqueue_event(a2a_event)

        # Publish the final task result event
        if aggregator.task_state == TaskState.working:
            # If task is still working (and we finished the stream), it usually means
            # we completed successfully. Send the completed status.
            await task_updater.update_status(
                TaskState.completed,
                timestamp=datetime.now(timezone.utc).isoformat(),
                final=True,
            )
        else:
            # Send the terminal state we collected (input_required, failed, etc.)
            await task_updater.update_status(
                aggregator.task_state,
                message=aggregator.task_status_message,
                timestamp=datetime.now(timezone.utc).isoformat(),
                final=True,
            )

    async def _convert_stream_to_events(
        self,
        stream: AsyncIterator[Any],
        context: RequestContext,
        conversation_id: str | None,
    ) -> AsyncIterator[Any]:
        """
        Convert Llama Stack stream chunks to A2A events.

        Args:
            stream: The Llama Stack response stream
            context: The request context
            conversation_id: The conversation ID

        Yields:
            A2A events (TaskStatusUpdateEvent or TaskArtifactUpdateEvent)
        """
        task_id = context.task_id
        context_id = context.context_id
        if not task_id or not context_id:
            raise ValueError("Task ID and Context ID are required")

        artifact_id = str(uuid.uuid4())

        async for chunk in stream:
            if not (hasattr(chunk, "event") and chunk.event is not None):
                continue

            payload = chunk.event.payload
            event_type = payload.event_type

            if event_type == "turn_awaiting_input":
                logger.debug("Turn awaiting input")
                # We don't have the accumulated text here easily if we rely on aggregator for that.
                # But ADK approach implies we send a message.
                # For now, we send an empty message or generic prompt,
                # relying on the aggregator to capture previous working messages if needed.
                # But wait, input_required needs a message.

                # In strict ADK loop, we'd rely on the last message.
                # Here we construct a new message.
                yield TaskStatusUpdateEvent(
                    task_id=task_id,
                    status=TaskStatus(
                        state=TaskState.input_required,
                        message=new_agent_text_message(
                            "",  # Text accumulated in aggregator or separate
                            context_id=context_id,
                            task_id=task_id,
                        ),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                    context_id=context_id,
                    final=False,  # Will be handled by aggregator/loop end
                )

            elif event_type == "turn_complete":
                logger.debug("Turn complete event")
                # Convert Llama Stack content to A2A parts
                output_message = chunk.event.payload.turn.output_message
                a2a_parts = _convert_llama_content_to_a2a_parts(output_message.content)
                yield TaskArtifactUpdateEvent(
                    task_id=task_id,
                    last_chunk=True,
                    context_id=context_id,
                    artifact=Artifact(
                        artifact_id=artifact_id,
                        parts=a2a_parts,
                        metadata={"conversation_id": str(conversation_id)},
                    ),
                )

            elif event_type == "step_progress":
                if hasattr(payload, "delta"):
                    delta = payload.delta
                    if delta.type == "text" and delta.text:
                        yield TaskStatusUpdateEvent(
                            task_id=task_id,
                            status=TaskStatus(
                                state=TaskState.working,
                                message=new_agent_text_message(
                                    delta.text,
                                    context_id=context_id,
                                    task_id=task_id,
                                ),
                                timestamp=datetime.now(timezone.utc).isoformat(),
                            ),
                            context_id=context_id,
                            final=False,
                        )
                    elif delta.type == "tool_call":
                        # Only emit status when tool call parsing is complete
                        if (
                            hasattr(delta, "parse_status")
                            and delta.parse_status == "succeeded"
                            and hasattr(delta.tool_call, "tool_name")
                        ):
                            tool_name = delta.tool_call.tool_name
                            logger.debug("Tool call completed: %s", tool_name)
                            yield TaskStatusUpdateEvent(
                                task_id=task_id,
                                status=TaskStatus(
                                    state=TaskState.working,
                                    message=new_agent_text_message(
                                        f"Calling tool: {tool_name}",
                                        context_id=context_id,
                                        task_id=task_id,
                                    ),
                                    timestamp=datetime.now(timezone.utc).isoformat(),
                                ),
                                context_id=context_id,
                                final=False,
                            )

    async def cancel(
        self,
        context: RequestContext,  # pylint: disable=unused-argument
        event_queue: EventQueue,  # pylint: disable=unused-argument
    ) -> None:
        """
        Handle task cancellation.

        Args:
            context: The request context
            event_queue: Queue for sending cancellation events

        Raises:
            NotImplementedError: Task cancellation is not currently supported
        """
        logger.info("Cancellation requested but not currently supported")
        raise NotImplementedError("Task cancellation not currently supported")


# -----------------------------
# Agent Card Configuration
# -----------------------------
def get_lightspeed_agent_card() -> AgentCard:
    """
    Generate the A2A Agent Card for Lightspeed.

    If agent_card_path is configured, loads the agent card from the YAML file.
    Otherwise, uses default hardcoded values.

    Returns:
        AgentCard: The agent card describing Lightspeed's capabilities.
    """
    # Get base URL from configuration or construct it
    service_config = configuration.service_configuration
    base_url = (
        service_config.base_url
        if service_config.base_url is not None
        else "http://localhost:8080"
    )

    if not configuration.customization:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Customization configuration not found",
        )

    if not configuration.customization.agent_card_config:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent card configuration not found",
        )

    config = configuration.customization.agent_card_config

    # Parse skills from config
    skills = [
        AgentSkill(
            id=skill.get("id"),
            name=skill.get("name"),
            description=skill.get("description"),
            tags=skill.get("tags", []),
            input_modes=skill.get("inputModes", []),
            output_modes=skill.get("outputModes", []),
            examples=skill.get("examples", []),
        )
        for skill in config.get("skills", [])
    ]

    # Parse provider from config
    provider_config = config.get("provider", {})
    provider = AgentProvider(
        organization=provider_config.get("organization", ""),
        url=provider_config.get("url", ""),
    )

    # Parse capabilities from config
    capabilities_config = config.get("capabilities", {})
    capabilities = AgentCapabilities(
        streaming=capabilities_config.get("streaming", True),
        push_notifications=capabilities_config.get("pushNotifications", False),
        state_transition_history=capabilities_config.get(
            "stateTransitionHistory", False
        ),
    )

    return AgentCard(
        name=config.get("name", "Lightspeed AI Assistant"),
        description=config.get("description", ""),
        version=__version__,
        url=f"{base_url}/a2a",
        documentation_url=f"{base_url}/docs",
        provider=provider,
        skills=skills,
        default_input_modes=config.get("defaultInputModes", ["text/plain"]),
        default_output_modes=config.get("defaultOutputModes", ["text/plain"]),
        capabilities=capabilities,
        protocol_version="0.2.1",
        security=config.get("security", [{"bearer": []}]),
        security_schemes=config.get("security_schemes", {}),
    )


# -----------------------------
# FastAPI Endpoints
# -----------------------------
@router.get("/.well-known/agent.json", response_model=AgentCard)
@router.get("/.well-known/agent-card.json", response_model=AgentCard)
async def get_agent_card(  # pylint: disable=unused-argument
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
) -> AgentCard:
    """
    Serve the A2A Agent Card at the well-known location.

    This endpoint provides the agent card that describes Lightspeed's
    capabilities according to the A2A protocol specification.

    Returns:
        AgentCard: The agent card describing this agent's capabilities.
    """
    try:
        logger.info("Serving A2A Agent Card")
        agent_card = get_lightspeed_agent_card()
        logger.info("Agent Card URL: %s", agent_card.url)
        logger.info(
            "Agent Card capabilities: streaming=%s", agent_card.capabilities.streaming
        )
        return agent_card
    except Exception as exc:
        logger.error("Error serving A2A Agent Card: %s", str(exc))
        raise


def _create_a2a_app(auth_token: str, mcp_headers: dict[str, dict[str, str]]) -> Any:
    """
    Create an A2A Starlette application instance with auth context.

    Args:
        auth_token: Authentication token for the request
        mcp_headers: MCP headers for context propagation

    Returns:
        A2A Starlette ASGI application
    """
    agent_executor = LightspeedAgentExecutor(
        auth_token=auth_token, mcp_headers=mcp_headers
    )

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=_TASK_STORE,
    )

    a2a_app = A2AStarletteApplication(
        agent_card=get_lightspeed_agent_card(),
        http_handler=request_handler,
    )

    return a2a_app.build()


@router.api_route("/a2a", methods=["GET", "POST"], response_model=None)
@authorize(Action.A2A_JSONRPC)
async def handle_a2a_jsonrpc(  # pylint: disable=too-many-locals,too-many-statements
    request: Request,
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> Response | StreamingResponse:
    """
    Handle A2A JSON-RPC requests following the A2A protocol specification.

    This endpoint uses the DefaultRequestHandler from the A2A SDK to handle
    all JSON-RPC requests including message/send, message/stream, etc.

    The A2A SDK application is created per-request to include authentication
    context while still leveraging FastAPI's authorization middleware.

    Automatically detects streaming requests (message/stream JSON-RPC method)
    and returns a StreamingResponse to enable real-time chunk delivery.

    Args:
        request: FastAPI request object
        auth: Authentication tuple
        mcp_headers: MCP headers for context propagation

    Returns:
        JSON-RPC response or streaming response
    """
    logger.debug("A2A endpoint called: %s %s", request.method, request.url.path)

    # Extract auth token from AuthTuple
    # AuthTuple format: (user_id, username, roles, token, ...)
    try:
        auth_token = auth[3] if len(auth) > 3 else ""
    except (IndexError, TypeError):
        logger.warning("Failed to extract auth token from auth tuple")
        auth_token = ""

    # Create A2A app with auth context
    a2a_app = _create_a2a_app(auth_token, mcp_headers)

    # Detect if this is a streaming request by checking the JSON-RPC method
    is_streaming_request = False
    body = b""
    try:
        # Read and parse the request body to check the method
        body = await request.body()
        logger.debug("A2A request body size: %d bytes", len(body))
        if body:
            try:
                rpc_request = json.loads(body)
                # Check if the method is message/stream
                method = rpc_request.get("method", "")
                is_streaming_request = method == "message/stream"
                logger.info(
                    "A2A request method: %s, streaming: %s",
                    method,
                    is_streaming_request,
                )
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(
                    "Could not parse A2A request body for method detection: %s", str(e)
                )
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Error detecting streaming request: %s", str(e))

    # Setup scope for A2A app
    scope = dict(request.scope)
    scope["path"] = "/"  # A2A app expects root path

    # We need to re-provide the body since we already read it
    body_sent = False

    async def receive() -> MutableMapping[str, Any]:
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        # After sending body once, delegate to original receive
        # This prevents infinite loops - the original receive() will block/disconnect properly
        return await request.receive()

    if is_streaming_request:
        # Streaming mode: Forward chunks to client as they arrive
        logger.info("Handling A2A streaming request")

        # Create queue for passing chunks from ASGI app to response generator
        chunk_queue: asyncio.Queue = asyncio.Queue()

        async def streaming_send(message: dict[str, Any]) -> None:
            """Send callback that queues chunks for streaming."""
            if message["type"] == "http.response.body":
                body_chunk = message.get("body", b"")
                if body_chunk:
                    await chunk_queue.put(body_chunk)
                # Signal end of stream if no more body
                if not message.get("more_body", False):
                    logger.debug("Streaming: End of stream signaled")
                    await chunk_queue.put(None)

        # Run the A2A app in a background task
        async def run_a2a_app() -> None:
            """Run A2A app and handle any errors."""
            try:
                logger.debug("Streaming: Starting A2A app execution")
                await a2a_app(scope, receive, streaming_send)
                logger.debug("Streaming: A2A app execution completed")
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "Error in A2A app during streaming: %s", str(exc), exc_info=True
                )
                await chunk_queue.put(None)  # Signal end even on error

        # Start the A2A app task
        app_task = asyncio.create_task(run_a2a_app())

        async def response_generator() -> AsyncIterator[bytes]:
            """Generate chunks from the queue for streaming response."""
            chunk_count = 0
            try:
                while True:
                    # Get chunk from queue with timeout to prevent hanging
                    try:
                        chunk = await asyncio.wait_for(chunk_queue.get(), timeout=300.0)
                    except asyncio.TimeoutError:
                        logger.error("Timeout waiting for chunk from A2A app")
                        break

                    if chunk is None:
                        # End of stream
                        logger.debug(
                            "Streaming: Stream ended after %d chunks", chunk_count
                        )
                        break
                    chunk_count += 1
                    logger.debug("Chunk sent to A2A client: %s", str(chunk))
                    yield chunk
            finally:
                # Ensure the app task is cleaned up
                if not app_task.done():
                    app_task.cancel()
                    try:
                        await app_task
                    except asyncio.CancelledError:
                        pass

        # Return streaming response immediately
        # The status code and headers will be determined by the first chunk
        # We can't wait for the response to start because that would cause a deadlock:
        # the ASGI app won't send data until the client starts consuming
        logger.debug("Streaming: Returning StreamingResponse")

        # Return streaming response with SSE content type for A2A protocol
        return StreamingResponse(
            response_generator(),
            media_type="text/event-stream",
        )

    # Non-streaming mode: Buffer entire response
    logger.info("Handling A2A non-streaming request")

    response_started = False
    response_body = []
    status_code = 200
    headers = []

    async def buffering_send(message: dict[str, Any]) -> None:
        nonlocal response_started, status_code, headers
        if message["type"] == "http.response.start":
            response_started = True
            status_code = message["status"]
            headers = message.get("headers", [])
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    await a2a_app(scope, receive, buffering_send)

    # Return the response from A2A app
    return Response(
        content=b"".join(response_body),
        status_code=status_code,
        headers=dict((k.decode(), v.decode()) for k, v in headers),
    )


@router.get("/a2a/health")
async def a2a_health_check() -> dict[str, str]:
    """
    Health check endpoint for A2A service.

    Returns:
        Dict with health status information.
    """
    return {
        "status": "healthy",
        "service": "lightspeed-a2a",
        "version": __version__,
        "a2a_sdk_version": "0.2.1",
        "timestamp": datetime.now().isoformat(),
    }
