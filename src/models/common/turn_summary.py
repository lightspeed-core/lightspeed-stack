"""RAG context, chunks, document refs, tool summaries, and per-turn aggregation.

Used on query and streaming paths.
"""

from typing import Any, Optional

from pydantic import AnyUrl, BaseModel, Field

from utils.token_counter import TokenCounter


class RAGChunk(BaseModel):
    """Model representing a RAG chunk used in the response."""

    content: str = Field(description="The content of the chunk")
    source: Optional[str] = Field(
        default=None,
        description="Index name identifying the knowledge source from configuration",
    )
    score: Optional[float] = Field(default=None, description="Relevance score")
    attributes: Optional[dict[str, Any]] = Field(
        default=None,
        description="Document metadata from the RAG provider (e.g., url, title, author)",
    )


class ReferencedDocument(BaseModel):
    """Model representing a document referenced in generating a response.

    Attributes:
        doc_url: Url to the referenced doc.
        doc_title: Title of the referenced doc.
        document_id: Document ID for preserving identity during deduplication.
    """

    doc_url: Optional[AnyUrl] = Field(
        default=None, description="URL of the referenced document"
    )

    doc_title: Optional[str] = Field(
        default=None, description="Title of the referenced document"
    )

    source: Optional[str] = Field(
        default=None,
        description="Index name identifying the knowledge source from configuration",
    )

    document_id: Optional[str] = Field(
        default=None,
        description="Document ID for preserving identity during deduplication",
    )


class RAGContext(BaseModel):
    """Result of building RAG context from all enabled pre-query RAG sources.

    Attributes:
        context_text: Formatted RAG context string for injection into the query.
        rag_chunks: RAG chunks from pre-query sources (BYOK + Solr).
        referenced_documents: Referenced documents from pre-query sources.
    """

    context_text: str = Field(default="", description="Formatted context for injection")
    rag_chunks: list[RAGChunk] = Field(
        default_factory=list,
        description="RAG chunks from pre-query sources",
    )
    referenced_documents: list[ReferencedDocument] = Field(
        default_factory=list,
        description="Documents from pre-query sources",
    )


class ToolCallSummary(BaseModel):
    """Model representing a tool call made during response generation (for tool_calls list)."""

    id: str = Field(description="ID of the tool call")
    name: str = Field(description="Name of the tool called")
    args: dict[str, Any] = Field(
        default_factory=dict, description="Arguments passed to the tool"
    )
    type: str = Field("tool_call", description="Type indicator for tool call")


class ToolResultSummary(BaseModel):
    """Model representing a result from a tool call (for tool_results list)."""

    id: str = Field(
        description="ID of the tool call/result, matches the corresponding tool call 'id'"
    )
    status: str = Field(
        ..., description="Status of the tool execution (e.g., 'success')"
    )
    content: str = Field(..., description="Content/result returned from the tool")
    type: str = Field("tool_result", description="Type indicator for tool result")
    round: int = Field(..., description="Round number or step of tool execution")


class TurnSummary(BaseModel):
    """Summary of a turn in llama stack."""

    id: str = Field(default="", description="ID of the response")
    llm_response: str = ""
    tool_calls: list[ToolCallSummary] = Field(default_factory=list)
    tool_results: list[ToolResultSummary] = Field(default_factory=list)
    rag_chunks: list[RAGChunk] = Field(default_factory=list)
    referenced_documents: list[ReferencedDocument] = Field(default_factory=list)
    token_usage: TokenCounter = Field(default_factory=TokenCounter)
