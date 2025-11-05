"""Handler for A2A (Agent-to-Agent) protocol endpoints."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response, StreamingResponse

from a2a.types import (
    AgentCard,
    AgentSkill,
    AgentProvider,
    AgentCapabilities,
    Task,
    TaskState,
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
        self.auth_token = auth_token
        self.mcp_headers = mcp_headers or {}

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
        task = await self._prepare_task(context, event_queue)

        # Process the task with streaming
        await self._process_task_streaming(
            context, event_queue, task.context_id, task.id
        )

    async def _prepare_task(
        self, context: RequestContext, event_queue: EventQueue
    ) -> Task:
        """
        Get existing task or create a new one.

        Args:
            context: The request context
            event_queue: Queue for sending events

        Returns:
            Task object
        """
        task = context.current_task
        if not task:
            if not context.message:
                raise ValueError("No message provided in context")
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        return task

    async def _process_task_streaming(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self,
        context: RequestContext,
        event_queue: EventQueue,
        context_id: str,
        task_id: str,
    ) -> None:
        """
        Process the task with streaming updates.

        Args:
            context: The request context
            event_queue: Queue for sending events
            context_id: Context ID for the task
            task_id: Task ID
        """
        task_updater = TaskUpdater(event_queue, task_id, context_id)

        try:
            # Extract user input using SDK utility
            user_input = context.get_user_input()
            if not user_input:
                await task_updater.update_status(
                    TaskState.input_required,
                    message=new_agent_text_message(
                        "I didn't receive any input. "
                        "How can I help you with OpenShift installation?",
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
            )

            # Get LLM client and select model
            client = AsyncLlamaStackClientHolder().get_client()
            llama_stack_model_id, _model_id, _provider_id = (
                select_model_and_provider_id(
                    await client.models.list(),
                    *evaluate_model_hints(
                        user_conversation=None, query_request=query_request
                    ),
                )
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

            # Stream incremental updates: emit working status with text deltas.
            # Terminal conditions:
            #   - turn_awaiting_input -> TaskState.input_required with accumulated text
            #   - turn_complete -> TaskState.completed (final), leverage contextId for follow-ups
            final_event_sent = False
            accumulated_text_chunks: list[str] = []
            streamed_any_delta = False

            async for chunk in stream:
                # Extract text from chunk - llama-stack structure
                if hasattr(chunk, "event") and chunk.event is not None:
                    payload = chunk.event.payload
                    event_type = payload.event_type

                    # Handle turn_awaiting_input - request more input with accumulated text
                    if event_type == "turn_awaiting_input":
                        try:
                            final_text = (
                                ""
                                if streamed_any_delta
                                else "".join(accumulated_text_chunks)
                            )
                            await task_updater.update_status(
                                TaskState.input_required,
                                message=new_agent_text_message(
                                    final_text,
                                    context_id=context_id,
                                    task_id=task_id,
                                ),
                                final=True,
                            )
                            final_event_sent = True
                            logger.info("Input required for task %s", task_id)
                        except Exception:  # pylint: disable=broad-except
                            logger.debug(
                                "Error sending input_required status", exc_info=True
                            )
                            # End the stream for this turn after requesting input
                            break

                    # Handle turn_complete - complete the task for this turn
                    elif event_type == "turn_complete":
                        try:
                            final_text = (
                                ""
                                if streamed_any_delta
                                else "".join(accumulated_text_chunks)
                            )
                            await task_updater.update_status(
                                TaskState.completed,
                                message=new_agent_text_message(
                                    final_text,
                                    context_id=context_id,
                                    task_id=task_id,
                                ),
                                final=True,
                            )
                            final_event_sent = True
                        except Exception:  # pylint: disable=broad-except
                            logger.debug(
                                "Error sending completed on turn_complete",
                                exc_info=True,
                            )
                        logger.info("Turn completed for task %s", task_id)
                        # End the stream for this turn
                        break

                    # Handle streaming inference tokens
                    elif event_type == "step_progress":
                        if hasattr(payload, "delta") and payload.delta.type == "text":
                            delta_text = payload.delta.text
                            if delta_text:
                                accumulated_text_chunks.append(delta_text)
                                await task_updater.update_status(
                                    TaskState.working,
                                    message=new_agent_text_message(
                                        delta_text,
                                        context_id=context_id,
                                        task_id=task_id,
                                    ),
                                )
                                streamed_any_delta = True

            # Ensure exactly one terminal status per turn
            if not final_event_sent:
                try:
                    final_text = (
                        "" if streamed_any_delta else "".join(accumulated_text_chunks)
                    )
                    await task_updater.update_status(
                        TaskState.completed,
                        message=new_agent_text_message(
                            final_text,
                            context_id=context_id,
                            task_id=task_id,
                        ),
                        final=True,
                    )
                except Exception:  # pylint: disable=broad-except
                    logger.debug(
                        "Error sending fallback completed status", exc_info=True
                    )

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error executing agent: %s", str(exc), exc_info=True)
            await task_updater.update_status(
                TaskState.failed,
                message=new_agent_text_message(
                    f"Sorry, I encountered an error: {str(exc)}",
                    context_id=context_id,
                    task_id=task_id,
                ),
                final=True,
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
    base_url = service_config.base_url if service_config.base_url is not None else "http://localhost:8080"

    # Check if agent card is configured via file
    if (
        configuration.customization is not None
        and configuration.customization.agent_card_config is not None
    ):
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

    # Fallback to default hardcoded agent card
    logger.info("Using default hardcoded agent card (no agent_card_path configured)")

    # Define Lightspeed's skills for OpenShift cluster installation
    skills = [
        AgentSkill(
            id="cluster_installation_guidance",
            name="Cluster Installation Guidance",
            description=(
                "Provide guidance and assistance for OpenShift cluster "
                "installation using assisted-installer"
            ),
            tags=["openshift", "installation", "assisted-installer"],
            input_modes=["text/plain", "application/json"],
            output_modes=["text/plain", "application/json"],
            examples=[
                "How do I install OpenShift using assisted-installer?",
                "What are the prerequisites for OpenShift installation?",
            ],
        ),
        AgentSkill(
            id="cluster_configuration_validation",
            name="Cluster Configuration Validation",
            description=(
                "Validate and provide recommendations for OpenShift "
                "cluster configuration parameters"
            ),
            tags=["openshift", "configuration", "validation"],
            input_modes=["application/json", "text/plain"],
            output_modes=["application/json", "text/plain"],
            examples=[
                "Validate my cluster configuration",
                "Check if my OpenShift setup meets requirements",
            ],
        ),
        AgentSkill(
            id="installation_troubleshooting",
            name="Installation Troubleshooting",
            description=(
                "Help troubleshoot OpenShift cluster installation issues "
                "and provide solutions"
            ),
            tags=["openshift", "troubleshooting", "support"],
            input_modes=["text/plain", "application/json"],
            output_modes=["text/plain", "application/json"],
            examples=[
                "My cluster installation is failing",
                "How do I fix installation errors?",
            ],
        ),
        AgentSkill(
            id="cluster_requirements_analysis",
            name="Cluster Requirements Analysis",
            description=(
                "Analyze infrastructure requirements for "
                "OpenShift cluster deployment"
            ),
            tags=["openshift", "requirements", "planning"],
            input_modes=["application/json", "text/plain"],
            output_modes=["application/json", "text/plain"],
            examples=[
                "What hardware do I need for OpenShift?",
                "Analyze requirements for a 5-node cluster",
            ],
        ),
    ]

    # Provider information
    provider = AgentProvider(organization="Red Hat", url="https://redhat.com")

    # Agent capabilities
    capabilities = AgentCapabilities(
        streaming=True, push_notifications=False, state_transition_history=False
    )

    return AgentCard(
        name="OpenShift Assisted Installer AI Assistant",
        description=(
            "AI-powered assistant specialized in OpenShift cluster "
            "installation, configuration, and troubleshooting using "
            "assisted-installer backend"
        ),
        version=__version__,
        url=f"{base_url}/a2a",
        documentation_url=f"{base_url}/docs",
        provider=provider,
        skills=skills,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=capabilities,
        protocol_version="0.2.1",
        security=[{"bearer": []}],
        security_schemes={},
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
    Main A2A JSON-RPC endpoint following the A2A protocol specification.

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
    scope = request.scope.copy()
    scope["path"] = "/"  # A2A app expects root path

    # We need to re-provide the body since we already read it
    body_sent = False

    async def receive():
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

        async def response_generator() -> Any:
            """Generator that yields chunks from the queue."""
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
