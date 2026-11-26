# Responses contract models

LCORE-owned OpenResponses types used by `ResponsesRequest` and
`ResponsesResponse`. These replace the previous `ogx_api.openai_responses`
imports.

## [content.py](content.py)

Input/output content parts, annotations, and token logprobs.

## [tools.py](tools.py)

Request tools, echoed output tools, and tool-choice.

## [items.py](items.py)

Message, tool-call, approval, and reasoning items; input/output unions.

## [config.py](config.py)

Prompt, text format, reasoning, usage, and error objects.

## [response.py](response.py)

OpenResponses response envelope nested in SSE lifecycle events.

## [events.py](events.py)

OpenResponses SSE event types.
