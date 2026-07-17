"""Function to dump the schema of all data models into OpenAPI-compatible format."""

import lightspeed_stack.models.api.requests
import lightspeed_stack.models.api.responses.error
import lightspeed_stack.models.api.responses.successful
import lightspeed_stack.models.common
import lightspeed_stack.models.common.agents
import lightspeed_stack.models.common.responses
import lightspeed_stack.models.compaction
from lightspeed_stack.utils.openapi_schema_dumper import dump_openapi_schema


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
    models = [lightspeed_stack.models.compaction.ConversationSummary]

    # add all requests data models
    for model in [
        lightspeed_stack.models.api.requests.ConversationUpdateRequest,
        lightspeed_stack.models.api.requests.FeedbackRequest,
        lightspeed_stack.models.api.requests.FeedbackStatusUpdateRequest,
        lightspeed_stack.models.api.requests.MCPServerRegistrationRequest,
        lightspeed_stack.models.api.requests.ModelFilter,
        lightspeed_stack.models.api.requests.PromptCreateRequest,
        lightspeed_stack.models.api.requests.PromptUpdateRequest,
        lightspeed_stack.models.api.requests.QueryRequest,
        lightspeed_stack.models.api.requests.ResponsesRequest,
        lightspeed_stack.models.api.requests.RlsapiV1Attachment,
        lightspeed_stack.models.api.requests.RlsapiV1CLA,
        lightspeed_stack.models.api.requests.RlsapiV1Context,
        lightspeed_stack.models.api.requests.RlsapiV1InferRequest,
        lightspeed_stack.models.api.requests.RlsapiV1SystemInfo,
        lightspeed_stack.models.api.requests.RlsapiV1Terminal,
        lightspeed_stack.models.api.requests.StreamingInterruptRequest,
        lightspeed_stack.models.api.requests.VectorStoreCreateRequest,
        lightspeed_stack.models.api.requests.VectorStoreFileCreateRequest,
        lightspeed_stack.models.api.requests.VectorStoreUpdateRequest,
        lightspeed_stack.models.api.responses.successful.AuthorizedResponse,
        lightspeed_stack.models.api.responses.successful.ConfigurationResponse,
        lightspeed_stack.models.api.responses.successful.ConversationDeleteResponse,
        lightspeed_stack.models.api.responses.successful.ConversationResponse,
        lightspeed_stack.models.api.responses.successful.ConversationUpdateResponse,
        lightspeed_stack.models.api.responses.successful.ConversationsListResponse,
        lightspeed_stack.models.api.responses.successful.ConversationsListResponseV2,
        lightspeed_stack.models.api.responses.successful.FeedbackResponse,
        lightspeed_stack.models.api.responses.successful.FeedbackStatusUpdateResponse,
        lightspeed_stack.models.api.responses.successful.FileResponse,
        lightspeed_stack.models.api.responses.successful.InfoResponse,
        lightspeed_stack.models.api.responses.successful.LivenessResponse,
        lightspeed_stack.models.api.responses.successful.MCPClientAuthOptionsResponse,
        lightspeed_stack.models.api.responses.successful.MCPServerDeleteResponse,
        lightspeed_stack.models.api.responses.successful.MCPServerListResponse,
        lightspeed_stack.models.api.responses.successful.MCPServerRegistrationResponse,
        lightspeed_stack.models.api.responses.successful.ModelsResponse,
        lightspeed_stack.models.api.responses.successful.PromptDeleteResponse,
        lightspeed_stack.models.api.responses.successful.PromptResourceResponse,
        lightspeed_stack.models.api.responses.successful.PromptsListResponse,
        lightspeed_stack.models.api.responses.successful.ProviderResponse,
        lightspeed_stack.models.api.responses.successful.ProvidersListResponse,
        lightspeed_stack.models.api.responses.successful.QueryResponse,
        lightspeed_stack.models.api.responses.successful.RAGInfoResponse,
        lightspeed_stack.models.api.responses.successful.RAGListResponse,
        lightspeed_stack.models.api.responses.successful.ReadinessResponse,
        lightspeed_stack.models.api.responses.successful.ResponsesResponse,
        lightspeed_stack.models.api.responses.successful.RlsapiV1InferData,
        lightspeed_stack.models.api.responses.successful.RlsapiV1InferResponse,
        lightspeed_stack.models.api.responses.successful.ShieldsResponse,
        lightspeed_stack.models.api.responses.successful.StatusResponse,
        lightspeed_stack.models.api.responses.successful.StreamingInterruptResponse,
        lightspeed_stack.models.api.responses.successful.StreamingQueryResponse,
        lightspeed_stack.models.api.responses.successful.ToolsResponse,
        lightspeed_stack.models.api.responses.successful.VectorStoreDeleteResponse,
        lightspeed_stack.models.api.responses.successful.VectorStoreFileDeleteResponse,
        lightspeed_stack.models.api.responses.successful.VectorStoreFileResponse,
        lightspeed_stack.models.api.responses.successful.VectorStoreFilesListResponse,
        lightspeed_stack.models.api.responses.successful.VectorStoreResponse,
        lightspeed_stack.models.api.responses.successful.VectorStoresListResponse,
        lightspeed_stack.models.api.responses.error.AbstractErrorResponse,
        lightspeed_stack.models.api.responses.error.BadRequestResponse,
        lightspeed_stack.models.api.responses.error.ConflictResponse,
        lightspeed_stack.models.api.responses.error.DetailModel,
        lightspeed_stack.models.api.responses.error.FileTooLargeResponse,
        lightspeed_stack.models.api.responses.error.ForbiddenResponse,
        lightspeed_stack.models.api.responses.error.InternalServerErrorResponse,
        lightspeed_stack.models.api.responses.error.NotFoundResponse,
        lightspeed_stack.models.api.responses.error.PromptTooLongResponse,
        lightspeed_stack.models.api.responses.error.QuotaExceededResponse,
        lightspeed_stack.models.api.responses.error.ServiceUnavailableResponse,
        lightspeed_stack.models.api.responses.error.UnauthorizedResponse,
        lightspeed_stack.models.api.responses.error.UnprocessableEntityResponse,
        lightspeed_stack.models.common.Attachment,
        lightspeed_stack.models.common.ConversationData,
        lightspeed_stack.models.common.ConversationDetails,
        lightspeed_stack.models.common.ConversationTurn,
        lightspeed_stack.models.common.MCPListToolsSummary,
        lightspeed_stack.models.common.MCPServerAuthInfo,
        lightspeed_stack.models.common.MCPServerInfo,
        lightspeed_stack.models.common.Message,
        lightspeed_stack.models.common.ProviderHealthStatus,
        lightspeed_stack.models.common.RAGChunk,
        lightspeed_stack.models.common.RAGContext,
        lightspeed_stack.models.common.ReferencedDocument,
        lightspeed_stack.models.common.ShieldModerationBlocked,
        lightspeed_stack.models.common.ShieldModerationPassed,
        lightspeed_stack.models.common.SolrVectorSearchRequest,
        lightspeed_stack.models.common.ToolCallSummary,
        lightspeed_stack.models.common.ToolInfoSummary,
        lightspeed_stack.models.common.ToolResultSummary,
        lightspeed_stack.models.common.Transcript,
        lightspeed_stack.models.common.TranscriptMetadata,
        lightspeed_stack.models.common.TurnSummary,
        lightspeed_stack.models.common.agents.EndEventData,
        lightspeed_stack.models.common.agents.EndStreamPayload,
        lightspeed_stack.models.common.agents.ErrorEventData,
        lightspeed_stack.models.common.agents.ErrorStreamPayload,
        lightspeed_stack.models.common.agents.InterruptedEventData,
        lightspeed_stack.models.common.agents.InterruptedStreamPayload,
        lightspeed_stack.models.common.agents.StartEventData,
        lightspeed_stack.models.common.agents.StartStreamPayload,
        lightspeed_stack.models.common.agents.StreamPayloadBase,
        lightspeed_stack.models.common.agents.TokenChunkData,
        lightspeed_stack.models.common.agents.TokenStreamPayload,
        lightspeed_stack.models.common.agents.ToolCallStreamPayload,
        lightspeed_stack.models.common.agents.ToolResultStreamPayload,
        lightspeed_stack.models.common.agents.TurnCompleteStreamPayload,
        lightspeed_stack.models.common.responses.InputToolMCP,
        lightspeed_stack.models.common.responses.ResponsesApiParams,
    ]:
        models.append(model)
    dump_openapi_schema(models, filename)
