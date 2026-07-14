"""Unit tests for utils/config_dumper module."""

from json import load
from pathlib import Path

from utils.config_dumper import dump_schema


def test_dump_schema(tmpdir: Path) -> None:
    """Test that schema can be dump into a JSON file.

    An example of schema dump:
    {
        "openapi": "3.0.0",
        "info": {
            "title": "Lightspeed Core Stack",
            "version": "0.3.0"
        },
        "components": {
            "schemas": {
                "A2AStateConfiguration": {
                    "additionalProperties": false,
                    "description": "xyzzy",
                    "properties": {
                        "sqlite": {
                            "anyOf": [
                                {
                                    "$ref": "#/components/schemas/SQLiteDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "SQLite database configuration for A2A state storage.",
                            "title": "SQLite configuration"
                        },
                    ...
                }
                ...
                ...
                ...
        },
        "paths": {}
    }
    """
    filename = tmpdir / "foo.json"
    dump_schema(str(filename))

    with open(filename, "r", encoding="utf-8") as fin:
        # schema should be stored in JSON format
        content = load(fin)
        assert content is not None

        # top-level keys test
        keys = ("openapi", "info", "components", "paths")
        for key in keys:
            assert key in content

        # components should be top-level node
        components = content["components"]
        assert components is not None

        # schemas should be a node stored inside components node
        assert "schemas" in components
        schemas = components["schemas"]
        assert schemas is not None

        # list of schemas expected in a dump
        expected_schemas = (
            "A2AStateConfiguration",
            "APIKeyTokenConfiguration",
            "AccessRule",
            "Action",
            "ApprovalFilter",
            "ApprovalsConfiguration",
            "AuthenticationConfiguration",
            "AuthorizationConfiguration",
            "AzureEntraIdConfiguration",
            "ByokRag",
            "CORSConfiguration",
            "CompactionConfiguration",
            "Configuration",
            "ConversationHistoryConfiguration",
            "CustomProfile",
            "Customization",
            "DatabaseConfiguration",
            "InMemoryCacheConfig",
            "InferenceConfiguration",
            "JsonPathOperator",
            "JwkConfiguration",
            "JwtConfiguration",
            "JwtRoleRule",
            "LlamaStackConfiguration",
            "ModelContextProtocolServer",
            "OkpConfiguration",
            "PostgreSQLDatabaseConfiguration",
            "QuotaHandlersConfiguration",
            "QuotaLimiterConfiguration",
            "QuotaSchedulerConfiguration",
            "RHIdentityConfiguration",
            "RagConfiguration",
            "RerankerConfiguration",
            "RlsapiV1Configuration",
            "SQLiteDatabaseConfiguration",
            "ServiceConfiguration",
            "SkillsConfiguration",
            "SplunkConfiguration",
            "TLSConfiguration",
            "UserDataCollection",
        )
        for expected_schema in expected_schemas:
            assert expected_schema in schemas
