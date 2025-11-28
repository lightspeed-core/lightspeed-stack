# pylint: disable=unsupported-membership-test,unsubscriptable-object, too-many-lines

"""Unit tests for all successful response models."""

from typing import Any

import pytest
from pydantic import AnyUrl, ValidationError
from pydantic_core import SchemaError

from models.config import (
    Configuration,
    LlamaStackConfiguration,
    ServiceConfiguration,
    UserDataCollection,
)
from models.responses import (
    AbstractSuccessfulResponse,
    AuthorizedResponse,
    ConfigurationResponse,
    ConversationData,
    ConversationDeleteResponse,
    ConversationDetails,
    ConversationResponse,
    ConversationsListResponse,
    ConversationsListResponseV2,
    ConversationUpdateResponse,
    FeedbackResponse,
    FeedbackStatusUpdateResponse,
    InfoResponse,
    LivenessResponse,
    ModelsResponse,
    ProviderHealthStatus,
    ProviderResponse,
    ProvidersListResponse,
    QueryResponse,
    RAGChunk,
    ReadinessResponse,
    ReferencedDocument,
    ShieldsResponse,
    StatusResponse,
    StreamingQueryResponse,
    ToolCall,
    ToolsResponse,
)


class TestModelsResponse:
    """Test cases for ModelsResponse."""

    def test_constructor(self) -> None:
        """Test ModelsResponse with valid models list."""
        models = [
            {
                "identifier": "openai/gpt-4-turbo",
                "metadata": {},
                "api_model_type": "llm",
                "provider_id": "openai",
                "type": "model",
                "provider_resource_id": "gpt-4-turbo",
                "model_type": "llm",
            }
        ]
        response = ModelsResponse(models=models)
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.models == models
        assert len(response.models) == 1

    def test_empty_models_list(self) -> None:
        """Test ModelsResponse with empty models list."""
        response = ModelsResponse(models=[])
        assert response.models == []
        assert len(response.models) == 0

    def test_multiple_models(self) -> None:
        """Test ModelsResponse with multiple models."""
        models = [
            {"identifier": "model1", "provider_id": "provider1"},
            {"identifier": "model2", "provider_id": "provider2"},
        ]
        response = ModelsResponse(models=models)
        assert len(response.models) == 2

    def test_missing_required_parameter(self) -> None:
        """Test ModelsResponse raises ValidationError when models is missing."""
        with pytest.raises(ValidationError):
            ModelsResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ModelsResponse.openapi_response() method."""
        schema = ModelsResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ModelsResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ModelsResponse
        assert "content" in result
        assert "application/json" in result["content"]

        # For single-example responses, check "example" key exists
        assert "example" in result["content"]["application/json"]
        example = result["content"]["application/json"]["example"]
        assert "models" in example
        assert isinstance(example["models"], list)

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestToolsResponse:
    """Test cases for ToolsResponse."""

    def test_constructor(self) -> None:
        """Test ToolsResponse with valid tools list."""
        tools = [
            {
                "identifier": "filesystem_read",
                "description": "Read contents of a file",
                "parameters": [],
                "provider_id": "mcp",
                "type": "tool",
            }
        ]
        response = ToolsResponse(tools=tools)
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.tools == tools

    def test_empty_tools_list(self) -> None:
        """Test ToolsResponse with empty tools list."""
        response = ToolsResponse(tools=[])
        assert response.tools == []

    def test_missing_required_parameter(self) -> None:
        """Test ToolsResponse raises ValidationError when tools is missing."""
        with pytest.raises(ValidationError):
            ToolsResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ToolsResponse.openapi_response() method."""
        schema = ToolsResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ToolsResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ToolsResponse
        assert "example" in result["content"]["application/json"]
        assert "tools" in result["content"]["application/json"]["example"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestShieldsResponse:
    """Test cases for ShieldsResponse."""

    def test_constructor(self) -> None:
        """Test ShieldsResponse with valid shields list."""
        shields = [{"name": "shield1", "status": "active"}]
        response = ShieldsResponse(shields=shields)
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.shields == shields

    def test_missing_required_parameter(self) -> None:
        """Test ShieldsResponse raises ValidationError when shields is missing."""
        with pytest.raises(ValidationError):
            ShieldsResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ShieldsResponse.openapi_response() method."""
        schema = ShieldsResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ShieldsResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ShieldsResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestProvidersListResponse:
    """Test cases for ProvidersListResponse."""

    def test_constructor(self) -> None:
        """Test ProvidersListResponse with valid providers dict."""
        providers = {
            "inference": [{"provider_id": "openai", "provider_type": "remote::openai"}]
        }
        response = ProvidersListResponse(providers=providers)
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.providers == providers

    def test_empty_providers(self) -> None:
        """Test ProvidersListResponse with empty providers dict."""
        response = ProvidersListResponse(providers={})
        assert response.providers == {}

    def test_missing_required_parameter(self) -> None:
        """Test ProvidersListResponse raises ValidationError when providers is missing."""
        with pytest.raises(ValidationError):
            ProvidersListResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ProvidersListResponse.openapi_response() method."""
        schema = ProvidersListResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ProvidersListResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ProvidersListResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestProviderResponse:
    """Test cases for ProviderResponse."""

    def test_constructor(self) -> None:
        """Test ProviderResponse with all required fields."""
        response = ProviderResponse(
            api="inference",
            config={"api_key": "test"},
            health={"status": "OK"},
            provider_id="openai",
            provider_type="remote::openai",
        )
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.api == "inference"
        assert response.config == {"api_key": "test"}
        assert response.health == {"status": "OK"}
        assert response.provider_id == "openai"
        assert response.provider_type == "remote::openai"

    def test_missing_required_parameters(self) -> None:
        """Test ProviderResponse raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ProviderResponse()  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            ProviderResponse(api="inference")  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ProviderResponse.openapi_response() method."""
        schema = ProviderResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ProviderResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ProviderResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestQueryResponse:
    """Test cases for QueryResponse."""

    def test_constructor_minimal(self) -> None:
        """Test QueryResponse with only required fields."""
        response_obj = QueryResponse(response="Test response")  # type: ignore[call-arg]
        assert isinstance(response_obj, AbstractSuccessfulResponse)
        assert response_obj.response == "Test response"
        assert response_obj.conversation_id is None
        assert response_obj.rag_chunks == []
        assert response_obj.tool_calls is None
        assert response_obj.referenced_documents == []
        assert response_obj.truncated is False
        assert response_obj.input_tokens == 0
        assert response_obj.output_tokens == 0
        assert response_obj.available_quotas == {}

    def test_constructor_full(self) -> None:
        """Test QueryResponse with all fields."""
        rag_chunks = [RAGChunk(content="chunk1", source="doc1", score=0.9)]
        tool_calls = [
            ToolCall(tool_name="tool1", arguments={"arg": "value"}, result=None)
        ]
        referenced_docs = [
            ReferencedDocument(doc_url=AnyUrl("https://example.com"), doc_title="Doc")
        ]

        response = QueryResponse(  # type: ignore[call-arg]
            conversation_id="conv-123",
            response="Test response",
            rag_chunks=rag_chunks,
            tool_calls=tool_calls,
            referenced_documents=referenced_docs,
            truncated=True,
            input_tokens=100,
            output_tokens=50,
            available_quotas={"daily": 1000},
        )
        assert response.conversation_id == "conv-123"
        assert response.rag_chunks == rag_chunks
        assert response.tool_calls == tool_calls
        assert response.referenced_documents == referenced_docs
        assert response.truncated is True
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.available_quotas == {"daily": 1000}

    def test_missing_required_parameter(self) -> None:
        """Test QueryResponse raises ValidationError when response is missing."""
        with pytest.raises(ValidationError):
            QueryResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test QueryResponse.openapi_response() method."""
        schema = QueryResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = QueryResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == QueryResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestInfoResponse:
    """Test cases for InfoResponse."""

    def test_constructor(self) -> None:
        """Test InfoResponse with all fields."""
        response = InfoResponse(
            name="Lightspeed Stack",
            service_version="1.0.0",
            llama_stack_version="1.0.0",
        )
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.name == "Lightspeed Stack"
        assert response.service_version == "1.0.0"
        assert response.llama_stack_version == "1.0.0"

    def test_missing_required_parameters(self) -> None:
        """Test InfoResponse raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            InfoResponse()  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            InfoResponse(name="Test")  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test InfoResponse.openapi_response() method."""
        schema = InfoResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = InfoResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == InfoResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestReadinessResponse:
    """Test cases for ReadinessResponse."""

    def test_constructor_ready(self) -> None:
        """Test ReadinessResponse when service is ready."""
        response = ReadinessResponse(
            ready=True, reason="Service is ready", providers=[]
        )
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.ready is True
        assert response.reason == "Service is ready"
        assert response.providers == []

    def test_constructor_not_ready(self) -> None:
        """Test ReadinessResponse when service is not ready."""
        providers = [
            ProviderHealthStatus(
                provider_id="provider1", status="unhealthy", message="Error"
            )
        ]
        response = ReadinessResponse(
            ready=False, reason="Service is not ready", providers=providers
        )
        assert response.ready is False
        assert len(response.providers) == 1
        assert response.providers[0].provider_id == "provider1"

    def test_missing_required_parameters(self) -> None:
        """Test ReadinessResponse raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ReadinessResponse()  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            ReadinessResponse(ready=True)  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ReadinessResponse.openapi_response() method."""
        schema = ReadinessResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ReadinessResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ReadinessResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestLivenessResponse:
    """Test cases for LivenessResponse."""

    def test_constructor_alive(self) -> None:
        """Test LivenessResponse when service is alive."""
        response = LivenessResponse(alive=True)
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.alive is True

    def test_constructor_not_alive(self) -> None:
        """Test LivenessResponse when service is not alive."""
        response = LivenessResponse(alive=False)
        assert response.alive is False

    def test_missing_required_parameter(self) -> None:
        """Test LivenessResponse raises ValidationError when alive is missing."""
        with pytest.raises(ValidationError):
            LivenessResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test LivenessResponse.openapi_response() method."""
        schema = LivenessResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = LivenessResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == LivenessResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestFeedbackResponse:
    """Test cases for FeedbackResponse."""

    def test_constructor(self) -> None:
        """Test FeedbackResponse with response message."""
        response = FeedbackResponse(response="feedback received")
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.response == "feedback received"

    def test_missing_required_parameter(self) -> None:
        """Test FeedbackResponse raises ValidationError when response is missing."""
        with pytest.raises(ValidationError):
            FeedbackResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test FeedbackResponse.openapi_response() method."""
        schema = FeedbackResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = FeedbackResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == FeedbackResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestStatusResponse:
    """Test cases for StatusResponse."""

    def test_constructor_feedback_enabled(self) -> None:
        """Test the StatusResponse constructor."""
        sr = StatusResponse(functionality="feedback", status={"enabled": True})
        assert sr.functionality == "feedback"
        assert sr.status == {"enabled": True}
        assert isinstance(sr, AbstractSuccessfulResponse)

    def test_constructor_feedback_disabled(self) -> None:
        """Test the StatusResponse constructor."""
        sr = StatusResponse(functionality="feedback", status={"enabled": False})
        assert sr.functionality == "feedback"
        assert sr.status == {"enabled": False}
        assert isinstance(sr, AbstractSuccessfulResponse)

    def test_missing_required_parameters(self) -> None:
        """Test StatusResponse raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            StatusResponse()  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            StatusResponse(functionality="feedback")  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test StatusResponse.openapi_response() method."""
        schema = StatusResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = StatusResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == StatusResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestAuthorizedResponse:
    """Test cases for AuthorizedResponse."""

    def test_constructor(self) -> None:
        """Test AuthorizedResponse with all fields."""
        response = AuthorizedResponse(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            username="user1",
            skip_userid_check=False,
        )
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert response.username == "user1"
        assert response.skip_userid_check is False

    def test_skip_userid_check_true(self) -> None:
        """Test AuthorizedResponse with skip_userid_check=True."""
        response = AuthorizedResponse(
            user_id="user-123", username="test", skip_userid_check=True
        )
        assert response.skip_userid_check is True

    def test_missing_required_parameters(self) -> None:
        """Test AuthorizedResponse raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            AuthorizedResponse()  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            AuthorizedResponse(user_id="user-123")  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test AuthorizedResponse.openapi_response() method."""
        schema = AuthorizedResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = AuthorizedResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == AuthorizedResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1

    def test_constructor_fields_required(self) -> None:
        """Test the AuthorizedResponse constructor."""
        with pytest.raises(ValidationError):
            # missing all parameters
            _ = AuthorizedResponse()  # pyright: ignore

        with pytest.raises(ValidationError):
            # missing user_id parameter
            _ = AuthorizedResponse(username="testuser")  # pyright: ignore

        with pytest.raises(ValidationError):
            # missing username parameter
            _ = AuthorizedResponse(
                user_id="123e4567-e89b-12d3-a456-426614174000"
            )  # pyright: ignore


class TestConversationResponse:
    """Test cases for ConversationResponse."""

    def test_constructor(self) -> None:
        """Test ConversationResponse with conversation_id and chat_history."""
        chat_history = [
            {
                "messages": [
                    {"content": "Hello", "type": "user"},
                    {"content": "Hi there!", "type": "assistant"},
                ],
                "started_at": "2024-01-01T00:01:00Z",
                "completed_at": "2024-01-01T00:01:05Z",
            }
        ]
        response = ConversationResponse(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            chat_history=chat_history,
        )
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert response.chat_history == chat_history

    def test_empty_chat_history(self) -> None:
        """Test ConversationResponse with empty chat_history."""
        response = ConversationResponse(conversation_id="conv-123", chat_history=[])
        assert response.chat_history == []

    def test_missing_required_parameters(self) -> None:
        """Test ConversationResponse raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ConversationResponse()  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            ConversationResponse(conversation_id="conv-123")  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ConversationResponse.openapi_response() method."""
        schema = ConversationResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ConversationResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ConversationResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestConversationDeleteResponse:
    """Test cases for ConversationDeleteResponse."""

    def test_constructor_deleted(self) -> None:
        """Test ConversationDeleteResponse when conversation is deleted."""
        response = ConversationDeleteResponse(
            deleted=True, conversation_id="123e4567-e89b-12d3-a456-426614174000"
        )
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert response.success is True
        assert response.response == "Conversation deleted successfully"

    def test_constructor_not_deleted(self) -> None:
        """Test ConversationDeleteResponse when conversation cannot be deleted."""
        response = ConversationDeleteResponse(deleted=False, conversation_id="conv-123")
        assert response.success is True
        assert response.response == "Conversation cannot be deleted"

    def test_missing_required_parameters(self) -> None:
        """Test ConversationDeleteResponse raises ValidationError when required fields missing."""
        with pytest.raises(TypeError):
            ConversationDeleteResponse()  # pylint: disable=missing-kwoa
        with pytest.raises(TypeError):
            ConversationDeleteResponse(deleted=True)  # pylint: disable=missing-kwoa

    def test_openapi_response(self) -> None:
        """Test ConversationDeleteResponse.openapi_response() method."""
        schema = ConversationDeleteResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ConversationDeleteResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ConversationDeleteResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 2

        # Verify all labeled examples are present
        assert "deleted" in examples
        assert "not found" in examples

        # Verify example structure for "deleted" example
        deleted_example = examples["deleted"]
        assert "value" in deleted_example
        assert (
            deleted_example["value"]["conversation_id"]
            == "123e4567-e89b-12d3-a456-426614174000"
        )
        assert deleted_example["value"]["success"] is True
        assert (
            deleted_example["value"]["response"] == "Conversation deleted successfully"
        )

        # Verify example structure for "not found" example
        not_found_example = examples["not found"]
        assert "value" in not_found_example
        assert not_found_example["value"]["conversation_id"] == (
            "123e4567-e89b-12d3-a456-426614174000"
        )
        assert not_found_example["value"]["success"] is True
        assert (
            not_found_example["value"]["response"] == "Conversation can not be deleted"
        )

    def test_openapi_response_missing_label(self) -> None:
        """Test openapi_response() raises SchemaError when example has no label."""

        class InvalidResponse(ConversationDeleteResponse):
            """Class with invalid examples (missing label)."""

            model_config = {
                "json_schema_extra": {
                    "examples": [
                        {
                            # Missing "label" key
                            "value": {
                                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                                "success": True,
                                "response": "Conversation deleted successfully",
                            },
                        },
                    ]
                }
            }

        with pytest.raises(SchemaError, match="has no label"):
            InvalidResponse.openapi_response()

    def test_openapi_response_missing_value(self) -> None:
        """Test openapi_response() raises SchemaError when example has no value."""

        class InvalidResponse(ConversationDeleteResponse):
            """Class with invalid examples (missing value)."""

            model_config = {
                "json_schema_extra": {
                    "examples": [
                        {
                            "label": "deleted",
                            # Missing "value" key
                        },
                    ]
                }
            }

        with pytest.raises(SchemaError, match="has no value"):
            InvalidResponse.openapi_response()


class TestConversationsListResponse:
    """Test cases for ConversationsListResponse."""

    def test_constructor(self) -> None:
        """Test ConversationsListResponse with conversation details."""
        conversations = [
            ConversationDetails(
                conversation_id="123e4567-e89b-12d3-a456-426614174000",
                created_at="2024-01-01T00:00:00Z",
                last_message_at="2024-01-01T00:05:00Z",
                message_count=5,
                last_used_model="gpt-4",
                last_used_provider="openai",
                topic_summary="Test topic",
            )
        ]
        response = ConversationsListResponse(conversations=conversations)
        assert isinstance(response, AbstractSuccessfulResponse)
        assert len(response.conversations) == 1
        assert (
            response.conversations[0].conversation_id
            == "123e4567-e89b-12d3-a456-426614174000"
        )

    def test_empty_conversations(self) -> None:
        """Test ConversationsListResponse with empty conversations list."""
        response = ConversationsListResponse(conversations=[])
        assert response.conversations == []

    def test_missing_required_parameter(self) -> None:
        """Test ConversationsListResponse raises ValidationError when conversations is missing."""
        with pytest.raises(ValidationError):
            ConversationsListResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ConversationsListResponse.openapi_response() method."""
        schema = ConversationsListResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ConversationsListResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ConversationsListResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestConversationsListResponseV2:
    """Test cases for ConversationsListResponseV2."""

    def test_constructor(self) -> None:
        """Test ConversationsListResponseV2 with conversation data."""
        conversations = [
            ConversationData(
                conversation_id="123e4567-e89b-12d3-a456-426614174000",
                topic_summary="Test topic",
                last_message_timestamp=1704067200.0,
            )
        ]
        response = ConversationsListResponseV2(conversations=conversations)
        assert isinstance(response, AbstractSuccessfulResponse)
        assert len(response.conversations) == 1
        assert (
            response.conversations[0].conversation_id
            == "123e4567-e89b-12d3-a456-426614174000"
        )

    def test_conversation_with_none_topic(self) -> None:
        """Test ConversationsListResponseV2 with conversation having None topic_summary."""
        conversations = [
            ConversationData(
                conversation_id="conv-123",
                topic_summary=None,
                last_message_timestamp=1704067200.0,
            )
        ]
        response = ConversationsListResponseV2(conversations=conversations)
        assert response.conversations[0].topic_summary is None

    def test_missing_required_parameter(self) -> None:
        """Test ConversationsListResponseV2 raises ValidationError when conversations is missing."""
        with pytest.raises(ValidationError):
            ConversationsListResponseV2()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ConversationsListResponseV2.openapi_response() method."""
        schema = ConversationsListResponseV2.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ConversationsListResponseV2.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ConversationsListResponseV2
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestFeedbackStatusUpdateResponse:
    """Test cases for FeedbackStatusUpdateResponse."""

    def test_constructor(self) -> None:
        """Test FeedbackStatusUpdateResponse with status dict."""
        status_dict = {
            "previous_status": True,
            "updated_status": False,
            "updated_by": "user/test",
            "timestamp": "2023-03-15 12:34:56",
        }
        response = FeedbackStatusUpdateResponse(status=status_dict)
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.status == status_dict

    def test_missing_required_parameter(self) -> None:
        """Test FeedbackStatusUpdateResponse raises ValidationError when status is missing."""
        with pytest.raises(ValidationError):
            FeedbackStatusUpdateResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test FeedbackStatusUpdateResponse.openapi_response() method."""
        schema = FeedbackStatusUpdateResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = FeedbackStatusUpdateResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == FeedbackStatusUpdateResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestConversationUpdateResponse:
    """Test cases for ConversationUpdateResponse."""

    def test_constructor_success(self) -> None:
        """Test ConversationUpdateResponse with successful update."""
        response = ConversationUpdateResponse(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            success=True,
            message="Topic summary updated successfully",
        )
        assert isinstance(response, AbstractSuccessfulResponse)
        assert response.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert response.success is True
        assert response.message == "Topic summary updated successfully"

    def test_constructor_failure(self) -> None:
        """Test ConversationUpdateResponse with failed update."""
        response = ConversationUpdateResponse(
            conversation_id="conv-123", success=False, message="Update failed"
        )
        assert response.success is False
        assert response.message == "Update failed"

    def test_missing_required_parameters(self) -> None:
        """Test ConversationUpdateResponse raises ValidationError when required fields missing."""
        with pytest.raises(ValidationError):
            ConversationUpdateResponse()  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            ConversationUpdateResponse(conversation_id="conv-123")  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ConversationUpdateResponse.openapi_response() method."""
        schema = ConversationUpdateResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ConversationUpdateResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ConversationUpdateResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestConfigurationResponse:
    """Test cases for ConfigurationResponse."""

    def test_constructor(self) -> None:
        """Test ConfigurationResponse with Configuration object."""
        # Create a minimal Configuration object for testing
        config = Configuration(
            name="test",
            service=ServiceConfiguration(host="localhost", port=8080),
            llama_stack=LlamaStackConfiguration(url="http://localhost:8321"),
            user_data_collection=UserDataCollection(feedback_enabled=False),
        )
        response = ConfigurationResponse(configuration=config)
        assert isinstance(response, AbstractSuccessfulResponse)
        assert isinstance(response.configuration, Configuration)
        assert response.configuration.name == "test"

    def test_missing_required_parameter(self) -> None:
        """Test ConfigurationResponse raises ValidationError when configuration is missing."""
        with pytest.raises(ValidationError):
            ConfigurationResponse()  # type: ignore[call-arg]

    def test_openapi_response(self) -> None:
        """Test ConfigurationResponse.openapi_response() method."""
        schema = ConfigurationResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ConfigurationResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == ConfigurationResponse
        assert "example" in result["content"]["application/json"]

        # Verify example count matches schema examples count (should be 1)
        assert expected_count == 1


class TestStreamingQueryResponse:
    """Test cases for StreamingQueryResponse."""

    def test_openapi_response_structure(self) -> None:
        """Test that openapi_response() returns correct structure."""
        result = StreamingQueryResponse.openapi_response()

        assert "description" in result
        assert "content" in result
        assert result["description"] == "Successful response"
        assert "model" not in result

        assert "text/event-stream" in result["content"]
        content = result["content"]["text/event-stream"]
        assert "schema" in content
        assert "example" in content

        schema = content["schema"]
        assert schema["type"] == "string"
        assert schema["format"] == "text/event-stream"

    def test_model_json_schema_has_examples(self) -> None:
        """Test that model_json_schema() includes examples."""
        schema = StreamingQueryResponse.model_json_schema()
        assert "examples" in schema
        assert len(schema["examples"]) == 1
        assert isinstance(schema["examples"][0], str)


class TestAbstractSuccessfulResponseOpenAPI:
    """Test cases for AbstractSuccessfulResponse.openapi_response() edge cases."""

    def test_openapi_response_requires_examples(self) -> None:
        """Test that openapi_response raises SchemaError if no examples found."""

        # Create a class without examples
        class NoExamplesResponse(AbstractSuccessfulResponse):
            """Class without examples."""

            field: str = "test"
            model_config: dict[str, Any] = {"json_schema_extra": {}}

        with pytest.raises(SchemaError, match="Examples not found"):
            NoExamplesResponse.openapi_response()

    def test_openapi_response_structure(self) -> None:
        """Test that openapi_response returns correct structure."""
        result = ModelsResponse.openapi_response()
        assert "description" in result
        assert "model" in result
        assert "content" in result
        assert result["description"] == "Successful response"
        assert result["model"] == ModelsResponse
        assert "application/json" in result["content"]
        assert "example" in result["content"]["application/json"]
