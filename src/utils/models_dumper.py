"""Function to dump the schema of all data models into OpenAPI-compatible format."""

import models.compaction as models_compaction
import models.api.requests as r
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
    ]:
        models.append(model)
    dump_openapi_schema(models, filename)
