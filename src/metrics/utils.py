"""Utility functions for metrics handling."""

from typing import cast

from fastapi import HTTPException
from llama_stack.models.llama.datatypes import RawMessage
from llama_stack.models.llama.llama3.chat_format import ChatFormat
from llama_stack.models.llama.llama3.tokenizer import Tokenizer
from llama_stack_client import APIConnectionError, APIStatusError
from llama_stack_client.types.alpha.agents.turn import Turn

import metrics
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from log import get_logger
from models.responses import ServiceUnavailableResponse
from utils.common import run_once_async
from utils.endpoints import check_configuration_loaded

logger = get_logger(__name__)


@run_once_async
async def setup_model_metrics() -> None:
    """Perform setup of all metrics related to LLM model and provider."""
    logger.info("Setting up model metrics")
    check_configuration_loaded(configuration)
    try:
        model_list = await AsyncLlamaStackClientHolder().get_client().models.list()
    except (APIConnectionError, APIStatusError) as e:
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e

    models = [
        model
        for model in model_list
        if model.model_type == "llm"  # pyright: ignore[reportAttributeAccessIssue]
    ]

    default_model_label = (
        configuration.inference.default_provider,  # type: ignore[reportAttributeAccessIssue]
        configuration.inference.default_model,  # type: ignore[reportAttributeAccessIssue]
    )

    for model in models:
        provider = model.provider_id
        model_name = model.identifier
        if provider and model_name:
            # If the model/provider combination is the default, set the metric value to 1
            # Otherwise, set it to 0
            default_model_value = 0
            label_key = (provider, model_name)
            if label_key == default_model_label:
                default_model_value = 1

            # Set the metric for the provider/model configuration
            metrics.provider_model_configuration.labels(*label_key).set(
                default_model_value
            )
            logger.debug(
                "Set provider/model configuration for %s/%s to %d",
                provider,
                model_name,
                default_model_value,
            )
    logger.info("Model metrics setup complete")


def update_llm_token_count_from_turn(
    turn: Turn, model: str, provider: str, system_prompt: str = ""
) -> None:
    """Update the LLM calls metrics from a turn."""
    tokenizer = Tokenizer.get_instance()
    formatter = ChatFormat(tokenizer)

    raw_message = cast(RawMessage, turn.output_message)
    encoded_output = formatter.encode_dialog_prompt([raw_message])
    token_count = len(encoded_output.tokens) if encoded_output.tokens else 0
    metrics.llm_token_received_total.labels(provider, model).inc(token_count)

    input_messages = [RawMessage(role="user", content=system_prompt)] + cast(
        list[RawMessage], turn.input_messages
    )
    encoded_input = formatter.encode_dialog_prompt(input_messages)
    token_count = len(encoded_input.tokens) if encoded_input.tokens else 0
    metrics.llm_token_sent_total.labels(provider, model).inc(token_count)
