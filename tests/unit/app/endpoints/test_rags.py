"""Unit tests for the /rags REST API endpoints."""

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError, BadRequestError
from pytest_mock import MockerFixture

from app.endpoints.rags import (
    get_rag_endpoint_handler,
    rags_endpoint_handler,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_rags_endpoint_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test that /rags endpoint raises HTTP 500 if configuration is not loaded."""
    mock_authorization_resolvers(mocker)
    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.rags.configuration", mock_config)
    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await rags_endpoint_handler(request=request, auth=auth)
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.asyncio
async def test_rags_endpoint_connection_error(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /rags endpoint raises HTTP 503 if Llama Stack connection fails."""
    mocker.patch("app.endpoints.rags.configuration", minimal_config)
    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.list.side_effect = APIConnectionError(request=None)  # type: ignore
    mocker.patch(
        "app.endpoints.rags.AsyncLlamaStackClientHolder"
    ).return_value.get_client.return_value = mock_client

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await rags_endpoint_handler(request=request, auth=auth)
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    detail = e.value.detail
    assert isinstance(detail, dict)
    assert "response" in detail
    assert "Unable to connect to Llama Stack" in detail["response"]


@pytest.mark.asyncio
async def test_rags_endpoint_success(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /rags endpoint returns list of RAG IDs."""
    mocker.patch("app.endpoints.rags.configuration", minimal_config)

    # pylint: disable=R0903
    class RagInfo:
        """RagInfo mock."""

        def __init__(self, rag_id: str) -> None:
            """
            Initialize a RagInfo instance with the given identifier.

            Parameters:
                rag_id (str): The unique identifier for the RAG.
            """
            self.id = rag_id

    class RagList:
        """List of RAGs mock."""

        def __init__(self) -> None:
            """
            Initialize the object with a predefined list of RagInfo objects used as mock data.

            The instance attribute `data` contains three RagInfo instances with
            fixed IDs simulating available RAG entries for tests.
            """
            self.data = [
                RagInfo("vs_00000000-cafe-babe-0000-000000000000"),
                RagInfo("vs_7b52a8cf-0fa3-489c-beab-27e061d102f3"),
                RagInfo("vs_7b52a8cf-0fa3-489c-cafe-27e061d102f3"),
            ]

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.list.return_value = RagList()
    mocker.patch(
        "app.endpoints.rags.AsyncLlamaStackClientHolder"
    ).return_value.get_client.return_value = mock_client

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await rags_endpoint_handler(request=request, auth=auth)
    assert len(response.rags) == 3


@pytest.mark.asyncio
async def test_rag_info_endpoint_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test that /rags/{rag_id} endpoint raises HTTP 500 if configuration is not loaded."""
    mock_authorization_resolvers(mocker)
    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.rags.configuration", mock_config)
    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await get_rag_endpoint_handler(request=request, auth=auth, rag_id="xyzzy")
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.asyncio
async def test_rag_info_endpoint_rag_not_found(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /rags/{rag_id} endpoint returns HTTP 404 when the requested RAG is not found."""
    mocker.patch("app.endpoints.rags.configuration", minimal_config)
    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.retrieve = mocker.AsyncMock(
        side_effect=BadRequestError(
            message="RAG not found",
            response=mocker.Mock(request=None),
            body=None,
        )
    )  # type: ignore
    mocker.patch(
        "app.endpoints.rags.AsyncLlamaStackClientHolder"
    ).return_value.get_client.return_value = mock_client

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await get_rag_endpoint_handler(request=request, auth=auth, rag_id="xyzzy")
    assert e.value.status_code == status.HTTP_404_NOT_FOUND
    detail = e.value.detail
    assert isinstance(detail, dict)
    assert "response" in detail
    assert "Rag not found" in detail["response"]


@pytest.mark.asyncio
async def test_rag_info_endpoint_connection_error(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /rags/{rag_id} endpoint raises HTTP 503 if Llama Stack connection fails."""
    mocker.patch("app.endpoints.rags.configuration", minimal_config)
    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.retrieve.side_effect = APIConnectionError(
        request=None  # type: ignore
    )
    mocker.patch(
        "app.endpoints.rags.AsyncLlamaStackClientHolder"
    ).return_value.get_client.return_value = mock_client

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await get_rag_endpoint_handler(request=request, auth=auth, rag_id="xyzzy")
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    detail = e.value.detail
    assert isinstance(detail, dict)
    assert "response" in detail
    assert "Unable to connect to Llama Stack" in detail["response"]


@pytest.mark.asyncio
async def test_rag_info_endpoint_success(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /rags/{rag_id} endpoint returns information about selected RAG."""
    mocker.patch("app.endpoints.rags.configuration", minimal_config)

    # pylint: disable=R0902
    # pylint: disable=R0903
    class RagInfo:
        """RagInfo mock."""

        def __init__(self) -> None:
            """This function initializes an instance with predefined attributes.

            Attributes:
                id (str): Identifier for the instance, set to "xyzzy".
                name (str): Name of the instance, set to "rag_name".
                created_at (int): Creation timestamp, set to 123456.
                last_active_at (int): Last active timestamp, set to 1234567.
                expires_at (int): Expiry timestamp, set to 12345678.
                object (str): Type of object, set to "faiss".
                status (str): Status of the instance, set to "completed".
                usage_bytes (int): Usage in bytes, set to 100."""
            self.id = "xyzzy"
            self.name = "rag_name"
            self.created_at = 123456
            self.last_active_at = 1234567
            self.expires_at = 12345678
            self.object = "faiss"
            self.status = "completed"
            self.usage_bytes = 100

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.retrieve.return_value = RagInfo()
    mocker.patch(
        "app.endpoints.rags.AsyncLlamaStackClientHolder"
    ).return_value.get_client.return_value = mock_client

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await get_rag_endpoint_handler(
        request=request, auth=auth, rag_id="xyzzy"
    )
    assert response.id == "xyzzy"
    assert response.name == "rag_name"
    assert response.created_at == 123456
    assert response.last_active_at == 1234567
    assert response.expires_at == 12345678
    assert response.object == "faiss"
    assert response.status == "completed"
    assert response.usage_bytes == 100
