import json
import os
from pathlib import Path
import typing as t

import pytest

# Testing framework note:
# These tests are written for pytest (fixtures, parametrize, expressive assertions).

# Strategy:
# - Load the OpenAPI document from conventional locations (docs/openapi.json, openapi.json).
# - Validate critical structure based on the PR diff:
#   * openapi version, info, servers
#   * presence of paths/methods and key response codes
#   * presence and key attributes of important component schemas (enums, required fields)
# - Avoid strict OpenAPI 3.1 validation (no external deps); focus on contract elements introduced/modified in the diff.

CANDIDATE_SPEC_PATHS = [
    Path("docs/openapi.json"),
    Path("openapi.json"),
    Path("static/openapi.json"),
    Path("public/openapi.json"),
]

def _load_openapi_spec() -> dict:
    for p in CANDIDATE_SPEC_PATHS:
        if p.is_file():
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
    # Fallback: if a test copies the spec into tests/unit/docs/openapi.json for isolation.
    local = Path(__file__).with_name("openapi.json")
    if local.is_file():
        with local.open("r", encoding="utf-8") as f:
            return json.load(f)
    pytest.fail(
        "OpenAPI spec not found. Expected one of: "
        + ", ".join(str(p) for p in CANDIDATE_SPEC_PATHS + [local])
    )

@pytest.fixture(scope="module")
def spec() -> dict:
    return _load_openapi_spec()

def test_openapi_top_level_info(spec: dict):
    assert spec.get("openapi") == "3.1.0"
    info = spec.get("info") or {}
    assert info.get("title") == "Lightspeed Core Service (LCS) service - OpenAPI"
    assert info.get("version") == "0.2.0"
    contact = info.get("contact") or {}
    assert contact.get("name") == "Pavel Tisnovsky"
    assert contact.get("url") == "https://github.com/tisnik/"
    assert contact.get("email") == "ptisnovs@redhat.com"
    license_ = info.get("license") or {}
    assert license_.get("name") == "Apache 2.0"
    assert "apache.org/licenses" in (license_.get("url") or "")

def test_servers_section_present_and_localhost_default(spec: dict):
    servers = spec.get("servers")
    assert isinstance(servers, list) and servers, "servers must be a non-empty list"
    local = servers[0]
    assert local.get("url") == "http://localhost:8080/"
    assert "Locally running service" in (local.get("description") or "")

# Paths and methods introduced in the diff
@pytest.mark.parametrize(
    "path,method,expected_codes",
    [
        ("/", "get", {"200"}),
        ("/v1/info", "get", {"200", "500"}),
        ("/v1/models", "get", {"200", "503"}),
        ("/v1/query", "post", {"200", "400", "403", "503", "422"}),
        ("/v1/streaming_query", "post", {"200", "422"}),
        ("/v1/config", "get", {"200", "503"}),
        ("/v1/feedback", "post", {"200", "401", "403", "500", "422"}),
        ("/v1/feedback/status", "get", {"200"}),
        ("/v1/feedback/status", "put", {"200", "422"}),
        ("/v1/conversations", "get", {"200", "503"}),
        ("/v1/conversations/{conversation_id}", "get", {"200", "404", "503", "422"}),
        ("/v1/conversations/{conversation_id}", "delete", {"200", "404", "503", "422"}),
        ("/readiness", "get", {"200", "503"}),
        ("/liveness", "get", {"200", "503"}),
        ("/authorized", "post", {"200", "400", "403"}),
        ("/metrics", "get", {"200"}),
    ],
)
def test_paths_and_responses_exist(spec: dict, path: str, method: str, expected_codes: t.Set[str]):
    paths = spec.get("paths") or {}
    assert path in paths, f"Missing path: {path}"
    op = (paths[path] or {}).get(method)
    assert isinstance(op, dict), f"Missing method {method.upper()} for path {path}"
    responses = (op.get("responses") or {})
    got_codes = set(responses.keys())
    for code in expected_codes:
        assert code in got_codes, f"Missing response code {code} for {method.upper()} {path}"

def test_operation_ids_present_for_key_endpoints(spec: dict):
    paths = spec.get("paths") or {}
    exp = {
        "/": ("get", "root_endpoint_handler__get"),
        "/v1/info": ("get", "info_endpoint_handler_v1_info_get"),
        "/v1/models": ("get", "models_endpoint_handler_v1_models_get"),
        "/v1/query": ("post", "query_endpoint_handler_v1_query_post"),
        "/v1/streaming_query": ("post", "streaming_query_endpoint_handler_v1_streaming_query_post"),
        "/v1/config": ("get", "config_endpoint_handler_v1_config_get"),
        "/v1/feedback": ("post", "feedback_endpoint_handler_v1_feedback_post"),
        "/v1/feedback/status": ("get", "feedback_status_v1_feedback_status_get"),
        "/v1/feedback/status": ("put", "update_feedback_status_v1_feedback_status_put"),
        "/v1/conversations": ("get", "get_conversations_list_endpoint_handler_v1_conversations_get"),
        "/v1/conversations/{conversation_id}": ("get", "get_conversation_endpoint_handler_v1_conversations__conversation_id__get"),
        "/v1/conversations/{conversation_id}": ("delete", "delete_conversation_endpoint_handler_v1_conversations__conversation_id__delete"),
        "/readiness": ("get", "readiness_probe_get_method_readiness_get"),
        "/liveness": ("get", "liveness_probe_get_method_liveness_get"),
        "/metrics": ("get", "metrics_endpoint_handler_metrics_get"),
    }
    for path, (method, op_id) in exp.items():
        op = (paths.get(path) or {}).get(method) or {}
        assert op.get("operationId") == op_id, f"{path} {method}: expected operationId {op_id}"

def test_components_schemas_exist(spec: dict):
    schemas = ((spec.get("components") or {}).get("schemas")) or {}
    # Core response models
    for required_schema in [
        "InfoResponse",
        "ModelsResponse",
        "QueryRequest",
        "QueryResponse",
        "ErrorResponse",
        "UnauthorizedResponse",
        "ForbiddenResponse",
        "HTTPValidationError",
        "ReadinessResponse",
        "ProviderHealthStatus",
        "LivenessResponse",
        "Configuration",
        "ServiceConfiguration",
        "CORSConfiguration",
        "TLSConfiguration",
        "LlamaStackConfiguration",
        "UserDataCollection",
        "ConversationDetails",
        "ConversationsListResponse",
        "ConversationResponse",
        "ConversationDeleteResponse",
        "FeedbackRequest",
        "FeedbackResponse",
        "FeedbackStatusUpdateRequest",
        "FeedbackStatusUpdateResponse",
        "Attachment",
        "Action",
        "AccessRule",
        "AuthorizationConfiguration",
        "AuthenticationConfiguration",
        "JwtConfiguration",
        "JwtRoleRule",
        "JwkConfiguration",
        "JsonPathOperator",
        "SQLiteDatabaseConfiguration",
        "PostgreSQLDatabaseConfiguration",
        "InferenceConfiguration",
        "StatusResponse",
        "ValidationError",
        "ModelContextProtocolServer",
    ]:
        assert required_schema in schemas, f"Missing schema: {required_schema}"

def test_enums_match_expected(spec: dict):
    schemas = ((spec.get("components") or {}).get("schemas")) or {}
    action = schemas.get("Action") or {}
    action_enum = set((action.get("enum") or []))
    expected_actions = {
        "admin",
        "list_other_conversations",
        "read_other_conversations",
        "query_other_conversations",
        "delete_other_conversations",
        "query",
        "streaming_query",
        "get_conversation",
        "list_conversations",
        "delete_conversation",
        "feedback",
        "get_models",
        "get_metrics",
        "get_config",
        "info",
    }
    assert expected_actions.issubset(action_enum)

    fb_cat = (schemas.get("FeedbackCategory") or {}).get("enum") or []
    assert fb_cat == ["incorrect", "not_relevant", "incomplete", "outdated_information", "unsafe", "other"]

    jsonpath_ops = (schemas.get("JsonPathOperator") or {}).get("enum") or []
    assert jsonpath_ops == ["equals", "contains", "in"]

def test_required_fields_in_key_models(spec: dict):
    schemas = ((spec.get("components") or {}).get("schemas")) or {}
    # InfoResponse requires name, service_version, llama_stack_version
    info_req = set((schemas.get("InfoResponse") or {}).get("required") or [])
    assert {"name", "service_version", "llama_stack_version"}.issubset(info_req)

    # QueryRequest requires query
    qr_req = set((schemas.get("QueryRequest") or {}).get("required") or [])
    assert {"query"}.issubset(qr_req)

    # ConversationDeleteResponse requires conversation_id, success, response
    cdr_req = set((schemas.get("ConversationDeleteResponse") or {}).get("required") or [])
    assert {"conversation_id", "success", "response"}.issubset(cdr_req)

    # ReadinessResponse requires ready, reason, providers
    rr_req = set((schemas.get("ReadinessResponse") or {}).get("required") or [])
    assert {"ready", "reason", "providers"}.issubset(rr_req)

    # LivenessResponse requires alive
    lr_req = set((schemas.get("LivenessResponse") or {}).get("required") or [])
    assert {"alive"}.issubset(lr_req)

def test_response_content_refs_for_selected_endpoints(spec: dict):
    """Spot-check a few endpoints to ensure 200 responses reference the right schemas."""
    paths = spec.get("paths") or {}

    def _schema_ref(path: str, method: str, code: str) -> t.Optional[str]:
        op = (paths.get(path) or {}).get(method) or {}
        resp = (op.get("responses") or {}).get(code) or {}
        content = resp.get("content") or {}
        # Pick first content type and get $ref if present
        for _ct, meta in content.items():
            schema = (meta or {}).get("schema") or {}
            ref = schema.get("$ref")
            if ref:
                return ref
        return None

    assert _schema_ref("/v1/info", "get", "200") == "#/components/schemas/InfoResponse"
    assert _schema_ref("/v1/models", "get", "200") == "#/components/schemas/ModelsResponse"
    assert _schema_ref("/v1/query", "post", "200") == "#/components/schemas/QueryResponse"

def test_health_endpoints_share_readiness_schema(spec: dict):
    paths = spec.get("paths") or {}
    readiness = (paths.get("/readiness") or {}).get("get") or {}
    liveness = (paths.get("/liveness") or {}).get("get") or {}

    def first_schema_ref(op: dict, code: str) -> t.Optional[str]:
        resp = (op.get("responses") or {}).get(code) or {}
        content = resp.get("content") or {}
        for meta in content.values():
            schema = (meta or {}).get("schema") or {}
            ref = schema.get("$ref")
            if ref:
                return ref
        return None

    # Liveness uses LivenessResponse, Readiness uses ReadinessResponse
    assert first_schema_ref(liveness, "200") == "#/components/schemas/LivenessResponse"
    assert first_schema_ref(readiness, "200") == "#/components/schemas/ReadinessResponse"

def test_feedback_status_put_has_request_body(spec: dict):
    op = ((spec.get("paths") or {}).get("/v1/feedback/status") or {}).get("put") or {}
    rb = op.get("requestBody") or {}
    assert rb.get("required") is True
    content = rb.get("content") or {}
    assert "application/json" in content
    schema = (content["application/json"] or {}).get("schema") or {}
    assert schema.get("$ref") == "#/components/schemas/FeedbackStatusUpdateRequest"

def test_conversation_id_param_present_in_path(spec: dict):
    op = ((spec.get("paths") or {}).get("/v1/conversations/{conversation_id}") or {}).get("get") or {}
    params = op.get("parameters") or []
    has_conv_id = any(
        (p.get("name") == "conversation_id" and p.get("in") == "path" and (p.get("schema") or {}).get("type") == "string")
        for p in params
    )
    assert has_conv_id, "conversation_id path parameter is required for GET /v1/conversations/{conversation_id}"

def test_no_tools_default_false_in_query_request(spec: dict):
    qr = ((spec.get("components") or {}).get("schemas") or {}).get("QueryRequest") or {}
    props = qr.get("properties") or {}
    no_tools = props.get("no_tools") or {}
    assert no_tools.get("default") is False

def test_cors_defaults_in_service_configuration(spec: dict):
    svc = ((spec.get("components") or {}).get("schemas") or {}).get("ServiceConfiguration") or {}
    props = svc.get("properties") or {}
    cors = (props.get("cors") or {})
    assert cors.get("$ref") == "#/components/schemas/CORSConfiguration" or "default" in cors

def test_database_defaults_in_configuration(spec: dict):
    conf = ((spec.get("components") or {}).get("schemas") or {}).get("Configuration") or {}
    props = conf.get("properties") or {}
    db = props.get("database") or {}
    default = db.get("default") or {}
    sqlite = default.get("sqlite") or {}
    assert sqlite.get("db_path") == "/tmp/lightspeed-stack.db"

def test_examples_present_on_selected_models(spec: dict):
    schemas = ((spec.get("components") or {}).get("schemas")) or {}
    info = schemas.get("InfoResponse") or {}
    examples = info.get("examples") or []
    assert isinstance(examples, list) and examples, "InfoResponse should include examples"
    models = schemas.get("ModelsResponse") or {}
    assert isinstance(models.get("properties", {}).get("models", {}), dict)
