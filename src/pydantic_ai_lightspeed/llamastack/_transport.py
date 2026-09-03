"""httpx transports for Llama Stack library and server modes."""

from __future__ import annotations as _annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from typing import Any, Optional

import httpx
from ogx.core.library_client import (
    AsyncOGXAsLibraryClient,
    convert_pydantic_to_json_value,
)
from ogx.core.request_headers import (
    PROVIDER_DATA_VAR,
    request_provider_data_context,
)
from ogx.core.server.routes import find_matching_route
from ogx.core.utils.context import preserve_contexts_async_generator
from starlette.responses import StreamingResponse

_PROVIDER_DATA_HEADER_KEYS = (
    "X-OGX-Provider-Data",
    "x-llamastack-provider-data",
)


def decode_request_headers(request: httpx.Request) -> dict[str, str]:
    """Decode raw httpx request headers into a string-to-string mapping.

    Args:
        request: The outgoing httpx request.

    Returns:
        Request headers with byte keys and values decoded to UTF-8 strings.
    """
    return {
        k.decode("utf-8") if isinstance(k, bytes) else k: (
            v.decode("utf-8") if isinstance(v, bytes) else v
        )
        for k, v in request.headers.raw
    }


def inject_provider_data_into_headers(
    headers: Mapping[str, str],
    provider_data: Optional[Mapping[str, Any]],
) -> dict[str, str]:
    """Add ``X-OGX-Provider-Data`` when provider data is configured.

    Args:
        headers: Existing request headers.
        provider_data: Provider credentials/metadata to forward to Llama Stack.

    Returns:
        Headers with provider data injected when absent from the request.
    """
    if not provider_data:
        return dict(headers)
    if any(key in headers for key in _PROVIDER_DATA_HEADER_KEYS):
        return dict(headers)
    result = dict(headers)
    result["X-OGX-Provider-Data"] = json.dumps(provider_data)
    return result


def request_with_provider_data_headers(
    request: httpx.Request,
    provider_data: Optional[Mapping[str, Any]],
) -> httpx.Request:
    """Return a request copy with provider data headers injected when needed.

    Args:
        request: The outgoing httpx request.
        provider_data: Provider credentials/metadata to forward to Llama Stack.

    Returns:
        The original request, or a copy with provider data headers added.
    """
    headers = inject_provider_data_into_headers(
        decode_request_headers(request),
        provider_data,
    )
    if headers == decode_request_headers(request):
        return request
    return httpx.Request(
        method=request.method,
        url=request.url,
        headers=headers,
        content=request.content,
        extensions=request.extensions,
    )


def wrap_http_client_with_provider_data(
    http_client: httpx.AsyncClient,
    provider_data: Optional[Mapping[str, Any]],
) -> httpx.AsyncClient:
    """Wrap an httpx client so outbound requests include provider data headers.

    Args:
        http_client: The client whose transport will be wrapped.
        provider_data: Provider credentials/metadata to forward to Llama Stack.

    Returns:
        The original client when ``provider_data`` is empty, otherwise a new
        client with a wrapping transport.
    """
    if not provider_data:
        return http_client

    transport = OgxServerTransport(
        http_client._transport,  # pylint: disable=protected-access
        provider_data=provider_data,
    )
    return httpx.AsyncClient(
        transport=transport,
        timeout=http_client.timeout,
        follow_redirects=http_client.follow_redirects,
    )


class OgxServerTransport(httpx.AsyncBaseTransport):
    """httpx transport that injects provider data headers before delegating over HTTP."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport,
        *,
        provider_data: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Initialize the wrapping transport.

        Args:
            transport: The underlying transport used for real HTTP requests.
            provider_data: Provider credentials/metadata to forward to Llama Stack.
        """
        self._transport = transport
        self._provider_data = provider_data

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Inject provider data headers and delegate to the wrapped transport.

        Args:
            request: The outgoing httpx request.

        Returns:
            The response from the wrapped transport.
        """
        request = request_with_provider_data_headers(request, self._provider_data)
        return await self._transport.handle_async_request(request)

    async def aclose(self) -> None:
        """Close the wrapped transport."""
        await self._transport.aclose()


class _AsyncByteStream(httpx.AsyncByteStream):
    """Wraps an async byte generator as an httpx AsyncByteStream."""

    def __init__(self, gen: AsyncGenerator[bytes, None]) -> None:
        """Store an async generator that yields raw bytes for streaming.

        Args:
            gen: An async generator producing byte chunks to stream.
        """
        self._gen = gen

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Yield bytes chunks from the wrapped generator.

        Returns:
            An async iterator of bytes fulfilling the httpx.AsyncByteStream contract.
        """
        async for chunk in self._gen:
            yield chunk


class OgxLibraryTransport(httpx.AsyncBaseTransport):
    """Custom httpx transport that dispatches requests through a Llama Stack library client.

    Instead of making real HTTP calls, this transport routes requests directly
    to the Llama Stack's in-process route handlers via the library client's
    route matching and body conversion logic.
    """

    def __init__(self, client: AsyncOGXAsLibraryClient) -> None:
        """Initialize the transport with a Llama Stack library client.

        Args:
            client: An initialized ``AsyncOGXAsLibraryClient`` whose route
                handlers will receive dispatched requests.
        """
        self._client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Dispatch an httpx request to the in-process Llama Stack route handlers.

        Args:
            request: The outgoing httpx request to route.

        Returns:
            An httpx response built from the matched route handler result.

        Raises:
            RuntimeError: If the library client has not been initialized.
        """
        if self._client.route_impls is None:
            raise RuntimeError(
                "Llama Stack library client not initialized. Call initialize() first."
            )

        method = request.method
        path = request.url.raw_path.decode("utf-8")

        body = json.loads(request.content) if request.content else {}

        headers = inject_provider_data_into_headers(
            decode_request_headers(request),
            self._client.provider_data,
        )

        with request_provider_data_context(headers):
            is_stream = body.get("stream", False)

            if is_stream:
                return await self._handle_streaming(request, method, path, body)
            return await self._handle_non_streaming(request, method, path, body)

    async def _handle_non_streaming(
        self,
        request: httpx.Request,
        method: str,
        path: str,
        body: dict[str, Any],
    ) -> httpx.Response:
        """Dispatch a non-streaming request to the matched route handler.

        Args:
            request: The original httpx request (attached to the response).
            method: The HTTP method (e.g. ``"POST"``).
            path: The decoded URL path used for route matching.
            body: The parsed JSON request body.

        Returns:
            An httpx.Response containing the JSON-serialized handler result.

        Raises:
            RuntimeError: If route_impls is not initialized.
        """
        if self._client.route_impls is None:
            raise RuntimeError("route_impls is not initialized")

        matched_func, path_params, _, _ = find_matching_route(
            method, path, self._client.route_impls
        )
        merged_body = {**body, **path_params}
        merged_body = self._client._convert_body(  # pylint: disable=protected-access
            matched_func, merged_body
        )

        result = await matched_func(**merged_body)

        json_content = json.dumps(convert_pydantic_to_json_value(result))
        status_code = httpx.codes.OK

        if method.upper() == "DELETE" and result is None:
            status_code = httpx.codes.NO_CONTENT
            json_content = ""

        return httpx.Response(
            status_code=status_code,
            content=json_content.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            request=request,
        )

    async def _handle_streaming(
        self,
        request: httpx.Request,
        method: str,
        path: str,
        body: dict[str, Any],
    ) -> httpx.Response:
        """Dispatch a streaming request and return an SSE event-stream response.

        Args:
            request: The original httpx request (attached to the response).
            method: The HTTP method (e.g. ``"POST"``).
            path: The decoded URL path used for route matching.
            body: The parsed JSON request body (must contain ``stream: True``).

        Returns:
            An httpx.Response with a streaming body of SSE-formatted chunks.

        Raises:
            RuntimeError: If route_impls is not initialized.
        """
        if self._client.route_impls is None:
            raise RuntimeError("route_impls is not initialized")

        func, path_params, _, _ = find_matching_route(
            method, path, self._client.route_impls
        )
        merged_body = {**body, **path_params}
        merged_body = self._client._convert_body(  # pylint: disable=protected-access
            func, merged_body
        )

        result = await func(**merged_body)

        async def gen() -> AsyncGenerator[bytes, None]:
            if isinstance(result, StreamingResponse):
                async for chunk in result.body_iterator:
                    if isinstance(chunk, str):
                        yield chunk.encode("utf-8")
                    else:
                        yield bytes(chunk)
            else:
                async for chunk in result:
                    data = json.dumps(convert_pydantic_to_json_value(chunk))
                    yield f"data: {data}\n\n".encode("utf-8")

        wrapped_gen = preserve_contexts_async_generator(gen(), [PROVIDER_DATA_VAR])

        return httpx.Response(
            status_code=httpx.codes.OK,
            stream=_AsyncByteStream(wrapped_gen),
            headers={"Content-Type": "text/event-stream"},
            request=request,
        )
