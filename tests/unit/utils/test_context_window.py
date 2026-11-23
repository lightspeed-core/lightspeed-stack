"""Unit tests for utils/context_window."""

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from pytest_mock import MockerFixture

from constants import DEFAULT_CONTEXT_WINDOW
from models.config import InferenceConfiguration
from utils import context_window
from utils.context_window import (
    resolve_context_window,
    resolve_context_window_automatically,
)

PROVIDERS: list[dict[str, Any]] = [
    {
        "type": "vllm",
        "id": "rhaiis",
        "allowed_models": [
            {
                "provider_model_id": "ibm-granite/granite-3.3-8b-instruct",
                "metadata": {"context_window": 32_768},
            },
            {
                "name": "small",
                "provider_model_id": "ibm-granite/granite-3.3-2b-instruct",
                "metadata": {"context_window": 8192},
            },
            "llama",
        ],
    },
    {
        "type": "openai",
        "id": "my-openai",
        "allowed_models": [{"name": "luna", "provider_model_id": "gpt-5.6-luna"}],
    },
]

AUTOMATIC_WINDOWS: dict[tuple[str, str], int] = {
    ("openai", "gpt-5.6-luna"): 1_050_000,
}


def _inference(
    context_windows: Optional[dict[str, int]] = None,
) -> InferenceConfiguration:
    """Build an inference configuration with the test providers."""
    return InferenceConfiguration.model_validate(
        {"providers": PROVIDERS, "context_windows": context_windows or {}}
    )


def _automatic_window(provider: str, model_ref: str) -> Optional[int]:
    """Stand in for the automatic tier; it is never asked without a provider."""
    assert provider
    assert model_ref
    return AUTOMATIC_WINDOWS.get((provider, model_ref))


@pytest.fixture(autouse=True)
def _clear_automatic_cache() -> Generator[None, None, None]:
    """Keep automatic lookups cached in one test out of any other test."""
    resolve_context_window_automatically.cache_clear()
    yield
    resolve_context_window_automatically.cache_clear()


@pytest.mark.parametrize(
    ("model_id", "context_windows", "expected"),
    [
        pytest.param(
            "rhaiis/ibm-granite/granite-3.3-8b-instruct",
            None,
            32_768,
            id="catalog-metadata",
        ),
        pytest.param(
            "rhaiis/ibm-granite/granite-3.3-2b-instruct",
            None,
            8192,
            id="catalog-metadata-by-backend-id",
        ),
        pytest.param(
            "other/ibm-granite/granite-3.3-8b-instruct",
            None,
            DEFAULT_CONTEXT_WINDOW,
            id="catalog-other-provider",
        ),
        pytest.param(
            "rhaiis/ibm-granite/granite-3.3-8b-instruct",
            {"rhaiis/ibm-granite/granite-3.3-8b-instruct": 1000},
            32_768,
            id="metadata-before-deprecated-map",
        ),
        pytest.param("rhaiis/llama", {"rhaiis/llama": 1000}, 1000, id="deprecated-map"),
        pytest.param(
            "openai/gpt-5.6-luna",
            {"openai/gpt-5.6-luna": 2000},
            2000,
            id="deprecated-map-before-automatic",
        ),
        pytest.param(
            "openai/gpt-5.6-luna", None, 1_050_000, id="automatic-unlisted-provider"
        ),
        pytest.param(
            "my-openai/luna", None, 1_050_000, id="automatic-provider-type-and-model-id"
        ),
        pytest.param("rhaiis/llama", None, 128_000, id="default"),
        pytest.param("gpt-5.6-luna", None, DEFAULT_CONTEXT_WINDOW, id="no-provider"),
    ],
)
def test_resolve_context_window(
    mocker: MockerFixture,
    model_id: str,
    context_windows: Optional[dict[str, int]],
    expected: int,
) -> None:
    """Metadata, then the deprecated map, then automatic, then the default."""
    mocker.patch.object(
        context_window,
        "resolve_context_window_automatically",
        side_effect=_automatic_window,
    )
    assert resolve_context_window(model_id, _inference(context_windows)) == expected


@pytest.mark.parametrize(
    ("provider", "model_ref", "known"),
    [
        ("openai", "gpt-4o-mini", True),
        ("bedrock", "anthropic.claude-3-5-sonnet-20240620-v1:0", True),
        # an OpenAI model name served by vLLM must not get OpenAI's window
        ("vllm", "gpt-4o-mini", False),
        ("openai", "no-such-model", False),
    ],
)
def test_resolve_context_window_automatically(
    provider: str, model_ref: str, known: bool
) -> None:
    """Known models resolve to a positive window; anything else to None."""
    window = resolve_context_window_automatically(provider, model_ref)
    assert (window is not None) is known
    assert window is None or window > 0


@pytest.mark.parametrize("listed_window", [None, 0])
def test_resolve_context_window_automatically_ignores_unusable_window(
    mocker: MockerFixture, listed_window: Optional[int]
) -> None:
    """A model listed without a positive window resolves to None."""
    snapshot = mocker.Mock()
    snapshot.find_provider_model.return_value = (
        None,
        SimpleNamespace(context_window=listed_window),
    )
    mocker.patch.object(context_window, "get_snapshot", return_value=snapshot)
    assert resolve_context_window_automatically("openai", "gpt-4o-mini") is None
