"""OpenAPI-only metadata for A2A JSON-RPC routes."""

from typing import Any, Final

from constants import MEDIA_TYPE_EVENT_STREAM, MEDIA_TYPE_JSON

# 200 may be buffered JSON-RPC (application/json) or SSE (text/event-stream).
a2a_jsonrpc_responses: Final[dict[int | str, dict[str, Any]]] = {
    200: {
        "description": (
            "Successful response: buffered JSON-RPC or HTTP payload for "
            "non-streaming calls, or a Server-Sent Events stream when the "
            "JSON-RPC method is message/stream."
        ),
        "content": {
            MEDIA_TYPE_JSON: {
                "schema": {
                    "type": "object",
                    "description": "JSON-RPC 2.0 response or A2A-over-HTTP payload",
                },
                "example": {"jsonrpc": "2.0", "id": "1", "result": {}},
            },
            MEDIA_TYPE_EVENT_STREAM: {
                "schema": {
                    "type": "string",
                    "format": MEDIA_TYPE_EVENT_STREAM,
                },
                "example": 'data: {"jsonrpc":"2.0","id":"1","result":{}}\n\n',
            },
        },
    },
}
