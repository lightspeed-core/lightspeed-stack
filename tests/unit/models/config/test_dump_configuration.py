"""Unit tests checking ability to dump configuration."""

# pylint: disable=too-many-lines
# pyright: reportCallIssue=false

import json

from pathlib import Path

from pydantic import SecretStr

from models.config import (
    ModelContextProtocolServer,
    LlamaStackConfiguration,
    UserDataCollection,
    DatabaseConfiguration,
    PostgreSQLDatabaseConfiguration,
    CORSConfiguration,
    Configuration,
    ByokRag,
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
    QuotaSchedulerConfiguration,
    ServiceConfiguration,
    InferenceConfiguration,
    TLSConfiguration,
)


def test_dump_configuration(tmp_path: Path) -> None:
    """
    Test that the Configuration object can be serialized to a JSON file and
    that the resulting file contains all expected sections and values.

    Please note that redaction process is not in place.

    Parameters:
        tmp_path (Path): Directory where the test JSON file will be written.
    """
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(
            tls_config=TLSConfiguration(
                tls_certificate_path=Path("tests/configuration/server.crt"),
                tls_key_path=Path("tests/configuration/server.key"),
                tls_key_password=Path("tests/configuration/password"),
            ),
            cors=CORSConfiguration(
                allow_origins=["foo_origin", "bar_origin", "baz_origin"],
                allow_credentials=False,
                allow_methods=["foo_method", "bar_method", "baz_method"],
                allow_headers=["foo_header", "bar_header", "baz_header"],
            ),
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
            api_key=SecretStr("whatever"),
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        database=DatabaseConfiguration(
            sqlite=None,
            postgres=PostgreSQLDatabaseConfiguration(
                db="lightspeed_stack",
                user="ls_user",
                password=SecretStr("ls_password"),
                port=5432,
                ca_cert_path=None,
                ssl_mode="require",
                gss_encmode="disable",
            ),
        ),
        mcp_servers=[],
        customization=None,
        inference=InferenceConfiguration(
            default_provider="default_provider",
            default_model="default_model",
        ),
    )
    assert cfg is not None
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        # content should be loaded
        assert content is not None

        # all sections must exists
        assert "name" in content
        assert "service" in content
        assert "llama_stack" in content
        assert "user_data_collection" in content
        assert "mcp_servers" in content
        assert "authentication" in content
        assert "authorization" in content
        assert "customization" in content
        assert "inference" in content
        assert "database" in content
        assert "byok_rag" in content
        assert "quota_handlers" in content
        assert "azure_entra_id" in content

        # check the whole deserialized JSON file content
        assert content == {
            "name": "test_name",
            "service": {
                "host": "localhost",
                "port": 8080,
                "base_url": None,
                "auth_enabled": False,
                "workers": 1,
                "color_log": True,
                "access_log": True,
                "tls_config": {
                    "tls_certificate_path": "tests/configuration/server.crt",
                    "tls_key_password": "tests/configuration/password",
                    "tls_key_path": "tests/configuration/server.key",
                },
                "root_path": "",
                "cors": {
                    "allow_credentials": False,
                    "allow_headers": [
                        "foo_header",
                        "bar_header",
                        "baz_header",
                    ],
                    "allow_methods": [
                        "foo_method",
                        "bar_method",
                        "baz_method",
                    ],
                    "allow_origins": [
                        "foo_origin",
                        "bar_origin",
                        "baz_origin",
                    ],
                },
            },
            "llama_stack": {
                "url": None,
                "use_as_library_client": True,
                "api_key": "**********",
                "library_client_config_path": "tests/configuration/run.yaml",
                "timeout": 180,
            },
            "user_data_collection": {
                "feedback_enabled": False,
                "feedback_storage": None,
                "transcripts_enabled": False,
                "transcripts_storage": None,
            },
            "mcp_servers": [],
            "authentication": {
                "module": "noop",
                "skip_tls_verification": False,
                "skip_for_health_probes": False,
                "k8s_ca_cert_path": None,
                "k8s_cluster_api": None,
                "jwk_config": None,
                "api_key_config": None,
                "rh_identity_config": None,
            },
            "customization": None,
            "inference": {
                "default_provider": "default_provider",
                "default_model": "default_model",
            },
            "database": {
                "sqlite": None,
                "postgres": {
                    "host": "localhost",
                    "port": 5432,
                    "db": "lightspeed_stack",
                    "user": "ls_user",
                    "password": "**********",
                    "ssl_mode": "require",
                    "gss_encmode": "disable",
                    "namespace": "public",
                    "ca_cert_path": None,
                },
            },
            "authorization": None,
            "conversation_cache": {
                "memory": None,
                "postgres": None,
                "sqlite": None,
                "type": None,
            },
            "byok_rag": [],
            "quota_handlers": {
                "sqlite": None,
                "postgres": None,
                "limiters": [],
                "scheduler": {
                    "period": 1,
                    "database_reconnection_count": 10,
                    "database_reconnection_delay": 1,
                },
                "enable_token_history": False,
            },
            "a2a_state": {
                "sqlite": None,
                "postgres": None,
            },
            "azure_entra_id": None,
            "solr": None,
            "splunk": None,
            "deployment_environment": "development",
        }


def test_dump_configuration_with_one_mcp_server(tmp_path: Path) -> None:
    """
    Verify that a configuration with a single MCP server can be
    serialized to JSON and that all expected fields and values are
    present in the output.

    Parameters:
        tmp_path: Temporary directory path provided by pytest for file output.
    """
    mcp_servers = [
        ModelContextProtocolServer(name="test-server", url="http://localhost:8080"),
    ]
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=mcp_servers,
        customization=None,
        inference=InferenceConfiguration(),
    )
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        assert content is not None
        assert "mcp_servers" in content
        assert len(content["mcp_servers"]) == 1
        assert content["mcp_servers"][0]["name"] == "test-server"
        assert content["mcp_servers"][0]["url"] == "http://localhost:8080"
        assert content["mcp_servers"][0]["provider_id"] == "model-context-protocol"

        # check the MCP server configuration
        assert content["mcp_servers"] == [
            {
                "name": "test-server",
                "url": "http://localhost:8080",
                "provider_id": "model-context-protocol",
                "authorization_headers": {},
                "timeout": None,
            }
        ]


def test_dump_configuration_with_more_mcp_servers(tmp_path: Path) -> None:
    """
    Test that a configuration with multiple MCP servers can be
    serialized to JSON and that all server entries are correctly
    included in the output.

    Verifies that the dumped configuration file contains all
    expected fields and that each MCP server is present with the
    correct name, URL, and provider ID.
    """
    mcp_servers = [
        ModelContextProtocolServer(name="test-server-1", url="http://localhost:8081"),
        ModelContextProtocolServer(name="test-server-2", url="http://localhost:8082"),
        ModelContextProtocolServer(name="test-server-3", url="http://localhost:8083"),
    ]
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=mcp_servers,
        customization=None,
        inference=InferenceConfiguration(),
    )
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        assert content is not None
        assert "mcp_servers" in content
        assert len(content["mcp_servers"]) == 3
        assert content["mcp_servers"][0]["name"] == "test-server-1"
        assert content["mcp_servers"][0]["url"] == "http://localhost:8081"
        assert content["mcp_servers"][0]["provider_id"] == "model-context-protocol"
        assert content["mcp_servers"][1]["name"] == "test-server-2"
        assert content["mcp_servers"][1]["url"] == "http://localhost:8082"
        assert content["mcp_servers"][1]["provider_id"] == "model-context-protocol"
        assert content["mcp_servers"][2]["name"] == "test-server-3"
        assert content["mcp_servers"][2]["url"] == "http://localhost:8083"
        assert content["mcp_servers"][2]["provider_id"] == "model-context-protocol"

        # check the MCP server configuration
        assert content["mcp_servers"] == [
            {
                "name": "test-server-1",
                "provider_id": "model-context-protocol",
                "url": "http://localhost:8081",
                "authorization_headers": {},
                "timeout": None,
            },
            {
                "name": "test-server-2",
                "provider_id": "model-context-protocol",
                "url": "http://localhost:8082",
                "authorization_headers": {},
                "timeout": None,
            },
            {
                "name": "test-server-3",
                "provider_id": "model-context-protocol",
                "url": "http://localhost:8083",
                "authorization_headers": {},
                "timeout": None,
            },
        ]


def test_dump_configuration_with_quota_limiters(tmp_path: Path) -> None:
    """
    Test that the Configuration object can be serialized to a JSON file and
    that the resulting file contains all expected sections and values.

    Please note that redaction process is not in place.
    """
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(
            tls_config=TLSConfiguration(
                tls_certificate_path=Path("tests/configuration/server.crt"),
                tls_key_path=Path("tests/configuration/server.key"),
                tls_key_password=Path("tests/configuration/password"),
            ),
            cors=CORSConfiguration(
                allow_origins=["foo_origin", "bar_origin", "baz_origin"],
                allow_credentials=False,
                allow_methods=["foo_method", "bar_method", "baz_method"],
                allow_headers=["foo_header", "bar_header", "baz_header"],
            ),
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
            api_key=SecretStr("whatever"),
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        database=DatabaseConfiguration(
            sqlite=None,
            postgres=PostgreSQLDatabaseConfiguration(
                db="lightspeed_stack",
                user="ls_user",
                password=SecretStr("ls_password"),
                port=5432,
                ca_cert_path=None,
                ssl_mode="require",
                gss_encmode="disable",
            ),
        ),
        mcp_servers=[],
        customization=None,
        inference=InferenceConfiguration(
            default_provider="default_provider",
            default_model="default_model",
        ),
        quota_handlers=QuotaHandlersConfiguration(
            limiters=[
                QuotaLimiterConfiguration(
                    type="user_limiter",
                    name="user_monthly_limits",
                    initial_quota=1,
                    quota_increase=10,
                    period="2 seconds",
                ),
                QuotaLimiterConfiguration(
                    type="cluster_limiter",
                    name="cluster_monthly_limits",
                    initial_quota=2,
                    quota_increase=20,
                    period="1 month",
                ),
            ],
            scheduler=QuotaSchedulerConfiguration(period=10),
            enable_token_history=True,
        ),
    )
    assert cfg is not None
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        # content should be loaded
        assert content is not None

        # all sections must exists
        assert "name" in content
        assert "service" in content
        assert "llama_stack" in content
        assert "user_data_collection" in content
        assert "mcp_servers" in content
        assert "authentication" in content
        assert "authorization" in content
        assert "customization" in content
        assert "inference" in content
        assert "database" in content
        assert "byok_rag" in content
        assert "quota_handlers" in content
        assert "azure_entra_id" in content

        # check the whole deserialized JSON file content
        assert content == {
            "name": "test_name",
            "service": {
                "host": "localhost",
                "port": 8080,
                "base_url": None,
                "auth_enabled": False,
                "workers": 1,
                "color_log": True,
                "access_log": True,
                "tls_config": {
                    "tls_certificate_path": "tests/configuration/server.crt",
                    "tls_key_password": "tests/configuration/password",
                    "tls_key_path": "tests/configuration/server.key",
                },
                "root_path": "",
                "cors": {
                    "allow_credentials": False,
                    "allow_headers": [
                        "foo_header",
                        "bar_header",
                        "baz_header",
                    ],
                    "allow_methods": [
                        "foo_method",
                        "bar_method",
                        "baz_method",
                    ],
                    "allow_origins": [
                        "foo_origin",
                        "bar_origin",
                        "baz_origin",
                    ],
                },
            },
            "llama_stack": {
                "url": None,
                "use_as_library_client": True,
                "api_key": "**********",
                "library_client_config_path": "tests/configuration/run.yaml",
                "timeout": 180,
            },
            "user_data_collection": {
                "feedback_enabled": False,
                "feedback_storage": None,
                "transcripts_enabled": False,
                "transcripts_storage": None,
            },
            "mcp_servers": [],
            "authentication": {
                "module": "noop",
                "skip_tls_verification": False,
                "skip_for_health_probes": False,
                "k8s_ca_cert_path": None,
                "k8s_cluster_api": None,
                "jwk_config": None,
                "api_key_config": None,
                "rh_identity_config": None,
            },
            "customization": None,
            "inference": {
                "default_provider": "default_provider",
                "default_model": "default_model",
            },
            "database": {
                "sqlite": None,
                "postgres": {
                    "host": "localhost",
                    "port": 5432,
                    "db": "lightspeed_stack",
                    "user": "ls_user",
                    "password": "**********",
                    "ssl_mode": "require",
                    "gss_encmode": "disable",
                    "namespace": "public",
                    "ca_cert_path": None,
                },
            },
            "authorization": None,
            "conversation_cache": {
                "memory": None,
                "postgres": None,
                "sqlite": None,
                "type": None,
            },
            "byok_rag": [],
            "quota_handlers": {
                "sqlite": None,
                "postgres": None,
                "limiters": [
                    {
                        "initial_quota": 1,
                        "name": "user_monthly_limits",
                        "period": "2 seconds",
                        "quota_increase": 10,
                        "type": "user_limiter",
                    },
                    {
                        "initial_quota": 2,
                        "name": "cluster_monthly_limits",
                        "period": "1 month",
                        "quota_increase": 20,
                        "type": "cluster_limiter",
                    },
                ],
                "scheduler": {
                    "period": 10,
                    "database_reconnection_count": 10,
                    "database_reconnection_delay": 1,
                },
                "enable_token_history": True,
            },
            "a2a_state": {
                "sqlite": None,
                "postgres": None,
            },
            "azure_entra_id": None,
            "solr": None,
            "splunk": None,
            "deployment_environment": "development",
        }


def test_dump_configuration_with_quota_limiters_different_values(
    tmp_path: Path,
) -> None:
    """
    Test that the Configuration object can be serialized to a JSON file and
    that the resulting file contains all expected sections and values.

    Please note that redaction process is not in place.
    """
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(
            tls_config=TLSConfiguration(
                tls_certificate_path=Path("tests/configuration/server.crt"),
                tls_key_path=Path("tests/configuration/server.key"),
                tls_key_password=Path("tests/configuration/password"),
            ),
            cors=CORSConfiguration(
                allow_origins=["foo_origin", "bar_origin", "baz_origin"],
                allow_credentials=False,
                allow_methods=["foo_method", "bar_method", "baz_method"],
                allow_headers=["foo_header", "bar_header", "baz_header"],
            ),
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
            api_key=SecretStr("whatever"),
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        database=DatabaseConfiguration(
            sqlite=None,
            postgres=PostgreSQLDatabaseConfiguration(
                db="lightspeed_stack",
                user="ls_user",
                password=SecretStr("ls_password"),
                port=5432,
                ca_cert_path=None,
                ssl_mode="require",
                gss_encmode="disable",
            ),
        ),
        mcp_servers=[],
        customization=None,
        inference=InferenceConfiguration(
            default_provider="default_provider",
            default_model="default_model",
        ),
        quota_handlers=QuotaHandlersConfiguration(
            limiters=[
                QuotaLimiterConfiguration(
                    type="user_limiter",
                    name="user_monthly_limits",
                    initial_quota=1,
                    quota_increase=10,
                    period="2 seconds",
                ),
                QuotaLimiterConfiguration(
                    type="cluster_limiter",
                    name="cluster_monthly_limits",
                    initial_quota=2,
                    quota_increase=20,
                    period="1 month",
                ),
            ],
            scheduler=QuotaSchedulerConfiguration(
                period=10,
                database_reconnection_count=123,
                database_reconnection_delay=456,
            ),
            enable_token_history=True,
        ),
    )
    assert cfg is not None
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        # content should be loaded
        assert content is not None

        # all sections must exists
        assert "name" in content
        assert "service" in content
        assert "llama_stack" in content
        assert "user_data_collection" in content
        assert "mcp_servers" in content
        assert "authentication" in content
        assert "authorization" in content
        assert "customization" in content
        assert "inference" in content
        assert "database" in content
        assert "byok_rag" in content
        assert "quota_handlers" in content

        # check the whole deserialized JSON file content
        assert content == {
            "name": "test_name",
            "service": {
                "host": "localhost",
                "port": 8080,
                "base_url": None,
                "auth_enabled": False,
                "workers": 1,
                "color_log": True,
                "access_log": True,
                "tls_config": {
                    "tls_certificate_path": "tests/configuration/server.crt",
                    "tls_key_password": "tests/configuration/password",
                    "tls_key_path": "tests/configuration/server.key",
                },
                "root_path": "",
                "cors": {
                    "allow_credentials": False,
                    "allow_headers": [
                        "foo_header",
                        "bar_header",
                        "baz_header",
                    ],
                    "allow_methods": [
                        "foo_method",
                        "bar_method",
                        "baz_method",
                    ],
                    "allow_origins": [
                        "foo_origin",
                        "bar_origin",
                        "baz_origin",
                    ],
                },
            },
            "llama_stack": {
                "url": None,
                "use_as_library_client": True,
                "api_key": "**********",
                "library_client_config_path": "tests/configuration/run.yaml",
                "timeout": 180,
            },
            "user_data_collection": {
                "feedback_enabled": False,
                "feedback_storage": None,
                "transcripts_enabled": False,
                "transcripts_storage": None,
            },
            "mcp_servers": [],
            "authentication": {
                "module": "noop",
                "skip_tls_verification": False,
                "skip_for_health_probes": False,
                "k8s_ca_cert_path": None,
                "k8s_cluster_api": None,
                "jwk_config": None,
                "api_key_config": None,
                "rh_identity_config": None,
            },
            "customization": None,
            "inference": {
                "default_provider": "default_provider",
                "default_model": "default_model",
            },
            "database": {
                "sqlite": None,
                "postgres": {
                    "host": "localhost",
                    "port": 5432,
                    "db": "lightspeed_stack",
                    "user": "ls_user",
                    "password": "**********",
                    "ssl_mode": "require",
                    "gss_encmode": "disable",
                    "namespace": "public",
                    "ca_cert_path": None,
                },
            },
            "authorization": None,
            "conversation_cache": {
                "memory": None,
                "postgres": None,
                "sqlite": None,
                "type": None,
            },
            "byok_rag": [],
            "quota_handlers": {
                "sqlite": None,
                "postgres": None,
                "limiters": [
                    {
                        "initial_quota": 1,
                        "name": "user_monthly_limits",
                        "period": "2 seconds",
                        "quota_increase": 10,
                        "type": "user_limiter",
                    },
                    {
                        "initial_quota": 2,
                        "name": "cluster_monthly_limits",
                        "period": "1 month",
                        "quota_increase": 20,
                        "type": "cluster_limiter",
                    },
                ],
                "scheduler": {
                    "period": 10,
                    "database_reconnection_count": 123,
                    "database_reconnection_delay": 456,
                },
                "enable_token_history": True,
            },
            "a2a_state": {
                "sqlite": None,
                "postgres": None,
            },
            "azure_entra_id": None,
            "solr": None,
            "splunk": None,
            "deployment_environment": "development",
        }


def test_dump_configuration_byok(tmp_path: Path) -> None:
    """
    Test that the Configuration object can be serialized to a JSON file and
    that the resulting file contains all expected sections and values.
    """
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(
            tls_config=TLSConfiguration(
                tls_certificate_path=Path("tests/configuration/server.crt"),
                tls_key_path=Path("tests/configuration/server.key"),
                tls_key_password=Path("tests/configuration/password"),
            ),
            cors=CORSConfiguration(
                allow_origins=["foo_origin", "bar_origin", "baz_origin"],
                allow_credentials=False,
                allow_methods=["foo_method", "bar_method", "baz_method"],
                allow_headers=["foo_header", "bar_header", "baz_header"],
            ),
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
            api_key=SecretStr("whatever"),
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        database=DatabaseConfiguration(
            sqlite=None,
            postgres=PostgreSQLDatabaseConfiguration(
                db="lightspeed_stack",
                user="ls_user",
                password=SecretStr("ls_password"),
                port=5432,
                ca_cert_path=None,
                ssl_mode="require",
                gss_encmode="disable",
                namespace="foo",
            ),
        ),
        mcp_servers=[],
        customization=None,
        inference=InferenceConfiguration(
            default_provider="default_provider",
            default_model="default_model",
        ),
        byok_rag=[
            ByokRag(
                rag_id="rag_id",
                vector_db_id="vector_db_id",
                db_path="tests/configuration/rag.txt",
            ),
        ],
    )
    assert cfg is not None
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        # content should be loaded
        assert content is not None

        # all sections must exists
        assert "name" in content
        assert "service" in content
        assert "llama_stack" in content
        assert "user_data_collection" in content
        assert "mcp_servers" in content
        assert "authentication" in content
        assert "authorization" in content
        assert "customization" in content
        assert "inference" in content
        assert "database" in content
        assert "byok_rag" in content
        assert "quota_handlers" in content

        # check the whole deserialized JSON file content
        assert content == {
            "name": "test_name",
            "service": {
                "host": "localhost",
                "port": 8080,
                "base_url": None,
                "auth_enabled": False,
                "workers": 1,
                "color_log": True,
                "access_log": True,
                "tls_config": {
                    "tls_certificate_path": "tests/configuration/server.crt",
                    "tls_key_password": "tests/configuration/password",
                    "tls_key_path": "tests/configuration/server.key",
                },
                "root_path": "",
                "cors": {
                    "allow_credentials": False,
                    "allow_headers": [
                        "foo_header",
                        "bar_header",
                        "baz_header",
                    ],
                    "allow_methods": [
                        "foo_method",
                        "bar_method",
                        "baz_method",
                    ],
                    "allow_origins": [
                        "foo_origin",
                        "bar_origin",
                        "baz_origin",
                    ],
                },
            },
            "llama_stack": {
                "url": None,
                "use_as_library_client": True,
                "api_key": "**********",
                "library_client_config_path": "tests/configuration/run.yaml",
                "timeout": 180,
            },
            "user_data_collection": {
                "feedback_enabled": False,
                "feedback_storage": None,
                "transcripts_enabled": False,
                "transcripts_storage": None,
            },
            "mcp_servers": [],
            "authentication": {
                "module": "noop",
                "skip_tls_verification": False,
                "skip_for_health_probes": False,
                "k8s_ca_cert_path": None,
                "k8s_cluster_api": None,
                "jwk_config": None,
                "api_key_config": None,
                "rh_identity_config": None,
            },
            "customization": None,
            "inference": {
                "default_provider": "default_provider",
                "default_model": "default_model",
            },
            "database": {
                "sqlite": None,
                "postgres": {
                    "host": "localhost",
                    "port": 5432,
                    "db": "lightspeed_stack",
                    "user": "ls_user",
                    "password": "**********",
                    "ssl_mode": "require",
                    "gss_encmode": "disable",
                    "namespace": "foo",
                    "ca_cert_path": None,
                },
            },
            "authorization": None,
            "conversation_cache": {
                "memory": None,
                "postgres": None,
                "sqlite": None,
                "type": None,
            },
            "byok_rag": [
                {
                    "db_path": "tests/configuration/rag.txt",
                    "embedding_dimension": 768,
                    "embedding_model": "sentence-transformers/all-mpnet-base-v2",
                    "rag_id": "rag_id",
                    "rag_type": "inline::faiss",
                    "vector_db_id": "vector_db_id",
                },
            ],
            "quota_handlers": {
                "sqlite": None,
                "postgres": None,
                "limiters": [],
                "scheduler": {
                    "period": 1,
                    "database_reconnection_count": 10,
                    "database_reconnection_delay": 1,
                },
                "enable_token_history": False,
            },
            "a2a_state": {
                "sqlite": None,
                "postgres": None,
            },
            "azure_entra_id": None,
            "solr": None,
            "splunk": None,
            "deployment_environment": "development",
        }


def test_dump_configuration_pg_namespace(tmp_path: Path) -> None:
    """
    Test that the Configuration object can be serialized to a JSON file and
    that the resulting file contains all expected sections and values.

    Please note that redaction process is not in place.
    """
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(
            tls_config=TLSConfiguration(
                tls_certificate_path=Path("tests/configuration/server.crt"),
                tls_key_path=Path("tests/configuration/server.key"),
                tls_key_password=Path("tests/configuration/password"),
            ),
            cors=CORSConfiguration(
                allow_origins=["foo_origin", "bar_origin", "baz_origin"],
                allow_credentials=False,
                allow_methods=["foo_method", "bar_method", "baz_method"],
                allow_headers=["foo_header", "bar_header", "baz_header"],
            ),
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
            api_key=SecretStr("whatever"),
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        database=DatabaseConfiguration(
            sqlite=None,
            postgres=PostgreSQLDatabaseConfiguration(
                db="lightspeed_stack",
                user="ls_user",
                password=SecretStr("ls_password"),
                port=5432,
                ca_cert_path=None,
                ssl_mode="require",
                gss_encmode="disable",
                namespace="foo",
            ),
        ),
        mcp_servers=[],
        customization=None,
        inference=InferenceConfiguration(
            default_provider="default_provider",
            default_model="default_model",
        ),
    )
    assert cfg is not None
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        # content should be loaded
        assert content is not None

        # all sections must exists
        assert "name" in content
        assert "service" in content
        assert "llama_stack" in content
        assert "user_data_collection" in content
        assert "mcp_servers" in content
        assert "authentication" in content
        assert "authorization" in content
        assert "customization" in content
        assert "inference" in content
        assert "database" in content
        assert "byok_rag" in content
        assert "quota_handlers" in content

        # check the whole deserialized JSON file content
        assert content == {
            "name": "test_name",
            "service": {
                "host": "localhost",
                "port": 8080,
                "base_url": None,
                "auth_enabled": False,
                "workers": 1,
                "color_log": True,
                "access_log": True,
                "tls_config": {
                    "tls_certificate_path": "tests/configuration/server.crt",
                    "tls_key_password": "tests/configuration/password",
                    "tls_key_path": "tests/configuration/server.key",
                },
                "root_path": "",
                "cors": {
                    "allow_credentials": False,
                    "allow_headers": [
                        "foo_header",
                        "bar_header",
                        "baz_header",
                    ],
                    "allow_methods": [
                        "foo_method",
                        "bar_method",
                        "baz_method",
                    ],
                    "allow_origins": [
                        "foo_origin",
                        "bar_origin",
                        "baz_origin",
                    ],
                },
            },
            "llama_stack": {
                "url": None,
                "use_as_library_client": True,
                "api_key": "**********",
                "library_client_config_path": "tests/configuration/run.yaml",
                "timeout": 180,
            },
            "user_data_collection": {
                "feedback_enabled": False,
                "feedback_storage": None,
                "transcripts_enabled": False,
                "transcripts_storage": None,
            },
            "mcp_servers": [],
            "authentication": {
                "module": "noop",
                "skip_tls_verification": False,
                "skip_for_health_probes": False,
                "k8s_ca_cert_path": None,
                "k8s_cluster_api": None,
                "jwk_config": None,
                "api_key_config": None,
                "rh_identity_config": None,
            },
            "customization": None,
            "inference": {
                "default_provider": "default_provider",
                "default_model": "default_model",
            },
            "database": {
                "sqlite": None,
                "postgres": {
                    "host": "localhost",
                    "port": 5432,
                    "db": "lightspeed_stack",
                    "user": "ls_user",
                    "password": "**********",
                    "ssl_mode": "require",
                    "gss_encmode": "disable",
                    "ca_cert_path": None,
                    "namespace": "foo",
                },
            },
            "authorization": None,
            "conversation_cache": {
                "memory": None,
                "postgres": None,
                "sqlite": None,
                "type": None,
            },
            "byok_rag": [],
            "quota_handlers": {
                "sqlite": None,
                "postgres": None,
                "limiters": [],
                "scheduler": {
                    "period": 1,
                    "database_reconnection_count": 10,
                    "database_reconnection_delay": 1,
                },
                "enable_token_history": False,
            },
            "a2a_state": {
                "sqlite": None,
                "postgres": None,
            },
            "azure_entra_id": None,
            "solr": None,
            "splunk": None,
            "deployment_environment": "development",
        }
