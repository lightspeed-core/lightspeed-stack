"""Function to dump the schema of all data models into OpenAPI-compatible format."""

import models.api.requests as r
import models.api.responses.error as e
import models.api.responses.successful as s
import models.common as c
import models.common.agents as a
import models.common.responses as cr
import models.compaction as models_compaction
from utils.openapi_schema_dumper import dump_openapi_schema


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
    models = [models_compaction.ConversationSummary]

    # add all requests data models
    for model in [
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
        c.CatalogShield,
        c.ShieldModerationBlocked,
        c.ShieldModerationPassed,
        c.SolrVectorSearchRequest,
        c.ToolCallSummary,
        c.ToolInfoSummary,
        c.ToolResultSummary,
        c.Transcript,
        c.TranscriptMetadata,
        c.TurnSummary,
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
        cr.InputToolMCP,
        cr.ResponsesApiParams,
    ]:
        models.append(model)
    dump_openapi_schema(models, filename)
