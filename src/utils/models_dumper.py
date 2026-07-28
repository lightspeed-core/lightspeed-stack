"""Function to dump the schema of all data models into OpenAPI-compatible format."""

from typing import Optional

from pydantic import BaseModel

import models.api.requests as r
import models.api.responses.error as e
import models.api.responses.successful as s
import models.common as c
import models.common.agents as a
import models.common.responses as cr
import models.compaction as models_compaction
from utils.openapi_schema_dumper import dump_openapi_schema

conversation_summary_models: list[type[BaseModel]] = [
    models_compaction.ConversationSummary
]

requests_models: list[type[BaseModel]] = [
    r.ConversationUpdateRequest,
    r.FeedbackRequest,
    r.FeedbackStatusUpdateRequest,
    r.MCPServerRegistrationRequest,
    r.ModelFilter,
    r.PromptCreateRequest,
    r.PromptUpdateRequest,
    r.QueryRequest,
    r.ResponsesRequest,
    r.RlsapiV1Attachment,
    r.RlsapiV1CLA,
    r.RlsapiV1Context,
    r.RlsapiV1InferRequest,
    r.RlsapiV1SystemInfo,
    r.RlsapiV1Terminal,
    r.StreamingInterruptRequest,
    r.VectorStoreCreateRequest,
    r.VectorStoreFileCreateRequest,
    r.VectorStoreUpdateRequest,
]

successful_responses_models: list[type[BaseModel]] = [
    s.AuthorizedResponse,
    s.ConfigurationResponse,
    s.ConversationDeleteResponse,
    s.ConversationResponse,
    s.ConversationUpdateResponse,
    s.ConversationsListResponse,
    s.ConversationsListResponseV2,
    s.FeedbackResponse,
    s.FeedbackStatusUpdateResponse,
    s.FileResponse,
    s.InfoResponse,
    s.LivenessResponse,
    s.MCPClientAuthOptionsResponse,
    s.MCPServerDeleteResponse,
    s.MCPServerListResponse,
    s.MCPServerRegistrationResponse,
    s.ModelsResponse,
    s.PromptDeleteResponse,
    s.PromptResourceResponse,
    s.PromptsListResponse,
    s.ProviderResponse,
    s.ProvidersListResponse,
    s.QueryResponse,
    s.RAGInfoResponse,
    s.RAGListResponse,
    s.ReadinessResponse,
    s.ResponsesResponse,
    s.RlsapiV1InferData,
    s.RlsapiV1InferResponse,
    s.SavedPromptDeleteResponse,
    s.SavedPromptResponse,
    s.SavedPromptsListResponse,
    s.ShieldsResponse,
    s.StatusResponse,
    s.StreamingInterruptResponse,
    s.StreamingQueryResponse,
    s.ToolsResponse,
    s.VectorStoreDeleteResponse,
    s.VectorStoreFileDeleteResponse,
    s.VectorStoreFileResponse,
    s.VectorStoreFilesListResponse,
    s.VectorStoreResponse,
    s.VectorStoresListResponse,
]

error_responses_models: list[type[BaseModel]] = [
    e.AbstractErrorResponse,
    e.BadRequestResponse,
    e.ConflictResponse,
    e.DetailModel,
    e.FileTooLargeResponse,
    e.ForbiddenResponse,
    e.InternalServerErrorResponse,
    e.NotFoundResponse,
    e.PromptTooLongResponse,
    e.QuotaExceededResponse,
    e.ServiceUnavailableResponse,
    e.UnauthorizedResponse,
    e.UnprocessableEntityResponse,
]

common_models: list[type[BaseModel]] = [
    c.Attachment,
    c.ConversationData,
    c.ConversationDetails,
    c.ConversationTurn,
    c.MCPListToolsSummary,
    c.MCPServerAuthInfo,
    c.MCPServerInfo,
    c.Message,
    c.ProviderHealthStatus,
    c.RAGChunk,
    c.RAGContext,
    c.ReferencedDocument,
    c.ShieldModerationBlocked,
    c.ShieldModerationPassed,
    c.SolrVectorSearchRequest,
    c.ToolCallSummary,
    c.ToolInfoSummary,
    c.ToolResultSummary,
    c.Transcript,
    c.TranscriptMetadata,
    c.TurnSummary,
]

agents_models: list[type[BaseModel]] = [
    a.EndEventData,
    a.EndStreamPayload,
    a.ErrorEventData,
    a.ErrorStreamPayload,
    a.InterruptedEventData,
    a.InterruptedStreamPayload,
    a.StartEventData,
    a.StartStreamPayload,
    a.StreamPayloadBase,
    a.TokenChunkData,
    a.TokenStreamPayload,
    a.ToolCallStreamPayload,
    a.ToolResultStreamPayload,
    a.TurnCompleteStreamPayload,
]

common_responses_models: list[type[BaseModel]] = [
    cr.InputToolMCP,
    cr.ResponsesApiParams,
]


def dump_models(filename: str) -> None:
    """Dump the schema of all models into OpenAPI-compatible JSON file.

    Parameters:
    ----------
        - filename: str - name of file to export the schema to

    Returns:
    -------
        - None

    Raises:
    ------
        IOError: If the file cannot be written.
    """
    # construct a list with all models
    models = (
        conversation_summary_models
        + requests_models
        + successful_responses_models
        + error_responses_models
        + common_models
        + agents_models
        + common_responses_models
    )

    # dump all the models into one OpenAPI-compatible JSON file
    dump_openapi_schema(models, filename)


def get_models_for_group(model_group: str) -> list[type[BaseModel]]:
    """Return the list of Pydantic model classes for the given model group.

    Supported groups:
    - "requests"
    - "successful_responses"
    - "error_responses"
    - "common"
    - "agents"
    - "common_responses"

    Parameters:
    ----------
        model_group: The name of the model group to look up.

    Returns:
    -------
        A list of Pydantic model classes belonging to the requested group.

    Raises:
    ------
        Exception: If model_group is not a recognized group name.
    """
    match model_group:
        case "requests":
            return requests_models
        case "successful_responses":
            return successful_responses_models
        case "error_responses":
            return error_responses_models
        case "common":
            return common_models
        case "agents":
            return agents_models
        case "common_responses":
            return common_responses_models
        case _:
            raise ValueError(f"Unknown model group provided: {model_group}")


def dump_models_group(model_group: str, filename: Optional[str] = None) -> None:
    """Dump the schema of selected models group into OpenAPI-compatible JSON file.

    Parameters:
    ----------
        - model_group: str - name of model group to export the schema to

    Returns:
    -------
        - None

    Raises:
    ------
        IOError: If the file cannot be written.
    """
    models = get_models_for_group(model_group)

    if filename is None:
        filename = f"{model_group}.json"

    # dump all selected models into one OpenAPI-compatible JSON file
    dump_openapi_schema(models, filename)
