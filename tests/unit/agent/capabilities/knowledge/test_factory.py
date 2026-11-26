"""Unit tests for knowledge capability construction."""

import logging
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture, MockType

from agent.capabilities.knowledge.factory import KnowledgeFactory
from agent.types.settings import KnowledgeSourceSettings
from agent.types.settings.knowledge import KnowledgeSettings, OKPKnowledgeSourceSettings
from constants import OKP_RAG_ID
from knowledge.capability import Knowledge
from knowledge.sources.okp import OkpKnowledgeSource, OkpProductFilter
from models.config import RerankerConfiguration
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
    ProviderNotFoundError,
)


def _install(
    mocker: MockerFixture,
    *,
    reranker: RerankerConfiguration | None,
    inline_chunks: int = 4,
    tool_chunks: int = 6,
) -> tuple[MockType, MockType]:
    """Patch configuration, the source registry, and model resolution."""
    config = SimpleNamespace(
        reranker=reranker,
        rag=SimpleNamespace(
            retrieval=SimpleNamespace(
                inline=SimpleNamespace(max_chunks=inline_chunks),
                tool=SimpleNamespace(max_chunks=tool_chunks),
            )
        ),
    )
    registry = mocker.Mock()
    mocker.patch("agent.capabilities.knowledge.factory.configuration", config)
    mocker.patch(
        "agent.capabilities.knowledge.factory.KnowledgeSourceRegistry",
        return_value=registry,
    )
    provider_registry = mocker.Mock()
    mocker.patch(
        "agent.capabilities.knowledge.factory.ProviderRegistry",
        return_value=provider_registry,
    )
    return registry, provider_registry


def _settings(
    *sources: KnowledgeSourceSettings, tool_max_matches: int | None = None
) -> KnowledgeSettings:
    """Wrap source settings in the object the factory accepts."""
    return KnowledgeSettings(sources=list(sources), tool_max_matches=tool_max_matches)


def test_no_enabled_sources_build_nothing(mocker: MockerFixture) -> None:
    """Disabled settings and an empty list produce no knowledge capability."""
    registry, providers = _install(mocker, reranker=RerankerConfiguration(enabled=True))

    assert KnowledgeFactory.build_capabilities(KnowledgeSettings()) is None
    assert (
        KnowledgeFactory.build_capabilities(
            _settings(KnowledgeSourceSettings(id="alpha", enabled=False))
        )
        is None
    )

    registry.find_source.assert_not_called()
    providers.resolve_model_instance.assert_not_called()


def test_unknown_sources_are_skipped(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """An id that is not registered is logged and skipped."""
    registry, _providers = _install(mocker, reranker=None)
    registry.find_source.return_value = None

    with caplog.at_level(logging.WARNING):
        capability = KnowledgeFactory.build_capabilities(
            _settings(KnowledgeSourceSettings(id="missing"))
        )

    assert capability is None
    assert "Knowledge source 'missing' is not registered" in caplog.text


def test_enabled_sources_keep_settings_order(mocker: MockerFixture) -> None:
    """Enabled, registered sources are attached in settings order."""
    alpha = mocker.Mock()
    beta = mocker.Mock()
    registry, providers = _install(
        mocker,
        reranker=None,
        inline_chunks=3,
        tool_chunks=9,
    )
    registry.find_source.side_effect = {"beta": beta, "alpha": alpha}.get

    capability = KnowledgeFactory.build_capabilities(
        _settings(
            KnowledgeSourceSettings(id="beta"),
            KnowledgeSourceSettings(id="alpha", enabled=False),
            KnowledgeSourceSettings(id="missing"),
            KnowledgeSourceSettings(id="alpha"),
        )
    )

    assert isinstance(capability, Knowledge)
    assert list(capability.sources) == [beta, alpha]
    assert capability.reranker is None
    assert capability.auto_max_matches == 3
    assert capability.tool_max_matches == 9
    assert [call.args[0] for call in registry.find_source.call_args_list] == [
        "beta",
        "missing",
        "alpha",
    ]
    providers.resolve_model_instance.assert_not_called()


def test_omitted_tool_max_matches_uses_the_configured_limit(
    mocker: MockerFixture,
) -> None:
    """An unset tool match cap leaves the configured tool chunk limit in place."""
    source = mocker.Mock()
    registry, _providers = _install(
        mocker, reranker=None, inline_chunks=3, tool_chunks=9
    )
    registry.find_source.return_value = source

    capability = KnowledgeFactory.build_capabilities(
        _settings(KnowledgeSourceSettings(id="alpha"))
    )

    assert isinstance(capability, Knowledge)
    assert capability.tool_max_matches == 9
    assert capability.auto_max_matches == 3


def test_tool_max_matches_overrides_the_configured_limit(
    mocker: MockerFixture,
) -> None:
    """A tool match cap on the settings replaces the configured tool chunk limit."""
    source = mocker.Mock()
    registry, _providers = _install(
        mocker, reranker=None, inline_chunks=3, tool_chunks=9
    )
    registry.find_source.return_value = source

    capability = KnowledgeFactory.build_capabilities(
        _settings(KnowledgeSourceSettings(id="alpha"), tool_max_matches=2)
    )

    assert isinstance(capability, Knowledge)
    assert capability.tool_max_matches == 2
    assert capability.auto_max_matches == 3


def test_disabled_reranker_is_not_loaded(mocker: MockerFixture) -> None:
    """A disabled reranker leaves the capability without a cross-encoder."""
    source = mocker.Mock()
    _registry, providers = _install(
        mocker, reranker=RerankerConfiguration(enabled=False)
    )
    _registry.find_source.return_value = source

    capability = KnowledgeFactory.build_capabilities(
        _settings(KnowledgeSourceSettings(id="alpha"))
    )

    assert isinstance(capability, Knowledge)
    assert capability.reranker is None
    providers.resolve_model_instance.assert_not_called()


def test_missing_reranker_configuration_skips_the_model(
    mocker: MockerFixture,
) -> None:
    """No reranker configuration leaves the capability without a cross-encoder."""
    source = mocker.Mock()
    _registry, providers = _install(mocker, reranker=None)
    _registry.find_source.return_value = source

    capability = KnowledgeFactory.build_capabilities(
        _settings(KnowledgeSourceSettings(id="alpha"))
    )

    assert isinstance(capability, Knowledge)
    assert capability.reranker is None
    providers.resolve_model_instance.assert_not_called()


def test_enabled_reranker_is_attached(mocker: MockerFixture) -> None:
    """An enabled reranker is resolved from the inference registry and attached."""
    source = mocker.Mock()
    model = mocker.Mock()
    _registry, providers = _install(
        mocker,
        reranker=RerankerConfiguration(
            enabled=True,
            provider="sentence_transformers",
            model="cross-encoder/test",
        ),
    )
    _registry.find_source.return_value = source
    providers.resolve_model_instance.return_value = model

    capability = KnowledgeFactory.build_capabilities(
        _settings(KnowledgeSourceSettings(id="alpha"))
    )

    assert isinstance(capability, Knowledge)
    assert capability.reranker is model
    providers.resolve_model_instance.assert_called_once_with(
        "rerank",
        "sentence_transformers",
        "cross-encoder/test",
    )


@pytest.mark.parametrize(
    "error",
    [
        ProviderNotFoundError("sentence_transformers"),
        ModelNotAvailableError("cross-encoder/test", "rerank", "sentence_transformers"),
        ModelTypeNotSupportedError("rerank", "sentence_transformers"),
    ],
)
def test_unresolved_reranker_leaves_sources_in_place(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    """A reranker that cannot be resolved does not drop the knowledge sources."""
    source = mocker.Mock()
    _registry, providers = _install(
        mocker,
        reranker=RerankerConfiguration(
            enabled=True,
            provider="sentence_transformers",
            model="cross-encoder/test",
        ),
    )
    _registry.find_source.return_value = source
    providers.resolve_model_instance.side_effect = error

    with caplog.at_level(logging.WARNING):
        capability = KnowledgeFactory.build_capabilities(
            _settings(KnowledgeSourceSettings(id="alpha"))
        )

    assert isinstance(capability, Knowledge)
    assert list(capability.sources) == [source]
    assert capability.reranker is None
    assert "Could not resolve cross-encoder" in caplog.text


def test_okp_product_filters_replace_the_registered_source(
    mocker: MockerFixture,
) -> None:
    """Request product filters are copied onto a new OKP source."""
    registered = OkpKnowledgeSource(name=OKP_RAG_ID, base_url="https://okp.example")
    registry, _providers = _install(mocker, reranker=None)
    registry.find_source.return_value = registered
    products = [
        OkpProductFilter("openshift_container_platform", ("4.19", "4.20")),
        OkpProductFilter("rhel"),
    ]

    capability = KnowledgeFactory.build_capabilities(
        _settings(OKPKnowledgeSourceSettings(id=OKP_RAG_ID, products=products))
    )

    assert isinstance(capability, Knowledge)
    source = capability.sources[0]
    assert isinstance(source, OkpKnowledgeSource)
    assert source is not registered
    assert source.products == tuple(products)
    assert registered.products == ()


def test_okp_source_is_reused_when_the_request_sets_no_products(
    mocker: MockerFixture,
) -> None:
    """An OKP request with no product filters keeps the registered source."""
    registered = OkpKnowledgeSource(name=OKP_RAG_ID, base_url="https://okp.example")
    registry, _providers = _install(mocker, reranker=None)
    registry.find_source.return_value = registered

    capability = KnowledgeFactory.build_capabilities(
        _settings(OKPKnowledgeSourceSettings(id=OKP_RAG_ID))
    )

    assert isinstance(capability, Knowledge)
    assert capability.sources[0] is registered


def test_product_filters_on_a_non_okp_source_are_ignored(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """Product filters are not applied when the registered source is not OKP."""
    source = mocker.Mock()
    registry, _providers = _install(mocker, reranker=None)
    registry.find_source.return_value = source

    with caplog.at_level(logging.WARNING):
        capability = KnowledgeFactory.build_capabilities(
            _settings(
                OKPKnowledgeSourceSettings(
                    id="alpha",
                    products=[OkpProductFilter("rhel")],
                )
            )
        )

    assert isinstance(capability, Knowledge)
    assert capability.sources[0] is source
    assert "is not an OKP source; ignoring product filters" in caplog.text
