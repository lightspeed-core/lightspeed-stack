"""Unit tests for the rlsapi v1 /infer REST API endpoint."""

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from app.endpoints.rlsapi_v1 import infer_endpoint
from authentication.interface import AuthTuple
from models.rlsapi.requests import (
    RlsapiV1Attachment,
    RlsapiV1Context,
    RlsapiV1InferRequest,
    RlsapiV1SystemInfo,
    RlsapiV1Terminal,
)
from models.rlsapi.responses import RlsapiV1InferResponse
from tests.unit.utils.auth_helpers import mock_authorization_resolvers
from utils.suid import check_suid

MOCK_AUTH: AuthTuple = ("test_user_id", "test_user", True, "test_token")


@pytest.mark.asyncio
async def test_infer_minimal_request(mocker: MockerFixture) -> None:
    """Test /infer endpoint returns valid response with UUID request_id."""
    mock_authorization_resolvers(mocker)
    request = RlsapiV1InferRequest(question="How do I list files?")

    response = await infer_endpoint(infer_request=request, auth=MOCK_AUTH)

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text
    # Verify request_id is valid SUID
    assert check_suid(response.data.request_id)


@pytest.mark.asyncio
async def test_infer_full_context_request(mocker: MockerFixture) -> None:
    """Test /infer endpoint handles full context (stdin, attachments, terminal)."""
    mock_authorization_resolvers(mocker)
    request = RlsapiV1InferRequest(
        question="Why did this command fail?",
        context=RlsapiV1Context(
            stdin="some piped input",
            attachments=RlsapiV1Attachment(contents="key=value", mimetype="text/plain"),
            terminal=RlsapiV1Terminal(output="bash: command not found"),
            systeminfo=RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64"),
        ),
    )

    response = await infer_endpoint(infer_request=request, auth=MOCK_AUTH)

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text
    assert response.data.request_id


@pytest.mark.asyncio
async def test_infer_generates_unique_request_ids(mocker: MockerFixture) -> None:
    """Test that each /infer call generates a unique request_id."""
    mock_authorization_resolvers(mocker)
    request = RlsapiV1InferRequest(question="How do I list files?")

    response1 = await infer_endpoint(infer_request=request, auth=MOCK_AUTH)
    response2 = await infer_endpoint(infer_request=request, auth=MOCK_AUTH)

    assert response1.data.request_id != response2.data.request_id


@pytest.mark.parametrize("invalid_question", ["", "   ", "\t\n"])
def test_infer_rejects_invalid_question(invalid_question: str) -> None:
    """Test that empty or whitespace-only questions are rejected."""
    with pytest.raises(ValidationError):
        RlsapiV1InferRequest(question=invalid_question)
