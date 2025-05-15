"""Handler for REST API call to provide answer to query."""

import logging
from typing import Any

from llama_stack_client import LlamaStackClient
from llama_stack_client.lib.agents.agent import Agent

from fastapi import APIRouter, Request

from configuration import configuration
from constant import KEYWORDS

from models.responses import QueryResponse
from models.validation import KeywordShield

logger = logging.getLogger(__name__)
router = APIRouter(tags=["models"])


query_response: dict[int | str, dict[str, Any]] = {
    200: {
        "query": "User query",
        "answer": "LLM answer",
    },
}


@router.post("/query", responses=query_response)
async def info_endpoint_handler(request: Request, query: str) -> QueryResponse:
    try:
        config = configuration.configuration
        llama_stack_config = config.llama_stack
        query_filters = config.query_filters
        validation_method = KeywordShield(banned_keywords=KEYWORDS) if config.query_validation_method == 'keywords' else None

        logger.info("LLama stack config: %s", llama_stack_config)

        base_url = llama_stack_config.base_url
        api_key = llama_stack_config.api_key

        client = LlamaStackClient(
            base_url=base_url,
            api_key=api_key
        )

        try:
            models = client.inference.models()
        except Exception as e:
            raise ValueError(f"Authentication failed for Llama Stack server: {e}")
        
        model_id = models[0].identifier

        logger.info("Model: %s", model_id)

        for f in query_filters:
            logger.info("Query filtered")
            query = f.filter(query)

        agent = Agent(
            client=client,
            model=model_id,
            instructions="You are a helpful assistant.",
            input_shields=validation_method
        )

        response = await agent.run(messages=[{"role": "user", "content": query}])
        return QueryResponse(query=query, response=str(response.message.content))
    
    except Exception as e:
        logger.error("Agent failed")
        return 
