"""Function to dump the schema of all data models into OpenAPI-compatible format."""

import json

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
    dump_openapi_schema(models, filename)
