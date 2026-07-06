"""Unit tests for pydantic_ai_lightspeed.llamastack._transport module."""

# pylint: disable=protected-access

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from pytest_mock import MockerFixture

from pydantic_ai_lightspeed.llamastack._transport import (
    LlamaStackLibraryTransport,
    _AsyncByteStream,
)


@pytest.fixture(name="mock_library_client")
def mock_library_client_fixture(mocker: MockerFixture) -> Any:
    """Create a mock AsyncLlamaStackAsLibraryClient.

    Returns:
        A mocked library client with route_impls set to an empty dict.
    """
    client = mocker.Mock()
    client.route_impls = {}
    client.provider_data = None
    return client


@pytest.fixture(name="transport")
def transport_fixture(mock_library_client: Any) -> LlamaStackLibraryTransport:
    """Create a LlamaStackLibraryTransport with a mocked library client.

    Returns:
        An initialized LlamaStackLibraryTransport.
    """
    return LlamaStackLibraryTransport(mock_library_client)


class TestAsyncByteStream:
    """Tests for the _AsyncByteStream helper class."""

    @pytest.mark.asyncio
    async def test_iterates_chunks(self) -> None:
        """Test that _AsyncByteStream yields all chunks from the wrapped generator."""

        async def gen() -> AsyncGenerator[bytes, None]:
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

        stream = _AsyncByteStream(gen())
        chunks = [chunk async for chunk in stream]

        assert chunks == [b"chunk1", b"chunk2", b"chunk3"]

    @pytest.mark.asyncio
    async def test_empty_generator(self) -> None:
        """Test that _AsyncByteStream handles an empty generator gracefully."""

        async def gen() -> AsyncGenerator[bytes, None]:
            return
            yield  # pragma: no cover

        stream = _AsyncByteStream(gen())
        chunks = [chunk async for chunk in stream]

        assert chunks == []


class TestLlamaStackLibraryTransportInit:  # pylint: disable=too-few-public-methods
    """Tests for LlamaStackLibraryTransport initialization."""

    def test_stores_client(self, mock_library_client: Any) -> None:
        """Test that the transport stores the provided library client."""
        transport = LlamaStackLibraryTransport(mock_library_client)
        assert transport._client is mock_library_client


class TestHandleAsyncRequest:
    """Tests for LlamaStackLibraryTransport.handle_async_request."""

    @pytest.mark.asyncio
    async def test_raises_when_route_impls_is_none(self, mocker: MockerFixture) -> None:
        """Test RuntimeError is raised when the library client is not initialized."""
        client = mocker.Mock()
        client.route_impls = None
        transport = LlamaStackLibraryTransport(client)

        request = httpx.Request("POST", "http://localhost/v1/responses")

        with pytest.raises(
            RuntimeError,
            match="Llama Stack library client not initialized",
        ):
            await transport.handle_async_request(request)

    @pytest.mark.asyncio
    async def test_non_streaming_request(
        self, mocker: MockerFixture, transport: LlamaStackLibraryTransport
    ) -> None:
        """Test a non-streaming request is dispatched correctly."""
        body = {"model": "test-model", "messages": []}
        request = httpx.Request(
            "POST",
            "http://localhost/v1/responses",
            content=json.dumps(body).encode("utf-8"),
        )

        mock_func = mocker.AsyncMock(return_value={"id": "resp-1", "choices": []})
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.find_matching_route",
            return_value=(mock_func, {}, None, None),
        )
        transport._client._convert_body = mocker.Mock(side_effect=lambda f, b: b)

        response = await transport.handle_async_request(request)

        assert response.status_code == httpx.codes.OK
        assert response.headers["Content-Type"] == "application/json"
        result = json.loads(response.content)
        assert result == {"id": "resp-1", "choices": []}

    @pytest.mark.asyncio
    async def test_streaming_request(
        self, mocker: MockerFixture, transport: LlamaStackLibraryTransport
    ) -> None:
        """Test a streaming request returns an event-stream response."""
        body = {"model": "test-model", "stream": True}
        request = httpx.Request(
            "POST",
            "http://localhost/v1/responses",
            content=json.dumps(body).encode("utf-8"),
        )

        async def mock_stream_result() -> AsyncGenerator[dict[str, int], None]:
            yield {"chunk": 1}
            yield {"chunk": 2}

        mock_func = mocker.AsyncMock(return_value=mock_stream_result())
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.find_matching_route",
            return_value=(mock_func, {}, None, None),
        )
        transport._client._convert_body = mocker.Mock(side_effect=lambda f, b: b)

        response = await transport.handle_async_request(request)

        assert response.status_code == httpx.codes.OK
        assert response.headers["Content-Type"] == "text/event-stream"

    @pytest.mark.asyncio
    async def test_empty_body_request(
        self, mocker: MockerFixture, transport: LlamaStackLibraryTransport
    ) -> None:
        """Test that a request with no content body passes an empty dict."""
        request = httpx.Request("GET", "http://localhost/v1/models")

        mock_func = mocker.AsyncMock(return_value=[])
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.find_matching_route",
            return_value=(mock_func, {}, None, None),
        )
        transport._client._convert_body = mocker.Mock(side_effect=lambda f, b: b)

        response = await transport.handle_async_request(request)

        assert response.status_code == httpx.codes.OK
        mock_func.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_provider_data_header_injection(self, mocker: MockerFixture) -> None:
        """Test that provider_data is injected as a header when not already present."""
        client = mocker.Mock()
        client.route_impls = {}
        client.provider_data = {"api_key": "test-key"}
        transport = LlamaStackLibraryTransport(client)

        body = {"model": "test-model"}
        request = httpx.Request(
            "POST",
            "http://localhost/v1/responses",
            content=json.dumps(body).encode("utf-8"),
        )

        mock_func = mocker.AsyncMock(return_value={"id": "resp-1"})
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.find_matching_route",
            return_value=(mock_func, {}, None, None),
        )
        client._convert_body = mocker.Mock(side_effect=lambda f, b: b)

        mock_ctx = mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.request_provider_data_context"
        )

        await transport.handle_async_request(request)

        call_args = mock_ctx.call_args[0][0]
        assert "X-LlamaStack-Provider-Data" in call_args
        assert json.loads(call_args["X-LlamaStack-Provider-Data"]) == {
            "api_key": "test-key"
        }

    @pytest.mark.asyncio
    async def test_provider_data_header_not_injected_when_present(
        self, mocker: MockerFixture
    ) -> None:
        """Test that provider_data is not duplicated when the header already exists."""
        client = mocker.Mock()
        client.route_impls = {}
        client.provider_data = {"api_key": "should-not-override"}
        transport = LlamaStackLibraryTransport(client)

        body = {"model": "test-model"}
        request = httpx.Request(
            "POST",
            "http://localhost/v1/responses",
            content=json.dumps(body).encode("utf-8"),
            headers={"X-LlamaStack-Provider-Data": '{"existing": true}'},
        )

        mock_func = mocker.AsyncMock(return_value={"id": "resp-1"})
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.find_matching_route",
            return_value=(mock_func, {}, None, None),
        )
        client._convert_body = mocker.Mock(side_effect=lambda f, b: b)

        mock_ctx = mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.request_provider_data_context"
        )

        await transport.handle_async_request(request)

        call_args = mock_ctx.call_args[0][0]
        assert json.loads(call_args["X-LlamaStack-Provider-Data"]) == {"existing": True}


class TestHandleNonStreaming:
    """Tests for LlamaStackLibraryTransport._handle_non_streaming."""

    @pytest.mark.asyncio
    async def test_merges_path_params(
        self, mocker: MockerFixture, transport: LlamaStackLibraryTransport
    ) -> None:
        """Test that path parameters are merged into the request body."""
        body: dict[str, Any] = {"model": "test"}
        request = httpx.Request(
            "GET",
            "http://localhost/v1/models/test-model",
            content=json.dumps(body).encode("utf-8"),
        )

        mock_func = mocker.AsyncMock(return_value={"id": "model-1"})
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.find_matching_route",
            return_value=(mock_func, {"model_id": "test-model"}, None, None),
        )
        transport._client._convert_body = mocker.Mock(side_effect=lambda f, b: b)

        await transport._handle_non_streaming(
            request, "GET", "/v1/models/test-model", body
        )

        mock_func.assert_awaited_once_with(model="test", model_id="test-model")

    @pytest.mark.asyncio
    async def test_delete_returns_no_content(
        self, mocker: MockerFixture, transport: LlamaStackLibraryTransport
    ) -> None:
        """Test that DELETE with None result returns 204 No Content."""
        request = httpx.Request("DELETE", "http://localhost/v1/resource/123")

        mock_func = mocker.AsyncMock(return_value=None)
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.find_matching_route",
            return_value=(mock_func, {}, None, None),
        )
        transport._client._convert_body = mocker.Mock(side_effect=lambda f, b: b)

        response = await transport._handle_non_streaming(
            request, "DELETE", "/v1/resource/123", {}
        )

        assert response.status_code == httpx.codes.NO_CONTENT
        assert response.content == b""

    @pytest.mark.asyncio
    async def test_delete_with_result_returns_ok(
        self, mocker: MockerFixture, transport: LlamaStackLibraryTransport
    ) -> None:
        """Test that DELETE with a non-None result returns 200 OK."""
        request = httpx.Request("DELETE", "http://localhost/v1/resource/123")

        mock_func = mocker.AsyncMock(return_value={"deleted": True})
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.find_matching_route",
            return_value=(mock_func, {}, None, None),
        )
        transport._client._convert_body = mocker.Mock(side_effect=lambda f, b: b)

        response = await transport._handle_non_streaming(
            request, "DELETE", "/v1/resource/123", {}
        )

        assert response.status_code == httpx.codes.OK


class TestHandleStreaming:  # pylint: disable=too-few-public-methods
    """Tests for LlamaStackLibraryTransport._handle_streaming."""

    @pytest.mark.asyncio
    async def test_produces_sse_format(
        self, mocker: MockerFixture, transport: LlamaStackLibraryTransport
    ) -> None:
        """Test that streaming responses produce SSE-formatted byte chunks."""

        async def mock_stream() -> AsyncGenerator[dict[str, str], None]:
            yield {"delta": "hello"}
            yield {"delta": "world"}

        request = httpx.Request(
            "POST",
            "http://localhost/v1/responses",
            content=json.dumps({"stream": True}).encode("utf-8"),
        )

        mock_func = mocker.AsyncMock(return_value=mock_stream())
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._transport.find_matching_route",
            return_value=(mock_func, {}, None, None),
        )
        transport._client._convert_body = mocker.Mock(side_effect=lambda f, b: b)

        response = await transport._handle_streaming(
            request, "POST", "/v1/responses", {"stream": True}
        )

        assert response.status_code == httpx.codes.OK
        assert response.headers["Content-Type"] == "text/event-stream"
        assert isinstance(response.stream, _AsyncByteStream)
