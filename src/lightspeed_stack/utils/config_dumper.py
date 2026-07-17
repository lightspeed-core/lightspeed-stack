"""Function to dump the configuration schema into OpenAPI-compatible format."""

from lightspeed_stack.models.config import Configuration
from lightspeed_stack.utils.openapi_schema_dumper import dump_openapi_schema


def dump_schema(filename: str) -> None:
    """Dump the configuration schema into OpenAPI-compatible JSON file.

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
    models = [Configuration]
    dump_openapi_schema(models, filename)
