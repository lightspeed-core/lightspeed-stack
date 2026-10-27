import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic_ai import AgentRunResult
from pydantic_ai.ui import SSE_CONTENT_TYPE

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from authorization.middleware import authorize
from client.ogx import AsyncOgxClientHolder
from configuration import AppConfig, configuration
from log import get_logger
from models.api.requests.agui import AGUIRunAgentInput
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES_WITH_MCP_OAUTH
from models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from models.api.responses.successful import StreamingQueryResponse
from models.config import Action
from utils.agui import (
    LightspeedAGUIAdapter,
    consume_token_usage,
    prepare_responses_params,
)
from utils.endpoints import (
    check_configuration_loaded,
)
from utils.mcp.mcp_headers import McpHeaders, mcp_headers_dependency
from utils.mcp.mcp_oauth_probe import check_mcp_auth
from utils.pydantic_ai_helpers import build_agent
from utils.query import validate_model_provider_override
from utils.quota_utils import check_tokens_available
from utils.types import Responses

logger = get_logger(__name__)
router = APIRouter(tags=["agui"])

agui_responses: Responses = {
    200: StreamingQueryResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=UNAUTHORIZED_OPENAPI_EXAMPLES_WITH_MCP_OAUTH
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "model override"]),
    404: NotFoundResponse.openapi_response(examples=["model", "provider"]),
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["OGX", "kubernetes api"]
    ),
}


# A tweak version of validate_shield_ids_override from src/utils/shields.py, instead of
# requiring a QueryRequest, we only need a list of shield id.
def _validate_shield_ids_override(
    shield_ids: list[str] | None,
    config: AppConfig,
) -> None:
    shield_ids_override_disabled = (
        config.customization is not None
        and config.customization.disable_shield_ids_override
    )
    if shield_ids_override_disabled and shield_ids is not None:
        response = UnprocessableEntityResponse(
            response="Shield IDs customization is disabled",
            cause=(
                "This instance does not support customizing shield IDs in the "
                "query request (disable_shield_ids_override is set). Please remove the "
                "shield_ids field from your request."
            ),
        )
        raise HTTPException(**response.model_dump())


@router.post(
    "/agui",
    response_class=StreamingResponse,
    responses=agui_responses,
    summary="AG-UI Streaming Query Endpoint Handler",
)
@authorize(Action.STREAMING_QUERY)
async def agui_endpoint_handler(
    request: Request,
    # We rely on FastAPI's standard request validation instead of AGUIAdapter.build_run_input() — this
    # gives us typed schema generation, consistent error handling (422 instead of silent data loss),
    # and aligns with how every other endpoint in the project works. Forward-compat shimming is
    # handled by keeping ag-ui-protocol up to date.
    run_input: AGUIRunAgentInput,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: McpHeaders = Depends(mcp_headers_dependency),
) -> StreamingResponse:
    """Handle AG-UI streaming query requests."""
    accept = request.headers.get("accept", SSE_CONTENT_TYPE)

    lsp = run_input.forwarded_props
    logger.info("-----AGUI-----")
    logger.info(run_input.model_dump_json(indent=2))

    check_configuration_loaded(configuration)

    user_id, _user_name, _skip_userid_check, token = auth
    started_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # TODO: OTEL span setup

    # Check MCP Auth
    await check_mcp_auth(configuration, mcp_headers, token, request.headers)

    # Check token availability
    check_tokens_available(configuration.quota_limiters, user_id)

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    validate_model_provider_override(
        lsp.model, lsp.provider, request.state.authorized_actions
    )

    _validate_shield_ids_override(lsp.shield_ids, configuration)

    # TODO: OTEL event for validation completion

    client = AsyncOgxClientHolder().get_client()

    responses_params = await prepare_responses_params(
        client=client,
        agui_forwarded_props=lsp,
        user_conversation=None,
        token=token,
        mcp_headers=mcp_headers,
        stream=True,
        store=False,
        request_headers=request.headers,
    )

    # Handle Azure token refresh if needed
    if (
        responses_params.model.startswith("azure")
        and AzureEntraIDManager().is_entra_id_configured
        and AzureEntraIDManager().is_token_expired
        and AzureEntraIDManager().refresh_token()
    ):
        client = await AsyncOgxClientHolder().update_azure_token()

    # TODO: Compaction?
    # TODO: Inline RAG?
    # TODO: Check the if we still need metric here

    agent = build_agent(
        client,
        responses_params,
        configuration,
        shields=lsp.shield_ids,
        no_tools=bool(lsp.no_tools),
    )

    adapter = LightspeedAGUIAdapter(agent=agent, run_input=run_input, accept=accept)

    # This might be the main way we collect everything after an AGUI streaming
    def record_run_result(run_result: AgentRunResult):
        consume_token_usage(run_result.usage, user_id, responses_params.model)

    event_stream = adapter.run_stream(on_complete=record_run_result)
    sse_event_stream = adapter.encode_stream(event_stream)
    return StreamingResponse(sse_event_stream, media_type=accept)
