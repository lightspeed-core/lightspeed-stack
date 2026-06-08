"""Llama Stack Responses model adapter for pydantic-ai.

Patches client.responses.create to reorder streaming tool-call events and to
persist compacted conversation turns when the conversation parameter is omitted
from inference requests.
"""

from __future__ import annotations as _annotations

from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Optional, Self, cast

from llama_stack_client import AsyncLlamaStackClient
from openai import AsyncStream
from openai.types import responses
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.settings import ModelSettings

from log import get_logger
from models.common.responses.types import ResponseInput
from utils.conversations import append_turn_items_to_conversation

logger = get_logger(__name__)


@dataclass
class CompactionTurnContext:
    """Mutable state for manually persisting compacted agent turns.

    latest_round_input is initialized to the real user query. The create patch
    leaves it unchanged on the first LLM round, then records pydantic-ai input
    for follow-up rounds after that turn is persisted.

    Attributes:
        client: Llama Stack client used to append conversation items.
        conversation_id: Conversation to store turns against.
        latest_round_input: Input stored for the current or next inference round.
        original_input_persisted: Whether the first compacted round was appended.
    """

    client: AsyncLlamaStackClient
    conversation_id: str
    latest_round_input: ResponseInput
    original_input_persisted: bool = False


class _NormalizedLlamaStackStream:
    """AsyncStream wrapper that normalizes Llama Stack response events.

    Buffers early tool-call argument deltas and replays them after the matching
    output item is announced. Optionally appends completed turns when compacted.
    """

    def __init__(
        self,
        source: AsyncStream[responses.ResponseStreamEvent],
        compaction: Optional[CompactionTurnContext] = None,
    ) -> None:
        """Initialize the stream wrapper.

        Args:
            source: Raw Responses API stream from the OpenAI SDK.
            compaction: Compaction state for turn persistence, if active.
        """
        self._source = source
        self._compaction = compaction
        self._announced_item_ids: set[str] = set()
        self._buffered_deltas: dict[
            str, list[responses.ResponseFunctionCallArgumentsDeltaEvent]
        ] = defaultdict(list)

    async def close(self) -> None:
        """Close the underlying SDK stream."""
        await self._source.close()

    async def __aenter__(self) -> Self:
        """Enter the underlying stream context manager."""
        await self._source.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit the underlying stream context manager."""
        await self._source.__aexit__(*args)

    def __aiter__(self) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Return an async iterator over normalized stream events."""
        return self._iter_normalized_events()

    async def _iter_normalized_events(
        self,
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Yield stream events in the order expected by pydantic-ai."""
        async for event in self._source:
            if isinstance(event, responses.ResponseOutputItemAddedEvent):
                if (
                    isinstance(event.item, responses.ResponseFunctionToolCall)
                    and event.item.id
                ):
                    item_id = event.item.id
                    self._announced_item_ids.add(item_id)
                    yield event
                    for delta in self._replay_function_tool_deltas(item_id):
                        yield delta
                    continue

                if isinstance(event.item, responses.response_output_item.McpCall):
                    item_id = event.item.id
                    self._announced_item_ids.add(item_id)
                    yield event
                    for delta in self._replay_mcp_tool_deltas(item_id):
                        yield delta
                    continue

            elif isinstance(event, responses.ResponseFunctionCallArgumentsDeltaEvent):
                if event.item_id not in self._announced_item_ids:
                    logger.debug(
                        "Buffering early argument delta for unannounced item_id=%s",
                        event.item_id,
                    )
                    self._buffered_deltas[event.item_id].append(event)
                    continue

            if (
                isinstance(event, responses.ResponseCompletedEvent)
                and self._compaction is not None
            ):
                compaction = self._compaction
                await append_turn_items_to_conversation(
                    compaction.client,
                    compaction.conversation_id,
                    compaction.latest_round_input,
                    cast(Sequence[Any], event.response.output),
                )
                compaction.original_input_persisted = True

            yield event

    def _replay_function_tool_deltas(
        self, item_id: str
    ) -> list[responses.ResponseFunctionCallArgumentsDeltaEvent]:
        """Return buffered deltas for a function tool-call item.

        Args:
            item_id: Output item id from ResponseOutputItemAddedEvent.

        Returns:
            Buffered argument delta events for the item, if any.
        """
        buffered = self._buffered_deltas.pop(item_id, [])
        if buffered:
            logger.debug(
                "Replaying %d buffered argument deltas for item_id=%s",
                len(buffered),
                item_id,
            )
        return buffered

    def _replay_mcp_tool_deltas(
        self, item_id: str
    ) -> list[responses.ResponseFunctionCallArgumentsDeltaEvent]:
        """Return buffered MCP deltas as a single function-call delta event.

        Args:
            item_id: MCP output item id from ResponseOutputItemAddedEvent.

        Returns:
            A one-element list with a synthetic delta for pydantic-ai, or empty.
        """
        buffered = self._buffered_deltas.pop(item_id, [])
        if not buffered:
            return []

        combined_args = "".join(delta.delta for delta in buffered) + "}"
        logger.debug(
            "Replaying %d buffered MCP argument deltas as single event "
            "for item_id=%s-call",
            len(buffered),
            item_id,
        )
        return [
            responses.ResponseFunctionCallArgumentsDeltaEvent(
                delta=combined_args,
                item_id=f"{item_id}-call",
                output_index=buffered[0].output_index,
                sequence_number=buffered[-1].sequence_number + 1,
                type="response.function_call_arguments.delta",
            )
        ]


class LlamaStackResponsesModel(OpenAIResponsesModel):
    """OpenAI Responses model with Llama Stack streaming and compaction support."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        model_name: str,
        *,
        provider: Any = "openai",
        profile: Any = None,
        settings: ModelSettings | None = None,
        compaction: Optional[CompactionTurnContext] = None,
    ) -> None:
        """Initialize the model and patch client.responses.create.

        Args:
            model_name: Model identifier passed to pydantic-ai.
            provider: Pydantic AI provider or provider name.
            profile: Optional model profile override.
            settings: Optional pydantic-ai model settings.
            compaction: Compaction state when turns must be stored manually.
        """
        super().__init__(
            model_name,
            provider=provider,
            profile=profile,
            settings=settings,
        )
        self.compaction = compaction
        self._patch_responses_create()

    def _patch_responses_create(self) -> None:
        """Replace client.responses.create with a wrapper for the model lifetime.

        pydantic-ai calls responses.create for every inference round. The wrapper
        runs before and after the real SDK method:

        Before (compacted mode only, after the first round is persisted):
            Copy kwargs input into CompactionTurnContext.latest_round_input so
            follow-up tool-loop rounds can be appended with the input pydantic-ai
            actually sent. The first round is left unchanged so the real user query
            is stored instead of the compacted explicit rewrite.

        After, depending on stream:

        * stream=True — return _NormalizedLlamaStackStream around the SDK stream to
          reorder early tool-call deltas and, when compacted, append the turn on
          response.completed.
        * stream=False — when compacted, append the completed turn immediately
          using latest_round_input and mark the first round as persisted.

        Stream normalization is always applied; compaction hooks run only when
        self.compaction is set.
        """
        responses_api = self.client.responses
        original_create = responses_api.create

        async def create(*args: Any, **kwargs: Any) -> Any:
            if (
                self.compaction is not None
                and "input" in kwargs
                and self.compaction.original_input_persisted
            ):
                self.compaction.latest_round_input = cast(
                    ResponseInput, kwargs["input"]
                )

            result = await original_create(*args, **kwargs)

            if kwargs.get("stream"):
                return _NormalizedLlamaStackStream(
                    cast(AsyncStream[responses.ResponseStreamEvent], result),
                    self.compaction,
                )

            if self.compaction is not None:
                await append_turn_items_to_conversation(
                    self.compaction.client,
                    self.compaction.conversation_id,
                    self.compaction.latest_round_input,
                    cast(Sequence[Any], result.output),
                )
                self.compaction.original_input_persisted = True
            return result

        responses_api.create = create  # type: ignore[method-assign]
