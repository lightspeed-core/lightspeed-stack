"""Functional tests for LCORE-1426: BYOK Config Refactoring.

Tests verify that all RAG-related configuration is unified under a single
``rag`` section, that old config formats are backward-compatible with
deprecation warnings, and that max-chunk constants are user-configurable.
"""

# pylint: disable=no-member

from collections.abc import Generator
from pathlib import Path

import pytest

from configuration import AppConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_app_config() -> Generator[None, None, None]:
    """Reset AppConfig singleton between tests."""
    # pylint: disable=broad-exception-caught,protected-access
    try:
        AppConfig()._configuration = None  # type: ignore[attr-defined]
        AppConfig()._quota_limiters = []  # type: ignore[attr-defined]
    except Exception:
        pass
    yield
    try:
        AppConfig()._configuration = None  # type: ignore[attr-defined]
        AppConfig()._quota_limiters = []  # type: ignore[attr-defined]
    except Exception:
        pass


def _base_config() -> dict:
    """Return the minimal required config sections (non-RAG)."""
    return {
        "name": "test",
        "service": {"host": "localhost", "port": 8080},
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {},
        "authentication": {"module": "noop"},
    }


def _make_config(extra: dict) -> AppConfig:
    """Create an AppConfig initialised with *extra* merged into the base."""
    cfg = AppConfig()
    data = _base_config()
    data.update(extra)
    cfg.init_from_dict(data)
    return cfg


# ===================================================================
# 1. New config structure — rag.byok.stores
# ===================================================================


class TestNewByokStoresSection:
    """AC-1: byok_rag section is moved under rag.byok.stores."""

    def test_single_store_under_rag_byok_stores(self, tmp_path: Path) -> None:
        """A single BYOK store defined under rag.byok.stores is accepted."""
        db_file = tmp_path / "ocp.faiss"
        db_file.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "stores": [
                            {
                                "rag_id": "ocp-docs",
                                "backend": "faiss",
                                "embedding_model": "sentence-transformers/all-mpnet-base-v2",
                                "embedding_dimension": 768,
                                "vector_db_id": "vs_123",
                                "db_path": str(db_file),
                                "score_multiplier": 1.0,
                            },
                        ],
                    },
                },
            }
        )
        # The config should be loadable and the store accessible
        assert cfg.configuration is not None

    def test_multiple_stores_under_rag_byok_stores(self, tmp_path: Path) -> None:
        """Multiple BYOK stores under rag.byok.stores are accepted."""
        db1 = tmp_path / "ocp.faiss"
        db1.touch()
        db2 = tmp_path / "kb.faiss"
        db2.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "stores": [
                            {
                                "rag_id": "ocp-docs",
                                "backend": "faiss",
                                "embedding_dimension": 768,
                                "vector_db_id": "vs_123",
                                "db_path": str(db1),
                                "score_multiplier": 1.0,
                            },
                            {
                                "rag_id": "knowledge-base",
                                "backend": "faiss",
                                "embedding_dimension": 384,
                                "vector_db_id": "vs_456",
                                "db_path": str(db2),
                                "score_multiplier": 1.2,
                            },
                        ],
                    },
                },
            }
        )
        assert cfg.configuration is not None

    def test_empty_stores_list_accepted(self) -> None:
        """An empty rag.byok.stores list is valid (no BYOK stores)."""
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "stores": [],
                    },
                },
            }
        )
        assert cfg.configuration is not None


# ===================================================================
# 2. New config structure — rag.retrieval.inline / rag.retrieval.tool
# ===================================================================


class TestNewRetrievalSection:
    """AC-2: rag.inline and rag.tool moved under rag.retrieval."""

    def test_retrieval_inline_sources(self) -> None:
        """rag.retrieval.inline.sources accepts a list of source IDs."""
        cfg = _make_config(
            {
                "rag": {
                    "retrieval": {
                        "inline": {
                            "sources": ["ocp-docs", "knowledge-base"],
                        },
                    },
                },
            }
        )
        assert cfg.configuration is not None

    def test_retrieval_tool_sources(self) -> None:
        """rag.retrieval.tool.sources accepts a list of source IDs."""
        cfg = _make_config(
            {
                "rag": {
                    "retrieval": {
                        "tool": {
                            "sources": ["ocp-docs", "knowledge-base"],
                        },
                    },
                },
            }
        )
        assert cfg.configuration is not None

    def test_retrieval_inline_and_tool_together(self) -> None:
        """Both inline and tool retrieval can be configured simultaneously."""
        cfg = _make_config(
            {
                "rag": {
                    "retrieval": {
                        "inline": {
                            "sources": ["ocp-docs", "knowledge-base", "okp"],
                        },
                        "tool": {
                            "sources": ["ocp-docs", "knowledge-base"],
                        },
                    },
                },
            }
        )
        assert cfg.configuration is not None

    def test_retrieval_empty_sources(self) -> None:
        """Empty sources lists are valid (disables that retrieval mode)."""
        cfg = _make_config(
            {
                "rag": {
                    "retrieval": {
                        "inline": {
                            "sources": [],
                        },
                        "tool": {
                            "sources": [],
                        },
                    },
                },
            }
        )
        assert cfg.configuration is not None


# ===================================================================
# 3. Configurable max_chunks with correct defaults
# ===================================================================


class TestMaxChunksConfigurable:
    """AC-3: RAG max chunk constants are user-configurable via config."""

    def test_byok_max_chunks_default_is_10(self) -> None:
        """rag.byok.max_chunks defaults to 10 when not specified."""
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "stores": [],
                    },
                },
            }
        )
        rag_config = cfg.configuration.rag
        byok = rag_config.byok
        assert byok.max_chunks == 10

    def test_byok_max_chunks_custom_value(self, tmp_path: Path) -> None:
        """rag.byok.max_chunks can be set to a custom value."""
        db_file = tmp_path / "test.faiss"
        db_file.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "max_chunks": 20,
                        "stores": [
                            {
                                "rag_id": "store-1",
                                "backend": "faiss",
                                "vector_db_id": "vs_1",
                                "db_path": str(db_file),
                            },
                        ],
                    },
                },
            }
        )
        assert cfg.configuration.rag.byok.max_chunks == 20

    def test_okp_max_chunks_default_is_5(self) -> None:
        """rag.okp.max_chunks defaults to 5 when not specified."""
        cfg = _make_config(
            {
                "rag": {
                    "okp": {
                        "offline": True,
                    },
                },
            }
        )
        assert cfg.configuration.rag.okp.max_chunks == 5

    def test_okp_max_chunks_custom_value(self) -> None:
        """rag.okp.max_chunks can be set to a custom value."""
        cfg = _make_config(
            {
                "rag": {
                    "okp": {
                        "offline": True,
                        "max_chunks": 15,
                    },
                },
            }
        )
        assert cfg.configuration.rag.okp.max_chunks == 15

    def test_inline_max_chunks_default_is_10(self) -> None:
        """rag.retrieval.inline.max_chunks defaults to 10."""
        cfg = _make_config(
            {
                "rag": {
                    "retrieval": {
                        "inline": {
                            "sources": ["store-1"],
                        },
                    },
                },
            }
        )
        assert cfg.configuration.rag.retrieval.inline.max_chunks == 10

    def test_inline_max_chunks_custom_value(self) -> None:
        """rag.retrieval.inline.max_chunks can be set to a custom value."""
        cfg = _make_config(
            {
                "rag": {
                    "retrieval": {
                        "inline": {
                            "sources": ["store-1"],
                            "max_chunks": 25,
                        },
                    },
                },
            }
        )
        assert cfg.configuration.rag.retrieval.inline.max_chunks == 25

    def test_tool_max_chunks_default_is_10(self) -> None:
        """rag.retrieval.tool.max_chunks defaults to 10."""
        cfg = _make_config(
            {
                "rag": {
                    "retrieval": {
                        "tool": {
                            "sources": ["store-1"],
                        },
                    },
                },
            }
        )
        assert cfg.configuration.rag.retrieval.tool.max_chunks == 10

    def test_tool_max_chunks_custom_value(self) -> None:
        """rag.retrieval.tool.max_chunks can be set to a custom value."""
        cfg = _make_config(
            {
                "rag": {
                    "retrieval": {
                        "tool": {
                            "sources": ["store-1"],
                            "max_chunks": 50,
                        },
                    },
                },
            }
        )
        assert cfg.configuration.rag.retrieval.tool.max_chunks == 50


# ===================================================================
# 4. rag_type renamed to backend
# ===================================================================


class TestBackendFieldRename:
    """AC-4: rag_type field renamed to backend."""

    def test_backend_field_accepted(self, tmp_path: Path) -> None:
        """The new 'backend' field is accepted in store config."""
        db_file = tmp_path / "test.faiss"
        db_file.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "stores": [
                            {
                                "rag_id": "store-1",
                                "backend": "faiss",
                                "vector_db_id": "vs_1",
                                "db_path": str(db_file),
                            },
                        ],
                    },
                },
            }
        )
        assert cfg.configuration is not None

    def test_old_rag_type_still_accepted_with_deprecation(
        self,
        tmp_path: Path,
    ) -> None:
        """The old 'rag_type' field is still accepted for backward compat."""
        db_file = tmp_path / "test.faiss"
        db_file.touch()
        with pytest.warns(DeprecationWarning, match="rag_type"):
            cfg = _make_config(
                {
                    "rag": {
                        "byok": {
                            "stores": [
                                {
                                    "rag_id": "store-1",
                                    "rag_type": "inline::faiss",
                                    "vector_db_id": "vs_1",
                                    "db_path": str(db_file),
                                },
                            ],
                        },
                    },
                }
            )
        assert cfg.configuration is not None

    def test_backend_uses_short_name(self, tmp_path: Path) -> None:
        """Backend uses short names like 'faiss' instead of 'inline::faiss'."""
        db_file = tmp_path / "test.faiss"
        db_file.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "stores": [
                            {
                                "rag_id": "store-1",
                                "backend": "faiss",
                                "vector_db_id": "vs_1",
                                "db_path": str(db_file),
                            },
                        ],
                    },
                },
            }
        )
        assert cfg.configuration is not None


# ===================================================================
# 5. Backward compatibility — old config format
# ===================================================================


class TestBackwardCompatibility:
    """AC-5: Old config format still works with deprecation warnings."""

    def test_old_top_level_byok_rag_still_works(
        self,
        tmp_path: Path,
    ) -> None:
        """The old top-level 'byok_rag' key is still accepted."""
        import warnings

        db_file = tmp_path / "test.faiss"
        db_file.touch()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            cfg = _make_config(
                {
                    "byok_rag": [
                        {
                            "rag_id": "store-1",
                            "vector_db_id": "vs_1",
                            "db_path": str(db_file),
                        },
                    ],
                }
            )
        assert cfg.configuration is not None

    def test_old_byok_rag_emits_deprecation_warning(
        self,
        tmp_path: Path,
    ) -> None:
        """Using old top-level 'byok_rag' emits a deprecation warning."""
        db_file = tmp_path / "test.faiss"
        db_file.touch()
        with pytest.warns(DeprecationWarning, match="byok_rag"):
            _make_config(
                {
                    "byok_rag": [
                        {
                            "rag_id": "store-1",
                            "vector_db_id": "vs_1",
                            "db_path": str(db_file),
                        },
                    ],
                }
            )

    def test_both_byok_rag_and_rag_byok_stores_raises_error(
        self,
        tmp_path: Path,
    ) -> None:
        """Providing both deprecated byok_rag and rag.byok.stores raises ValueError."""
        from pydantic import ValidationError

        db1 = tmp_path / "old.faiss"
        db1.touch()
        db2 = tmp_path / "new.faiss"
        db2.touch()
        with pytest.raises((ValidationError, ValueError), match="byok_rag"):
            _make_config(
                {
                    "byok_rag": [
                        {
                            "rag_id": "old-store",
                            "vector_db_id": "vs_old",
                            "db_path": str(db1),
                        },
                    ],
                    "rag": {
                        "byok": {
                            "stores": [
                                {
                                    "rag_id": "new-store",
                                    "backend": "faiss",
                                    "vector_db_id": "vs_new",
                                    "db_path": str(db2),
                                },
                            ],
                        },
                    },
                }
            )

    def test_old_rag_inline_list_still_works(
        self,
    ) -> None:
        """The old rag.inline (flat list) format is still accepted."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            cfg = _make_config(
                {
                    "rag": {
                        "inline": ["store-1", "store-2"],
                    },
                }
            )
        assert cfg.configuration is not None

    def test_old_rag_tool_list_still_works(
        self,
    ) -> None:
        """The old rag.tool (flat list) format is still accepted."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            cfg = _make_config(
                {
                    "rag": {
                        "tool": ["store-1"],
                    },
                }
            )
        assert cfg.configuration is not None

    def test_old_rag_inline_emits_deprecation(
        self,
    ) -> None:
        """Using old rag.inline (flat list) emits a deprecation warning."""
        with pytest.warns(DeprecationWarning, match="inline"):
            _make_config(
                {
                    "rag": {
                        "inline": ["store-1", "store-2"],
                    },
                }
            )

    def test_old_rag_tool_emits_deprecation(
        self,
    ) -> None:
        """Using old rag.tool (flat list) emits a deprecation warning."""
        with pytest.warns(DeprecationWarning, match="tool"):
            _make_config(
                {
                    "rag": {
                        "tool": ["store-1"],
                    },
                }
            )

    def test_old_top_level_okp_still_works(
        self,
    ) -> None:
        """The old top-level 'okp' key is still accepted."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            cfg = _make_config(
                {
                    "okp": {
                        "offline": True,
                        "chunk_filter_query": "is_chunk:true",
                    },
                }
            )
        assert cfg.configuration is not None

    def test_old_top_level_okp_emits_deprecation(
        self,
    ) -> None:
        """Using old top-level 'okp' emits a deprecation warning."""
        with pytest.warns(DeprecationWarning, match="okp"):
            _make_config(
                {
                    "okp": {
                        "offline": True,
                    },
                }
            )


# ===================================================================
# 6. Full target config structure
# ===================================================================


class TestFullTargetConfigStructure:
    """Test the complete target config structure from the spec."""

    def test_full_target_config_accepted(self, tmp_path: Path) -> None:
        """The full target config structure from the spec is accepted."""
        db1 = tmp_path / "ocp.faiss"
        db1.touch()
        db2 = tmp_path / "kb.faiss"
        db2.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "max_chunks": 10,
                        "stores": [
                            {
                                "rag_id": "ocp-docs",
                                "backend": "faiss",
                                "embedding_model": "sentence-transformers/all-mpnet-base-v2",
                                "embedding_dimension": 768,
                                "vector_db_id": "vs_123",
                                "db_path": str(db1),
                                "score_multiplier": 1.0,
                            },
                            {
                                "rag_id": "knowledge-base",
                                "backend": "faiss",
                                "embedding_dimension": 384,
                                "vector_db_id": "vs_456",
                                "db_path": str(db2),
                                "score_multiplier": 1.2,
                            },
                        ],
                    },
                    "okp": {
                        "offline": True,
                        "chunk_filter_query": "is_chunk:true",
                        "max_chunks": 5,
                    },
                    "retrieval": {
                        "inline": {
                            "sources": ["ocp-docs", "knowledge-base", "okp"],
                            "max_chunks": 10,
                        },
                        "tool": {
                            "sources": ["ocp-docs", "knowledge-base"],
                            "max_chunks": 10,
                        },
                    },
                },
            }
        )
        assert cfg.configuration is not None
        rag = cfg.configuration.rag

        # Verify byok section
        assert rag.byok.max_chunks == 10
        assert len(rag.byok.stores) == 2
        assert rag.byok.stores[0].rag_id == "ocp-docs"
        assert rag.byok.stores[1].rag_id == "knowledge-base"

        # Verify okp section
        assert rag.okp.offline is True
        assert rag.okp.chunk_filter_query == "is_chunk:true"
        assert rag.okp.max_chunks == 5

        # Verify retrieval section
        assert rag.retrieval.inline.sources == [
            "ocp-docs",
            "knowledge-base",
            "okp",
        ]
        assert rag.retrieval.inline.max_chunks == 10
        assert rag.retrieval.tool.sources == [
            "ocp-docs",
            "knowledge-base",
        ]
        assert rag.retrieval.tool.max_chunks == 10


# ===================================================================
# 7. Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge cases: missing fields, invalid values, partial configs."""

    def test_rag_section_with_no_subsections(self) -> None:
        """An empty rag section is valid (all subsections optional)."""
        cfg = _make_config(
            {
                "rag": {},
            }
        )
        assert cfg.configuration is not None

    def test_no_rag_section_at_all(self) -> None:
        """Config without any rag section is valid (RAG is optional)."""
        cfg = _make_config({})
        assert cfg.configuration is not None

    def test_byok_without_stores_key(self) -> None:
        """rag.byok without stores key defaults to empty stores."""
        cfg = _make_config(
            {
                "rag": {
                    "byok": {},
                },
            }
        )
        assert cfg.configuration is not None

    def test_retrieval_without_inline_or_tool(self) -> None:
        """rag.retrieval without inline or tool is valid."""
        cfg = _make_config(
            {
                "rag": {
                    "retrieval": {},
                },
            }
        )
        assert cfg.configuration is not None

    def test_max_chunks_must_be_positive(self) -> None:
        """max_chunks with zero or negative value should be rejected."""
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError)):
            _make_config(
                {
                    "rag": {
                        "byok": {
                            "max_chunks": 0,
                            "stores": [],
                        },
                    },
                }
            )

    def test_max_chunks_negative_rejected(self) -> None:
        """Negative max_chunks should be rejected."""
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError)):
            _make_config(
                {
                    "rag": {
                        "retrieval": {
                            "inline": {
                                "sources": [],
                                "max_chunks": -5,
                            },
                        },
                    },
                }
            )

    def test_byok_store_missing_required_rag_id(self, tmp_path: Path) -> None:
        """A BYOK store without rag_id should be rejected."""
        from pydantic import ValidationError

        db_file = tmp_path / "test.faiss"
        db_file.touch()
        with pytest.raises((ValidationError, ValueError)):
            _make_config(
                {
                    "rag": {
                        "byok": {
                            "stores": [
                                {
                                    "backend": "faiss",
                                    "vector_db_id": "vs_1",
                                    "db_path": str(db_file),
                                },
                            ],
                        },
                    },
                }
            )

    def test_byok_store_missing_required_vector_db_id(
        self,
        tmp_path: Path,
    ) -> None:
        """A BYOK store without vector_db_id should be rejected."""
        from pydantic import ValidationError

        db_file = tmp_path / "test.faiss"
        db_file.touch()
        with pytest.raises((ValidationError, ValueError)):
            _make_config(
                {
                    "rag": {
                        "byok": {
                            "stores": [
                                {
                                    "rag_id": "store-1",
                                    "backend": "faiss",
                                    "db_path": str(db_file),
                                },
                            ],
                        },
                    },
                }
            )

    def test_okp_max_chunks_zero_rejected(self) -> None:
        """OKP max_chunks of zero should be rejected."""
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError)):
            _make_config(
                {
                    "rag": {
                        "okp": {
                            "offline": True,
                            "max_chunks": 0,
                        },
                    },
                }
            )

    def test_tool_max_chunks_zero_rejected(self) -> None:
        """Tool max_chunks of zero should be rejected."""
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError)):
            _make_config(
                {
                    "rag": {
                        "retrieval": {
                            "tool": {
                                "sources": [],
                                "max_chunks": 0,
                            },
                        },
                    },
                }
            )


# ===================================================================
# 8. OKP under rag section
# ===================================================================


class TestOkpUnderRag:
    """Test OKP configuration under the rag section."""

    def test_okp_under_rag_with_offline_true(self) -> None:
        """rag.okp with offline=True is accepted."""
        cfg = _make_config(
            {
                "rag": {
                    "okp": {
                        "offline": True,
                    },
                },
            }
        )
        assert cfg.configuration.rag.okp.offline is True

    def test_okp_under_rag_with_offline_false(self) -> None:
        """rag.okp with offline=False is accepted."""
        cfg = _make_config(
            {
                "rag": {
                    "okp": {
                        "offline": False,
                    },
                },
            }
        )
        assert cfg.configuration.rag.okp.offline is False

    def test_okp_under_rag_with_chunk_filter_query(self) -> None:
        """rag.okp.chunk_filter_query is accepted."""
        cfg = _make_config(
            {
                "rag": {
                    "okp": {
                        "offline": True,
                        "chunk_filter_query": "is_chunk:true",
                    },
                },
            }
        )
        assert cfg.configuration.rag.okp.chunk_filter_query == "is_chunk:true"

    def test_okp_under_rag_defaults(self) -> None:
        """rag.okp with no fields uses defaults."""
        cfg = _make_config(
            {
                "rag": {
                    "okp": {},
                },
            }
        )
        assert cfg.configuration.rag.okp.offline is True
        assert cfg.configuration.rag.okp.max_chunks == 5


# ===================================================================
# 9. Constant mapping verification
# ===================================================================


class TestConstantMappingDefaults:
    """Verify the constant mapping table from the spec.

    | Old constant           | New config field                  | Default |
    |------------------------|-----------------------------------|---------|
    | BYOK_RAG_MAX_CHUNKS    | rag.byok.max_chunks               | 10      |
    | OKP_RAG_MAX_CHUNKS     | rag.okp.max_chunks                | 5       |
    | INLINE_RAG_MAX_CHUNKS  | rag.retrieval.inline.max_chunks   | 10      |
    | TOOL_RAG_MAX_CHUNKS    | rag.retrieval.tool.max_chunks     | 10      |
    """

    def test_all_defaults_match_spec(self, tmp_path: Path) -> None:
        """All max_chunks defaults match the constant mapping table."""
        db_file = tmp_path / "test.faiss"
        db_file.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "stores": [
                            {
                                "rag_id": "store-1",
                                "backend": "faiss",
                                "vector_db_id": "vs_1",
                                "db_path": str(db_file),
                            },
                        ],
                    },
                    "okp": {
                        "offline": True,
                    },
                    "retrieval": {
                        "inline": {
                            "sources": ["store-1"],
                        },
                        "tool": {
                            "sources": ["store-1"],
                        },
                    },
                },
            }
        )
        rag = cfg.configuration.rag
        assert rag.byok.max_chunks == 10, "BYOK_RAG_MAX_CHUNKS default should be 10"
        assert rag.okp.max_chunks == 5, "OKP_RAG_MAX_CHUNKS default should be 5"
        assert (
            rag.retrieval.inline.max_chunks == 10
        ), "INLINE_RAG_MAX_CHUNKS default should be 10"
        assert (
            rag.retrieval.tool.max_chunks == 10
        ), "TOOL_RAG_MAX_CHUNKS default should be 10"

    def test_all_max_chunks_overridable(self, tmp_path: Path) -> None:
        """All max_chunks values can be overridden from defaults."""
        db_file = tmp_path / "test.faiss"
        db_file.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "max_chunks": 42,
                        "stores": [
                            {
                                "rag_id": "store-1",
                                "backend": "faiss",
                                "vector_db_id": "vs_1",
                                "db_path": str(db_file),
                            },
                        ],
                    },
                    "okp": {
                        "offline": True,
                        "max_chunks": 99,
                    },
                    "retrieval": {
                        "inline": {
                            "sources": ["store-1"],
                            "max_chunks": 77,
                        },
                        "tool": {
                            "sources": ["store-1"],
                            "max_chunks": 55,
                        },
                    },
                },
            }
        )
        rag = cfg.configuration.rag
        assert rag.byok.max_chunks == 42
        assert rag.okp.max_chunks == 99
        assert rag.retrieval.inline.max_chunks == 77
        assert rag.retrieval.tool.max_chunks == 55


# ===================================================================
# 10. No deprecation warnings for new format
# ===================================================================


class TestNoDeprecationForNewFormat:
    """New config format should NOT emit deprecation warnings."""

    def test_new_format_no_deprecation_warnings(
        self,
        tmp_path: Path,
    ) -> None:
        """Using the new config format should not emit deprecation warnings."""
        import warnings

        db_file = tmp_path / "test.faiss"
        db_file.touch()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _make_config(
                {
                    "rag": {
                        "byok": {
                            "max_chunks": 10,
                            "stores": [
                                {
                                    "rag_id": "store-1",
                                    "backend": "faiss",
                                    "vector_db_id": "vs_1",
                                    "db_path": str(db_file),
                                },
                            ],
                        },
                        "okp": {
                            "offline": True,
                            "max_chunks": 5,
                        },
                        "retrieval": {
                            "inline": {
                                "sources": ["store-1"],
                                "max_chunks": 10,
                            },
                            "tool": {
                                "sources": ["store-1"],
                                "max_chunks": 10,
                            },
                        },
                    },
                }
            )
        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 0, (
            f"New config format should not emit deprecation warnings, "
            f"but got: {[str(w.message) for w in deprecation_warnings]}"
        )


# ===================================================================
# 11. Store field validation in new structure
# ===================================================================


class TestStoreFieldValidation:
    """Validate store fields within the new rag.byok.stores structure."""

    def test_store_with_all_fields(self, tmp_path: Path) -> None:
        """A store with all fields specified is accepted."""
        db_file = tmp_path / "test.faiss"
        db_file.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "stores": [
                            {
                                "rag_id": "full-store",
                                "backend": "faiss",
                                "embedding_model": "sentence-transformers/all-mpnet-base-v2",
                                "embedding_dimension": 768,
                                "vector_db_id": "vs_full",
                                "db_path": str(db_file),
                                "score_multiplier": 1.5,
                            },
                        ],
                    },
                },
            }
        )
        assert cfg.configuration is not None

    def test_store_with_minimal_fields(self, tmp_path: Path) -> None:
        """A store with only required fields is accepted (defaults apply)."""
        db_file = tmp_path / "test.faiss"
        db_file.touch()
        cfg = _make_config(
            {
                "rag": {
                    "byok": {
                        "stores": [
                            {
                                "rag_id": "minimal-store",
                                "vector_db_id": "vs_min",
                                "db_path": str(db_file),
                            },
                        ],
                    },
                },
            }
        )
        assert cfg.configuration is not None

    def test_store_empty_rag_id_rejected(self, tmp_path: Path) -> None:
        """A store with empty rag_id is rejected."""
        from pydantic import ValidationError

        db_file = tmp_path / "test.faiss"
        db_file.touch()
        with pytest.raises((ValidationError, ValueError)):
            _make_config(
                {
                    "rag": {
                        "byok": {
                            "stores": [
                                {
                                    "rag_id": "",
                                    "backend": "faiss",
                                    "vector_db_id": "vs_1",
                                    "db_path": str(db_file),
                                },
                            ],
                        },
                    },
                }
            )

    def test_store_negative_embedding_dimension_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        """A store with negative embedding_dimension is rejected."""
        from pydantic import ValidationError

        db_file = tmp_path / "test.faiss"
        db_file.touch()
        with pytest.raises((ValidationError, ValueError)):
            _make_config(
                {
                    "rag": {
                        "byok": {
                            "stores": [
                                {
                                    "rag_id": "store-1",
                                    "backend": "faiss",
                                    "embedding_dimension": -768,
                                    "vector_db_id": "vs_1",
                                    "db_path": str(db_file),
                                },
                            ],
                        },
                    },
                }
            )

    def test_store_zero_score_multiplier_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        """A store with score_multiplier of 0 is rejected."""
        from pydantic import ValidationError

        db_file = tmp_path / "test.faiss"
        db_file.touch()
        with pytest.raises((ValidationError, ValueError)):
            _make_config(
                {
                    "rag": {
                        "byok": {
                            "stores": [
                                {
                                    "rag_id": "store-1",
                                    "backend": "faiss",
                                    "vector_db_id": "vs_1",
                                    "db_path": str(db_file),
                                    "score_multiplier": 0.0,
                                },
                            ],
                        },
                    },
                }
            )
