# pylint: disable=redefined-outer-name, too-many-locals, too-many-lines
"""Unit tests for the /responses REST API endpoint (LCORE Responses API)."""

import json
from datetime import UTC, datetime
from typing import Any, Optional, cast

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api import OpenAIResponseObject
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolChoiceMode as ToolChoiceMode,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolMCP as InputToolMCP,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseMessage,
)
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient
from pytest_mock import MockerFixture

from app.endpoints.responses import (
    _is_server_mcp_output_item,
    _sanitize_response_dict,
    _should_filter_mcp_chunk,
    handle_non_streaming_response,
    handle_streaming_response,
    responses_endpoint_handler,
)
from configuration import AppConfig
from constants import DEFAULT_SYSTEM_PROMPT, SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.responses_context import ResponsesContext
from models.config import Action, ModelContextProtocolServer
from models.database.conversations import UserConversation
from models.requests import ResponsesRequest
from models.responses import ResponsesResponse
from utils.types import (
    RAGContext,
    ResponsesConversationContext,
    ShieldModerationBlocked,
    ShieldModerationPassed,
    TurnSummary,
)

MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)
VALID_CONV_ID = "conv_e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c"
VALID_CONV_ID_NORMALIZED = "e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c"
MODULE = "app.endpoints.responses"
ENDPOINTS_MODULE = "utils.endpoints"
UTILS_RESPONSES_MODULE = "utils.responses"
MODEL = "google-vertex/publishers/google/models/gemini-2.5-flash"
SERVER_INSTRUCTIONS = "Server instructions"


def build_api_params_and_context(  # pylint: disable=too-many-arguments
    *,
    updated_request: ResponsesRequest,
    client: Any,
    auth: tuple[str, str, bool, str],
    input_text: str,
    started_at: datetime,
    moderation_result: Any,
    inline_rag_context: RAGContext,
    background_tasks: Any = None,
    rh_identity_context: tuple[str, str] = ("", ""),
    filter_server_tools: bool = False,
    generate_topic_summary: bool = False,
    endpoint_path: str = "/responses",
    user_agent: Optional[str] = None,
) -> tuple[ResponsesApiParams, ResponsesContext]:
    """Build api_params/context for direct helper invocation tests."""
    api_params = ResponsesApiParams.model_validate(updated_request.model_dump())
    context = ResponsesContext.model_construct(
        client=client,
        auth=auth,
        input_text=input_text,
        started_at=started_at,
        moderation_result=moderation_result,
        inline_rag_context=inline_rag_context,
        filter_server_tools=filter_server_tools,
        background_tasks=background_tasks,
        rh_identity_context=rh_identity_context,
        generate_topic_summary=generate_topic_summary,
        endpoint_path=endpoint_path,
        user_agent=user_agent,
    )
    return api_params, context


def test_responses_api_params_preserves_mcp_authorization() -> None:
    """After model_validate, MCP tool authorization from model_dump is kept on api_params.tools."""
    token = "secret-token"
    req = ResponsesRequest(
        input="x",
        model=MODEL,
        conversation=VALID_CONV_ID,
        tools=[
            InputToolMCP(
                server_label="alpha",
                server_url="http://alpha",
                require_approval="never",
                authorization=token,
            )
        ],
    )
    api = ResponsesApiParams.model_validate(req.model_dump())
    assert api.tools is not None and api.tools[0].authorization == token


def _patch_base(mocker: MockerFixture, config: AppConfig) -> None:
    """Patch configuration and mandatory checks for responses endpoint."""
    mocker.patch(f"{MODULE}.configuration", config)
    mocker.patch(f"{MODULE}.check_configuration_loaded")
    mocker.patch(f"{MODULE}.check_tokens_available")
    mocker.patch(f"{MODULE}.validate_model_provider_override")
    mock_holder = mocker.Mock()
    mock_holder.get_client.return_value = mocker.Mock()
    mocker.patch(
        f"{UTILS_RESPONSES_MODULE}.AsyncLlamaStackClientHolder",
        return_value=mock_holder,
    )
    mocker.patch(
        f"{UTILS_RESPONSES_MODULE}.prepare_tools",
        new=mocker.AsyncMock(return_value=None),
    )


def _patch_client(mocker: MockerFixture) -> Any:
    """Patch AsyncLlamaStackClientHolder; return (mock_client, mock_holder)."""
    mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.list = mocker.AsyncMock(return_value=mocker.Mock(data=[]))
    mock_client.vector_stores = mock_vector_stores
    mock_holder = mocker.Mock()
    mock_holder.get_client.return_value = mock_client
    mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)
    return mock_client, mock_holder


def _patch_resolve_response_context(
    mocker: MockerFixture,
    *,
    conversation: str = "conv_new",
    user_conversation: Optional[UserConversation] = None,
    generate_topic_summary: bool = False,
) -> None:
    """Patch resolve_response_context to return the given conversation context."""
    mocker.patch(
        f"{MODULE}.resolve_response_context",
        new=mocker.AsyncMock(
            return_value=ResponsesConversationContext(
                conversation=conversation,
                user_conversation=user_conversation,
                generate_topic_summary=generate_topic_summary,
            )
        ),
    )


def _patch_rag(
    mocker: MockerFixture,
    *,
    rag_context: str = "",
) -> None:
    """Patch RAG for responses endpoint by mocking build_rag_context."""
    mocker.patch(
        f"{MODULE}.build_rag_context",
        new=mocker.AsyncMock(
            return_value=RAGContext(
                context_text=rag_context,
                referenced_documents=[],
            ),
        ),
    )


def _patch_moderation(mocker: MockerFixture, decision: str = "passed") -> Any:
    """Patch run_shield_moderation; return typed moderation result."""
    if decision == "blocked":
        moderation_result = ShieldModerationBlocked(
            message="Content blocked",
            moderation_id="mod_blocked",
            refusal_response=OpenAIResponseMessage(
                role="assistant",
                content="Content blocked",
                type="message",
            ),
        )
    else:
        moderation_result = ShieldModerationPassed()
    mocker.patch(
        f"{MODULE}.run_shield_moderation",
        new=mocker.AsyncMock(return_value=moderation_result),
    )
    return moderation_result


def _make_responses_response(
    *,
    output_text: str = "",
    conversation: str = "",
    model: str = "provider/model1",
    **kwargs: Any,
) -> ResponsesResponse:
    """Build a minimal valid ResponsesResponse for tests."""
    defaults = {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": model,
        "output": [],
        "conversation": conversation,
        "completed_at": 0,
        "output_text": output_text,
        "available_quotas": {},
    }
    defaults.update(kwargs)
    return ResponsesResponse(**defaults)


def _patch_handle_non_streaming_common(
    mocker: MockerFixture, config: AppConfig
) -> None:
    """Patch deps used by handle_non_streaming_response (blocked and success)."""
    mocker.patch(f"{MODULE}.configuration", config)
    mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
    mocker.patch(
        f"{MODULE}.get_topic_summary",
        new=mocker.AsyncMock(return_value=None),
    )
    mocker.patch(f"{MODULE}.store_query_results")


@pytest.fixture(name="dummy_request")
def dummy_request_fixture() -> Request:
    """Minimal FastAPI Request with authorized_actions for responses endpoint."""
    req = Request(scope={"type": "http", "headers": []})
    req.state.authorized_actions = {Action.RESPONSES, Action.READ_OTHERS_CONVERSATIONS}
    return req


@pytest.fixture(name="minimal_config")
def minimal_config_fixture() -> AppConfig:
    """Minimal AppConfig for responses endpoint tests."""
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "test-key",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "authorization": {"access_rules": []},
        }
    )
    return cfg


def _request_with_model_and_conv(
    input_text: str = "Hello", model: str = "provider/model1"
) -> ResponsesRequest:
    """Build request with model and conversation set (as handler does)."""
    return ResponsesRequest(
        input=input_text,
        model=model,
        conversation=VALID_CONV_ID,
    )


def _request_with_previous_response_id(
    input_text: str = "Hello",
    model: str = "provider/model1",
    previous_response_id: str = "resp_prev_123",
    store: bool = True,
) -> ResponsesRequest:
    """Build request with previous_response_id (conversation set by handler)."""
    request = ResponsesRequest(
        input=input_text,
        model=model,
        previous_response_id=previous_response_id,
        store=store,
    )
    request.conversation = VALID_CONV_ID
    return request


class TestResponsesEndpointHandler:
    """Unit tests for responses_endpoint_handler."""

    @pytest.mark.asyncio
    async def test_successful_responses_string_input_non_streaming(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test successful responses request with string input returns ResponsesResponse."""
        responses_request = ResponsesRequest(input="What is Kubernetes?")
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker, conversation="conv_new_123")
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")

        mock_response = _make_responses_response(
            output_text="Kubernetes is a container orchestration platform.",
            conversation="conv_new_123",
        )
        mocker.patch(
            f"{MODULE}.handle_non_streaming_response",
            new=mocker.AsyncMock(return_value=mock_response),
        )

        response = await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )
        assert isinstance(response, ResponsesResponse)
        assert (
            response.output_text == "Kubernetes is a container orchestration platform."
        )
        assert response.conversation == "conv_new_123"

    @pytest.mark.asyncio
    async def test_responses_with_conversation_validates_and_retrieves(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that providing conversation ID calls validate_and_retrieve_conversation."""
        responses_request = ResponsesRequest(
            input="Follow-up question",
            conversation=VALID_CONV_ID,
        )
        _patch_base(mocker, minimal_config)
        mock_user_conv = mocker.Mock(spec=UserConversation)
        mock_user_conv.id = VALID_CONV_ID_NORMALIZED
        mock_validate = mocker.patch(
            f"{ENDPOINTS_MODULE}.validate_and_retrieve_conversation",
            return_value=mock_user_conv,
        )
        _, mock_holder = _patch_client(mocker)
        mocker.patch(
            f"{ENDPOINTS_MODULE}.AsyncLlamaStackClientHolder",
            return_value=mock_holder,
        )
        mocker.patch(
            f"{ENDPOINTS_MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(
            f"{ENDPOINTS_MODULE}.to_llama_stack_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")
        mocker.patch(
            f"{MODULE}.handle_non_streaming_response",
            new=mocker.AsyncMock(
                return_value=_make_responses_response(
                    output_text="Answer",
                    conversation=VALID_CONV_ID_NORMALIZED,
                )
            ),
        )

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_responses_model_not_configured_raises_404(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that unconfigured model leads to 404 HTTPException."""
        responses_request = ResponsesRequest(input="Hello", model="provider/unknown")
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker)
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/unknown"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=False),
        )
        mocker.patch(
            f"{MODULE}.extract_provider_and_model_from_model_id",
            return_value=("provider", "unknown"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await responses_endpoint_handler(
                request=dummy_request,
                responses_request=responses_request,
                auth=MOCK_AUTH,
                mcp_headers={},
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_responses_streaming_returns_streaming_response(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that stream=True delegates to handle_streaming_response."""
        responses_request = ResponsesRequest(input="Stream this", stream=True)
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker)
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")
        mock_streaming = mocker.Mock(spec=StreamingResponse)
        mocker.patch(
            f"{MODULE}.handle_streaming_response",
            new=mocker.AsyncMock(return_value=mock_streaming),
        )

        response = await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )
        assert response is mock_streaming

    @pytest.mark.asyncio
    async def test_responses_azure_token_refresh(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that Azure token refresh is called when model starts with azure."""
        responses_request = ResponsesRequest(input="Hi", model="azure/some-model")
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker)
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="azure/some-model"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        mock_azure = mocker.Mock()
        mock_azure.is_entra_id_configured = True
        mock_azure.is_token_expired = True
        mock_azure.refresh_token.return_value = True
        mocker.patch(f"{MODULE}.AzureEntraIDManager", return_value=mock_azure)
        updated_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_update_token = mocker.patch(
            f"{MODULE}.update_azure_token",
            new=mocker.AsyncMock(return_value=updated_client),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")
        mocker.patch(
            f"{MODULE}.handle_non_streaming_response",
            new=mocker.AsyncMock(
                return_value=_make_responses_response(
                    output_text="Ok",
                    conversation="conv_new",
                    model="azure/some-model",
                )
            ),
        )

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )
        mock_update_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_responses_structured_input_appends_rag_message(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that non-string input uses extract_text and appends RAG message."""
        structured_input: list[Any] = [
            OpenAIResponseMessage(role="user", content="What is K8s?"),
        ]
        responses_request = ResponsesRequest(
            input=cast(Any, structured_input),
        )
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker)
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        mock_build_rag = mocker.patch(
            f"{MODULE}.build_rag_context",
            new=mocker.AsyncMock(
                return_value=RAGContext(
                    context_text="\n\nRelevant documentation:\nDoc1",
                    referenced_documents=[],
                ),
            ),
        )
        _patch_moderation(mocker, decision="passed")
        mocker.patch(
            f"{MODULE}.handle_non_streaming_response",
            new=mocker.AsyncMock(
                return_value=_make_responses_response(
                    output_text="K8s is Kubernetes.",
                    conversation="conv_new",
                )
            ),
        )

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        mock_build_rag.assert_called_once()
        call_args = mock_build_rag.call_args[0]
        assert (
            call_args[2] == "What is K8s?"
        )  # input_text (3rd arg to build_rag_context)

    @pytest.mark.asyncio
    async def test_responses_blocked_with_conversation_appends_refusal(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Blocked moderation with conversation calls append_turn_items_to_conversation."""
        responses_request = ResponsesRequest(
            input="Bad",
            conversation=VALID_CONV_ID,
            stream=False,
            model="provider/model1",
        )
        _patch_base(mocker, minimal_config)
        mock_user_conv = mocker.Mock(spec=UserConversation)
        mock_user_conv.id = VALID_CONV_ID_NORMALIZED
        mocker.patch(
            f"{ENDPOINTS_MODULE}.validate_and_retrieve_conversation",
            return_value=mock_user_conv,
        )
        mock_client, mock_holder = _patch_client(mocker)
        mocker.patch(
            f"{ENDPOINTS_MODULE}.AsyncLlamaStackClientHolder",
            return_value=mock_holder,
        )
        mocker.patch(
            f"{ENDPOINTS_MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(
            f"{ENDPOINTS_MODULE}.to_llama_stack_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        mock_moderation = _patch_moderation(mocker, decision="blocked")
        mock_moderation.message = "Blocked"
        mock_moderation.moderation_id = "resp_blocked_123"
        mock_moderation.refusal_response = OpenAIResponseMessage(
            type="message", role="assistant", content="Blocked"
        )
        mock_append = mocker.patch(
            f"{MODULE}.append_turn_items_to_conversation",
            new=mocker.AsyncMock(),
        )
        mocker.patch(f"{MODULE}.store_query_results")

        response = await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        mock_append.assert_awaited_once_with(
            client=mock_client,
            conversation_id=VALID_CONV_ID,
            user_input=responses_request.input,
            llm_output=[mock_moderation.refusal_response],
        )
        assert isinstance(response, ResponsesResponse)
        payload = response.model_dump()
        assert "model" in payload, "Handler must set model on the response payload"
        ResponsesResponse.model_validate(payload)

    @pytest.mark.asyncio
    async def test_tool_choice_none_without_tools_does_not_load_server_tools(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Regression: tool_choice='none' with no client tools must not load server tools."""
        responses_request = ResponsesRequest(
            input="Hello",
            tool_choice=ToolChoiceMode.none,
            # tools intentionally omitted
        )
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker, conversation="conv_new_123")
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")

        mock_handle = mocker.patch(
            f"{MODULE}.handle_non_streaming_response",
            new=mocker.AsyncMock(
                return_value=_make_responses_response(
                    output_text="answer",
                    conversation="conv_new_123",
                )
            ),
        )

        # Spy on prepare_tools to verify it is never called
        mock_prepare = mocker.patch(
            f"{UTILS_RESPONSES_MODULE}.prepare_tools",
            new=mocker.AsyncMock(return_value=None),
        )

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        # prepare_tools must NOT be called when tool_choice is "none"
        mock_prepare.assert_not_awaited()

        # The handler passes tools=None and tool_choice=None to the response handler
        # (the endpoint deep-copies the request, so we inspect the handler call args)
        call_kwargs = mock_handle.call_args[1]
        assert call_kwargs["api_params"].tools is None
        assert call_kwargs["api_params"].tool_choice is None

    @pytest.mark.asyncio
    async def test_responses_endpoint_rejects_without_responses_action(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Verify that requests lacking Action.RESPONSES are rejected with 403.

        Constructs a request whose authorized_actions includes Action.QUERY and
        Action.READ_OTHERS_CONVERSATIONS but NOT Action.RESPONSES, then asserts
        the @authorize(Action.RESPONSES) decorator raises HTTPException 403.
        """
        req = Request(scope={"type": "http", "headers": []})
        req.state.authorized_actions = {Action.QUERY, Action.READ_OTHERS_CONVERSATIONS}

        mock_role_resolver = mocker.AsyncMock()
        mock_role_resolver.resolve_roles = mocker.AsyncMock(return_value=set())

        mock_access_resolver = mocker.Mock()
        mock_access_resolver.check_access.return_value = False

        mocker.patch(
            "authorization.middleware.get_authorization_resolvers",
            return_value=(mock_role_resolver, mock_access_resolver),
        )

        with pytest.raises(HTTPException) as exc_info:
            await responses_endpoint_handler(
                request=req,
                responses_request=ResponsesRequest(input="Hello"),
                auth=MOCK_AUTH,
                mcp_headers={},
            )
        assert exc_info.value.status_code == 403


class TestHandleNonStreamingResponse:
    """Unit tests for handle_non_streaming_response."""

    @pytest.mark.asyncio
    async def test_handle_non_streaming_blocked_returns_refusal(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that blocked moderation returns response with refusal message."""
        request = _request_with_model_and_conv("Bad input")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "blocked"
        mock_moderation.message = "Content blocked"
        mock_refusal = mocker.Mock(spec=OpenAIResponseMessage)
        mock_refusal.type = "message"
        mock_refusal.role = "assistant"
        mock_refusal.content = "Content blocked"
        mock_moderation.refusal_response = mock_refusal

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mock_client.conversations.items.create = mocker.AsyncMock()
        mock_api_response = mocker.Mock()
        mock_api_response.output = [mock_refusal]
        mock_api_response.model_dump.return_value = {
            "id": "resp_blocked",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "model": "provider/model1",
            "output": [
                {"type": "message", "role": "assistant", "content": "Content blocked"}
            ],
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
        mocker.patch(
            f"{MODULE}.OpenAIResponseObject.model_construct",
            return_value=mock_api_response,
        )

        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Bad input",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
        )
        response = await handle_non_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )
        assert isinstance(response, ResponsesResponse)
        assert response.output_text == "Content blocked"
        mock_client.responses.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_non_streaming_success_returns_response(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test successful handle_non_streaming_response returns ResponsesResponse."""
        request = _request_with_model_and_conv("Hello")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mock_api_response = mocker.Mock(spec=OpenAIResponseObject)
        mock_api_response.output = []
        mock_api_response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        mock_api_response.model_dump.return_value = {
            "id": "resp_1",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "model": "provider/model1",
            "output": [],
            "usage": {
                "input_tokens": 1,
                "output_tokens": 2,
                "total_tokens": 3,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_api_response)

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.extract_token_usage",
            return_value=mocker.Mock(input_tokens=1, output_tokens=2),
        )
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=mocker.Mock(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.extract_text_from_response_items",
            return_value="Model reply",
        )
        mocker.patch(
            f"{MODULE}.extract_vector_store_ids_from_tools",
            return_value=[],
        )
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )

        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hello",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
        )
        response = await handle_non_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )

        assert isinstance(response, ResponsesResponse)
        assert response.output_text == "Model reply"
        mock_client.responses.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_non_streaming_with_previous_response_id_appends_turn(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test append_turn_items_to_conversation triggers with store and previous_response_id."""
        request = _request_with_previous_response_id("Hi", previous_response_id="r1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mock_api_response = mocker.Mock(spec=OpenAIResponseObject)
        mock_api_response.output = []
        mock_api_response.id = "resp_1"
        mock_api_response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        mock_api_response.model_dump.return_value = {
            "id": "resp_1",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "model": "provider/model1",
            "output": [],
            "usage": {
                "input_tokens": 1,
                "output_tokens": 2,
                "total_tokens": 3,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_api_response)

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.extract_token_usage",
            return_value=mocker.Mock(input_tokens=1, output_tokens=2),
        )
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=mocker.Mock(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.extract_text_from_response_items",
            return_value="Reply",
        )
        mocker.patch(
            f"{MODULE}.extract_vector_store_ids_from_tools",
            return_value=[],
        )
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mock_append = mocker.patch(
            f"{MODULE}.append_turn_items_to_conversation",
            new=mocker.AsyncMock(),
        )

        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
        )
        await handle_non_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )

        mock_append.assert_awaited_once()
        call_args = mock_append.call_args[0]
        assert call_args[1] == VALID_CONV_ID
        assert call_args[3] == []

    @pytest.mark.asyncio
    async def test_handle_non_streaming_context_length_raises_413(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that RuntimeError with context_length raises 413."""
        request = _request_with_model_and_conv("Long input")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("context_length exceeded")
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )

        with pytest.raises(HTTPException) as exc_info:
            api_params, context = build_api_params_and_context(
                updated_request=request,
                client=mock_client,
                auth=MOCK_AUTH,
                input_text="Long input",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                inline_rag_context=RAGContext(),
            )
            await handle_non_streaming_response(
                original_request=request,
                api_params=api_params,
                context=context,
            )

        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_handle_non_streaming_connection_error_raises_503(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that APIConnectionError raises 503."""
        request = _request_with_model_and_conv("Hi")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed",
                request=mocker.Mock(),
            )
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )

        with pytest.raises(HTTPException) as exc_info:
            api_params, context = build_api_params_and_context(
                updated_request=request,
                client=mock_client,
                auth=MOCK_AUTH,
                input_text="Hi",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                inline_rag_context=RAGContext(),
            )
            await handle_non_streaming_response(
                original_request=request,
                api_params=api_params,
                context=context,
            )

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_handle_non_streaming_api_status_error_raises_http(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that APIStatusError is handled and re-raised as HTTPException."""
        request = _request_with_model_and_conv("Hi")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIStatusError(
                message="API error",
                response=mocker.Mock(request=None),
                body=None,
            )
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(
            f"{MODULE}.handle_known_apistatus_errors",
            return_value=mocker.Mock(
                model_dump=lambda: {
                    "status_code": 500,
                    "detail": {"response": "Error", "cause": "API error"},
                }
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            api_params, context = build_api_params_and_context(
                updated_request=request,
                client=mock_client,
                auth=MOCK_AUTH,
                input_text="Hi",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                inline_rag_context=RAGContext(),
            )
            await handle_non_streaming_response(
                original_request=request,
                api_params=api_params,
                context=context,
            )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_handle_non_streaming_runtime_error_without_context_reraises(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that RuntimeError without context_length is re-raised."""
        request = _request_with_model_and_conv("Hi")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("Some other error")
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )

        with pytest.raises(RuntimeError, match="Some other error"):
            api_params, context = build_api_params_and_context(
                updated_request=request,
                client=mock_client,
                auth=MOCK_AUTH,
                input_text="Hi",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                inline_rag_context=RAGContext(),
            )
            await handle_non_streaming_response(
                original_request=request,
                api_params=api_params,
                context=context,
            )


class TestHandleStreamingResponse:
    """Unit tests for handle_streaming_response and streaming generators."""

    @pytest.mark.asyncio
    async def test_handle_streaming_blocked_returns_sse_consumes_shield_generator(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming with blocked moderation yields SSE from shield_violation_generator."""
        request = _request_with_model_and_conv("Bad", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "blocked"
        mock_moderation.message = "Blocked"
        mock_moderation.moderation_id = "mod_123"
        mock_refusal = OpenAIResponseMessage(
            role="assistant", content="Blocked", type="message"
        )
        mock_moderation.refusal_response = mock_refusal

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")

        mock_client.conversations.items.create = mocker.AsyncMock()
        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Bad",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
        )
        response = await handle_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        collected: list[str] = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        body = "".join(collected)
        assert "event: response.created" in body
        assert "event: response.output_item.added" in body
        assert "event: response.output_item.done" in body
        assert "event: response.completed" in body
        assert "[DONE]" in body
        mock_client.responses.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_streaming_success_returns_sse_consumes_response_generator(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming with passed moderation yields SSE from response_generator."""
        request = _request_with_model_and_conv("Hi", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mock_chunk = mocker.Mock()
        mock_chunk.type = "response.completed"
        mock_chunk.response = mocker.Mock()
        mock_chunk.response.id = "r1"
        mock_chunk.response.output = []
        mock_chunk.response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        mock_chunk.model_dump.return_value = {
            "type": "response.completed",
            "response": {"id": "r1", "usage": {"input_tokens": 1}},
        }

        async def mock_stream() -> Any:
            yield mock_chunk

        mock_client.responses.create = mocker.AsyncMock(return_value=mock_stream())

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(f"{MODULE}.extract_token_usage", return_value=mocker.Mock())
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(f"{MODULE}.extract_vector_store_ids_from_tools", return_value=[])
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=TurnSummary(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mock_holder = mocker.Mock()
        mock_holder.get_client.return_value = mock_client
        mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)
        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
        )
        response = await handle_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )
        assert isinstance(response, StreamingResponse)
        collected: list[str] = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        body = "".join(collected)
        assert "response.completed" in body or "event:" in body
        assert "[DONE]" in body
        mock_client.responses.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_streaming_in_progress_chunk_sets_quotas_and_output_text(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test in_progress chunk includes available_quotas and output_text."""
        request = _request_with_model_and_conv("Hi", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        in_progress_chunk = mocker.Mock()
        in_progress_chunk.type = "response.in_progress"
        in_progress_chunk.model_dump.return_value = {
            "type": "response.in_progress",
            "response": {"id": "r0"},
        }

        completed_chunk = mocker.Mock()
        completed_chunk.type = "response.completed"
        completed_chunk.response = mocker.Mock()
        completed_chunk.response.id = "r1"
        completed_chunk.response.output = []
        completed_chunk.response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        completed_chunk.model_dump.return_value = {
            "type": "response.completed",
            "response": {"id": "r1", "usage": {"input_tokens": 1}},
        }

        async def mock_stream() -> Any:
            yield in_progress_chunk
            yield completed_chunk

        mock_client.responses.create = mocker.AsyncMock(return_value=mock_stream())

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(f"{MODULE}.extract_token_usage", return_value=mocker.Mock())
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(f"{MODULE}.extract_vector_store_ids_from_tools", return_value=[])
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=TurnSummary(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mock_holder = mocker.Mock()
        mock_holder.get_client.return_value = mock_client
        mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)

        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
        )
        response = await handle_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )
        collected: list[str] = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        body = "".join(collected)
        assert "response.in_progress" in body
        assert '"available_quotas":{}' in body or '"available_quotas": {}' in body
        assert "[DONE]" in body

    @pytest.mark.asyncio
    async def test_handle_streaming_builds_tool_call_summary_from_output(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that response output items are passed to build_tool_call_summary."""
        request = _request_with_model_and_conv("Hi", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mock_output_item = mocker.Mock()
        completed_chunk = mocker.Mock()
        completed_chunk.type = "response.completed"
        completed_chunk.response = mocker.Mock()
        completed_chunk.response.id = "r1"
        completed_chunk.response.output = [mock_output_item]
        completed_chunk.response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        completed_chunk.model_dump.return_value = {
            "type": "response.completed",
            "response": {"id": "r1", "usage": {"input_tokens": 1}},
        }

        async def mock_stream() -> Any:
            yield completed_chunk

        mock_client.responses.create = mocker.AsyncMock(return_value=mock_stream())

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(f"{MODULE}.extract_token_usage", return_value=mocker.Mock())
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(f"{MODULE}.extract_vector_store_ids_from_tools", return_value=[])
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=TurnSummary(referenced_documents=[]),
        )
        mock_build_tool_call = mocker.patch(
            f"{MODULE}.build_tool_call_summary",
            return_value=(mocker.Mock(), mocker.Mock()),
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(f"{MODULE}.parse_referenced_documents", return_value=[])
        mocker.patch(
            f"{MODULE}.deduplicate_referenced_documents", side_effect=lambda x: x
        )
        mock_holder = mocker.Mock()
        mock_holder.get_client.return_value = mock_client
        mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)

        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
        )
        response = await handle_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )
        collected: list[str] = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        mock_build_tool_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_streaming_with_previous_response_id_appends_turn(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that store=True and previous_response_id in streaming triggers append_turn_items."""
        request = _request_with_previous_response_id(
            "Hi", previous_response_id="r_prev"
        )
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        completed_chunk = mocker.Mock()
        completed_chunk.type = "response.completed"
        completed_chunk.response = mocker.Mock()
        completed_chunk.response.id = "r1"
        completed_chunk.response.output = []
        completed_chunk.response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        completed_chunk.model_dump.return_value = {
            "type": "response.completed",
            "response": {"id": "r1", "usage": {"input_tokens": 1}},
        }

        async def mock_stream() -> Any:
            yield completed_chunk

        mock_client.responses.create = mocker.AsyncMock(return_value=mock_stream())

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(f"{MODULE}.extract_token_usage", return_value=mocker.Mock())
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(f"{MODULE}.extract_vector_store_ids_from_tools", return_value=[])
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=TurnSummary(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mock_append = mocker.patch(
            f"{MODULE}.append_turn_items_to_conversation",
            new=mocker.AsyncMock(),
        )
        mock_holder = mocker.Mock()
        mock_holder.get_client.return_value = mock_client
        mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)

        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
        )
        response = await handle_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )
        collected: list[str] = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        mock_append.assert_called_once()
        call_args = mock_append.call_args[0]
        assert call_args[1] == VALID_CONV_ID
        assert call_args[3] == []

    @pytest.mark.asyncio
    async def test_handle_streaming_context_length_raises_413(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming raises 413 when create raises RuntimeError context_length."""
        request = _request_with_model_and_conv("Long", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("context_length exceeded")
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        with pytest.raises(HTTPException) as exc_info:
            api_params, context = build_api_params_and_context(
                updated_request=request,
                client=mock_client,
                auth=MOCK_AUTH,
                input_text="Long",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                inline_rag_context=RAGContext(),
            )
            await handle_streaming_response(
                original_request=request,
                api_params=api_params,
                context=context,
            )
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_handle_streaming_connection_error_raises_503(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming raises 503 when create raises APIConnectionError."""
        request = _request_with_model_and_conv("Hi", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed",
                request=mocker.Mock(),
            )
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        with pytest.raises(HTTPException) as exc_info:
            api_params, context = build_api_params_and_context(
                updated_request=request,
                client=mock_client,
                auth=MOCK_AUTH,
                input_text="Hi",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                inline_rag_context=RAGContext(),
            )
            await handle_streaming_response(
                original_request=request,
                api_params=api_params,
                context=context,
            )

        assert exc_info.value.status_code == 503


class TestResponsesInstructionResolution:
    """Tests for server-side instruction resolution in responses_endpoint_handler."""

    @pytest.mark.asyncio
    async def test_default_instructions_applied_when_client_omits_them(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """When client sends no instructions, the server default is applied."""
        responses_request = ResponsesRequest(input="Hello")
        assert responses_request.instructions is None

        _patch_base(mocker, minimal_config)
        mocker.patch("utils.prompts.configuration", minimal_config)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker, conversation="conv_new_123")
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")

        mock_handler = mocker.AsyncMock(
            return_value=_make_responses_response(
                output_text="Reply", conversation="conv_new_123"
            )
        )
        mocker.patch(f"{MODULE}.handle_non_streaming_response", new=mock_handler)

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        # The updated request passed to handle_non_streaming_response should have
        # instructions resolved to the default system prompt.
        call_kwargs = mock_handler.call_args[1]
        assert call_kwargs["api_params"].instructions == DEFAULT_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_client_provided_instructions_pass_through(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """When client provides instructions, they are used as-is."""
        custom_instructions = "You are a RHEL expert."
        responses_request = ResponsesRequest(
            input="Hello", instructions=custom_instructions
        )

        _patch_base(mocker, minimal_config)
        mocker.patch("utils.prompts.configuration", minimal_config)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker, conversation="conv_new_123")
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")

        mock_handler = mocker.AsyncMock(
            return_value=_make_responses_response(
                output_text="Reply", conversation="conv_new_123"
            )
        )
        mocker.patch(f"{MODULE}.handle_non_streaming_response", new=mock_handler)

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        call_kwargs = mock_handler.call_args[1]
        assert call_kwargs["api_params"].instructions == custom_instructions

    @pytest.mark.asyncio
    async def test_configured_system_prompt_used_when_no_client_instructions(
        self,
        dummy_request: Request,
        mocker: MockerFixture,
    ) -> None:
        """When config has a custom system_prompt and client sends none, use it."""
        cfg = AppConfig()
        cfg.init_from_dict(
            {
                "name": "test",
                "service": {"host": "localhost", "port": 8080},
                "llama_stack": {
                    "api_key": "test-key",
                    "url": "http://test.com:1234",
                    "use_as_library_client": False,
                },
                "user_data_collection": {},
                "authentication": {"module": "noop"},
                "authorization": {"access_rules": []},
                "customization": {
                    "system_prompt": "You are a deployment assistant.",
                },
            }
        )

        responses_request = ResponsesRequest(input="Hello")

        _patch_base(mocker, cfg)
        # Also patch configuration in prompts module so get_system_prompt sees it
        mocker.patch("utils.prompts.configuration", cfg)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker, conversation="conv_new_123")
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")

        mock_handler = mocker.AsyncMock(
            return_value=_make_responses_response(
                output_text="Reply", conversation="conv_new_123"
            )
        )
        mocker.patch(f"{MODULE}.handle_non_streaming_response", new=mock_handler)

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        call_kwargs = mock_handler.call_args[1]
        assert (
            call_kwargs["api_params"].instructions == "You are a deployment assistant."
        )

    @pytest.mark.asyncio
    async def test_client_instructions_rejected_when_disabled(
        self,
        dummy_request: Request,
        mocker: MockerFixture,
    ) -> None:
        """When disable_query_system_prompt is set, client instructions raise 422."""
        cfg = AppConfig()
        cfg.init_from_dict(
            {
                "name": "test",
                "service": {"host": "localhost", "port": 8080},
                "llama_stack": {
                    "api_key": "test-key",
                    "url": "http://test.com:1234",
                    "use_as_library_client": False,
                },
                "user_data_collection": {},
                "authentication": {"module": "noop"},
                "authorization": {"access_rules": []},
                "customization": {
                    "disable_query_system_prompt": True,
                },
            }
        )

        responses_request = ResponsesRequest(
            input="Hello", instructions="Custom instructions"
        )

        _patch_base(mocker, cfg)
        mocker.patch("utils.prompts.configuration", cfg)

        with pytest.raises(HTTPException) as exc_info:
            await responses_endpoint_handler(
                request=dummy_request,
                responses_request=responses_request,
                auth=MOCK_AUTH,
                mcp_headers={},
            )

        assert exc_info.value.status_code == 422
        assert isinstance(exc_info.value.detail, dict)
        assert "instructions field" in exc_info.value.detail.get("cause", "")

    @pytest.mark.asyncio
    async def test_streaming_response_uses_resolved_instructions(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """When streaming, instructions are resolved the same way as non-streaming."""
        responses_request = ResponsesRequest(input="Hello", stream=True)
        assert responses_request.instructions is None

        _patch_base(mocker, minimal_config)
        mocker.patch("utils.prompts.configuration", minimal_config)
        _patch_client(mocker)
        _patch_resolve_response_context(mocker, conversation="conv_new_123")
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")

        mock_handler = mocker.AsyncMock(
            return_value=mocker.Mock(spec=StreamingResponse)
        )
        mocker.patch(f"{MODULE}.handle_streaming_response", new=mock_handler)

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        call_kwargs = mock_handler.call_args[1]
        assert call_kwargs["api_params"].instructions == DEFAULT_SYSTEM_PROMPT


class TestIsServerMcpOutputItem:
    """Tests for _is_server_mcp_output_item helper."""

    def test_mcp_call_with_matching_label(self) -> None:
        """Test mcp_call item with a configured server_label returns True."""
        item: dict[str, Any] = {"type": "mcp_call", "server_label": "my-server"}
        assert _is_server_mcp_output_item(item, {"my-server"}) is True

    def test_mcp_call_with_non_matching_label(self) -> None:
        """Test mcp_call item with unconfigured server_label returns False."""
        item: dict[str, Any] = {"type": "mcp_call", "server_label": "client-server"}
        assert _is_server_mcp_output_item(item, {"my-server"}) is False

    def test_mcp_list_tools_with_matching_label(self) -> None:
        """Test mcp_list_tools item with configured label returns True."""
        item: dict[str, Any] = {"type": "mcp_list_tools", "server_label": "fs"}
        assert _is_server_mcp_output_item(item, {"fs", "other"}) is True

    def test_mcp_approval_request_with_matching_label(self) -> None:
        """Test mcp_approval_request item with configured label returns True."""
        item: dict[str, Any] = {
            "type": "mcp_approval_request",
            "server_label": "tool-a",
        }
        assert _is_server_mcp_output_item(item, {"tool-a"}) is True

    def test_mcp_call_missing_server_label(self) -> None:
        """Test mcp_call without server_label returns False."""
        item: dict[str, Any] = {"type": "mcp_call"}
        assert _is_server_mcp_output_item(item, {"my-server"}) is False

    def test_message_type_returns_false(self) -> None:
        """Test non-MCP type returns False."""
        item: dict[str, Any] = {"type": "message", "role": "assistant"}
        assert _is_server_mcp_output_item(item, {"my-server"}) is False

    def test_function_call_type_returns_false(self) -> None:
        """Test function_call type returns False."""
        item: dict[str, Any] = {"type": "function_call", "name": "get_weather"}
        assert _is_server_mcp_output_item(item, {"my-server"}) is False

    def test_empty_configured_labels(self) -> None:
        """Test mcp_call with empty configured labels returns False."""
        item: dict[str, Any] = {"type": "mcp_call", "server_label": "any-server"}
        assert _is_server_mcp_output_item(item, set()) is False

    def test_file_search_call_returns_false(self) -> None:
        """Test file_search_call type returns False."""
        item: dict[str, Any] = {"type": "file_search_call"}
        assert _is_server_mcp_output_item(item, {"my-server"}) is False


class TestShouldFilterMcpChunk:
    """Tests for _should_filter_mcp_chunk helper."""

    def test_filters_mcp_call_substream_events(self, mocker: MockerFixture) -> None:
        """Test that response.mcp_call.* events are filtered for tracked indices."""
        chunk = mocker.Mock()
        chunk.output_index = 5
        chunk.type = "response.mcp_call.in_progress"
        server_mcp_output_indices: set[int] = {5}
        assert (
            _should_filter_mcp_chunk(
                chunk,
                {"server-a"},
                server_mcp_output_indices,
            )
            is True
        )

    def test_filters_mcp_list_tools_substream_events(
        self, mocker: MockerFixture
    ) -> None:
        """Test that response.mcp_list_tools.* events are filtered for tracked indices."""
        chunk = mocker.Mock()
        chunk.output_index = 3
        chunk.type = "response.mcp_list_tools.in_progress"
        server_mcp_output_indices: set[int] = {3}
        assert (
            _should_filter_mcp_chunk(
                chunk,
                {"server-a"},
                server_mcp_output_indices,
            )
            is True
        )

    def test_filters_mcp_approval_request_substream_events(
        self, mocker: MockerFixture
    ) -> None:
        """Test that response.mcp_approval_request.* events are filtered for tracked indices."""
        chunk = mocker.Mock()
        chunk.output_index = 7
        chunk.type = "response.mcp_approval_request.in_progress"
        server_mcp_output_indices: set[int] = {7}
        assert (
            _should_filter_mcp_chunk(
                chunk,
                {"server-a"},
                server_mcp_output_indices,
            )
            is True
        )

    def test_does_not_filter_untracked_mcp_approval_request(
        self, mocker: MockerFixture
    ) -> None:
        """Test that mcp_approval_request events for untracked indices pass through."""
        chunk = mocker.Mock()
        chunk.output_index = 7
        chunk.type = "response.mcp_approval_request.in_progress"
        server_mcp_output_indices: set[int] = {99}
        assert (
            _should_filter_mcp_chunk(
                chunk,
                {"server-a"},
                server_mcp_output_indices,
            )
            is False
        )

    def test_does_not_filter_untracked_mcp_call(self, mocker: MockerFixture) -> None:
        """Test that mcp_call events for untracked indices pass through."""
        chunk = mocker.Mock()
        chunk.output_index = 10
        chunk.type = "response.mcp_call.completed"
        server_mcp_output_indices: set[int] = {5}
        assert (
            _should_filter_mcp_chunk(
                chunk,
                {"server-a"},
                server_mcp_output_indices,
            )
            is False
        )

    def test_filters_output_item_added_for_server_mcp(
        self, mocker: MockerFixture
    ) -> None:
        """Test that output_item.added for server MCP items is filtered and tracked."""
        item = mocker.Mock()
        item.type = "mcp_approval_request"
        item.server_label = "server-a"
        chunk = mocker.Mock()
        chunk.item = item
        chunk.output_index = 2
        chunk.type = "response.output_item.added"
        server_mcp_output_indices: set[int] = set()
        assert (
            _should_filter_mcp_chunk(
                chunk,
                {"server-a"},
                server_mcp_output_indices,
            )
            is True
        )
        assert 2 in server_mcp_output_indices

    def test_filters_output_item_done_for_server_mcp(
        self, mocker: MockerFixture
    ) -> None:
        """Test that output_item.done for server MCP items is filtered and cleaned up."""
        item = mocker.Mock()
        item.type = "mcp_approval_request"
        chunk = mocker.Mock()
        chunk.item = item
        chunk.output_index = 2
        chunk.type = "response.output_item.done"
        server_mcp_output_indices: set[int] = {2}
        assert (
            _should_filter_mcp_chunk(
                chunk,
                {"server-a"},
                server_mcp_output_indices,
            )
            is True
        )
        assert 2 not in server_mcp_output_indices

    def test_does_not_filter_non_mcp_event(self, mocker: MockerFixture) -> None:
        """Test that non-MCP events pass through."""
        chunk = mocker.Mock()
        chunk.type = "response.output_text.delta"
        assert _should_filter_mcp_chunk(chunk, {"server-a"}, set()) is False


def mock_original_request(
    *, instructions: Optional[str] = None, model: Optional[str] = None
) -> ResponsesRequest:
    """Build a minimal ResponsesRequest for _sanitize_response_dict tests."""
    kwargs: dict[str, Any] = {"input": "x"}
    if instructions is not None:
        kwargs["instructions"] = instructions
    if model is not None:
        kwargs["model"] = model
    return ResponsesRequest(**kwargs)


class TestSanitizeResponseDict:
    """Unit tests for _sanitize_response_dict."""

    def test_substituted_instructions_replaced_with_placeholder(self) -> None:
        """Test that substituted instructions are replaced with the slug constant."""
        d: dict[str, Any] = {"instructions": "secret server prompt", "model": "m"}
        _sanitize_response_dict(d, set(), mock_original_request(instructions=None))
        assert d["instructions"] == SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER

    def test_client_instructions_preserved_when_not_substituted(self) -> None:
        """Test that client-provided instructions are echoed back unchanged."""
        d: dict[str, Any] = {"instructions": "my custom prompt"}
        _sanitize_response_dict(
            d,
            set(),
            mock_original_request(**d),
        )
        assert d["instructions"] == "my custom prompt"

    def test_substituted_instructions_set_even_when_absent(self) -> None:
        """Test that placeholder is set even when instructions field is missing."""
        d: dict[str, Any] = {"model": "m"}
        _sanitize_response_dict(d, set(), mock_original_request(instructions=None))
        assert d["instructions"] == SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER

    def test_strips_server_mcp_tools(self) -> None:
        """Test that server-deployed MCP tools are removed from tools array."""
        d: dict[str, Any] = {
            "tools": [
                {"server_label": "server-a", "name": "tool1"},
                {"server_label": "server-b", "name": "tool2"},
                {"name": "client-tool"},
            ]
        }
        _sanitize_response_dict(d, {"server-a", "server-b"}, mock_original_request())
        assert d["tools"] == [{"name": "client-tool"}]

    def test_preserves_client_tools(self) -> None:
        """Test that client-provided tools are preserved."""
        d: dict[str, Any] = {
            "tools": [
                {"server_label": "server-a", "name": "server-tool"},
                {"name": "client-tool"},
            ]
        }
        _sanitize_response_dict(d, {"server-a"}, mock_original_request())
        assert d["tools"] == [{"name": "client-tool"}]

    def test_no_error_when_tools_absent(self) -> None:
        """Test that missing tools field does not raise."""
        d: dict[str, Any] = {"model": "m"}
        _sanitize_response_dict(d, {"server-a"}, mock_original_request())
        assert "tools" not in d

    def test_empty_configured_mcp_labels_preserves_all_tools(self) -> None:
        """Test that empty configured_mcp_labels preserves all tools."""
        d: dict[str, Any] = {
            "tools": [
                {"server_label": "server-a", "name": "tool1"},
                {"name": "client-tool"},
            ]
        }
        _sanitize_response_dict(d, set(), mock_original_request())
        assert len(d["tools"]) == 2

    def test_strips_server_mcp_items_from_output(self) -> None:
        """Test that server-deployed MCP output items are removed from output array."""
        d: dict[str, Any] = {
            "instructions": "prompt",
            "output": [
                {
                    "type": "mcp_list_tools",
                    "server_label": "okp",
                    "tools": [{"name": "search_portal"}],
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"text": "hello"}],
                },
                {"type": "mcp_call", "server_label": "okp", "id": "call-1"},
            ],
        }
        _sanitize_response_dict(
            d, {"okp"}, mock_original_request(instructions="client-provided")
        )
        assert len(d["output"]) == 1
        assert d["output"][0]["type"] == "message"

    def test_preserves_non_server_mcp_output_items(self) -> None:
        """Test that client MCP output items and regular items are preserved."""
        d: dict[str, Any] = {
            "output": [
                {"type": "mcp_list_tools", "server_label": "client-mcp", "tools": []},
                {"type": "message", "role": "assistant", "content": []},
                {"type": "function_call", "name": "my_func"},
            ],
        }
        _sanitize_response_dict(d, {"okp"}, mock_original_request())
        assert len(d["output"]) == 3

    def test_no_error_when_output_absent(self) -> None:
        """Test that missing output field does not raise."""
        d: dict[str, Any] = {"model": "m"}
        _sanitize_response_dict(d, {"okp"}, mock_original_request())
        assert "output" not in d

    def test_strips_provider_prefix_from_model_when_substituted(self) -> None:
        """Test that provider routing prefix is stripped when server substituted the model."""
        d: dict[str, Any] = {
            "model": "google-vertex/publishers/google/models/gemini-2.5-flash"
        }
        _sanitize_response_dict(d, set(), mock_original_request(model=None))
        assert d["model"] == "gemini-2.5-flash"

    def test_preserves_client_model_when_not_substituted(self) -> None:
        """Test that client-specified model is echoed back unchanged."""
        d: dict[str, Any] = {
            "model": "google-vertex/publishers/google/models/gemini-2.5-flash"
        }
        _sanitize_response_dict(d, set(), mock_original_request(**d))
        assert d["model"] == "google-vertex/publishers/google/models/gemini-2.5-flash"

    def test_model_without_slash_preserved(self) -> None:
        """Test that model names without provider prefix are left unchanged."""
        d: dict[str, Any] = {"model": "gemini-2.5-flash"}
        _sanitize_response_dict(d, set(), mock_original_request())
        assert d["model"] == "gemini-2.5-flash"

    def test_all_fields_sanitized_together_with_substitution(self) -> None:
        """Test that all sanitizations are applied in a single call."""
        d: dict[str, Any] = {
            "instructions": "secret prompt",
            "model": "google-vertex/publishers/google/models/gemini",
            "tools": [
                {"server_label": "mcp-server", "name": "server-tool"},
                {"name": "client-tool"},
            ],
            "output": [
                {"type": "mcp_list_tools", "server_label": "mcp-server", "tools": []},
                {"type": "message", "role": "assistant", "content": []},
            ],
        }
        _sanitize_response_dict(
            d, {"mcp-server"}, mock_original_request(instructions=None, model=None)
        )
        assert d["instructions"] == SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER
        assert d["model"] == "gemini"
        assert d["tools"] == [{"name": "client-tool"}]
        assert len(d["output"]) == 1
        assert d["output"][0]["type"] == "message"

    def test_all_fields_sanitized_together_without_substitution(self) -> None:
        """Test that client instructions and model are preserved while tools are still filtered."""
        d: dict[str, Any] = {
            "instructions": "client prompt",
            "model": "google-vertex/publishers/google/models/gemini",
            "tools": [
                {"server_label": "mcp-server", "name": "server-tool"},
                {"name": "client-tool"},
            ],
            "output": [
                {"type": "mcp_list_tools", "server_label": "mcp-server", "tools": []},
                {"type": "message", "role": "assistant", "content": []},
            ],
        }
        _sanitize_response_dict(
            d,
            {"mcp-server"},
            mock_original_request(
                instructions="client prompt",
                model="provider/model1",
            ),
        )
        assert d["instructions"] == "client prompt"
        assert d["model"] == "google-vertex/publishers/google/models/gemini"
        assert d["tools"] == [{"name": "client-tool"}]
        assert len(d["output"]) == 1
        assert d["output"][0]["type"] == "message"


class TestSanitizesOutputAndModel:
    """Integration test: sanitize MCP output, model, and instructions.

    Covers both streaming and non-streaming code paths.
    """

    @pytest.mark.asyncio
    async def test_non_streaming_sanitizes_mcp_output_and_model(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that non-streaming response strips MCP items, model prefix, and instructions."""
        mcp_server = ModelContextProtocolServer(
            name="server-a",
            provider_id="model-context-protocol",
            url="http://mcp.example.com",
        )
        mock_config = mocker.Mock()
        mock_config.mcp_servers = [mcp_server]
        mock_config.quota_limiters = minimal_config.quota_limiters
        mock_config.rag_id_mapping = {}

        original_request = ResponsesRequest(input="Hi")
        updated_request = ResponsesRequest(
            input="Hi",
            model=MODEL,
            instructions=SERVER_INSTRUCTIONS,
            conversation=VALID_CONV_ID_NORMALIZED,
        )

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mock_api_response = mocker.Mock(spec=OpenAIResponseObject)
        mock_api_response.output = []
        mock_api_response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        mock_api_response.model_dump.return_value = {
            "id": "resp_1",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "instructions": "secret system prompt",
            "model": "google-vertex/publishers/google/models/gemini-2.5-flash",
            "output": [
                {
                    "type": "mcp_list_tools",
                    "server_label": "server-a",
                    "tools": [{"name": "search_portal"}],
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hello"}],
                },
            ],
            "usage": {
                "input_tokens": 1,
                "output_tokens": 2,
                "total_tokens": 3,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_api_response)

        mocker.patch(f"{MODULE}.configuration", mock_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(
            f"{MODULE}.extract_token_usage",
            return_value=mocker.Mock(input_tokens=1, output_tokens=2),
        )
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=mocker.Mock(
                referenced_documents=[],
                rag_chunks=[],
                token_usage=mocker.Mock(input_tokens=1, output_tokens=2),
            ),
        )
        mocker.patch(
            f"{MODULE}.extract_text_from_response_items",
            return_value="hello",
        )
        mocker.patch(
            f"{MODULE}.extract_vector_store_ids_from_tools",
            return_value=[],
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )

        api_params, context = build_api_params_and_context(
            updated_request=updated_request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
        )
        response = await handle_non_streaming_response(
            original_request=original_request,
            api_params=api_params,
            context=context,
        )

        assert isinstance(response, ResponsesResponse)
        # Model provider prefix should be stripped when server-substituted
        assert response.model == "gemini-2.5-flash"
        # Client omitted instructions: hide resolved server prompt
        assert response.instructions == SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER
        # MCP output items should be filtered out
        output_types = [item.type for item in response.output]
        assert "mcp_list_tools" not in output_types
        assert "message" in output_types
        assert len(response.output) == 1

    def _make_streaming_completed_chunk(self, mocker: MockerFixture) -> Any:
        """Build a mocked response.completed chunk containing sanitizable fields."""
        completed_chunk = mocker.Mock()
        completed_chunk.type = "response.completed"
        completed_chunk.response = mocker.Mock()
        completed_chunk.response.id = "r1"
        completed_chunk.response.output = []
        completed_chunk.response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        completed_chunk.model_dump.return_value = {
            "type": "response.completed",
            "response": {
                "id": "r1",
                "instructions": SERVER_INSTRUCTIONS,
                "model": MODEL,
                "output": [
                    {
                        "type": "mcp_list_tools",
                        "server_label": "server-a",
                        "tools": [{"name": "search_portal"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hello"}],
                    },
                ],
            },
        }
        return completed_chunk

    @pytest.mark.asyncio
    async def test_streaming_sanitizes_mcp_output_model_and_instructions(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming response.completed sanitizes MCP items, model prefix, and instructions.

        Verifies model prefix stripping, instructions replacement, and MCP output filtering.
        """
        mcp_server = ModelContextProtocolServer(
            name="server-a",
            provider_id="model-context-protocol",
            url="http://mcp.example.com",
        )
        mock_config = mocker.Mock()
        mock_config.mcp_servers = [mcp_server]
        mock_config.quota_limiters = minimal_config.quota_limiters
        mock_config.rag_id_mapping = {}

        original_request = ResponsesRequest(input="Hi")
        updated_request = ResponsesRequest(
            input="Hi",
            model=MODEL,
            instructions=SERVER_INSTRUCTIONS,
            conversation=VALID_CONV_ID_NORMALIZED,
        )
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        completed_chunk = self._make_streaming_completed_chunk(mocker)

        async def mock_stream() -> Any:
            yield completed_chunk

        mock_client.responses.create = mocker.AsyncMock(return_value=mock_stream())

        mocker.patch(f"{MODULE}.configuration", mock_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(f"{MODULE}.extract_token_usage", return_value=mocker.Mock())
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(f"{MODULE}.extract_vector_store_ids_from_tools", return_value=[])
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=TurnSummary(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(
            f"{MODULE}.extract_text_from_response_items",
            return_value="hello",
        )
        mock_holder = mocker.Mock()
        mock_holder.get_client.return_value = mock_client
        mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)

        api_params, context = build_api_params_and_context(
            updated_request=updated_request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
            filter_server_tools=False,
        )
        response = await handle_streaming_response(
            original_request=original_request,
            api_params=api_params,
            context=context,
        )
        collected: list[str] = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        body = "".join(collected)

        assert "response.completed" in body

        for line in body.split("\n"):
            if line.startswith("data: ") and line.strip() != "data: [DONE]":
                data = json.loads(line[len("data: ") :])
                if data.get("type") == "response.completed":
                    resp = data["response"]
                    assert resp["model"] == "gemini-2.5-flash"
                    assert resp["instructions"] == SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER
                    output_types = [item["type"] for item in resp["output"]]
                    assert "mcp_list_tools" not in output_types
                    assert "message" in output_types
                    assert len(resp["output"]) == 1
                    break
        else:
            pytest.fail("response.completed event not found in SSE output")


class TestMcpEventsFilteredUnconditionally:
    """Integration test: MCP events are filtered regardless of X-LCS-Merge-Server-Tools."""

    @pytest.mark.asyncio
    async def test_mcp_events_filtered_without_merge_server_tools_header(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test MCP streaming events are filtered even without X-LCS-Merge-Server-Tools header."""
        mcp_server = ModelContextProtocolServer(
            name="server-a",
            provider_id="model-context-protocol",
            url="http://mcp.example.com",
        )
        mock_config = mocker.Mock()
        mock_config.mcp_servers = [mcp_server]
        mock_config.quota_limiters = minimal_config.quota_limiters
        mock_config.rag_id_mapping = {}

        request = _request_with_model_and_conv("Hi", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mcp_item = mocker.Mock()
        mcp_item.type = "mcp_call"
        mcp_item.server_label = "server-a"

        mcp_added_chunk = mocker.Mock()
        mcp_added_chunk.type = "response.output_item.added"
        mcp_added_chunk.item = mcp_item
        mcp_added_chunk.output_index = 0
        mcp_added_chunk.model_dump.return_value = {
            "type": "response.output_item.added",
            "output_index": 0,
        }

        completed_chunk = mocker.Mock()
        completed_chunk.type = "response.completed"
        completed_chunk.response = mocker.Mock()
        completed_chunk.response.id = "r1"
        completed_chunk.response.output = []
        completed_chunk.response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        completed_chunk.model_dump.return_value = {
            "type": "response.completed",
            "response": {"id": "r1"},
        }

        async def mock_stream() -> Any:
            yield mcp_added_chunk
            yield completed_chunk

        mock_client.responses.create = mocker.AsyncMock(return_value=mock_stream())

        mocker.patch(f"{MODULE}.configuration", mock_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(f"{MODULE}.extract_token_usage", return_value=mocker.Mock())
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(f"{MODULE}.extract_vector_store_ids_from_tools", return_value=[])
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=TurnSummary(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mock_holder = mocker.Mock()
        mock_holder.get_client.return_value = mock_client
        mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)

        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
            filter_server_tools=False,
        )
        response = await handle_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )
        collected: list[str] = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        body = "".join(collected)
        assert "response.output_item.added" not in body
        assert "response.completed" in body

    @pytest.mark.asyncio
    async def test_mcp_events_filtered_with_no_mcp_servers_configured(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that non-MCP output_item.added events pass through when no MCP servers configured.

        When no MCP servers are configured, configured_mcp_labels is empty and no events
        are filtered.
        """
        request = _request_with_model_and_conv("Hi", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        text_item = mocker.Mock()
        text_item.type = "message"

        text_added_chunk = mocker.Mock()
        text_added_chunk.type = "response.output_item.added"
        text_added_chunk.item = text_item
        text_added_chunk.output_index = 0
        text_added_chunk.model_dump.return_value = {
            "type": "response.output_item.added",
            "output_index": 0,
        }

        completed_chunk = mocker.Mock()
        completed_chunk.type = "response.completed"
        completed_chunk.response = mocker.Mock()
        completed_chunk.response.id = "r1"
        completed_chunk.response.output = []
        completed_chunk.response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        completed_chunk.model_dump.return_value = {
            "type": "response.completed",
            "response": {"id": "r1"},
        }

        async def mock_stream() -> Any:
            yield text_added_chunk
            yield completed_chunk

        mock_client.responses.create = mocker.AsyncMock(return_value=mock_stream())

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(f"{MODULE}.extract_token_usage", return_value=mocker.Mock())
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(f"{MODULE}.extract_vector_store_ids_from_tools", return_value=[])
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=TurnSummary(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mock_holder = mocker.Mock()
        mock_holder.get_client.return_value = mock_client
        mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)

        api_params, context = build_api_params_and_context(
            updated_request=request,
            client=mock_client,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            inline_rag_context=RAGContext(),
            filter_server_tools=False,
        )
        response = await handle_streaming_response(
            original_request=request,
            api_params=api_params,
            context=context,
        )
        collected: list[str] = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        body = "".join(collected)
        assert "response.output_item.added" in body
        assert "response.completed" in body
