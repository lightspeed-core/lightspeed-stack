"""Handler for REST API calls to manage vector stores and files."""

import asyncio
import os
from io import BytesIO
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from llama_stack_client import (
    APIConnectionError,
    BadRequestError,
)
from llama_stack_client import (
    APIStatusError as LLSApiStatusError,
)
from openai._exceptions import APIStatusError as OpenAIAPIStatusError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from constants import DEFAULT_MAX_FILE_UPLOAD_SIZE
from log import get_logger
from models.api.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
    FileTooLargeResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.config import Action
from models.requests import (
    VectorStoreCreateRequest,
    VectorStoreFileCreateRequest,
    VectorStoreUpdateRequest,
)
from models.responses import (
    FileResponse,
    VectorStoreDeleteResponse,
    VectorStoreFileDeleteResponse,
    VectorStoreFileResponse,
    VectorStoreFilesListResponse,
    VectorStoreResponse,
    VectorStoresListResponse,
)
from utils.endpoints import check_configuration_loaded
from utils.query import handle_known_apistatus_errors

logger = get_logger(__name__)
router = APIRouter(tags=["vector-stores"])


# Response schemas for OpenAPI documentation
vector_stores_list_responses: dict[int | str, dict[str, Any]] = {
    200: VectorStoresListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}

vector_store_responses: dict[int | str, dict[str, Any]] = {
    200: VectorStoreResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["vector store"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}

file_responses: dict[int | str, dict[str, Any]] = {
    200: FileResponse.openapi_response(),
    413: FileTooLargeResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}

vector_store_file_responses: dict[int | str, dict[str, Any]] = {
    200: VectorStoreFileResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["file"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}

vector_store_files_list_responses: dict[int | str, dict[str, Any]] = {
    200: VectorStoreFilesListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["vector store"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}

vector_store_delete_responses: dict[int | str, dict[str, Any]] = {
    200: VectorStoreDeleteResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}

vector_store_file_delete_responses: dict[int | str, dict[str, Any]] = {
    200: VectorStoreFileDeleteResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}


@router.post("/vector-stores", responses=vector_store_responses)
@authorize(Action.MANAGE_VECTOR_STORES)
async def create_vector_store(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    body: VectorStoreCreateRequest,
) -> VectorStoreResponse:
    """Create a new vector store.

    Parameters:
        request: The incoming HTTP request.
        auth: Authentication tuple from the auth dependency.
        body: Vector store creation parameters.

    Returns:
        VectorStoreResponse: The created vector store object.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()

        # Extract provider_id for extra_body (not a direct client parameter)
        body_dict = body.model_dump(exclude_none=True)
        extra_body = {}
        if "provider_id" in body_dict:
            extra_body["provider_id"] = body_dict.pop("provider_id")
        if "embedding_model" in body_dict:
            extra_body["embedding_model"] = body_dict.pop("embedding_model")
        if "embedding_dimension" in body_dict:
            extra_body["embedding_dimension"] = body_dict.pop("embedding_dimension")

        logger.debug(
            "Creating vector store - body_dict: %s, extra_body: %s",
            body_dict,
            extra_body,
        )

        vector_store = await client.vector_stores.create(
            **body_dict,
            extra_body=extra_body,
        )

        return VectorStoreResponse(
            id=vector_store.id,
            name=vector_store.name,
            created_at=vector_store.created_at,
            last_active_at=vector_store.last_active_at,
            expires_at=vector_store.expires_at,
            status=vector_store.status or "unknown",
            usage_bytes=vector_store.usage_bytes or 0,
            metadata=vector_store.metadata,
        )
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while creating vector store: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.get("/vector-stores", responses=vector_stores_list_responses)
@authorize(Action.READ_VECTOR_STORES)
async def list_vector_stores(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> VectorStoresListResponse:
    """List all vector stores.

    Parameters:
        request: The incoming HTTP request.
        auth: Authentication tuple from the auth dependency.

    Returns:
        VectorStoresListResponse: List of all vector stores.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        vector_stores = await client.vector_stores.list()

        data = [
            VectorStoreResponse(
                id=vs.id,
                name=vs.name,
                created_at=vs.created_at,
                last_active_at=vs.last_active_at,
                expires_at=vs.expires_at or None,
                status=vs.status or "unknown",
                usage_bytes=vs.usage_bytes or 0,
                metadata=vs.metadata,
            )
            for vs in vector_stores.data
        ]

        return VectorStoresListResponse(data=data)
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while listing vector stores: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.get("/vector-stores/{vector_store_id}", responses=vector_store_responses)
@authorize(Action.READ_VECTOR_STORES)
async def get_vector_store(
    request: Request,
    vector_store_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> VectorStoreResponse:
    """Retrieve a vector store by ID.

    Parameters:
        request: The incoming HTTP request.
        vector_store_id: ID of the vector store to retrieve.
        auth: Authentication tuple from the auth dependency.

    Returns:
        VectorStoreResponse: The vector store object.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 404: Vector store not found
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        vector_store = await client.vector_stores.retrieve(vector_store_id)

        return VectorStoreResponse(
            id=vector_store.id,
            name=vector_store.name,
            created_at=vector_store.created_at,
            last_active_at=vector_store.last_active_at,
            expires_at=vector_store.expires_at,
            status=vector_store.status or "unknown",
            usage_bytes=vector_store.usage_bytes or 0,
            metadata=vector_store.metadata,
        )
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except BadRequestError as e:
        logger.error("Vector store not found: %s", e)
        response = NotFoundResponse(
            resource="vector store", resource_id=vector_store_id
        )
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while getting vector store: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.put("/vector-stores/{vector_store_id}", responses=vector_store_responses)
@authorize(Action.MANAGE_VECTOR_STORES)
async def update_vector_store(
    request: Request,
    vector_store_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    body: VectorStoreUpdateRequest,
) -> VectorStoreResponse:
    """Update a vector store.

    Parameters:
        request: The incoming HTTP request.
        vector_store_id: ID of the vector store to update.
        auth: Authentication tuple from the auth dependency.
        body: Vector store update parameters.

    Returns:
        VectorStoreResponse: The updated vector store object.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 404: Vector store not found
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        vector_store = await client.vector_stores.update(
            vector_store_id, **body.model_dump(exclude_none=True)
        )

        return VectorStoreResponse(
            id=vector_store.id,
            name=vector_store.name,
            created_at=vector_store.created_at,
            last_active_at=vector_store.last_active_at,
            expires_at=vector_store.expires_at,
            status=vector_store.status or "unknown",
            usage_bytes=vector_store.usage_bytes or 0,
            metadata=vector_store.metadata or None,
        )
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except BadRequestError as e:
        logger.error("Vector store not found: %s", e)
        response = NotFoundResponse(
            resource="vector store", resource_id=vector_store_id
        )
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while updating vector store: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.delete(
    "/vector-stores/{vector_store_id}",
    responses=vector_store_delete_responses,
)
@authorize(Action.MANAGE_VECTOR_STORES)
async def delete_vector_store(
    request: Request,
    vector_store_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> VectorStoreDeleteResponse:
    """Delete a vector store.

    Parameters:
        request: The incoming HTTP request.
        vector_store_id: ID of the vector store to delete.
        auth: Authentication tuple from the auth dependency.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack

    Returns:
        VectorStoreDeleteResponse: Delete outcome for the requested vector store.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        await client.vector_stores.delete(vector_store_id)
        return VectorStoreDeleteResponse(deleted=True, vector_store_id=vector_store_id)
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except (BadRequestError, ValueError) as e:
        logger.error("Vector store delete failed: %s", e)
        return VectorStoreDeleteResponse(deleted=False, vector_store_id=vector_store_id)
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while deleting vector store: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.post("/files", responses=file_responses)
@authorize(Action.MANAGE_FILES)
async def create_file(  # pylint: disable=too-many-branches,too-many-statements
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    file: UploadFile = File(...),
) -> FileResponse:
    """Upload a file.

    Parameters:
        request: The incoming HTTP request.
        auth: Authentication tuple from the auth dependency.
        file: The file to upload.

    Returns:
        FileResponse: The uploaded file object.

    Raises:
        HTTPException:
            - 400: Bad request (e.g., file too large, invalid format)
            - 401: Authentication failed
            - 403: Authorization failed
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack
    """
    _ = auth

    check_configuration_loaded(configuration)

    # Check Content-Length header BEFORE reading to prevent DoS via memory exhaustion
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            if size > DEFAULT_MAX_FILE_UPLOAD_SIZE:
                response = FileTooLargeResponse.exceeds_local_limit(
                    file_size=size,
                    max_size=DEFAULT_MAX_FILE_UPLOAD_SIZE,
                )
                raise HTTPException(**response.model_dump())
        except ValueError:
            # Invalid Content-Length header, continue and validate after reading
            pass

    # file.size attribute if available
    if hasattr(file, "size") and file.size is not None:
        if file.size > DEFAULT_MAX_FILE_UPLOAD_SIZE:
            response = FileTooLargeResponse.exceeds_local_limit(
                file_size=file.size,
                max_size=DEFAULT_MAX_FILE_UPLOAD_SIZE,
            )
            raise HTTPException(**response.model_dump())

    try:
        client = AsyncLlamaStackClientHolder().get_client()

        # Read file content once
        content = await file.read()

        # Verify actual size after reading
        if len(content) > DEFAULT_MAX_FILE_UPLOAD_SIZE:
            response = FileTooLargeResponse.exceeds_local_limit(
                file_size=len(content),
                max_size=DEFAULT_MAX_FILE_UPLOAD_SIZE,
            )
            raise HTTPException(**response.model_dump())

        filename = file.filename or "uploaded_file"

        # Add .txt extension if no extension present
        # (since parsed PDFs/URLs are sent as plain text)
        if not os.path.splitext(filename)[1]:
            filename = f"{filename}.txt"

        logger.info(
            "Uploading file - filename: %s, size: %d bytes",
            filename,
            len(content),
        )

        file_bytes = BytesIO(content)
        file_bytes.name = filename

        file_obj = await client.files.create(
            file=file_bytes,
            purpose="assistants",
        )

        return FileResponse(
            id=file_obj.id,
            filename=file_obj.filename or filename,
            bytes=file_obj.bytes or len(content),
            created_at=file_obj.created_at,
            purpose=file_obj.purpose or "assistants",
            object=file_obj.object or "file",
        )
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except BadRequestError as e:
        logger.error("Bad request for file upload: %s", e)
        # Check if backend rejected due to file size
        error_msg = str(e).lower()
        if "too large" in error_msg or "size" in error_msg or "exceeds" in error_msg:
            response = FileTooLargeResponse.from_backend_rejection(message=str(e))
        else:
            response = InternalServerErrorResponse.query_failed(
                cause=f"File upload rejected by Llama Stack: {str(e)}"
            )
            # Override to use 400 status code since it's a client error
            response.status_code = status.HTTP_400_BAD_REQUEST
            response.detail.response = "Invalid file upload"
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while uploading file: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.post(
    "/vector-stores/{vector_store_id}/files", responses=vector_store_file_responses
)
@authorize(Action.MANAGE_VECTOR_STORES)
async def add_file_to_vector_store(  # pylint: disable=too-many-locals,too-many-statements
    request: Request,
    vector_store_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    body: VectorStoreFileCreateRequest,
) -> VectorStoreFileResponse:
    """Add a file to a vector store.

    Parameters:
        request: The incoming HTTP request.
        vector_store_id: ID of the vector store.
        auth: Authentication tuple from the auth dependency.
        body: File addition parameters.

    Returns:
        VectorStoreFileResponse: The vector store file object.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 404: Vector store or file not found
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()

        # Retry logic for database lock errors
        max_retries = 3
        retry_delay = 0.5  # seconds
        vs_file = None
        last_lock_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                vs_file = await client.vector_stores.files.create(
                    vector_store_id=vector_store_id,
                    **body.model_dump(exclude_none=True),
                )
                break  # Success, exit retry loop
            except Exception as retry_error:  # pylint: disable=broad-exception-caught
                error_msg = str(retry_error).lower()
                is_lock_error = (
                    "database is locked" in error_msg or "locked" in error_msg
                )
                is_last_attempt = attempt == max_retries - 1

                if is_lock_error:
                    last_lock_error = retry_error
                    if not is_last_attempt:
                        logger.warning(
                            "Database locked while adding file to vector store, "
                            "retrying in %s seconds (attempt %d/%d)",
                            retry_delay,
                            attempt + 1,
                            max_retries,
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    break
                raise  # Re-raise if not a lock error
        if vs_file is None:
            if last_lock_error is not None:
                # Use standard error response model for consistency
                response = InternalServerErrorResponse(
                    response="Failed to create vector store file",
                    cause="All retry attempts failed to create the vector store file",
                )
                raise HTTPException(**response.model_dump()) from last_lock_error
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        logger.info(
            "Vector store file created - ID: %s, status: %s, last_error: %s",
            vs_file.id,
            vs_file.status,
            vs_file.last_error or "None",
        )

        return VectorStoreFileResponse(
            id=vs_file.id,
            vector_store_id=vs_file.vector_store_id or vector_store_id,
            status=vs_file.status or "unknown",
            attributes=vs_file.attributes,
            last_error=(
                vs_file.last_error.message
                if vs_file.last_error and hasattr(vs_file.last_error, "message")
                else None
            ),
            object=vs_file.object or "vector_store.file",
        )
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except BadRequestError as e:
        logger.error("Vector store file operation failed: %s", e)
        # Don't assume which resource is missing - could be vector_store_id OR file_id
        response = NotFoundResponse(
            resource="vector_store_or_file",
            resource_id=f"vector_store={vector_store_id}, file={body.file_id}",
        )
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while adding file to vector store: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.get(
    "/vector-stores/{vector_store_id}/files",
    responses=vector_store_files_list_responses,
)
@authorize(Action.READ_VECTOR_STORES)
async def list_vector_store_files(
    request: Request,
    vector_store_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> VectorStoreFilesListResponse:
    """List files in a vector store.

    Parameters:
        request: The incoming HTTP request.
        vector_store_id: ID of the vector store.
        auth: Authentication tuple from the auth dependency.

    Returns:
        VectorStoreFilesListResponse: List of files in the vector store.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 404: Vector store not found
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        files = await client.vector_stores.files.list(vector_store_id=vector_store_id)

        data = [
            VectorStoreFileResponse(
                id=f.id,
                vector_store_id=f.vector_store_id or vector_store_id,
                status=f.status or "unknown",
                attributes=f.attributes,
                last_error=(
                    f.last_error.message
                    if f.last_error and hasattr(f.last_error, "message")
                    else None
                ),
                object=f.object or "vector_store.file",
            )
            for f in files.data
        ]
        return VectorStoreFilesListResponse(data=data)
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except BadRequestError as e:
        logger.error("Vector store not found: %s", e)
        response = NotFoundResponse(
            resource="vector_store", resource_id=vector_store_id
        )
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while listing vector store files: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.get(
    "/vector-stores/{vector_store_id}/files/{file_id}",
    responses=vector_store_file_responses,
)
@authorize(Action.READ_VECTOR_STORES)
async def get_vector_store_file(
    request: Request,
    vector_store_id: str,
    file_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> VectorStoreFileResponse:
    """Retrieve a file from a vector store.

    Parameters:
        request: The incoming HTTP request.
        vector_store_id: ID of the vector store.
        file_id: ID of the file.
        auth: Authentication tuple from the auth dependency.

    Returns:
        VectorStoreFileResponse: The vector store file object.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 404: File not found in vector store
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        vs_file = await client.vector_stores.files.retrieve(
            vector_store_id=vector_store_id,
            file_id=file_id,
        )

        return VectorStoreFileResponse(
            id=vs_file.id,
            vector_store_id=vs_file.vector_store_id or vector_store_id,
            status=vs_file.status or "unknown",
            attributes=vs_file.attributes,
            last_error=(
                vs_file.last_error.message
                if vs_file.last_error and hasattr(vs_file.last_error, "message")
                else None
            ),
            object=vs_file.object or "vector_store.file",
        )
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except BadRequestError as e:
        logger.error("Vector store file not found: %s", e)
        response = NotFoundResponse(resource="file", resource_id=file_id)
        raise HTTPException(**response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while getting vector store file: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e


@router.delete(
    "/vector-stores/{vector_store_id}/files/{file_id}",
    responses=vector_store_file_delete_responses,
)
@authorize(Action.MANAGE_VECTOR_STORES)
async def delete_vector_store_file(
    request: Request,
    vector_store_id: str,
    file_id: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> VectorStoreFileDeleteResponse:
    """Delete a file from a vector store.

    Parameters:
        request: The incoming HTTP request.
        vector_store_id: ID of the vector store.
        file_id: ID of the file to delete.
        auth: Authentication tuple from the auth dependency.

    Raises:
        HTTPException:
            - 401: Authentication failed
            - 403: Authorization failed
            - 500: Lightspeed Stack configuration not loaded
            - 503: Unable to connect to Llama Stack

    Returns:
        VectorStoreFileDeleteResponse: Delete outcome for the requested file.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        await client.vector_stores.files.delete(
            vector_store_id=vector_store_id,
            file_id=file_id,
        )
        return VectorStoreFileDeleteResponse(deleted=True, file_id=file_id)
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except (BadRequestError, ValueError) as e:
        logger.error("Vector store file delete failed: %s", e)
        return VectorStoreFileDeleteResponse(deleted=False, file_id=file_id)
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        logger.error("API status error while deleting vector store file: %s", e)
        error_response = handle_known_apistatus_errors(e, "llama-stack")
        raise HTTPException(**error_response.model_dump()) from e
