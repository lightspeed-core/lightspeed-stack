"""Unit tests for conversation_cache → OGX conversations wiring (RHIDP-14967)."""

import copy
from typing import Any, Optional

import pytest

from constants import CONVERSATIONS_BACKEND_NAME, DEFAULT_CONVERSATIONS_TABLE_NAME
from llama_stack_configuration import (
    enrich_conversation_storage,
    load_default_baseline,
    synthesize_configuration,
    warn_conversation_persistence,
)

# ---------------------------------------------------------------------------
# conversation persistence from conversation_cache (RHIDP-14967)
# ---------------------------------------------------------------------------


def test_enrich_conversation_storage_postgres_h1() -> None:
    """H1: postgres cache upserts conversations_default and retargets store."""
    ls_config = load_default_baseline()
    sql_default_before = copy.deepcopy(ls_config["storage"]["backends"]["sql_default"])
    cache = {
        "type": "postgres",
        "postgres": {
            "host": "db.example.com",
            "db": "lightspeed",
            "user": "ls",
            "password": "${env.POSTGRES_PASSWORD}",
        },
    }
    enrich_conversation_storage(ls_config, cache)
    backend = ls_config["storage"]["backends"][CONVERSATIONS_BACKEND_NAME]
    assert backend == {
        "type": "sql_postgres",
        "host": "db.example.com",
        "port": 5432,
        "db": "lightspeed",
        "user": "ls",
        "password": "${env.POSTGRES_PASSWORD}",
    }
    assert (
        ls_config["storage"]["stores"]["conversations"]["backend"]
        == CONVERSATIONS_BACKEND_NAME
    )
    assert ls_config["storage"]["backends"]["sql_default"] == sql_default_before


def test_enrich_conversation_storage_sqlite_h2() -> None:
    """H2: sqlite cache shares db_path on conversations_default."""
    ls_config = load_default_baseline()
    cache = {
        "type": "sqlite",
        "sqlite": {"db_path": "/var/lib/lightspeed/cache.db"},
    }
    enrich_conversation_storage(ls_config, cache)
    assert ls_config["storage"]["backends"][CONVERSATIONS_BACKEND_NAME] == {
        "type": "sql_sqlite",
        "db_path": "/var/lib/lightspeed/cache.db",
    }
    assert (
        ls_config["storage"]["stores"]["conversations"]["backend"]
        == CONVERSATIONS_BACKEND_NAME
    )


def test_enrich_conversation_storage_creates_store_when_missing_h3() -> None:
    """H3: missing stores.conversations is created with default table_name."""
    ls_config: dict[str, Any] = {"storage": {"backends": {}}}
    cache = {"type": "sqlite", "sqlite": {"db_path": "/data/cache.db"}}
    enrich_conversation_storage(ls_config, cache)
    assert ls_config["storage"]["stores"]["conversations"] == {
        "table_name": DEFAULT_CONVERSATIONS_TABLE_NAME,
        "backend": CONVERSATIONS_BACKEND_NAME,
    }


@pytest.mark.parametrize(
    "ls_config",
    [
        {"storage": None},
        {"storage": {"backends": None, "stores": None}},
        {"storage": {"backends": {}, "stores": None}},
    ],
)
def test_enrich_conversation_storage_tolerates_null_storage_nodes(
    ls_config: dict[str, Any],
) -> None:
    """YAML null storage/backends/stores must not crash; wire from empty dicts."""
    cache = {"type": "sqlite", "sqlite": {"db_path": "/data/cache.db"}}
    enrich_conversation_storage(ls_config, cache)
    assert ls_config["storage"]["backends"][CONVERSATIONS_BACKEND_NAME] == {
        "type": "sql_sqlite",
        "db_path": "/data/cache.db",
    }
    assert (
        ls_config["storage"]["stores"]["conversations"]["backend"]
        == CONVERSATIONS_BACKEND_NAME
    )


def test_enrich_conversation_storage_preserves_custom_table_name() -> None:
    """G18: existing table_name is preserved while backend is overwritten."""
    ls_config = {
        "storage": {
            "backends": {},
            "stores": {
                "conversations": {
                    "table_name": "custom_convs",
                    "backend": "sql_default",
                }
            },
        }
    }
    cache = {"type": "sqlite", "sqlite": {"db_path": "/data/cache.db"}}
    enrich_conversation_storage(ls_config, cache)
    assert (
        ls_config["storage"]["stores"]["conversations"]["table_name"] == "custom_convs"
    )
    assert (
        ls_config["storage"]["stores"]["conversations"]["backend"]
        == CONVERSATIONS_BACKEND_NAME
    )


@pytest.mark.parametrize(
    "cache",
    [
        None,
        {},
        {"type": "noop"},
        {"type": "memory", "memory": {"max_entries": 10}},
        {"type": "postgres"},
        {"type": "postgres", "postgres": {"host": "h", "db": "d", "user": "u"}},
        {"type": "sqlite", "sqlite": {}},
    ],
)
def test_enrich_conversation_storage_skips_incomplete_e1_e2(
    cache: Optional[dict[str, Any]],
) -> None:
    """E1/E2: non-durable or incomplete cache leaves ls_config unchanged."""
    ls_config = load_default_baseline()
    before = copy.deepcopy(ls_config)
    enrich_conversation_storage(ls_config, cache)
    assert ls_config == before


def test_enrich_conversation_storage_defaults_port_e5() -> None:
    """E5: omitted postgres port defaults to 5432."""
    ls_config = load_default_baseline()
    enrich_conversation_storage(
        ls_config,
        {
            "type": "postgres",
            "postgres": {
                "host": "h",
                "db": "d",
                "user": "u",
                "password": "p",
            },
        },
    )
    assert ls_config["storage"]["backends"][CONVERSATIONS_BACKEND_NAME]["port"] == 5432


def test_enrich_conversation_storage_defaults_host() -> None:
    """Omitted postgres host defaults to localhost (mirrors model default)."""
    ls_config = load_default_baseline()
    enrich_conversation_storage(
        ls_config,
        {
            "type": "postgres",
            "postgres": {
                "db": "d",
                "user": "u",
                "password": "p",
            },
        },
    )
    backend = ls_config["storage"]["backends"][CONVERSATIONS_BACKEND_NAME]
    assert backend == {
        "type": "sql_postgres",
        "host": "localhost",
        "port": 5432,
        "db": "d",
        "user": "u",
        "password": "p",
    }
    assert (
        ls_config["storage"]["stores"]["conversations"]["backend"]
        == CONVERSATIONS_BACKEND_NAME
    )


def test_enrich_conversation_storage_retargets_existing_sql_postgres_e8() -> None:
    """E8/G2: profile backend other_pg is overwritten to conversations_default."""
    ls_config: dict[str, Any] = {
        "storage": {
            "backends": {
                "other_pg": {
                    "type": "sql_postgres",
                    "host": "a",
                    "port": 5432,
                    "db": "a",
                    "user": "a",
                    "password": "a",
                }
            },
            "stores": {
                "conversations": {
                    "table_name": DEFAULT_CONVERSATIONS_TABLE_NAME,
                    "backend": "other_pg",
                }
            },
        }
    }
    enrich_conversation_storage(
        ls_config,
        {
            "type": "postgres",
            "postgres": {
                "host": "b",
                "port": 5432,
                "db": "b",
                "user": "b",
                "password": "b",
            },
        },
    )
    assert (
        ls_config["storage"]["stores"]["conversations"]["backend"]
        == CONVERSATIONS_BACKEND_NAME
    )
    assert ls_config["storage"]["backends"][CONVERSATIONS_BACKEND_NAME]["host"] == "b"


def _durable_pg_cache(password: str = "${env.POSTGRES_PASSWORD}") -> dict[str, Any]:
    """Build a minimal durable postgres conversation_cache dict."""
    return {
        "type": "postgres",
        "postgres": {
            "host": "h",
            "port": 5432,
            "db": "d",
            "user": "u",
            "password": password,
        },
    }


def test_warn_w1_when_override_clobbers() -> None:
    """U1: W1 when final conversations backend is not conversations_default."""
    ls_config = {
        "storage": {
            "backends": {
                CONVERSATIONS_BACKEND_NAME: {
                    "type": "sql_sqlite",
                    "db_path": "/x",
                }
            },
            "stores": {
                "conversations": {
                    "backend": "sql_default",
                    "table_name": DEFAULT_CONVERSATIONS_TABLE_NAME,
                }
            },
        }
    }
    lcs = {"conversation_cache": {"type": "sqlite", "sqlite": {"db_path": "/x"}}}
    msgs = warn_conversation_persistence(ls_config, lcs)
    assert any(
        "native_override still owns storage.stores.conversations" in msg for msg in msgs
    )


def test_warn_w2_absent_database() -> None:
    """E6/U3: W2 when database key is absent."""
    ls_config = {
        "storage": {
            "backends": {
                CONVERSATIONS_BACKEND_NAME: {
                    "type": "sql_sqlite",
                    "db_path": "/data/c.db",
                }
            },
            "stores": {"conversations": {"backend": CONVERSATIONS_BACKEND_NAME}},
        }
    }
    lcs = {
        "conversation_cache": {"type": "sqlite", "sqlite": {"db_path": "/data/c.db"}}
    }
    msgs = warn_conversation_persistence(ls_config, lcs)
    assert any("database is ephemeral or type-mismatched" in msg for msg in msgs)


def test_warn_w2_type_mismatch() -> None:
    """U4: W2 when cache is postgres and database is sqlite."""
    ls_config = {
        "storage": {
            "backends": {
                CONVERSATIONS_BACKEND_NAME: {
                    "type": "sql_postgres",
                    "host": "h",
                    "port": 5432,
                    "db": "d",
                    "user": "u",
                    "password": "p",
                }
            },
            "stores": {"conversations": {"backend": CONVERSATIONS_BACKEND_NAME}},
        }
    }
    lcs = {
        "conversation_cache": _durable_pg_cache(password="p"),
        "database": {"sqlite": {"db_path": "/var/lib/lightspeed/app.db"}},
    }
    msgs = warn_conversation_persistence(ls_config, lcs)
    assert any("database is ephemeral or type-mismatched" in msg for msg in msgs)


def test_warn_no_w2_when_matching_postgres() -> None:
    """U5: no W2 when database and cache are both postgres."""
    ls_config = {
        "storage": {
            "backends": {
                CONVERSATIONS_BACKEND_NAME: {
                    "type": "sql_postgres",
                    "host": "h",
                    "port": 5432,
                    "db": "d",
                    "user": "u",
                    "password": "${env.P}",
                }
            },
            "stores": {"conversations": {"backend": CONVERSATIONS_BACKEND_NAME}},
        }
    }
    lcs = {
        "conversation_cache": _durable_pg_cache(password="${env.P}"),
        "database": {
            "postgres": {
                "host": "other",
                "db": "other",
                "user": "u",
                "password": "${env.P}",
            }
        },
    }
    msgs = warn_conversation_persistence(ls_config, lcs)
    assert not any("database is ephemeral or type-mismatched" in msg for msg in msgs)


def test_warn_w3_literal_password() -> None:
    """U6: W3 for literal password; secret value must not appear in messages."""
    ls_config = {
        "storage": {
            "backends": {
                CONVERSATIONS_BACKEND_NAME: {
                    "type": "sql_postgres",
                    "host": "h",
                    "port": 5432,
                    "db": "d",
                    "user": "u",
                    "password": "s3cret",
                }
            },
            "stores": {"conversations": {"backend": CONVERSATIONS_BACKEND_NAME}},
        }
    }
    lcs = {
        "conversation_cache": _durable_pg_cache(password="s3cret"),
        "database": {
            "postgres": {
                "host": "h",
                "db": "d",
                "user": "u",
                "password": "s3cret",
            }
        },
    }
    msgs = warn_conversation_persistence(ls_config, lcs)
    assert any("literal postgres password" in msg for msg in msgs)
    assert all("s3cret" not in msg for msg in msgs)


def test_warn_no_w3_for_env_ref_with_default() -> None:
    """E7/U7: ${env.VAR:=default} does not trigger W3."""
    password = "${env.POSTGRES_PASSWORD:=secret}"
    ls_config = {
        "storage": {
            "backends": {
                CONVERSATIONS_BACKEND_NAME: {
                    "type": "sql_postgres",
                    "host": "h",
                    "port": 5432,
                    "db": "d",
                    "user": "u",
                    "password": password,
                }
            },
            "stores": {"conversations": {"backend": CONVERSATIONS_BACKEND_NAME}},
        }
    }
    lcs = {
        "conversation_cache": _durable_pg_cache(password=password),
        "database": {
            "postgres": {
                "host": "h",
                "db": "d",
                "user": "u",
                "password": password,
            }
        },
    }
    msgs = warn_conversation_persistence(ls_config, lcs)
    assert not any("literal postgres password" in msg for msg in msgs)


def test_warn_noop_when_cache_not_durable() -> None:
    """E1: no warnings when conversation_cache is not durable."""
    msgs = warn_conversation_persistence(
        load_default_baseline(),
        {"conversation_cache": {"type": "memory", "memory": {"max_entries": 1}}},
    )
    assert not msgs


def test_synthesize_wires_postgres_cache_h1() -> None:
    """Pipeline H1: synthesize wires postgres cache to conversations_default."""
    lcs = {
        "llama_stack": {
            "use_as_library_client": True,
            "config": {"baseline": "default"},
        },
        "conversation_cache": {
            "type": "postgres",
            "postgres": {
                "host": "db.example.com",
                "db": "lightspeed",
                "user": "ls",
                "password": "${env.POSTGRES_PASSWORD}",
            },
        },
        "database": {
            "postgres": {
                "host": "db.example.com",
                "db": "lightspeed",
                "user": "ls",
                "password": "${env.POSTGRES_PASSWORD}",
            }
        },
    }
    result = synthesize_configuration(lcs)
    assert (
        result["storage"]["stores"]["conversations"]["backend"]
        == CONVERSATIONS_BACKEND_NAME
    )
    assert (
        result["storage"]["backends"][CONVERSATIONS_BACKEND_NAME]["type"]
        == "sql_postgres"
    )


def test_synthesize_override_wins_u1(caplog: pytest.LogCaptureFixture) -> None:
    """U1/G1: native_override restores sql_default; unused backend remains; W1."""
    lcs = {
        "llama_stack": {
            "use_as_library_client": True,
            "config": {
                "baseline": "default",
                "native_override": {
                    "storage": {
                        "stores": {
                            "conversations": {
                                "table_name": DEFAULT_CONVERSATIONS_TABLE_NAME,
                                "backend": "sql_default",
                            }
                        }
                    }
                },
            },
        },
        "conversation_cache": {
            "type": "sqlite",
            "sqlite": {"db_path": "/data/cache.db"},
        },
    }
    with caplog.at_level(
        "WARNING", logger="lightspeed_stack.llama_stack_configuration"
    ):
        result = synthesize_configuration(lcs)
    assert result["storage"]["stores"]["conversations"]["backend"] == "sql_default"
    assert CONVERSATIONS_BACKEND_NAME in result["storage"]["backends"]
    assert "native_override still owns storage.stores.conversations" in caplog.text


def test_synthesize_migrate_shape_with_durable_cache_u2(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """U2: dumb-migrate shape keeps override-owned conversations backend + W1."""
    run_yaml = {
        "version": 2,
        "storage": {
            "backends": {
                "sql_default": {
                    "type": "sql_sqlite",
                    "db_path": "/tmp/sql.db",
                }
            },
            "stores": {
                "conversations": {
                    "table_name": DEFAULT_CONVERSATIONS_TABLE_NAME,
                    "backend": "sql_default",
                }
            },
        },
    }
    lcs = {
        "llama_stack": {
            "use_as_library_client": True,
            "config": {"baseline": "empty", "native_override": run_yaml},
        },
        "conversation_cache": {
            "type": "sqlite",
            "sqlite": {"db_path": "/data/cache.db"},
        },
    }
    with caplog.at_level(
        "WARNING", logger="lightspeed_stack.llama_stack_configuration"
    ):
        result = synthesize_configuration(lcs)
    assert result["storage"]["stores"]["conversations"]["backend"] == "sql_default"
    assert "native_override still owns storage.stores.conversations" in caplog.text
