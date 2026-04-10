"""Unit tests for the /vector-stores REST API endpoints."""

# pylint: disable=too-many-lines

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError, BadRequestError
from pytest_mock import MockerFixture

from app.endpoints.vector_stores import (
    add_file_to_vector_store,
    create_file,
    create_vector_store,
    delete_vector_store,
    delete_vector_store_file,
    get_vector_store,
    get_vector_store_file,
    list_vector_store_files,
    list_vector_stores,
    update_vector_store,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.requests import (
    VectorStoreCreateRequest,
    VectorStoreFileCreateRequest,
    VectorStoreUpdateRequest,
)
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


# pylint: disable=R0903,R0902
class VectorStore:
    """Mock vector store object."""

    def __init__(
        self,
        vs_id: str,
        name: str,
        created_at: int = 1735689600,
        vs_status: str = "active",
    ) -> None:
        """Initialize vector store mock."""
        self.id = vs_id
        self.name = name
        self.created_at = created_at
        self.last_active_at = created_at
        self.expires_at = None
        self.object = "vector_store"
        self.status = vs_status
        self.usage_bytes = 0
        self.metadata = None


# pylint: disable=R0903
class VectorStoresList:
    """Mock vector stores list."""

    def __init__(self, stores: list[VectorStore]) -> None:
        """Initialize vector stores list mock."""
        self.data = stores


# pylint: disable=R0903
class File:
    """Mock file object."""

    def __init__(self, file_id: str, filename: str, file_bytes: int = 1024) -> None:
        """Initialize file mock."""
        self.id = file_id
        self.filename = filename
        self.bytes = file_bytes
        self.created_at = 1735689600
        self.purpose = "assistants"
        self.object = "file"


# pylint: disable=R0903
class VectorStoreFile:
    """Mock vector store file object."""

    def __init__(
        self, file_id: str, vector_store_id: str, file_status: str = "completed"
    ) -> None:
        """Initialize vector store file mock."""
        self.id = file_id
        self.vector_store_id = vector_store_id
        self.created_at = 1735689600
        self.status = file_status
        self.attributes = None
        self.last_error = None
        self.object = "vector_store.file"


# pylint: disable=R0903
class VectorStoreFilesList:
    """Mock vector store files list."""

    def __init__(self, files: list[VectorStoreFile]) -> None:
        """Initialize vector store files list mock."""
        self.data = files


def get_test_config() -> dict[str, Any]:
    """Get test configuration dictionary.

    Returns:
        Test configuration dictionary.
    """
    return {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "xyzzy",
            "url": "http://x.y.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_enabled": False,
        },
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }


def get_test_request() -> Request:
    """Get test request object.

    Returns:
        Test request object.
    """
    return Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer test-token")],
        }
    )


def get_test_auth() -> AuthTuple:
    """Get test auth tuple.

    Returns:
        Test auth tuple.
    """
    return ("test_user_id", "test_user", True, "test_token")


@pytest.mark.asyncio
async def test_create_vector_store_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test create vector store endpoint if configuration is not loaded."""
    mock_authorization_resolvers(mocker)

    mock_config = AppConfig()
    mocker.patch("app.endpoints.vector_stores.configuration", mock_config)

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreCreateRequest(name="test_store")

    with pytest.raises(HTTPException) as e:
        await create_vector_store(request=request, auth=auth, body=body)

    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert e.value.detail["response"] == "Configuration is not loaded"  # type: ignore


@pytest.mark.asyncio
async def test_create_vector_store_success(mocker: MockerFixture) -> None:
    """Test successful vector store creation."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.create.return_value = VectorStore("vs_123", "test_store")
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreCreateRequest(name="test_store")

    response = await create_vector_store(request=request, auth=auth, body=body)
    assert response is not None
    assert response.id == "vs_123"
    assert response.name == "test_store"
    assert response.status == "active"


@pytest.mark.asyncio
async def test_create_vector_store_connection_error(mocker: MockerFixture) -> None:
    """Test create vector store with connection error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.create.side_effect = APIConnectionError(request=None)  # type: ignore
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreCreateRequest(name="test_store")

    with pytest.raises(HTTPException) as e:
        await create_vector_store(request=request, auth=auth, body=body)

    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert e.value.detail["response"] == "Unable to connect to Llama Stack"  # type: ignore


@pytest.mark.asyncio
async def test_list_vector_stores_success(mocker: MockerFixture) -> None:
    """Test successful vector stores list."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.list.return_value = VectorStoresList(
        [VectorStore("vs_1", "store1"), VectorStore("vs_2", "store2")]
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    response = await list_vector_stores(request=request, auth=auth)
    assert response is not None
    assert len(response.data) == 2
    assert response.data[0].id == "vs_1"
    assert response.data[1].id == "vs_2"


@pytest.mark.asyncio
async def test_get_vector_store_success(mocker: MockerFixture) -> None:
    """Test successful vector store retrieval."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.retrieve.return_value = VectorStore(
        "vs_123", "test_store"
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    response = await get_vector_store(
        request=request, vector_store_id="vs_123", auth=auth
    )
    assert response is not None
    assert response.id == "vs_123"
    assert response.name == "test_store"


@pytest.mark.asyncio
async def test_get_vector_store_not_found(mocker: MockerFixture) -> None:
    """Test vector store retrieval with not found error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    # Create a mock response for BadRequestError
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_client.vector_stores.retrieve.side_effect = BadRequestError(
        message="Not found", response=mock_response, body=None
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await get_vector_store(request=request, vector_store_id="vs_999", auth=auth)
    assert e.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_vector_store_success(mocker: MockerFixture) -> None:
    """Test successful vector store update."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.update.return_value = VectorStore(
        "vs_123", "updated_store"
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreUpdateRequest(name="updated_store")

    response = await update_vector_store(
        request=request, vector_store_id="vs_123", auth=auth, body=body
    )
    assert response is not None
    assert response.id == "vs_123"
    assert response.name == "updated_store"


@pytest.mark.asyncio
async def test_delete_vector_store_success(mocker: MockerFixture) -> None:
    """Test successful vector store deletion."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.delete.return_value = None
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    response = await delete_vector_store(
        request=request, vector_store_id="vs_123", auth=auth
    )
    assert response is None


@pytest.mark.asyncio
async def test_create_file_success(mocker: MockerFixture) -> None:
    """Test successful file upload."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.files.create.return_value = File("file_123", "test.txt", 1024)
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    # Mock UploadFile
    mock_file = mocker.AsyncMock()
    mock_file.filename = "test.txt"
    mock_file.size = 12  # Size of "test content"
    mock_file.read.return_value = b"test content"

    response = await create_file(request=request, auth=auth, file=mock_file)
    assert response is not None
    assert response.id == "file_123"
    assert response.filename == "test.txt"
    assert response.bytes == 1024


@pytest.mark.asyncio
async def test_add_file_to_vector_store_success(mocker: MockerFixture) -> None:
    """Test successfully adding file to vector store."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.files.create.return_value = VectorStoreFile(
        "file_123", "vs_123"
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreFileCreateRequest(file_id="file_123")

    response = await add_file_to_vector_store(
        request=request, vector_store_id="vs_123", auth=auth, body=body
    )
    assert response is not None
    assert response.id == "file_123"
    assert response.vector_store_id == "vs_123"
    assert response.status == "completed"


@pytest.mark.asyncio
async def test_add_file_to_vector_store_retry_on_database_lock(
    mocker: MockerFixture,
) -> None:
    """Test retry logic when database lock error occurs."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    # First call raises database lock error, second call succeeds
    mock_client.vector_stores.files.create.side_effect = [
        Exception("database is locked"),
        VectorStoreFile("file_123", "vs_123"),
    ]
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    # Mock asyncio.sleep to avoid actual delays in tests
    mock_sleep = mocker.patch("app.endpoints.vector_stores.asyncio.sleep")

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreFileCreateRequest(file_id="file_123")

    response = await add_file_to_vector_store(
        request=request, vector_store_id="vs_123", auth=auth, body=body
    )
    assert response is not None
    assert response.id == "file_123"
    assert response.vector_store_id == "vs_123"
    assert response.status == "completed"

    # Verify retry logic was triggered
    assert mock_client.vector_stores.files.create.call_count == 2
    # Verify sleep was called once with 0.5 seconds (first retry delay)
    mock_sleep.assert_called_once_with(0.5)


@pytest.mark.asyncio
async def test_add_file_to_vector_store_max_retries_exceeded(
    mocker: MockerFixture,
) -> None:
    """Test that max retries are respected when database lock persists."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    # All attempts fail with database lock error
    mock_client.vector_stores.files.create.side_effect = Exception("database is locked")
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    # Mock asyncio.sleep to avoid actual delays in tests
    mock_sleep = mocker.patch("app.endpoints.vector_stores.asyncio.sleep")

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreFileCreateRequest(file_id="file_123")

    with pytest.raises(HTTPException) as e:
        await add_file_to_vector_store(
            request=request, vector_store_id="vs_123", auth=auth, body=body
        )
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # Verify all 3 retry attempts were made
    assert mock_client.vector_stores.files.create.call_count == 3
    # Verify exponential backoff: 0.5s, then 1s (0.5 * 2)
    assert mock_sleep.call_count == 2
    assert mock_sleep.call_args_list[0][0][0] == 0.5
    assert mock_sleep.call_args_list[1][0][0] == 1.0


@pytest.mark.asyncio
async def test_add_file_to_vector_store_non_lock_error_no_retry(
    mocker: MockerFixture,
) -> None:
    """Test that non-lock errors are not retried."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    # Raise a non-lock error
    mock_client.vector_stores.files.create.side_effect = Exception("Some other error")
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    # Mock asyncio.sleep to verify it's not called
    mock_sleep = mocker.patch("app.endpoints.vector_stores.asyncio.sleep")

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreFileCreateRequest(file_id="file_123")

    with pytest.raises(HTTPException) as e:
        await add_file_to_vector_store(
            request=request, vector_store_id="vs_123", auth=auth, body=body
        )
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # Verify only one attempt was made (no retries for non-lock errors)
    assert mock_client.vector_stores.files.create.call_count == 1
    # Verify sleep was not called (no retry)
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_list_vector_store_files_success(mocker: MockerFixture) -> None:
    """Test successfully listing files in vector store."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.files.list.return_value = VectorStoreFilesList(
        [
            VectorStoreFile("file_1", "vs_123"),
            VectorStoreFile("file_2", "vs_123"),
        ]
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    response = await list_vector_store_files(
        request=request, vector_store_id="vs_123", auth=auth
    )
    assert response is not None
    assert len(response.data) == 2
    assert response.data[0].id == "file_1"
    assert response.data[1].id == "file_2"


@pytest.mark.asyncio
async def test_get_vector_store_file_success(mocker: MockerFixture) -> None:
    """Test successfully retrieving file from vector store."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.files.retrieve.return_value = VectorStoreFile(
        "file_123", "vs_123"
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    response = await get_vector_store_file(
        request=request, vector_store_id="vs_123", file_id="file_123", auth=auth
    )
    assert response is not None
    assert response.id == "file_123"
    assert response.vector_store_id == "vs_123"


@pytest.mark.asyncio
async def test_delete_vector_store_file_success(mocker: MockerFixture) -> None:
    """Test successfully deleting file from vector store."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.files.delete.return_value = None
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    response = await delete_vector_store_file(
        request=request, vector_store_id="vs_123", file_id="file_123", auth=auth
    )
    assert response is None


# Additional error path tests


@pytest.mark.asyncio
async def test_list_vector_stores_connection_error(mocker: MockerFixture) -> None:
    """Test list vector stores with connection error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.list.side_effect = APIConnectionError(request=None)  # type: ignore
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await list_vector_stores(request=request, auth=auth)
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_update_vector_store_connection_error(mocker: MockerFixture) -> None:
    """Test update vector store with connection error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.update.side_effect = APIConnectionError(request=None)  # type: ignore
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreUpdateRequest(name="updated_store")

    with pytest.raises(HTTPException) as e:
        await update_vector_store(
            request=request, vector_store_id="vs_123", auth=auth, body=body
        )
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_update_vector_store_not_found(mocker: MockerFixture) -> None:
    """Test update vector store with not found error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_client.vector_stores.update.side_effect = BadRequestError(
        message="Not found", response=mock_response, body=None
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreUpdateRequest(name="updated_store")

    with pytest.raises(HTTPException) as e:
        await update_vector_store(
            request=request, vector_store_id="vs_999", auth=auth, body=body
        )
    assert e.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_vector_store_connection_error(mocker: MockerFixture) -> None:
    """Test delete vector store with connection error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.delete.side_effect = APIConnectionError(request=None)  # type: ignore
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await delete_vector_store(request=request, vector_store_id="vs_123", auth=auth)
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_delete_vector_store_not_found(mocker: MockerFixture) -> None:
    """Test delete vector store with not found error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_client.vector_stores.delete.side_effect = BadRequestError(
        message="Not found", response=mock_response, body=None
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await delete_vector_store(request=request, vector_store_id="vs_999", auth=auth)
    assert e.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_create_file_connection_error(mocker: MockerFixture) -> None:
    """Test create file with connection error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.files.create.side_effect = APIConnectionError(request=None)  # type: ignore
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    mock_file = mocker.AsyncMock()
    mock_file.filename = "test.txt"
    mock_file.size = 12  # Size of "test content"
    mock_file.read.return_value = b"test content"

    with pytest.raises(HTTPException) as e:
        await create_file(request=request, auth=auth, file=mock_file)
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_create_file_bad_request(mocker: MockerFixture) -> None:
    """Test create file with bad request error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_client.files.create.side_effect = BadRequestError(
        message="File too large", response=mock_response, body=None
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    mock_file = mocker.AsyncMock()
    mock_file.filename = "test.txt"
    mock_file.size = 12  # Size of "test content"
    mock_file.read.return_value = b"test content"

    with pytest.raises(HTTPException) as e:
        await create_file(request=request, auth=auth, file=mock_file)

    assert e.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE


@pytest.mark.asyncio
async def test_create_file_too_large(mocker: MockerFixture) -> None:
    """Test create file with file size exceeding limit."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    # Create a mock file that exceeds the size limit
    mock_file = mocker.AsyncMock()
    mock_file.filename = "large_file.pdf"
    mock_file.size = 200 * 1024 * 1024  # 200 MB (exceeds 100 MB limit)
    mock_file.read.side_effect = AssertionError("File too large")

    with pytest.raises(HTTPException) as e:
        await create_file(request=request, auth=auth, file=mock_file)

    assert e.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert "too large" in str(e.value.detail).lower()


@pytest.mark.asyncio
async def test_create_file_content_length_too_large(mocker: MockerFixture) -> None:
    """Test create file with Content-Length header exceeding limit."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    # Create request with large Content-Length header
    request = Request(
        scope={
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer test-token"),
                (b"content-length", b"209715200"),  # 200 MB
            ],
        }
    )
    auth = get_test_auth()

    # Create a mock file
    mock_file = mocker.AsyncMock()
    mock_file.filename = "large_file.pdf"
    mock_file.size = None  # No size attribute

    with pytest.raises(HTTPException) as e:
        await create_file(request=request, auth=auth, file=mock_file)

    assert e.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert "too large" in str(e.value.detail).lower()


@pytest.mark.asyncio
async def test_add_file_to_vector_store_connection_error(
    mocker: MockerFixture,
) -> None:
    """Test add file to vector store with connection error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.files.create.side_effect = APIConnectionError(
        request=None  # type: ignore
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreFileCreateRequest(file_id="file_123")

    with pytest.raises(HTTPException) as e:
        await add_file_to_vector_store(
            request=request, vector_store_id="vs_123", auth=auth, body=body
        )
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_add_file_to_vector_store_not_found(mocker: MockerFixture) -> None:
    """Test add file to vector store with not found error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_client.vector_stores.files.create.side_effect = BadRequestError(
        message="File not found", response=mock_response, body=None
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()
    body = VectorStoreFileCreateRequest(file_id="file_999")

    with pytest.raises(HTTPException) as e:
        await add_file_to_vector_store(
            request=request, vector_store_id="vs_123", auth=auth, body=body
        )
    assert e.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_list_vector_store_files_connection_error(
    mocker: MockerFixture,
) -> None:
    """Test list vector store files with connection error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.files.list.side_effect = APIConnectionError(
        request=None  # type: ignore
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await list_vector_store_files(
            request=request, vector_store_id="vs_123", auth=auth
        )
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_list_vector_store_files_not_found(mocker: MockerFixture) -> None:
    """Test list vector store files with invalid vector store ID."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_client.vector_stores.files.list.side_effect = BadRequestError(
        message="Vector store not found", response=mock_response, body=None
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await list_vector_store_files(
            request=request, vector_store_id="vs_999", auth=auth
        )

    assert e.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_vector_store_file_connection_error(mocker: MockerFixture) -> None:
    """Test get vector store file with connection error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.files.retrieve.side_effect = APIConnectionError(
        request=None  # type: ignore
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await get_vector_store_file(
            request=request, vector_store_id="vs_123", file_id="file_123", auth=auth
        )
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_get_vector_store_file_not_found(mocker: MockerFixture) -> None:
    """Test get vector store file with not found error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_client.vector_stores.files.retrieve.side_effect = BadRequestError(
        message="File not found", response=mock_response, body=None
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await get_vector_store_file(
            request=request, vector_store_id="vs_123", file_id="file_999", auth=auth
        )
    assert e.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_vector_store_file_connection_error(
    mocker: MockerFixture,
) -> None:
    """Test delete vector store file with connection error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_client.vector_stores.files.delete.side_effect = APIConnectionError(
        request=None  # type: ignore
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await delete_vector_store_file(
            request=request, vector_store_id="vs_123", file_id="file_123", auth=auth
        )
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_delete_vector_store_file_not_found(mocker: MockerFixture) -> None:
    """Test delete vector store file with not found error."""
    mock_authorization_resolvers(mocker)

    config_dict = get_test_config()
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mock_client = mocker.AsyncMock()
    mock_response = mocker.Mock()
    mock_response.request = mocker.Mock()
    mock_client.vector_stores.files.delete.side_effect = BadRequestError(
        message="File not found", response=mock_response, body=None
    )
    mock_lsc = mocker.patch(
        "app.endpoints.vector_stores.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mocker.patch("app.endpoints.vector_stores.configuration", cfg)

    request = get_test_request()
    auth = get_test_auth()

    with pytest.raises(HTTPException) as e:
        await delete_vector_store_file(
            request=request, vector_store_id="vs_123", file_id="file_999", auth=auth
        )
    assert e.value.status_code == status.HTTP_404_NOT_FOUND
