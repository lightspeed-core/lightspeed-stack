"""Unit tests for utils/models_dumper module."""

from json import load
from pathlib import Path

from utils.models_dumper import dump_models


def test_dump_models(tmpdir: Path) -> None:
    """Test that models can be dump into a JSON file.

    An example of schema dump:
    {
    "openapi": "3.0.0",
    "info": {
        "title": "Lightspeed Core Stack",
        "version": "0.3.0"
    },
    "components": {
        "schemas": {
            "ConversationSummary": {
                "description": "A single compaction-produced summary chunk.\n\nAttributes:\n",
                "properties": {
                    "summary_text": {
                        "description": "Natural-language summary produced by the ...",
                        "title": "Summary text",
                        "type": "string"
                    },
                    "summarized_through_turn": {
                        "description": "Running total of conversation items consumed by this ...",
                        "minimum": 0,
                        "title": "Summarized through turn",
                        "type": "integer"
                    },
                    "token_count": {
                        "description": "Number of tokens in summary_text.",
                        "minimum": 0,
                        "title": "Token count",
                        "type": "integer"
                    },
                    "created_at": {
                        "description": "ISO 8601 timestamp recording when this summary ...",
                        "title": "Created at",
                        "type": "string"
                    },
                    "model_used": {
                        "description": "Fully-qualified model identifier used for the ...",
                        "title": "Model used",
                        "type": "string"
                    }
                },
                "required": [
                    "summary_text",
                    "summarized_through_turn",
                    "token_count",
                    "created_at",
                    "model_used"
                ],
                "title": "ConversationSummary",
                "type": "object"
            }
        }
    },
    "paths": {}
    }
    """
    filename = tmpdir / "foo.json"
    dump_models(str(filename))

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
        expected_schemas = ("ConversationSummary",)
        for expected_schema in expected_schemas:
            assert expected_schema in schemas
