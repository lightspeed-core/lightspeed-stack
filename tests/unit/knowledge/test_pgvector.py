"""Unit tests for knowledge.sources.pgvector."""

import json
from collections.abc import Sequence
from typing import Any, Optional, cast

import asyncpg
import pytest
from pydantic import SecretStr
from pydantic_ai.embeddings import (
    Embedder,
    EmbeddingResult,
    EmbeddingSettings,
    TestEmbeddingModel,
)
from pydantic_ai.embeddings.result import EmbedInputType

from knowledge.sources.pgvector import (
    PgVectorKnowledgeSource,
    PgVectorVectorStore,
)
from knowledge.types import KnowledgeMatch

_STORE_ID = "My-Store"
_DEFAULT_METADATA: Any = object()


class _RecordingEmbeddingModel(TestEmbeddingModel):
    """Test embedding model that records the texts it was asked to embed."""

    __test__ = False

    def __init__(self, dimensions: int = 2) -> None:
        """Create a recording model with a fixed embedding width.

        Args:
            dimensions: Width of the all-ones vectors this model returns.

        """
        super().__init__(dimensions=dimensions)
        self.inputs: list[str] = []
        self.last_settings: Optional[EmbeddingSettings] = None

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        """Record `inputs`, then return the parent model's embeddings.

        Args:
            inputs: Text or texts to embed.
            input_type: Whether the inputs are queries or documents.
            settings: Optional settings forwarded to the parent model.

        Returns:
            The parent model's embedding result.

        """
        recorded = [inputs] if isinstance(inputs, str) else list(inputs)
        self.inputs.extend(recorded)
        self.last_settings = settings
        return await super().embed(inputs, input_type=input_type, settings=settings)


def _embedder(dimensions: int = 2) -> tuple[Embedder, _RecordingEmbeddingModel]:
    """Build an embedder whose model returns all-ones vectors.

    Args:
        dimensions: Width of the generated vectors.

    Returns:
        The embedder and the recording model it uses.

    """
    model = _RecordingEmbeddingModel(dimensions=dimensions)
    return Embedder(model), model


def _document(
    content: Any = "alpha",
    chunk_id: str = "chunk-alpha",
    *,
    metadata: Any = _DEFAULT_METADATA,
    source: Optional[str] = "https://example.com/alpha",
) -> dict[str, Any]:
    """Build an OGX embedded-chunk document.

    Args:
        content: Chunk content stored in the document.
        chunk_id: Chunk id stored in the document.
        metadata: Inference metadata. Defaults to a one-key object. Pass
            ``None`` to store a null metadata field.
        source: Citation stored on ``chunk_metadata``. ``None`` omits it.

    Returns:
        A document object of the shape OGX writes into the JSONB column.

    """
    chunk_metadata: dict[str, Any] = {"document_id": "doc-1"}
    if source is not None:
        chunk_metadata["source"] = source
    stored_metadata: Any = (
        {"file_name": "alpha.txt"} if metadata is _DEFAULT_METADATA else metadata
    )
    return {
        "content": content,
        "chunk_id": chunk_id,
        "metadata": stored_metadata,
        "chunk_metadata": chunk_metadata,
        "embedding": [1.0, 0.0],
        "embedding_model": "sentence-transformers/all-mpnet-base-v2",
        "embedding_dimension": 2,
    }


def _row(
    distance: float,
    *,
    row_id: str = "chunk-alpha",
    document: Any = None,
    content_text: Optional[str] = "alpha",
) -> dict[str, Any]:
    """Build one pgvector result row.

    Args:
        distance: Distance the query would return.
        row_id: Value of the ``id`` column.
        document: JSONB document. Defaults to a standard embedded chunk.
        content_text: Flattened chunk text, or `None` when the column is null.

    Returns:
        A mapping with the columns the store reads.

    """
    return {
        "id": row_id,
        "document": _document() if document is None else document,
        "content_text": content_text,
        "distance": distance,
    }


class _FakeConnection:
    """asyncpg-like connection that records queries and returns scripted rows."""

    def __init__(
        self,
        responses: Optional[list[list[dict[str, Any]]]] = None,
        *,
        exists: bool = True,
        error: Optional[BaseException] = None,
    ) -> None:
        """Create a connection with scripted fetch results.

        Args:
            responses: Row batches returned by successive ``fetch`` calls.
                When omitted, every fetch returns an empty list.
            exists: Value returned by ``fetchval`` for the table probe.
            error: Exception raised by ``fetch`` and ``fetchval`` when set.

        """
        self._responses = list(responses or [])
        self.exists = exists
        self.error = error
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Record `query` and return the next scripted batch.

        Args:
            query: SQL text.
            args: Bound parameters.

        Returns:
            The next scripted row batch, or an empty list when none remain.

        """
        self.calls.append((query, args))
        if self.error is not None:
            raise self.error
        if not self._responses:
            return []
        return self._responses.pop(0)

    async def fetchval(self, query: str, *args: Any) -> bool:
        """Record a probe query and return whether the table exists.

        Args:
            query: SQL text.
            args: Bound parameters.

        Returns:
            The scripted existence flag.

        """
        self.calls.append((query, args))
        if self.error is not None:
            raise self.error
        return self.exists


class _Acquire:
    """Async context manager yielding one fake connection."""

    def __init__(self, connection: _FakeConnection) -> None:
        """Hold the connection `acquire` should yield.

        Args:
            connection: Connection entered by the context manager.

        """
        self._connection = connection

    async def __aenter__(self) -> _FakeConnection:
        """Return the held connection."""
        return self._connection

    async def __aexit__(self, *_exc: object) -> None:
        """Leave the context without closing the connection."""


class _FakePool:
    """asyncpg-like pool over one fake connection."""

    def __init__(self, connection: _FakeConnection) -> None:
        """Serve `connection` from every acquire.

        Args:
            connection: Connection handed out by ``acquire``.

        """
        self.connection = connection
        self.acquires = 0
        self.closed = False

    def acquire(self) -> _Acquire:
        """Count an acquire and return its context manager.

        Returns:
            A context manager yielding the scripted connection.

        """
        self.acquires += 1
        return _Acquire(self.connection)

    async def close(self) -> None:
        """Record that the pool was closed."""
        self.closed = True


def _pool(
    responses: Optional[list[list[dict[str, Any]]]] = None,
    **kwargs: Any,
) -> tuple[_FakePool, _FakeConnection]:
    """Build a fake pool and the connection it serves.

    Args:
        responses: Row batches for successive searches.
        kwargs: Forwarded to :class:`_FakeConnection`.

    Returns:
        The pool and its connection.

    """
    connection = _FakeConnection(responses, **kwargs)
    return _FakePool(connection), connection


def _store(
    pool: _FakePool,
    vector_store_id: str = _STORE_ID,
    **kwargs: Any,
) -> PgVectorVectorStore:
    """Build a store that uses `pool` instead of opening PostgreSQL.

    Args:
        pool: Pool injected into the store.
        vector_store_id: OGX vector-store identifier.
        kwargs: Forwarded to :class:`PgVectorVectorStore`.

    Returns:
        A store bound to `pool`.

    """
    return PgVectorVectorStore(
        vector_store_id,
        pool=cast(asyncpg.Pool, pool),
        **kwargs,
    )


class TestPgVectorVectorStore:
    """Tests for reading an OGX pgvector table."""

    @pytest.mark.asyncio
    async def test_queries_the_sanitized_ogx_table(self) -> None:
        """Search issues OGX's cosine query against ``vs_<sanitized id>``."""
        pool, connection = _pool([[_row(0.5)]])
        store = _store(pool)

        matches = await store.search([[1.0, 0.0]], limit=3)

        query, args = connection.calls[0]
        assert query == (
            "SELECT id, document, content_text, "
            "embedding <=> $1::vector AS distance "
            'FROM "vs_My_Store" '
            "ORDER BY distance "
            "LIMIT $2"
        )
        assert args == ("[1,0]", 3)
        assert matches == [
            KnowledgeMatch(
                content="alpha",
                score=2.0,
                id="chunk-alpha",
                source="https://example.com/alpha",
                metadata={"file_name": "alpha.txt"},
            )
        ]

    def test_rejects_an_empty_vector_store_id(self) -> None:
        """An empty identifier cannot name an OGX table."""
        with pytest.raises(ValueError, match="vector_store_id is required"):
            PgVectorVectorStore("")

    @pytest.mark.asyncio
    async def test_replaces_unsafe_identifier_characters(self) -> None:
        """Quotes and other non-identifiers never reach the SQL text."""
        pool, connection = _pool()
        store = _store(pool, 'bad"; drop')

        await store.search([[1.0]], limit=1)

        query, _args = connection.calls[0]
        assert 'FROM "vs_bad___drop"' in query
        assert "drop table" not in query.lower()

    @pytest.mark.asyncio
    async def test_parses_a_json_string_document(self) -> None:
        """JSONB returned as text is parsed into the same match."""
        document = _document(chunk_id="from-json")
        pool, _connection = _pool(
            [[_row(1.0, document=json.dumps(document), content_text="from json")]]
        )
        store = _store(pool)

        matches = await store.search([[1.0, 0.0]], limit=1)

        assert matches[0].id == "from-json"
        assert matches[0].content == "from json"
        assert matches[0].score == 1.0

    @pytest.mark.asyncio
    async def test_falls_back_to_interleaved_content_when_text_is_null(
        self,
    ) -> None:
        """A null ``content_text`` is rebuilt from the document content."""
        document = _document(
            content=[
                {"type": "text", "text": "hello"},
                {"type": "image", "image": {"url": "https://example.com/a.png"}},
            ],
            source=None,
        )
        pool, _connection = _pool([[_row(0.25, document=document, content_text=None)]])
        store = _store(pool)

        matches = await store.search([[1.0, 0.0]], limit=1)

        assert matches[0].content == "hello <image>"
        assert matches[0].source is None
        assert matches[0].score == 4.0

    @pytest.mark.asyncio
    async def test_null_metadata_becomes_an_empty_mapping(self) -> None:
        """Missing and null metadata both become an empty mapping."""
        pool, _connection = _pool(
            [
                [
                    _row(1.0, document=_document(metadata=None)),
                    _row(
                        0.5,
                        row_id="other",
                        document=_document(chunk_id="other", metadata={}),
                    ),
                ]
            ]
        )
        store = _store(pool)

        matches = await store.search([[1.0, 0.0]], limit=2)

        assert [match.metadata for match in matches] == [{}, {}]

    @pytest.mark.asyncio
    async def test_uses_the_row_id_when_the_document_has_no_chunk_id(self) -> None:
        """The table ``id`` is the match id when ``chunk_id`` is absent."""
        document = _document()
        del document["chunk_id"]
        pool, _connection = _pool([[_row(1.0, row_id="row-id", document=document)]])
        store = _store(pool)

        matches = await store.search([[1.0, 0.0]], limit=1)

        assert matches[0].id == "row-id"

    @pytest.mark.asyncio
    async def test_zero_distance_scores_as_infinity(self) -> None:
        """A distance of zero uses OGX's infinite score."""
        pool, _connection = _pool([[_row(0.0)]])
        store = _store(pool)

        matches = await store.search([[1.0, 0.0]], limit=1)

        assert matches[0].score == float("inf")

    @pytest.mark.asyncio
    async def test_drops_rows_below_the_score_threshold(self) -> None:
        """Scores below the threshold are not returned."""
        pool, _connection = _pool(
            [
                [
                    _row(1.0),
                    _row(
                        0.25,
                        row_id="near",
                        document=_document(chunk_id="near"),
                    ),
                ]
            ]
        )
        store = _store(pool)

        matches = await store.search([[1.0, 0.0]], limit=2, threshold=3.0)

        assert [match.id for match in matches] == ["near"]

    @pytest.mark.asyncio
    async def test_merges_query_vectors_keeping_the_best_score(self) -> None:
        """Several query vectors are deduped by chunk id and ranked together."""
        shared = _row(1.0, row_id="shared", document=_document(chunk_id="shared"))
        best = _row(0.5, row_id="shared", document=_document(chunk_id="shared"))
        other = _row(0.25, row_id="other", document=_document(chunk_id="other"))
        pool, connection = _pool([[shared, other], [best]])
        store = _store(pool)

        matches = await store.search([[1.0, 0.0], [0.0, 1.0]], limit=2)

        assert len(connection.calls) == 2
        assert [(match.id, match.score) for match in matches] == [
            ("other", 4.0),
            ("shared", 2.0),
        ]

    @pytest.mark.asyncio
    async def test_empty_embeddings_do_not_query(self) -> None:
        """No query vectors means no connection acquire."""
        pool, connection = _pool()
        store = _store(pool)

        assert await store.search([]) == []
        assert not connection.calls
        assert pool.acquires == 0

    @pytest.mark.asyncio
    async def test_rejects_a_document_that_is_not_an_object(self) -> None:
        """A JSON array in ``document`` raises ``ValueError``."""
        pool, _connection = _pool([[_row(1.0, document=[1, 2, 3])]])
        store = _store(pool)

        with pytest.raises(ValueError, match="JSON object"):
            await store.search([[1.0, 0.0]], limit=1)

    @pytest.mark.asyncio
    async def test_table_exists_probes_the_quoted_name(self) -> None:
        """Readiness lookup uses ``to_regclass`` on the quoted table name."""
        pool, connection = _pool(exists=True)
        store = _store(pool)

        assert await store.table_exists() is True
        assert connection.calls == [
            ("SELECT to_regclass($1) IS NOT NULL", ('"vs_My_Store"',))
        ]

    @pytest.mark.asyncio
    async def test_table_exists_is_false_when_the_probe_is_empty(self) -> None:
        """A null ``to_regclass`` result means the table is absent."""
        pool, _connection = _pool(exists=False)
        store = _store(pool)

        assert await store.table_exists() is False

    @pytest.mark.asyncio
    async def test_opens_a_pool_from_connection_settings(self, mocker: Any) -> None:
        """The first search opens one pool and later searches reuse it."""
        pool, _connection = _pool([[_row(1.0)]])
        create_pool = mocker.AsyncMock(return_value=pool)
        mocker.patch("knowledge.sources.pgvector.asyncpg.create_pool", create_pool)
        store = PgVectorVectorStore(
            "docs",
            host="db.internal",
            port=5433,
            database="vectors",
            user="rag",
            password=SecretStr("s3cret"),
        )

        await store.search([[1.0, 0.0]], limit=1)
        await store.search([[1.0, 0.0]], limit=1)

        create_pool.assert_awaited_once_with(
            host="db.internal",
            port=5433,
            database="vectors",
            user="rag",
            password="s3cret",
            min_size=1,
            max_size=10,
            command_timeout=30.0,
        )
        assert pool.acquires == 2

    @pytest.mark.asyncio
    async def test_close_closes_an_owned_pool(self, mocker: Any) -> None:
        """``close`` closes the pool the store opened."""
        pool, _connection = _pool()
        mocker.patch(
            "knowledge.sources.pgvector.asyncpg.create_pool",
            mocker.AsyncMock(return_value=pool),
        )
        store = PgVectorVectorStore("docs")
        await store.table_exists()

        await store.close()

        assert pool.closed is True

    @pytest.mark.asyncio
    async def test_close_leaves_an_injected_pool_open(self) -> None:
        """A caller-supplied pool is not closed with the store."""
        pool, _connection = _pool()
        store = _store(pool)

        await store.close()

        assert pool.closed is False


class TestPgVectorKnowledgeSource:
    """Tests for the pgvector-backed knowledge source wrapper."""

    def test_defaults_to_tool_mode(self) -> None:
        """Omitted options use tool mode, top 5, and no score cutoff."""
        embedder, _model = _embedder()
        pool, _connection = _pool()
        source = PgVectorKnowledgeSource(
            "docs",
            _STORE_ID,
            embedder,
            pool=cast(asyncpg.Pool, pool),
        )

        assert source.name == "docs"
        assert source.mode == {"tool"}
        assert source.top_k == 5
        assert source.score_threshold == 0.0
        assert source.embedding_settings is None
        assert isinstance(source.store, PgVectorVectorStore)
        assert (
            source._pgvector.table_name  # pylint: disable=protected-access
            == "vs_My_Store"
        )

    def test_default_mode_is_not_shared_across_instances(self) -> None:
        """Each defaulted source gets its own mode set."""
        pool, _connection = _pool()
        first = PgVectorKnowledgeSource(
            "docs",
            _STORE_ID,
            _embedder()[0],
            pool=cast(asyncpg.Pool, pool),
        )
        second = PgVectorKnowledgeSource(
            "docs",
            _STORE_ID,
            _embedder()[0],
            pool=cast(asyncpg.Pool, pool),
        )

        first.mode.add("auto")

        assert second.mode == {"tool"}

    @pytest.mark.asyncio
    async def test_honors_explicit_mode_and_search_options(self) -> None:
        """Explicit mode, settings, top_k, and threshold are stored."""
        embedder, _model = _embedder()
        settings: EmbeddingSettings = {"dimensions": 2}
        pool, connection = _pool()
        source = PgVectorKnowledgeSource(
            "docs",
            _STORE_ID,
            embedder,
            embedding_settings=settings,
            top_k=1,
            score_threshold=0.9,
            mode={"tool", "auto"},
            pool=cast(asyncpg.Pool, pool),
        )

        await source.search("query")

        assert source.mode == {"tool", "auto"}
        assert source.embedding_settings == {"dimensions": 2}
        assert source.top_k == 1
        assert source.score_threshold == 0.9
        assert "embedding <=> $1::vector" in connection.calls[0][0]

    @pytest.mark.asyncio
    async def test_search_embeds_the_prompt_and_returns_ranked_matches(
        self,
    ) -> None:
        """Search embeds the prompt and returns the stored chunk."""
        embedder, model = _embedder()
        pool, _connection = _pool([[_row(0.5)]])
        source = PgVectorKnowledgeSource(
            "docs",
            _STORE_ID,
            embedder,
            pool=cast(asyncpg.Pool, pool),
        )

        matches = await source.search("where is alpha?")

        assert model.inputs == ["where is alpha?"]
        assert [(match.id, match.score) for match in matches] == [("chunk-alpha", 2.0)]

    @pytest.mark.asyncio
    async def test_search_applies_top_k_and_score_threshold(self) -> None:
        """``top_k`` and ``score_threshold`` are passed through to the store."""
        pool, connection = _pool(
            [
                [
                    _row(0.25),
                    _row(1.0, document=_document(chunk_id="far")),
                ]
            ]
        )
        source = PgVectorKnowledgeSource(
            "docs",
            _STORE_ID,
            _embedder()[0],
            top_k=1,
            score_threshold=3.0,
            pool=cast(asyncpg.Pool, pool),
        )

        matches = await source.search("query")

        assert connection.calls[0][1][1] == 1
        assert [match.id for match in matches] == ["chunk-alpha"]

    @pytest.mark.asyncio
    async def test_forwards_embedding_settings(self) -> None:
        """Per-source embedding settings reach the embedder."""
        embedder, model = _embedder(dimensions=8)
        settings: EmbeddingSettings = {"dimensions": 2}
        pool, _connection = _pool([[_row(1.0)]])
        source = PgVectorKnowledgeSource(
            "docs",
            _STORE_ID,
            embedder,
            embedding_settings=settings,
            top_k=1,
            pool=cast(asyncpg.Pool, pool),
        )

        matches = await source.search("query")

        assert model.last_settings == {"dimensions": 2}
        assert [match.id for match in matches] == ["chunk-alpha"]

    @pytest.mark.asyncio
    async def test_readiness_reports_ready_when_the_table_exists(self) -> None:
        """A visible table is ready."""
        pool, _connection = _pool(exists=True)
        source = PgVectorKnowledgeSource(
            "docs", _STORE_ID, _embedder()[0], pool=cast(asyncpg.Pool, pool)
        )

        readiness = await source.readiness()

        assert readiness.status == "ready"
        assert readiness.message == "pgvector table reachable"

    @pytest.mark.asyncio
    async def test_readiness_reports_missing_table(self) -> None:
        """A missing table is not ready and names the OGX table."""
        pool, _connection = _pool(exists=False)
        source = PgVectorKnowledgeSource(
            "docs", _STORE_ID, _embedder()[0], pool=cast(asyncpg.Pool, pool)
        )

        readiness = await source.readiness()

        assert readiness.status == "not_ready"
        assert readiness.message == (
            "pgvector table vs_My_Store for vector_store_id='My-Store' was not found"
        )

    @pytest.mark.asyncio
    async def test_readiness_reports_connection_failure(self) -> None:
        """A connection error is not ready and does not raise."""
        pool, _connection = _pool(error=OSError("connection refused"))
        source = PgVectorKnowledgeSource(
            "docs", _STORE_ID, _embedder()[0], pool=cast(asyncpg.Pool, pool)
        )

        readiness = await source.readiness()

        assert readiness.status == "not_ready"
        assert readiness.message == "connection refused"

    @pytest.mark.asyncio
    async def test_close_closes_the_store_pool(self, mocker: Any) -> None:
        """Closing the source closes the pool its store opened."""
        pool, _connection = _pool()
        mocker.patch(
            "knowledge.sources.pgvector.asyncpg.create_pool",
            mocker.AsyncMock(return_value=pool),
        )
        source = PgVectorKnowledgeSource("docs", _STORE_ID, _embedder()[0])
        await source.readiness()

        await source.close()

        assert pool.closed is True
