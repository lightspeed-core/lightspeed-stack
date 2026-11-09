"""Unit tests for knowledge.sources.faiss."""

import base64
import io
import json
import sqlite3
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import pytest
from pydantic_ai.embeddings import (
    Embedder,
    EmbeddingResult,
    EmbeddingSettings,
    TestEmbeddingModel,
)
from pydantic_ai.embeddings.result import EmbedInputType

from knowledge.sources.faiss import FaissKnowledgeSource, FaissVectorStore
from knowledge.types import KnowledgeMatch

_STORE_ID = "vs-standard"
_PDF_DB = Path(__file__).resolve().parents[2] / "e2e" / "rag" / "pdf_kv_store.db"
_PDF_STORE_ID = "vs_4a27375c-b8da-4134-96fc-b8198d111015"
_PDF_CHUNK_ID = "3ad87ee0-3c26-4cfe-8e96-7150ade6235f"


def _faiss_key(vector_store_id: str) -> str:
    """Build the sqlite-faiss kvstore key the loader looks up.

    Args:
        vector_store_id: Store id embedded in the key.

    Returns:
        The ``vector_io::faiss:faiss_index:v3`` key for that store.

    """
    return f"vector_io::faiss:faiss_index:v3::{vector_store_id}"


def _encode_index(index: faiss.Index) -> str:
    """Serialize a Faiss index the way sqlite-faiss stores it.

    Args:
        index: Index to encode.

    Returns:
        Base64 text of an ``.npy`` uint8 array produced by ``faiss.serialize_index``.

    """
    buffer = io.BytesIO()
    np.save(buffer, faiss.serialize_index(index))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _build_index(
    vectors: list[list[float]], dimension: int | None = None
) -> faiss.Index:
    """Build an L2 index from row vectors.

    Args:
        vectors: Rows to add. Empty builds an index with no rows.
        dimension: Width of an empty index. Required when `vectors` is empty.

    Returns:
        A ``faiss.IndexFlatL2`` containing `vectors`.

    """
    matrix = np.asarray(list(vectors), dtype=np.float32)
    if matrix.size == 0:
        if dimension is None:
            raise ValueError("dimension is required when vectors is empty")
        return faiss.IndexFlatL2(dimension)
    index = faiss.IndexFlatL2(int(matrix.shape[1]))
    index.add(matrix)  # pylint: disable=no-value-for-parameter
    return index


def _store_payload(
    vectors: list[list[float]],
    chunks: dict[int, dict[str, Any]],
    *,
    dimension: int | None = None,
) -> str:
    """Build the JSON value stored under a sqlite-faiss index key.

    Args:
        vectors: Embedding rows, in Faiss id order.
        chunks: Chunk payloads keyed by Faiss row id. Values are stored as JSON strings.
        dimension: Width of an empty index.

    Returns:
        JSON text with ``faiss_index`` and ``chunk_by_index``.

    """
    body = {
        "faiss_index": _encode_index(_build_index(vectors, dimension)),
        "chunk_by_index": {
            str(idx): json.dumps(chunk) for idx, chunk in chunks.items()
        },
    }
    return json.dumps(body)


def _write_kv_value(path: Path, key: str, value: str) -> None:
    """Insert one row into a sqlite-faiss ``kvstore`` table, creating the file if needed.

    Args:
        path: Database file to create or update.
        key: ``kvstore.key`` value.
        value: ``kvstore.value`` text.

    """
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS kvstore ("
            "key TEXT PRIMARY KEY, value TEXT, expiration TIMESTAMP)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO kvstore (key, value) VALUES (?, ?)",
            (key, value),
        )
        connection.commit()
    finally:
        connection.close()


def _write_store(
    path: Path,
    vector_store_id: str,
    vectors: list[list[float]],
    chunks: dict[int, dict[str, Any]],
    *,
    dimension: int | None = None,
) -> None:
    """Write one vector store into a sqlite-faiss file.

    Args:
        path: Database file to create or update.
        vector_store_id: Store id used in the kvstore key.
        vectors: Embedding rows, in Faiss id order.
        chunks: Chunk payloads keyed by Faiss row id.
        dimension: Width of an empty index.

    """
    _write_kv_value(
        path,
        _faiss_key(vector_store_id),
        _store_payload(vectors, chunks, dimension=dimension),
    )


def _score(distance: float) -> float:
    """Convert an L2 distance the same way the store does.

    Args:
        distance: Squared L2 distance returned by Faiss.

    Returns:
        The bounded, higher-is-better score ``1 / (1 + distance)``.

    """
    return 1.0 / (1.0 + distance)


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


@pytest.fixture(name="standard_db")
def standard_db_fixture(tmp_path: Path) -> Path:
    """Create a three-vector store with known L2 distances from ``[1, 0]``.

    Row 0 ``alpha`` is ``[1, 0]`` (distance 0), row 2 ``gamma`` is ``[1, 1]``
    (distance 1), and row 1 ``beta`` is ``[0, 1]`` (distance 2).

    Args:
        tmp_path: Per-test temporary directory.

    Returns:
        Path to the sqlite-faiss file.

    """
    path = tmp_path / "standard.db"
    _write_store(
        path,
        _STORE_ID,
        [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        {
            0: {"content": "alpha", "chunk_id": "chunk-alpha", "metadata": {"ord": 0}},
            1: {"content": "beta", "chunk_id": "chunk-beta", "metadata": {"ord": 1}},
            2: {"content": "gamma", "chunk_id": "chunk-gamma", "metadata": {"ord": 2}},
        },
    )
    return path


class TestFaissVectorStoreLoading:
    """Tests for reading a sqlite-faiss file into a vector store."""

    @pytest.mark.asyncio
    async def test_loads_chunk_text_id_source_and_metadata(
        self, standard_db: Path
    ) -> None:
        """An exact hit returns the stored chunk, using `chunk_id` as id and source."""
        store = FaissVectorStore(standard_db, _STORE_ID)

        matches = await store.search([[1.0, 0.0]], limit=1)

        assert matches == [
            KnowledgeMatch(
                content="alpha",
                score=1.0,
                id="chunk-alpha",
                source="chunk-alpha",
                metadata={"ord": 0},
            )
        ]

    @pytest.mark.asyncio
    async def test_accepts_a_string_path(self, standard_db: Path) -> None:
        """`db_path` may be a string or a `Path`."""
        store = FaissVectorStore(str(standard_db), _STORE_ID)

        matches = await store.search([[1.0, 0.0]], limit=1)

        assert [match.id for match in matches] == ["chunk-alpha"]

    @pytest.mark.asyncio
    async def test_loads_only_the_requested_store(self, tmp_path: Path) -> None:
        """A file with two stores serves the id passed to the constructor."""
        path = tmp_path / "multi.db"
        _write_store(
            path, "one", [[1.0, 0.0]], {0: {"content": "one", "chunk_id": "id-one"}}
        )
        _write_store(
            path, "two", [[0.0, 1.0]], {0: {"content": "two", "chunk_id": "id-two"}}
        )
        store = FaissVectorStore(path, "two")

        matches = await store.search([[0.0, 1.0]], limit=1)

        assert matches[0].content == "two"
        assert matches[0].id == "id-two"
        assert matches[0].source == "id-two"

    def test_missing_store_raises_key_error(self, standard_db: Path) -> None:
        """A store id that is not in the file raises `KeyError`."""
        with pytest.raises(KeyError, match="vector_store_id='missing-store'"):
            FaissVectorStore(standard_db, "missing-store")

    def test_legacy_unnamespaced_key_is_not_visible(self, tmp_path: Path) -> None:
        """Pre-1.0 keys without the ``vector_io::faiss`` namespace are ignored."""
        path = tmp_path / "legacy.db"
        payload = _store_payload(
            [[1.0, 0.0]],
            {0: {"content": "hidden", "chunk_id": "hidden-id"}},
        )
        _write_kv_value(path, f"faiss_index:v3::{_STORE_ID}", payload)

        with pytest.raises(KeyError, match=f"vector_store_id={_STORE_ID!r}"):
            FaissVectorStore(path, _STORE_ID)

    def test_missing_kvstore_table_raises(self, tmp_path: Path) -> None:
        """An empty SQLite file, with no ``kvstore`` table, raises."""
        path = tmp_path / "empty.db"
        sqlite3.connect(path).close()

        with pytest.raises(sqlite3.OperationalError, match="kvstore"):
            FaissVectorStore(path, _STORE_ID)

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        """A kvstore value that is not JSON raises `JSONDecodeError`."""
        path = tmp_path / "bad-json.db"
        _write_kv_value(path, _faiss_key(_STORE_ID), "not-json")

        with pytest.raises(json.JSONDecodeError):
            FaissVectorStore(path, _STORE_ID)

    def test_payload_missing_index_raises(self, tmp_path: Path) -> None:
        """A payload without ``faiss_index`` raises `KeyError`."""
        path = tmp_path / "no-index.db"
        _write_kv_value(path, _faiss_key(_STORE_ID), json.dumps({"chunk_by_index": {}}))

        with pytest.raises(KeyError, match="faiss_index"):
            FaissVectorStore(path, _STORE_ID)

    def test_undecodable_index_blob_raises(self, tmp_path: Path) -> None:
        """A ``faiss_index`` blob that is not a serialized index raises."""
        path = tmp_path / "bad-index.db"
        payload = json.dumps(
            {
                "faiss_index": base64.b64encode(b"not-an-npy").decode("ascii"),
                "chunk_by_index": {},
            }
        )
        _write_kv_value(path, _faiss_key(_STORE_ID), payload)

        with pytest.raises(ValueError):
            FaissVectorStore(path, _STORE_ID)

    def test_non_numeric_chunk_index_raises(self, tmp_path: Path) -> None:
        """Chunk map keys must be base-10 Faiss row ids."""
        path = tmp_path / "bad-chunk-key.db"
        payload = json.dumps(
            {
                "faiss_index": _encode_index(_build_index([[1.0, 0.0]])),
                "chunk_by_index": {
                    "row": json.dumps({"content": "text", "chunk_id": "id"})
                },
            }
        )
        _write_kv_value(path, _faiss_key(_STORE_ID), payload)

        with pytest.raises(ValueError):
            FaissVectorStore(path, _STORE_ID)

    def test_chunk_entry_must_be_a_json_string(self, tmp_path: Path) -> None:
        """``chunk_by_index`` values are JSON text, not nested objects."""
        path = tmp_path / "chunk-object.db"
        payload = json.dumps(
            {
                "faiss_index": _encode_index(_build_index([[1.0, 0.0]])),
                "chunk_by_index": {"0": {"content": "text", "chunk_id": "id"}},
            }
        )
        _write_kv_value(path, _faiss_key(_STORE_ID), payload)

        with pytest.raises(TypeError):
            FaissVectorStore(path, _STORE_ID)

    def test_chunk_missing_content_raises(self, tmp_path: Path) -> None:
        """A stored chunk without ``content`` raises `KeyError`."""
        path = tmp_path / "no-content.db"
        _write_store(path, _STORE_ID, [[1.0, 0.0]], {0: {"chunk_id": "id-only"}})

        with pytest.raises(KeyError, match="content"):
            FaissVectorStore(path, _STORE_ID)


class TestFaissVectorStoreSearch:
    """Tests for scoring, filtering, and merging Faiss search hits."""

    @pytest.mark.asyncio
    async def test_ranks_matches_by_converted_l2_score(self, standard_db: Path) -> None:
        """Squared L2 distance becomes ``1 / (1 + distance)``, highest score first."""
        store = FaissVectorStore(standard_db, _STORE_ID)

        matches = await store.search([[1.0, 0.0]], limit=3)

        assert [(match.id, match.score) for match in matches] == [
            ("chunk-alpha", pytest.approx(_score(0.0))),
            ("chunk-gamma", pytest.approx(_score(1.0))),
            ("chunk-beta", pytest.approx(_score(2.0))),
        ]

    @pytest.mark.asyncio
    async def test_limit_truncates_ranked_matches(self, standard_db: Path) -> None:
        """`limit` keeps the nearest rows after they are ranked."""
        store = FaissVectorStore(standard_db, _STORE_ID)

        matches = await store.search([[1.0, 0.0]], limit=1)

        assert [match.id for match in matches] == ["chunk-alpha"]

    @pytest.mark.asyncio
    async def test_threshold_drops_lower_scores_and_keeps_equal(
        self, standard_db: Path
    ) -> None:
        """Scores below `threshold` are dropped; a score equal to it is kept."""
        store = FaissVectorStore(standard_db, _STORE_ID)

        kept = await store.search([[1.0, 0.0]], limit=3, threshold=_score(1.0))
        dropped = await store.search(
            [[1.0, 0.0]], limit=3, threshold=_score(1.0) + 0.01
        )

        assert [match.id for match in kept] == ["chunk-alpha", "chunk-gamma"]
        assert [match.id for match in dropped] == ["chunk-alpha"]

    @pytest.mark.asyncio
    async def test_threshold_above_every_score_returns_nothing(
        self, standard_db: Path
    ) -> None:
        """A threshold no row can meet returns an empty list."""
        store = FaissVectorStore(standard_db, _STORE_ID)

        matches = await store.search(
            [[1.0, 0.0]], limit=3, threshold=_score(0.0) + 0.01
        )

        assert matches == []

    @pytest.mark.asyncio
    async def test_merges_queries_keeping_the_best_score_per_row(
        self, tmp_path: Path
    ) -> None:
        """Overlapping hits from several query vectors collapse to each row's best score."""
        path = tmp_path / "merge.db"
        _write_store(
            path,
            _STORE_ID,
            [[0.0, 0.0], [2.0, 0.0]],
            {
                0: {"content": "origin", "chunk_id": "origin"},
                1: {"content": "right", "chunk_id": "right"},
            },
        )
        store = FaissVectorStore(path, _STORE_ID)

        # [0, 0] scores origin at 1 and right at 0.2.
        # [2, 1] scores right at 0.5 and origin at 1/6.
        matches = await store.search([[0.0, 0.0], [2.0, 1.0]], limit=2)

        assert [(match.id, match.score) for match in matches] == [
            ("origin", pytest.approx(_score(0.0))),
            ("right", pytest.approx(_score(1.0))),
        ]

    @pytest.mark.asyncio
    async def test_applies_limit_after_merging_queries(self, tmp_path: Path) -> None:
        """The merged ranking is truncated to `limit`, not each query's hits."""
        path = tmp_path / "merge-limit.db"
        _write_store(
            path,
            _STORE_ID,
            [[0.0, 0.0], [2.0, 0.0]],
            {
                0: {"content": "origin", "chunk_id": "origin"},
                1: {"content": "right", "chunk_id": "right"},
            },
        )
        store = FaissVectorStore(path, _STORE_ID)

        matches = await store.search([[0.0, 0.0], [2.0, 1.0]], limit=1)

        assert [match.id for match in matches] == ["origin"]

    @pytest.mark.asyncio
    async def test_skips_faiss_padding_when_limit_exceeds_rows(
        self, tmp_path: Path
    ) -> None:
        """Faiss pads short result lists with index ``-1``; those rows are ignored."""
        path = tmp_path / "short.db"
        _write_store(
            path, _STORE_ID, [[1.0, 0.0]], {0: {"content": "only", "chunk_id": "only"}}
        )
        store = FaissVectorStore(path, _STORE_ID)

        matches = await store.search([[1.0, 0.0]], limit=5)

        assert [match.id for match in matches] == ["only"]
        assert matches[0].score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_skips_rows_that_have_no_stored_chunk(self, tmp_path: Path) -> None:
        """An index row with no ``chunk_by_index`` entry is left out of the results."""
        path = tmp_path / "gap.db"
        _write_store(
            path,
            _STORE_ID,
            [[0.0, 0.0], [1.0, 0.0]],
            {0: {"content": "kept", "chunk_id": "kept"}},
        )
        store = FaissVectorStore(path, _STORE_ID)

        matches = await store.search([[1.0, 0.0]], limit=2)

        assert [match.id for match in matches] == ["kept"]
        assert matches[0].score == pytest.approx(_score(1.0))

    @pytest.mark.asyncio
    async def test_empty_index_returns_no_matches(self, tmp_path: Path) -> None:
        """A store with an index and no rows searches to an empty list."""
        path = tmp_path / "empty-index.db"
        _write_store(path, _STORE_ID, [], {}, dimension=2)
        store = FaissVectorStore(path, _STORE_ID)

        matches = await store.search([[1.0, 0.0]], limit=3)

        assert matches == []

    @pytest.mark.asyncio
    async def test_missing_chunk_id_gets_a_generated_id(self, tmp_path: Path) -> None:
        """Chunks without ``chunk_id`` get a UUID id and no source."""
        path = tmp_path / "no-id.db"
        _write_store(
            path,
            _STORE_ID,
            [[0.0, 0.0], [1.0, 0.0]],
            {
                0: {"content": "first"},
                1: {"content": "second", "metadata": {"k": "v"}},
            },
        )
        store = FaissVectorStore(path, _STORE_ID)

        matches = await store.search([[0.0, 0.0]], limit=2)
        by_content = {match.content: match for match in matches}

        assert uuid.UUID(by_content["first"].id).version == 4
        assert uuid.UUID(by_content["second"].id).version == 4
        assert by_content["first"].id != by_content["second"].id
        assert by_content["first"].source is None
        assert by_content["second"].source is None
        assert by_content["second"].metadata == {"k": "v"}

    @pytest.mark.asyncio
    async def test_blank_chunk_id_is_replaced_but_kept_as_source(
        self, tmp_path: Path
    ) -> None:
        """An empty ``chunk_id`` is not a usable id, and is still stored as the source."""
        path = tmp_path / "blank-id.db"
        _write_store(
            path, _STORE_ID, [[1.0, 0.0]], {0: {"content": "blank", "chunk_id": ""}}
        )
        store = FaissVectorStore(path, _STORE_ID)

        matches = await store.search([[1.0, 0.0]], limit=1)

        assert uuid.UUID(matches[0].id).version == 4
        assert matches[0].source == ""

    @pytest.mark.asyncio
    async def test_missing_or_null_metadata_defaults_to_empty(
        self, tmp_path: Path
    ) -> None:
        """Omitted and null ``metadata`` both become an empty mapping."""
        path = tmp_path / "metadata.db"
        _write_store(
            path,
            _STORE_ID,
            [[0.0, 0.0], [1.0, 0.0]],
            {
                0: {"content": "omitted", "chunk_id": "omitted"},
                1: {"content": "null", "chunk_id": "null", "metadata": None},
            },
        )
        store = FaissVectorStore(path, _STORE_ID)

        matches = await store.search([[0.0, 0.0]], limit=2)
        by_id = {match.id: match for match in matches}

        assert by_id["omitted"].metadata == {}
        assert by_id["null"].metadata == {}

    @pytest.mark.asyncio
    async def test_reads_rag_content_sqlite_faiss_file(self) -> None:
        """A store written by rag-content deserializes to its stored chunk."""
        store = FaissVectorStore(_PDF_DB, _PDF_STORE_ID)

        matches = await store.search([[0.0] * 768], limit=1)

        assert len(matches) == 1
        assert "purple penguin named Zephyr" in matches[0].content
        assert matches[0].id == _PDF_CHUNK_ID
        assert matches[0].source == _PDF_CHUNK_ID
        assert matches[0].metadata["file_name"] == "lightspeed-field-notes.pdf"
        assert 0.0 < matches[0].score <= 1.0


class TestFaissKnowledgeSource:
    """Tests for the Faiss-backed knowledge source wrapper."""

    @pytest.fixture(name="embedded_db")
    def embedded_db_fixture(self, tmp_path: Path) -> Path:
        """Create a store whose nearest row to an all-ones vector is ``near``.

        Args:
            tmp_path: Per-test temporary directory.

        Returns:
            Path to the sqlite-faiss file.

        """
        path = tmp_path / "embedded.db"
        _write_store(
            path,
            _STORE_ID,
            [[1.0, 1.0], [0.0, 0.0]],
            {
                0: {
                    "content": "near",
                    "chunk_id": "near-id",
                    "metadata": {"k": "near"},
                },
                1: {"content": "far", "chunk_id": "far-id", "metadata": {"k": "far"}},
            },
        )
        return path

    def test_defaults_to_tool_mode(self, embedded_db: Path) -> None:
        """Omitted options use tool mode, top 5, and no score cutoff."""
        embedder, _model = _embedder()
        source = FaissKnowledgeSource(
            name="docs",
            db_path=embedded_db,
            vector_store_id=_STORE_ID,
            embedder=embedder,
        )

        assert source.name == "docs"
        assert source.mode == {"tool"}
        assert source.top_k == 5
        assert source.score_threshold == 0.0
        assert source.embedding_settings is None
        assert isinstance(source.store, FaissVectorStore)

    def test_default_mode_is_not_shared_across_instances(
        self, embedded_db: Path
    ) -> None:
        """Each defaulted source gets its own mode set."""
        first = FaissKnowledgeSource(
            "docs",
            embedded_db,
            _STORE_ID,
            _embedder()[0],
        )
        second = FaissKnowledgeSource(
            "docs",
            embedded_db,
            _STORE_ID,
            _embedder()[0],
        )

        first.mode.add("auto")

        assert second.mode == {"tool"}

    def test_honors_explicit_mode_and_search_options(self, embedded_db: Path) -> None:
        """Explicit mode, settings, top_k, and threshold are stored on the source."""
        embedder, _model = _embedder()
        settings: EmbeddingSettings = {"dimensions": 2}

        source = FaissKnowledgeSource(
            name="docs",
            db_path=str(embedded_db),
            vector_store_id=_STORE_ID,
            embedder=embedder,
            embedding_settings=settings,
            top_k=1,
            score_threshold=0.9,
            mode={"tool", "auto"},
        )

        assert source.mode == {"tool", "auto"}
        assert source.embedding_settings == {"dimensions": 2}
        assert source.top_k == 1
        assert source.score_threshold == 0.9

    def test_missing_store_raises_key_error(self, tmp_path: Path) -> None:
        """A missing store id fails while the source is being built."""
        path = tmp_path / "empty-of-stores.db"
        _write_store(
            path, "other", [[1.0, 0.0]], {0: {"content": "other", "chunk_id": "other"}}
        )

        with pytest.raises(KeyError, match="vector_store_id='missing-store'"):
            FaissKnowledgeSource("docs", path, "missing-store", _embedder()[0])

    @pytest.mark.asyncio
    async def test_search_embeds_the_prompt_and_returns_ranked_matches(
        self, embedded_db: Path
    ) -> None:
        """Search embeds the prompt and returns the nearest stored chunks."""
        embedder, model = _embedder()
        source = FaissKnowledgeSource("docs", embedded_db, _STORE_ID, embedder)

        matches = await source.search("where is the near document?")

        assert model.inputs == ["where is the near document?"]
        assert [(match.id, match.score) for match in matches] == [
            ("near-id", pytest.approx(_score(0.0))),
            ("far-id", pytest.approx(_score(2.0))),
        ]
        assert matches[0].metadata == {"k": "near"}

    @pytest.mark.asyncio
    async def test_search_applies_top_k_and_score_threshold(
        self, embedded_db: Path
    ) -> None:
        """`top_k` and `score_threshold` are passed through to the store search."""
        source = FaissKnowledgeSource(
            "docs",
            embedded_db,
            _STORE_ID,
            _embedder()[0],
            top_k=1,
            score_threshold=0.9,
        )

        matches = await source.search("query")

        assert [match.id for match in matches] == ["near-id"]

    @pytest.mark.asyncio
    async def test_forwards_embedding_settings(self, embedded_db: Path) -> None:
        """Per-source embedding settings override the model and reach the embedder."""
        embedder, model = _embedder(dimensions=8)
        settings: EmbeddingSettings = {"dimensions": 2}
        source = FaissKnowledgeSource(
            "docs",
            embedded_db,
            _STORE_ID,
            embedder,
            embedding_settings=settings,
            top_k=1,
        )

        matches = await source.search("query")

        assert model.last_settings == {"dimensions": 2}
        assert [match.id for match in matches] == ["near-id"]

    @pytest.mark.asyncio
    async def test_readiness_reports_ready_after_load(self, embedded_db: Path) -> None:
        """A source whose index loaded reports ready."""
        source = FaissKnowledgeSource("docs", embedded_db, _STORE_ID, _embedder()[0])

        readiness = await source.readiness()

        assert readiness.status == "ready"
        assert readiness.message == "FAISS index loaded"
