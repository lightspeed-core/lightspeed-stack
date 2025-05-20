"""Handler for REST API call to provide answer to query."""
import json
import logging
import re
from typing import Any, Optional, Iterator, AsyncGenerator, Mapping

from llama_stack_client.lib.agents.agent import Agent
from llama_stack_client.lib.agents.event_logger import TurnStreamPrintableEvent, TurnStreamEventPrinter
from llama_stack_client import LlamaStackClient
from llama_stack_client.types import UserMessage
from llama_stack_client.types.shared.interleaved_content_item import TextContentItem

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.endpoints.query import get_llama_stack_client, LLMRequest
from configuration import configuration

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query"])


query_response: dict[int | str, dict[str, Any]] = {
    200: {
        "query": "User query",
        "answer": "LLM answer",
    },
}


@router.post("/streaming_query", responses=query_response)
def info_endpoint_handler(request: LLMRequest) -> StreamingResponse:
    llama_stack_config = configuration.llama_stack_configuration
    logger.info("LLama stack config: %s", llama_stack_config)

    client = get_llama_stack_client(llama_stack_config)

    # retrieve list of available models
    models = client.models.list()

    # select the first LLM
    llm = next(m for m in models if m.model_type == "llm")
    model_id = llm.identifier

    logger.info("Model: %s", model_id)

    response = retrieve_response(client, model_id, request.query)

    return StreamingResponse(
        response_processing_wrapper(
            request,
            response,
        )
    );

def retrieve_response(client: LlamaStackClient, model_id: str, prompt: str) -> str:

    available_shields = [shield.identifier for shield in client.shields.list()]
    if not available_shields:
        logger.info("No available shields. Disabling safety")
    else:
        logger.info(f"Available shields found: {available_shields}")

    available_vector_dbs = [vector_db.identifier for vector_db in client.vector_dbs.list()]
    if not available_vector_dbs:
        raise RuntimeError("No available vector DBs.")
    vector_db_id = available_vector_dbs[0]

    agent = Agent(
        client,
        model=model_id,
        instructions="""You are a helpful assistant  with access to the following tools. 
When a tool is required to answer the user's query, respond only with <|tool_call|> 
followed by a JSON list of tools used. If a tool does not exist in the provided 
list of tools, notify the user that you do not have the ability to fulfill the request.
""",
        input_shields=available_shields if available_shields else [],
        tools=[
            {
                "name": "builtin::rag/knowledge_search",
                "args": {
                    "vector_db_ids": [vector_db_id],
                    # Defaults
                    "query_config": {
                        "chunk_size_in_tokens": 512,
                        "chunk_overlap_in_tokens": 0,
                        "chunk_template": "Result {index}\nContent: {chunk.content}\nMetadata: {metadata}\n",
                    },
                },
            }
        ],
    )
    session_id = agent.create_session("chat_session")
    response = agent.create_turn(
        messages=[UserMessage(role="user", content=prompt)],
        session_id=session_id,
    )
    return response
    # return str(response.output_message.content)


async def response_processing_wrapper(
    request: LLMRequest,
    generator: AsyncGenerator[Any, None],
) -> AsyncGenerator[str, None]:
    """Process the response from the generator and handle metadata and errors."""

    idx = 0
    logger = RAGEventLogger()
    try:
        for item in logger.log(generator):
            yield build_yield_item(str(item), idx)
            idx += 1
    finally:
        ref_docs = logger.printer.metadata_map
        yield stream_end_event(
            ref_docs,
        )


def build_yield_item(item: str, idx: int) -> str:
    return format_stream_data(
        {
            "event": "token",
            "data": {"id": idx, "token": item},
        }
    )


def stream_end_event(ref_docs_metadata: Mapping[str, dict]):
    ref_docs = []
    for k,v in ref_docs_metadata.items():
        ref_docs.append({
            "doc_url": v["docs_url"],
            "doc_title": v["title"], # todo
        })
    return format_stream_data(
        {
            "event": "end",
            "data": {
                "referenced_documents": ref_docs,
                "truncated": False, # TODO
                "input_tokens": 0, # TODO
                "output_tokens": 0, # TODO
            },
            "available_quotas": 0, # TODO
        }
    )


def format_stream_data(d: dict) -> str:
    """Format outbound data in the Event Stream Format."""
    data = json.dumps(d)
    return f"data: {data}\n\n"

class TurnStreamPrintableEventEx(TurnStreamPrintableEvent):
    def __str__(self) -> str:
        if self.role is not None:
            return f"\n\n`{self.role}>` {self.content}"
        else:
            return f"{self.content}"


class RAGTurnStreamEventPrinter(TurnStreamEventPrinter):
    metadata_pattern = re.compile(r"\nMetadata: (\{.+\})\n")

    def __init__(self):
        super().__init__()
        self.metadata_map = {}

    def _yield_printable_events(
        self, chunk: Any, previous_event_type: Optional[str] = None, previous_step_type: Optional[str] = None
    ) -> Iterator[TurnStreamPrintableEventEx]:
        if hasattr(chunk, "error"):
            yield TurnStreamPrintableEventEx(role=None, content=chunk.error["message"], color="red")
            return

        event = chunk.event
        event_type = event.payload.event_type

        if event_type in {"turn_start", "turn_complete", "turn_awaiting_input"}:
            # Currently not logging any turn related info
            yield TurnStreamPrintableEventEx(role=None, content="", end="", color="grey")
            return

        step_type = event.payload.step_type
        # handle safety
        if step_type == "shield_call" and event_type == "step_complete":
            violation = event.payload.step_details.violation
            if not violation:
                yield TurnStreamPrintableEventEx(role=step_type, content="No Violation", color="magenta")
            else:
                yield TurnStreamPrintableEventEx(
                    role=step_type,
                    content=f"{violation.metadata} {violation.user_message}",
                    color="red",
                )

        # handle inference
        if step_type == "inference":
            if event_type == "step_start":
                yield TurnStreamPrintableEventEx(role=step_type, content="", end="", color="yellow")
            elif event_type == "step_progress":
                if event.payload.delta.type == "tool_call":
                    if isinstance(event.payload.delta.tool_call, str):
                        yield TurnStreamPrintableEventEx(
                            role=None,
                            content=event.payload.delta.tool_call,
                            end="",
                            color="cyan",
                        )
                elif event.payload.delta.type == "text":
                    yield TurnStreamPrintableEventEx(
                        role=None,
                        content=event.payload.delta.text,
                        end="",
                        color="yellow",
                    )
            else:
                # step complete
                yield TurnStreamPrintableEventEx(role=None, content="")

        # handle tool_execution
        if step_type == "tool_execution" and event_type == "step_complete":
            # Only print tool calls and responses at the step_complete event
            details = event.payload.step_details
            for t in details.tool_calls:
                yield TurnStreamPrintableEventEx(
                    role=step_type,
                    content=f"Tool:{t.tool_name} Args:{t.arguments}",
                    color="green",
                )

            for r in details.tool_responses:
                if r.tool_name == "query_from_memory":
                    inserted_context = super().interleaved_content_as_str(r.content)
                    content = f"fetched {len(inserted_context)} bytes from memory"

                    yield TurnStreamPrintableEventEx(
                        role=step_type,
                        content=content,
                        color="cyan",
                    )
                else:
                    # Referenced documents support
                    if r.tool_name == "knowledge_search" and r.content:
                        summary = ""
                        for i,text_content_item in enumerate(r.content):
                            if isinstance(text_content_item, TextContentItem):
                                if i == 0:
                                    summary = text_content_item.text
                                    summary = summary[:summary.find("\n")]
                                matches = self.metadata_pattern.findall(text_content_item.text)
                                if matches:
                                    for match in matches:
                                        meta = json.loads(match.replace('\'', '"'))
                                        self.metadata_map[meta["document_id"]] = meta
                        yield TurnStreamPrintableEventEx(
                            role=step_type,
                            content=f"\nTool:{r.tool_name} Summary:{summary}\n",
                            color="green",
                        )
                    else:
                        yield TurnStreamPrintableEventEx(
                            role=step_type,
                            content=f"Tool:{r.tool_name} Response:{r.content}",
                            color="green",
                        )


class RAGEventLogger:
    printer: RAGTurnStreamEventPrinter
    def log(self, event_generator: Iterator[Any]) -> Iterator[TurnStreamPrintableEventEx]:
        self.printer = RAGTurnStreamEventPrinter()
        for chunk in event_generator:
            yield from self.printer.yield_printable_events(chunk)
