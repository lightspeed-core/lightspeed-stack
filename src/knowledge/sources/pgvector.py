"""pgvector knowledge source that reads OGX ``remote::pgvector`` tables.

OGX release 1.2 stores each vector store in its own PostgreSQL table,
``vs_<sanitized identifier>``, created by
``ogx.providers.remote.vector_io.pgvector.PGVectorIndex``. A row holds the
chunk id, the embedded chunk as JSONB (``document``), the ``embedding``
vector, the flattened ``content_text``, and a ``tokenized_content``
tsvector. Identifiers are sanitized the same way OGX does: every character
outside ``[A-Za-z0-9_]`` becomes an underscore.

This source only searches. It does not create the ``vector`` extension,
tables, or indexes, and it does not write rows. Similarity uses OGX's
default cosine operator (``<=>``) and ``1 / distance`` score. The service
configuration has no distance-metric setting, so other pgvector operators
are not selectable here.
"""

import asyncio
import json
import re
from collections.abc import Mapping
from typing import Any, Literal, Optional

import asyncpg
from pydantic import SecretStr
from pydantic_ai.embeddings import Embedder, EmbeddingSettings

from knowledge.sources.base import VectorStore, VectorStoreKnowledgeSource
from knowledge.types import KnowledgeMatch, KnowledgeReadiness
from log import get_logger

logger = get_logger(__name__)


class PgVectorVectorStore(
    VectorStore
):  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Vector store backed by one OGX pgvector table.

    ``vector_store_id`` is the OGX vector-store identifier. The table name
    is ``vs_`` plus that identifier with unsupported characters replaced by
    underscores, matching ``PGVectorIndex.initialize``.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        vector_store_id: str,
        *,
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
        user: str = "postgres",
        password: Optional[str | SecretStr] = None,
        pool: Optional[asyncpg.Pool] = None,
    ) -> None:
        """Open a reader for one OGX pgvector table.

        Args:
            vector_store_id: OGX vector-store identifier. Selects the table;
                it is not interpolated into SQL unsanitized.
            host: PostgreSQL host.
            port: PostgreSQL port.
            database: PostgreSQL database name (the pgvector ``db`` setting).
            user: PostgreSQL user.
            password: PostgreSQL password. ``SecretStr`` is unwrapped.
            pool: Existing asyncpg pool to use. When omitted, a pool is
                opened on the first search or readiness check.

        Raises:
            ValueError: If `vector_store_id` is empty.

        """
        if not vector_store_id:
            raise ValueError("vector_store_id is required")

        self.vector_store_id = vector_store_id
        self.table_name = "vs_" + re.sub(r"[^a-zA-Z0-9_]", "_", vector_store_id)
        quoted_table = '"' + self.table_name.replace('"', '""') + '"'
        self._search_sql = (
            "SELECT id, document, content_text, "
            "embedding <=> $1::vector AS distance "
            f"FROM {quoted_table} "
            "ORDER BY distance "
            "LIMIT $2"
        )
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = (
            password.get_secret_value() if isinstance(password, SecretStr) else password
        )
        self._pool = pool
        self._pool_lock = asyncio.Lock()
        self._owns_pool = pool is None

    async def search(  # pylint: disable=too-many-locals,too-many-branches
        self,
        embeddings: list[list[float]],
        limit: int = 5,
        threshold: float = 0.0,
    ) -> list[KnowledgeMatch]:
        """Search the pgvector table and return the best matches.

        Each query vector is limited to `limit` nearest rows. Matches are
        then merged by chunk id, keeping the highest score, and rows below
        `threshold` are dropped. Distance is cosine (``<=>``); the score
        is ``1 / distance`` (infinite when the distance is zero), which is
        how OGX ranks pgvector hits.

        Args:
            embeddings: Query embedding vectors.
            limit: Maximum number of matches to return.
            threshold: Minimum similarity score to return.

        Returns:
            Matches ordered by score, highest first, at most `limit` of them.

        """
        if not embeddings:
            return []

        pool = await self._ensure_pool()
        best: dict[str, KnowledgeMatch] = {}
        async with pool.acquire() as connection:
            for embedding in embeddings:
                vector = (
                    "["
                    + ",".join(format(float(value), ".16g") for value in embedding)
                    + "]"
                )
                rows = await connection.fetch(self._search_sql, vector, limit)
                for row in rows:
                    distance = float(row["distance"])
                    score = float("inf") if distance == 0 else 1.0 / distance
                    if score < threshold:
                        continue

                    document = row["document"]
                    if isinstance(document, str):
                        document = json.loads(document)
                    if not isinstance(document, Mapping):
                        raise ValueError(
                            "pgvector document column must be a JSON object"
                        )

                    content_text = row["content_text"]
                    content = (
                        content_text
                        if isinstance(content_text, str)
                        else _interleaved_content_as_str(document.get("content"))
                    )
                    stored_id = document.get("chunk_id")
                    row_id = row["id"]
                    chunk_id = (
                        stored_id
                        if isinstance(stored_id, str) and stored_id
                        else "" if row_id is None else str(row_id)
                    )
                    chunk_metadata = document.get("chunk_metadata")
                    source: Optional[str] = None
                    if isinstance(chunk_metadata, Mapping):
                        raw_source = chunk_metadata.get("source")
                        if raw_source is not None:
                            source = (
                                raw_source
                                if isinstance(raw_source, str)
                                else str(raw_source)
                            )
                    raw_metadata = document.get("metadata")
                    metadata = (
                        dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
                    )

                    current = best.get(chunk_id)
                    if current is None or score > current.score:
                        best[chunk_id] = KnowledgeMatch(
                            content=content,
                            score=score,
                            id=chunk_id,
                            source=source,
                            metadata=metadata,
                        )

        ranked = sorted(best.values(), key=lambda match: match.score, reverse=True)
        return ranked[:limit]

    async def table_exists(self) -> bool:
        """Return whether this store's table is visible on the search path.

        Returns:
            True when ``to_regclass`` resolves the quoted table name.

        """
        pool = await self._ensure_pool()
        quoted_table = '"' + self.table_name.replace('"', '""') + '"'
        async with pool.acquire() as connection:
            found = await connection.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", quoted_table
            )
        return bool(found)

    async def close(self) -> None:
        """Close the pool this store opened.

        A pool passed to the constructor stays open; its owner closes it.
        """
        if not self._owns_pool or self._pool is None:
            return
        pool = self._pool
        self._pool = None
        await pool.close()

    async def _ensure_pool(self) -> asyncpg.Pool:
        """Return the connection pool, opening it on first use."""
        if self._pool is not None:
            return self._pool
        async with self._pool_lock:
            if self._pool is None:
                self._pool = await asyncpg.create_pool(
                    host=self._host,
                    port=self._port,
                    database=self._database,
                    user=self._user,
                    password=self._password,
                    min_size=1,
                    max_size=10,
                    command_timeout=30.0,
                )
            return self._pool


class PgVectorKnowledgeSource(VectorStoreKnowledgeSource):
    """Knowledge source that embeds queries and searches an OGX pgvector table.

    ``_pgvector`` is the concrete store held by ``store``. It is kept aside so
    readiness and shutdown can call pgvector-specific methods.

    Convenience wrapper around :class:`VectorStoreKnowledgeSource` that
    builds its :class:`PgVectorVectorStore` from PostgreSQL connection
    settings, so callers don't construct the store separately.
    """

    _pgvector: PgVectorVectorStore

    def __init__(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        name: str,
        vector_store_id: str,
        embedder: Embedder,
        *,
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
        user: str = "postgres",
        password: Optional[str | SecretStr] = None,
        embedding_settings: Optional[EmbeddingSettings] = None,
        top_k: int = 5,
        score_threshold: float = 0.0,
        mode: Optional[set[Literal["tool", "auto"]]] = None,
        pool: Optional[asyncpg.Pool] = None,
    ) -> None:
        """Build a pgvector-backed knowledge source.

        Args:
            name: Name of this knowledge source.
            vector_store_id: OGX vector-store identifier whose table is read.
            embedder: Embedder used to embed search queries.
            host: PostgreSQL host.
            port: PostgreSQL port.
            database: PostgreSQL database name (the pgvector ``db`` setting).
            user: PostgreSQL user.
            password: PostgreSQL password. ``SecretStr`` is unwrapped.
            embedding_settings: Optional settings to use for the embedding.
            top_k: Maximum number of matches to return.
            score_threshold: Minimum similarity score to return.
            mode: How this source is exposed -- ``'tool'``, ``'auto'``, or
                both. Defaults to ``{'tool'}``.
            pool: Existing asyncpg pool. When omitted, the store opens one.

        """
        store = PgVectorVectorStore(
            vector_store_id,
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            pool=pool,
        )
        super().__init__(
            name=name,
            store=store,
            embedder=embedder,
            embedding_settings=embedding_settings,
            top_k=top_k,
            score_threshold=score_threshold,
            mode=mode if mode is not None else {"tool"},
        )
        self._pgvector = store

    async def readiness(self) -> KnowledgeReadiness:
        """Report whether the pgvector table can be reached.

        A missing table or a connection failure is ``not_ready``. A reachable
        table is ``ready``.

        Returns:
            Readiness of this source.

        """
        try:
            found = await self._pgvector.table_exists()
        except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as exc:
            logger.warning(
                "pgvector knowledge source %s is not ready: %s",
                self.name,
                exc,
            )
            return KnowledgeReadiness(status="not_ready", message=str(exc))
        if not found:
            return KnowledgeReadiness(
                status="not_ready",
                message=(
                    f"pgvector table {self._pgvector.table_name} for "
                    f"vector_store_id={self._pgvector.vector_store_id!r} was not found"
                ),
            )
        return KnowledgeReadiness(status="ready", message="pgvector table reachable")

    async def close(self) -> None:
        """Close the pool this source opened, if it owns one."""
        await self._pgvector.close()


def _interleaved_content_as_str(content: Any) -> str:
    """Flatten OGX interleaved chunk content to text.

    Accepts the JSON shapes stored in ``document['content']``: a string, a
    ``{"type": "text"|"image", ...}`` object, or a list of those.

    Args:
        content: Chunk content from an embedded-chunk document.

    Returns:
        Text joined with spaces. Image items become ``<image>``.

    Raises:
        ValueError: If `content` is not one of those shapes.

    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(_interleaved_content_as_str(item) for item in content)
    if isinstance(content, Mapping):
        kind = content.get("type")
        if kind == "text":
            text = content.get("text", "")
            return text if isinstance(text, str) else str(text)
        if kind == "image":
            return "<image>"
    raise ValueError(f"Unsupported pgvector chunk content: {content!r}")
