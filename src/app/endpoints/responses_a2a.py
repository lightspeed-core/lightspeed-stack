"""Handler for A2A (Agent-to-Agent) protocol endpoints using Responses API."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, AsyncIterator, MutableMapping

from fastapi import APIRouter, Depends, Request
from llama_stack.apis.agents.openai_responses import (
    OpenAIResponseObjectStream,
)
from starlette.responses import Response, StreamingResponse

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
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.server.apps import A2AStarletteApplication
from a2a.utils import new_agent_text_message, new_task

from authentication.interface import AuthTuple
from authentication import get_auth_dependency
from authorization.middleware import authorize
from models.config import Action
from models.requests import QueryRequest
from app.endpoints.a2a import (
    get_lightspeed_agent_card,
    TaskResultAggregator,
    _TASK_STORE,
)
from app.endpoints.query import (
    select_model_and_provider_id,
    evaluate_model_hints,
)
from app.endpoints.streaming_query_v2 import (
    retrieve_response as retrieve_responses_api_response,
)
from client import AsyncLlamaStackClientHolder
from utils.mcp_headers import mcp_headers_dependency
from utils.responses import extract_text_from_response_output_item
from version import __version__

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["responses_a2a"])

auth_dependency = get_auth_dependency()

# Map A2A contextId -> Responses API conversation_id (response.id) for multi-turn
_CONTEXT_TO_RESPONSE_ID: dict[str, str] = {}


def _convert_responses_content_to_a2a_parts(output: list[Any]) -> list[Part]:
    """Convert Responses API output to A2A Parts.

    Args:
        output: List of Responses API output items

    Returns:
        List of A2A Part objects
    """
    parts: list[Part] = []

    for output_item in output:
        text = extract_text_from_response_output_item(output_item)
        if text:
            parts.append(Part(root=TextPart(text=text)))

    return parts


class ResponsesAgentExecutor(AgentExecutor):
    """Agent Executor for A2A using Llama Stack Responses API.

    This executor implements the A2A AgentExecutor interface and handles
    routing queries to the LLM backend using the Responses API instead
    of the Agent API.
    """

    def __init__(
        self, auth_token: str, mcp_headers: dict[str, dict[str, str]] | None = None
    ):
        """Initialize the Responses agent executor.

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
        """Execute the agent with the given context and send results to the event queue.

        Args:
            context: The request context containing user input and metadata
            event_queue: Queue for sending response events
        """
        if not context.message:
            raise ValueError("A2A request must have a message")

        task_id = context.task_id or ""
        context_id = context.context_id or ""
        # for new task, create a task submitted event
        if not context.current_task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
            task_id = task.id
            context_id = task.context_id
        task_updater = TaskUpdater(event_queue, task_id, context_id)

        # Process the task with streaming
        try:
            await self._process_task_streaming(context, task_updater)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error handling A2A request: %s", e, exc_info=True)
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

    async def _process_task_streaming(  # pylint: disable=too-many-locals
        self,
        context: RequestContext,
        task_updater: TaskUpdater,
    ) -> None:
        """Process the task with streaming updates using Responses API.

        Args:
            context: The request context
            task_updater: Task updater for sending events
        """
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
        logger.info("Processing A2A request (Responses API): %s", preview)

        # Extract routing metadata from context
        metadata = context.message.metadata if context.message else {}
        model = metadata.get("model") if metadata else None
        provider = metadata.get("provider") if metadata else None

        # Resolve previous_response_id from A2A contextId for multi-turn
        a2a_context_id = context_id
        previous_response_id = _CONTEXT_TO_RESPONSE_ID.get(a2a_context_id)
        logger.info(
            "A2A contextId %s maps to previous_response_id %s",
            a2a_context_id,
            previous_response_id,
        )

        # Build internal query request
        query_request = QueryRequest(
            query=user_input,
            conversation_id=previous_response_id,
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

        # Stream response from LLM using the shared retrieve_response function
        stream, response_id = await retrieve_responses_api_response(
            client,
            llama_stack_model_id,
            query_request,
            self.auth_token,
            mcp_headers=self.mcp_headers,
        )

        # Persist response_id for next turn in same A2A context
        if response_id:
            _CONTEXT_TO_RESPONSE_ID[a2a_context_id] = response_id
            logger.info(
                "Persisted response_id %s for A2A contextId %s",
                response_id,
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
                    "response_id": response_id or "",
                },
            )
        )

        # Process stream using generator and aggregator pattern
        async for a2a_event in self._convert_stream_to_events(
            stream, context, response_id
        ):
            aggregator.process_event(a2a_event)
            await event_queue.enqueue_event(a2a_event)

        # Publish the final task result event
        if aggregator.task_state == TaskState.working:
            await task_updater.update_status(
                TaskState.completed,
                timestamp=datetime.now(timezone.utc).isoformat(),
                final=True,
            )
        else:
            await task_updater.update_status(
                aggregator.task_state,
                message=aggregator.task_status_message,
                timestamp=datetime.now(timezone.utc).isoformat(),
                final=True,
            )

    async def _convert_stream_to_events(  # pylint: disable=too-many-branches,too-many-locals
        self,
        stream: AsyncIterator[OpenAIResponseObjectStream],
        context: RequestContext,
        response_id: str | None,
    ) -> AsyncIterator[Any]:
        """Convert Responses API stream chunks to A2A events.

        Args:
            stream: The Responses API response stream
            context: The request context
            response_id: The response ID (may be updated from stream)

        Yields:
            A2A events (TaskStatusUpdateEvent or TaskArtifactUpdateEvent)
        """
        task_id = context.task_id
        context_id = context.context_id
        if not task_id or not context_id:
            raise ValueError("Task ID and Context ID are required")

        artifact_id = str(uuid.uuid4())
        text_parts: list[str] = []
        current_response_id = response_id

        async for chunk in stream:
            event_type = getattr(chunk, "type", None)

            # Extract response ID from response.created
            if event_type == "response.created":
                try:
                    current_response_id = getattr(chunk, "response").id
                    # Update the context mapping with the actual response ID
                    if current_response_id and context_id:
                        _CONTEXT_TO_RESPONSE_ID[context_id] = current_response_id
                except Exception:  # pylint: disable=broad-except
                    logger.warning("Missing response id in response.created")
                continue

            # Text streaming - emit as working status with text delta
            if event_type == "response.output_text.delta":
                delta = getattr(chunk, "delta", "")
                if delta:
                    text_parts.append(delta)
                    yield TaskStatusUpdateEvent(
                        task_id=task_id,
                        status=TaskStatus(
                            state=TaskState.working,
                            message=new_agent_text_message(
                                delta,
                                context_id=context_id,
                                task_id=task_id,
                            ),
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        ),
                        context_id=context_id,
                        final=False,
                    )

            # Tool call events
            elif event_type == "response.function_call_arguments.done":
                item_id = getattr(chunk, "item_id", "")
                yield TaskStatusUpdateEvent(
                    task_id=task_id,
                    status=TaskStatus(
                        state=TaskState.working,
                        message=new_agent_text_message(
                            f"Tool call: {item_id}",
                            context_id=context_id,
                            task_id=task_id,
                        ),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                    context_id=context_id,
                    final=False,
                )

            # MCP call completion
            elif event_type == "response.mcp_call.arguments.done":
                item_id = getattr(chunk, "item_id", "")
                yield TaskStatusUpdateEvent(
                    task_id=task_id,
                    status=TaskStatus(
                        state=TaskState.working,
                        message=new_agent_text_message(
                            f"MCP call: {item_id}",
                            context_id=context_id,
                            task_id=task_id,
                        ),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                    context_id=context_id,
                    final=False,
                )

            # Response completed - emit final artifact
            elif event_type == "response.completed":
                response_obj = getattr(chunk, "response", None)
                final_text = "".join(text_parts)

                if response_obj:
                    output = getattr(response_obj, "output", [])
                    a2a_parts = _convert_responses_content_to_a2a_parts(output)
                    if not a2a_parts and final_text:
                        a2a_parts = [Part(root=TextPart(text=final_text))]
                else:
                    a2a_parts = (
                        [Part(root=TextPart(text=final_text))] if final_text else []
                    )

                yield TaskArtifactUpdateEvent(
                    task_id=task_id,
                    last_chunk=True,
                    context_id=context_id,
                    artifact=Artifact(
                        artifact_id=artifact_id,
                        parts=a2a_parts,
                        metadata={"response_id": str(current_response_id or "")},
                    ),
                )

    async def cancel(
        self,
        context: RequestContext,  # pylint: disable=unused-argument
        event_queue: EventQueue,  # pylint: disable=unused-argument
    ) -> None:
        """Handle task cancellation.

        Args:
            context: The request context
            event_queue: Queue for sending cancellation events

        Raises:
            NotImplementedError: Task cancellation is not currently supported
        """
        logger.info("Cancellation requested but not currently supported")
        raise NotImplementedError("Task cancellation not currently supported")


def get_responses_agent_card() -> AgentCard:
    """Get the agent card for the Responses A2A endpoint.

    Returns:
        AgentCard with URL pointing to /responses/a2a endpoint
    """
    agent_card = get_lightspeed_agent_card()
    # Update the URL to point to the responses endpoint
    agent_card.url = agent_card.url.replace("/a2a", "/responses/a2a")
    return agent_card


def _create_responses_a2a_app(
    auth_token: str, mcp_headers: dict[str, dict[str, str]]
) -> Any:
    """Create an A2A Starlette application instance with Responses API backend.

    Args:
        auth_token: Authentication token for the request
        mcp_headers: MCP headers for context propagation

    Returns:
        A2A Starlette ASGI application
    """
    agent_executor = ResponsesAgentExecutor(
        auth_token=auth_token, mcp_headers=mcp_headers
    )

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=_TASK_STORE,
    )

    a2a_app = A2AStarletteApplication(
        agent_card=get_responses_agent_card(),
        http_handler=request_handler,
    )

    return a2a_app.build()


@router.api_route("/responses/a2a", methods=["GET", "POST"], response_model=None)
@authorize(Action.A2A_JSONRPC)
async def handle_responses_a2a_jsonrpc(  # pylint: disable=too-many-locals,too-many-statements
    request: Request,
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> Response | StreamingResponse:
    """Handle A2A JSON-RPC requests following the A2A protocol specification, using Responses API.

    This endpoint uses the DefaultRequestHandler from the A2A SDK to handle
    all JSON-RPC requests including message/send, message/stream, etc.
    It uses the Responses API instead of the Agent API for LLM interactions.

    Args:
        request: FastAPI request object
        auth: Authentication tuple
        mcp_headers: MCP headers for context propagation

    Returns:
        JSON-RPC response or streaming response
    """
    logger.debug(
        "Responses A2A endpoint called: %s %s", request.method, request.url.path
    )

    try:
        auth_token = auth[3] if len(auth) > 3 else ""
    except (IndexError, TypeError):
        logger.warning("Failed to extract auth token from auth tuple")
        auth_token = ""

    # Create A2A app with Responses API backend
    a2a_app = _create_responses_a2a_app(auth_token, mcp_headers)

    # Detect if this is a streaming request
    is_streaming_request = False
    body = b""
    try:
        body = await request.body()
        logger.debug("A2A request body size: %d bytes", len(body))
        if body:
            try:
                rpc_request = json.loads(body)
                method = rpc_request.get("method", "")
                is_streaming_request = method == "message/stream"
                logger.info(
                    "Responses A2A request method: %s, streaming: %s",
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
    scope["path"] = "/"

    body_sent = False

    async def receive() -> MutableMapping[str, Any]:
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await request.receive()

    if is_streaming_request:
        logger.info("Handling Responses A2A streaming request")
        chunk_queue: asyncio.Queue = asyncio.Queue()

        async def streaming_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.body":
                body_chunk = message.get("body", b"")
                if body_chunk:
                    await chunk_queue.put(body_chunk)
                if not message.get("more_body", False):
                    logger.debug("Streaming: End of stream signaled")
                    await chunk_queue.put(None)

        async def run_a2a_app() -> None:
            try:
                logger.debug("Streaming: Starting Responses A2A app execution")
                await a2a_app(scope, receive, streaming_send)
                logger.debug("Streaming: Responses A2A app execution completed")
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "Error in Responses A2A app during streaming: %s",
                    str(exc),
                    exc_info=True,
                )
                await chunk_queue.put(None)

        app_task = asyncio.create_task(run_a2a_app())

        async def response_generator() -> AsyncIterator[bytes]:
            """Generate chunks from the queue for streaming response."""
            chunk_count = 0
            try:
                while True:
                    try:
                        chunk = await asyncio.wait_for(chunk_queue.get(), timeout=300.0)
                    except asyncio.TimeoutError:
                        logger.error("Timeout waiting for chunk from Responses A2A app")
                        break

                    if chunk is None:
                        logger.debug(
                            "Streaming: Stream ended after %d chunks", chunk_count
                        )
                        break
                    chunk_count += 1
                    logger.debug("Chunk sent to A2A client: %s", str(chunk))
                    yield chunk
            finally:
                if not app_task.done():
                    app_task.cancel()
                    try:
                        await app_task
                    except asyncio.CancelledError:
                        pass

        logger.debug("Streaming: Returning StreamingResponse")
        return StreamingResponse(
            response_generator(),
            media_type="text/event-stream",
        )

    # Non-streaming mode
    logger.info("Handling Responses A2A non-streaming request")

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

    return Response(
        content=b"".join(response_body),
        status_code=status_code,
        headers=dict((k.decode(), v.decode()) for k, v in headers),
    )


@router.get("/responses/.well-known/agent.json", response_model=AgentCard)
@router.get("/responses/.well-known/agent-card.json", response_model=AgentCard)
async def get_responses_agent_card_endpoint(  # pylint: disable=unused-argument
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
) -> AgentCard:
    """Serve the A2A Agent Card for the Responses API endpoint.

    This endpoint provides the agent card that describes Lightspeed's
    capabilities when using the Responses API backend.

    Returns:
        AgentCard: The agent card describing this agent's capabilities.
    """
    try:
        logger.info("Serving Responses A2A Agent Card")
        agent_card = get_responses_agent_card()
        logger.info("Responses Agent Card URL: %s", agent_card.url)
        return agent_card
    except Exception as exc:
        logger.error("Error serving Responses A2A Agent Card: %s", str(exc))
        raise


@router.get("/responses/a2a/health")
async def responses_a2a_health_check() -> dict[str, str]:
    """Health check endpoint for Responses A2A service.

    Returns:
        Dict with health status information.
    """
    return {
        "status": "healthy",
        "service": "lightspeed-responses-a2a",
        "version": __version__,
        "a2a_sdk_version": "0.2.1",
        "api_type": "responses",
        "timestamp": datetime.now().isoformat(),
    }
