"""Unit tests for functions defined in src/models/config.py."""

import json
import pytest

from pathlib import Path

from models.config import (
    Configuration,
    LLamaStackConfiguration,
    ServiceConfiguration,
    UserDataCollection,
    TLSConfiguration,
)


def test_service_configuration_constructor() -> None:
    """Test the ServiceConfiguration constructor."""
    s = ServiceConfiguration()
    assert s is not None

    assert s.host == "localhost"
    assert s.port == 8080
    assert s.auth_enabled is False
    assert s.workers == 1
    assert s.color_log is True
    assert s.access_log is True
    assert s.tls_config == TLSConfiguration()


def test_service_configuration_port_value() -> None:
    """Test the ServiceConfiguration port value validation."""
    with pytest.raises(ValueError, match="Port value should not be negative"):
        ServiceConfiguration(port=-1)

    with pytest.raises(ValueError, match="Port value should be less than 65536"):
        ServiceConfiguration(port=100000)


def test_service_configuration_workers_value() -> None:
    """Test the ServiceConfiguration workers value validation."""
    with pytest.raises(ValueError, match="Workers must be set to at least 1"):
        ServiceConfiguration(workers=-1)


def test_llama_stack_configuration_constructor() -> None:
    """Test the LLamaStackConfiguration constructor."""
    llama_stack_configuration = LLamaStackConfiguration(
        use_as_library_client=True, library_client_config_path="foo"
    )
    assert llama_stack_configuration is not None

    llama_stack_configuration = LLamaStackConfiguration(
        use_as_library_client=False, url="http://localhost"
    )
    assert llama_stack_configuration is not None

    llama_stack_configuration = LLamaStackConfiguration(url="http://localhost")
    assert llama_stack_configuration is not None

    llama_stack_configuration = LLamaStackConfiguration(
        use_as_library_client=False, url="http://localhost", api_key="foo"
    )
    assert llama_stack_configuration is not None


def test_llama_stack_wrong_configuration_constructor_no_url() -> None:
    """Test the LLamaStackConfiguration constructor."""
    with pytest.raises(
        ValueError,
        match="LLama stack URL is not specified and library client mode is not specified",
    ):
        LLamaStackConfiguration()


def test_llama_stack_wrong_configuration_constructor_library_mode_off() -> None:
    """Test the LLamaStackConfiguration constructor."""
    with pytest.raises(
        ValueError,
        match="LLama stack URL is not specified and library client mode is not enabled",
    ):
        LLamaStackConfiguration(use_as_library_client=False)


def test_llama_stack_wrong_configuration_no_config_file() -> None:
    """Test the LLamaStackConfiguration constructor."""
    with pytest.raises(
        ValueError,
        match="LLama stack library client mode is enabled but a configuration file path is not specified",
    ):
        LLamaStackConfiguration(use_as_library_client=True)


def test_user_data_collection_feedback_enabled() -> None:
    """Test the UserDataCollection constructor for feedback."""
    # correct configuration
    cfg = UserDataCollection(feedback_disabled=True, feedback_storage=None)
    assert cfg is not None
    assert cfg.feedback_disabled is True
    assert cfg.feedback_storage is None


def test_user_data_collection_feedback_disabled() -> None:
    """Test the UserDataCollection constructor for feedback."""
    # incorrect configuration
    with pytest.raises(
        ValueError,
        match="feedback_storage is required when feedback is enabled",
    ):
        UserDataCollection(feedback_disabled=False, feedback_storage=None)


def test_user_data_collection_transcripts_enabled() -> None:
    """Test the UserDataCollection constructor for transcripts."""
    # correct configuration
    cfg = UserDataCollection(transcripts_disabled=True, transcripts_storage=None)
    assert cfg is not None


def test_user_data_collection_transcripts_disabled() -> None:
    """Test the UserDataCollection constructor for transcripts."""
    # incorrect configuration
    with pytest.raises(
        ValueError,
        match="transcripts_storage is required when transcripts is enabled",
    ):
        UserDataCollection(transcripts_disabled=False, transcripts_storage=None)


def test_tls_configuration() -> None:
    """Test the TLS configuration."""
    cfg = TLSConfiguration(
        tls_certificate_path="tests/configuration/server.crt",
        tls_key_path="tests/configuration/server.key",
        tls_key_password="tests/configuration/password",
    )
    assert cfg is not None
    assert cfg.tls_certificate_path == Path("tests/configuration/server.crt")
    assert cfg.tls_key_path == Path("tests/configuration/server.key")
    assert cfg.tls_key_password == Path("tests/configuration/password")


def test_tls_configuration_wrong_certificate_path() -> None:
    """Test the TLS configuration loading when some path is broken."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="this-is-wrong",
            tls_key_path="tests/configuration/server.key",
            tls_key_password="tests/configuration/password",
        )


def test_tls_configuration_wrong_key_path() -> None:
    """Test the TLS configuration loading when some path is broken."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/configurationserver.crt",
            tls_key_path="this-is-wrong",
            tls_key_password="tests/configuration/password",
        )


def test_tls_configuration_wrong_password_path() -> None:
    """Test the TLS configuration loading when some path is broken."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/configurationserver.crt",
            tls_key_path="tests/configuration/server.key",
            tls_key_password="this-is-wrong",
        )


def test_tls_configuration_certificate_path_to_directory() -> None:
    """Test the TLS configuration loading when some path points to a directory."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/",
            tls_key_path="tests/configuration/server.key",
            tls_key_password="tests/configuration/password",
        )


def test_tls_configuration_key_path_to_directory() -> None:
    """Test the TLS configuration loading when some path points to a directory."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/configurationserver.crt",
            tls_key_path="tests/",
            tls_key_password="tests/configuration/password",
        )


def test_tls_configuration_password_path_to_directory() -> None:
    """Test the TLS configuration loading when some path points to a directory."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/configurationserver.crt",
            tls_key_path="tests/configuration/server.key",
            tls_key_password="tests/",
        )


def test_dump_configuration(tmp_path) -> None:
    """Test the ability to dump configuration."""
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=True, library_client_config_path="foo"
        ),
        user_data_collection=UserDataCollection(
            feedback_disabled=True, feedback_storage=None
        ),
    )
    assert cfg is not None
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        assert content is not None
        assert "name" in content
        assert "service" in content
        assert "llama_stack" in content
        assert "user_data_collection" in content
