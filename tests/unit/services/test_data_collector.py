"""Unit tests for data collector service."""

from pathlib import Path
from unittest.mock import patch, MagicMock
import requests
import tarfile

from services.data_collector import DataCollectorService


def test_data_collector_service_creation() -> None:
    """Test that DataCollectorService can be created."""
    service = DataCollectorService()
    assert service is not None


@patch("services.data_collector.time.sleep")
@patch("services.data_collector.configuration")
def test_run_normal_operation(mock_config, mock_sleep) -> None:
    """Test normal operation of the run method."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.data_collector.collection_interval = (
        60
    )

    with patch.object(service, "_perform_collection") as mock_perform:
        mock_perform.side_effect = [None, KeyboardInterrupt()]

        service.run()

        assert mock_perform.call_count == 2
        mock_sleep.assert_called_once_with(60)


@patch("services.data_collector.time.sleep")
@patch("services.data_collector.configuration")
def test_run_with_exception(mock_config, mock_sleep) -> None:
    """Test run method with exception handling."""
    service = DataCollectorService()

    with patch.object(service, "_perform_collection") as mock_perform:
        mock_perform.side_effect = [OSError("Test error"), KeyboardInterrupt()]

        service.run()

        assert mock_perform.call_count == 2
        mock_sleep.assert_called_once_with(300)


@patch("services.data_collector.configuration")
def test_collect_feedback_files_disabled(mock_config) -> None:
    """Test collecting feedback files when disabled."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.feedback_disabled = True

    result = service._collect_feedback_files()
    assert result == []


@patch("services.data_collector.configuration")
def test_collect_feedback_files_no_storage(mock_config) -> None:
    """Test collecting feedback files when no storage configured."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.feedback_disabled = False
    mock_config.user_data_collection_configuration.feedback_storage = None

    result = service._collect_feedback_files()
    assert result == []


@patch("services.data_collector.configuration")
def test_collect_feedback_files_directory_not_exists(mock_config) -> None:
    """Test collecting feedback files when directory doesn't exist."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.feedback_disabled = False
    mock_config.user_data_collection_configuration.feedback_storage = "/tmp/feedback"

    with patch("services.data_collector.Path") as mock_path:
        mock_path.return_value.exists.return_value = False

        result = service._collect_feedback_files()
        assert result == []


@patch("services.data_collector.configuration")
def test_collect_feedback_files_success(mock_config) -> None:
    """Test collecting feedback files successfully."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.feedback_disabled = False
    mock_config.user_data_collection_configuration.feedback_storage = "/tmp/feedback"

    mock_files = [Path("/tmp/feedback/file1.json")]

    with patch("services.data_collector.Path") as mock_path:
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.glob.return_value = mock_files

        result = service._collect_feedback_files()
        assert result == mock_files


@patch("services.data_collector.configuration")
def test_collect_transcript_files_disabled(mock_config) -> None:
    """Test collecting transcript files when disabled."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.transcripts_disabled = True

    result = service._collect_transcript_files()
    assert result == []


@patch("services.data_collector.configuration")
def test_collect_transcript_files_directory_not_exists(mock_config) -> None:
    """Test collecting transcript files when directory doesn't exist."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.transcripts_disabled = False
    mock_config.user_data_collection_configuration.transcripts_storage = (
        "/tmp/transcripts"
    )

    with patch("services.data_collector.Path") as mock_path:
        mock_path.return_value.exists.return_value = False

        result = service._collect_transcript_files()
        assert result == []


@patch("services.data_collector.configuration")
def test_collect_transcript_files_success(mock_config) -> None:
    """Test collecting transcript files successfully."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.transcripts_disabled = False
    mock_config.user_data_collection_configuration.transcripts_storage = (
        "/tmp/transcripts"
    )

    mock_files = [Path("/tmp/transcripts/user1/conv1/file1.json")]

    with patch("services.data_collector.Path") as mock_path:
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.rglob.return_value = mock_files

        result = service._collect_transcript_files()
        assert result == mock_files


@patch("services.data_collector.configuration")
def test_perform_collection_no_files(mock_config) -> None:
    """Test _perform_collection when no files are found."""
    service = DataCollectorService()

    with (
        patch.object(service, "_collect_feedback_files", return_value=[]),
        patch.object(service, "_collect_transcript_files", return_value=[]),
    ):
        service._perform_collection()


@patch("services.data_collector.configuration")
def test_perform_collection_with_files(mock_config) -> None:
    """Test _perform_collection when files are found."""
    service = DataCollectorService()

    feedback_files = [Path("/tmp/feedback/file1.json")]

    with (
        patch.object(service, "_collect_feedback_files", return_value=feedback_files),
        patch.object(service, "_collect_transcript_files", return_value=[]),
        patch.object(service, "_create_and_send_tarball", return_value=1),
    ):
        service._perform_collection()


@patch("services.data_collector.configuration")
def test_perform_collection_with_exception(mock_config) -> None:
    """Test _perform_collection when an exception occurs."""
    service = DataCollectorService()

    with (
        patch.object(
            service, "_collect_feedback_files", return_value=[Path("/tmp/test.json")]
        ),
        patch.object(service, "_collect_transcript_files", return_value=[]),
        patch.object(
            service, "_create_and_send_tarball", side_effect=Exception("Test error")
        ),
    ):
        try:
            service._perform_collection()
            assert False, "Expected exception"
        except Exception as e:
            assert str(e) == "Test error"


@patch("services.data_collector.configuration")
def test_create_and_send_tarball_no_files(mock_config) -> None:
    """Test creating tarball with no files."""
    service = DataCollectorService()

    result = service._create_and_send_tarball([], "test", Path("/tmp"))
    assert result == 0


@patch("services.data_collector.configuration")
def test_create_and_send_tarball_success(mock_config) -> None:
    """Test creating and sending tarball successfully."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.data_collector.cleanup_after_send = (
        True
    )

    files = [Path("/tmp/test/file1.json")]
    tarball_path = Path("/tmp/test_tarball.tar.gz")

    with (
        patch.object(service, "_create_tarball", return_value=tarball_path),
        patch.object(service, "_send_tarball"),
        patch.object(service, "_cleanup_files"),
        patch.object(service, "_cleanup_empty_directories"),
        patch.object(service, "_cleanup_tarball"),
    ):
        result = service._create_and_send_tarball(files, "test", Path("/tmp"))
        assert result == 1


@patch("services.data_collector.configuration")
def test_create_and_send_tarball_no_cleanup(mock_config) -> None:
    """Test creating and sending tarball without cleanup."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.data_collector.cleanup_after_send = (
        False
    )

    files = [Path("/tmp/test/file1.json")]

    with (
        patch.object(service, "_create_tarball", return_value=Path("/tmp/test.tar.gz")),
        patch.object(service, "_send_tarball"),
        patch.object(service, "_cleanup_tarball"),
    ):
        result = service._create_and_send_tarball(files, "test", Path("/tmp"))
        assert result == 1


@patch("services.data_collector.datetime")
@patch("services.data_collector.tempfile.gettempdir")
@patch("services.data_collector.tarfile.open")
def test_create_tarball_success(mock_tarfile, mock_gettempdir, mock_datetime) -> None:
    """Test creating tarball successfully."""
    service = DataCollectorService()
    mock_datetime.now.return_value.strftime.return_value = "20230101_120000"
    mock_gettempdir.return_value = "/tmp"

    mock_tar = MagicMock()
    mock_tarfile.return_value.__enter__.return_value = mock_tar

    files = [Path("/data/test/file1.json")]

    with patch.object(Path, "stat") as mock_stat:
        mock_stat.return_value.st_size = 1024

        result = service._create_tarball(files, "test", Path("/data"))

        expected_path = Path("/tmp/test_20230101_120000.tar.gz")
        assert result == expected_path
        mock_tar.add.assert_called_once()


@patch("services.data_collector.datetime")
@patch("services.data_collector.tempfile.gettempdir")
@patch("services.data_collector.tarfile.open")
def test_create_tarball_file_add_error(
    mock_tarfile, mock_gettempdir, mock_datetime
) -> None:
    """Test creating tarball with file add error."""
    service = DataCollectorService()
    mock_datetime.now.return_value.strftime.return_value = "20230101_120000"
    mock_gettempdir.return_value = "/tmp"

    mock_tar = MagicMock()
    mock_tar.add.side_effect = OSError("File error")
    mock_tarfile.return_value.__enter__.return_value = mock_tar

    files = [Path("/data/test/file1.json")]

    with patch.object(Path, "stat") as mock_stat:
        mock_stat.return_value.st_size = 1024

        result = service._create_tarball(files, "test", Path("/data"))

        expected_path = Path("/tmp/test_20230101_120000.tar.gz")
        assert result == expected_path


@patch("services.data_collector.configuration")
@patch("services.data_collector.requests.post")
def test_send_tarball_success(mock_post, mock_config) -> None:
    """Test successful tarball sending."""
    service = DataCollectorService()

    mock_config.user_data_collection_configuration.data_collector.ingress_server_url = (
        "http://test.com"
    )
    mock_config.user_data_collection_configuration.data_collector.ingress_server_auth_token = (
        "token"
    )
    mock_config.user_data_collection_configuration.data_collector.connection_timeout = (
        30
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    with patch("builtins.open", create=True) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = b"test data"
        service._send_tarball(Path("/tmp/test.tar.gz"))

        mock_post.assert_called_once()


@patch("services.data_collector.configuration")
@patch("services.data_collector.requests.post")
def test_send_tarball_no_auth_token(mock_post, mock_config) -> None:
    """Test sending tarball without auth token."""
    service = DataCollectorService()

    mock_config.user_data_collection_configuration.data_collector.ingress_server_url = (
        "http://test.com"
    )
    mock_config.user_data_collection_configuration.data_collector.ingress_server_auth_token = (
        None
    )
    mock_config.user_data_collection_configuration.data_collector.connection_timeout = (
        30
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    with patch("builtins.open", create=True):
        service._send_tarball(Path("/tmp/test.tar.gz"))
        mock_post.assert_called_once()


@patch("services.data_collector.configuration")
@patch("services.data_collector.requests.post")
def test_send_tarball_http_error(mock_post, mock_config) -> None:
    """Test tarball sending with HTTP error."""
    service = DataCollectorService()

    mock_config.user_data_collection_configuration.data_collector.ingress_server_url = (
        "http://test.com"
    )
    mock_config.user_data_collection_configuration.data_collector.connection_timeout = (
        30
    )

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Server Error"
    mock_post.return_value = mock_response

    with patch("builtins.open", create=True):
        try:
            service._send_tarball(Path("/tmp/test.tar.gz"))
            assert False, "Expected exception"
        except Exception as e:
            assert "Failed to send tarball" in str(e)


@patch("services.data_collector.configuration")
def test_send_tarball_missing_url(mock_config) -> None:
    """Test tarball sending when ingress server URL is None."""
    service = DataCollectorService()

    mock_config.user_data_collection_configuration.data_collector.ingress_server_url = (
        None
    )

    try:
        service._send_tarball(Path("/tmp/test.tar.gz"))
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "Ingress server URL is not configured" in str(e)


@patch("services.data_collector.configuration")
def test_perform_collection_with_specific_exceptions(mock_config) -> None:
    """Test _perform_collection with specific exception types that should be caught."""
    service = DataCollectorService()

    # Test with OSError
    with (
        patch.object(
            service, "_collect_feedback_files", return_value=[Path("/tmp/test.json")]
        ),
        patch.object(service, "_collect_transcript_files", return_value=[]),
        patch.object(
            service, "_create_and_send_tarball", side_effect=OSError("OS Error")
        ),
    ):
        try:
            service._perform_collection()
            assert False, "Expected OSError"
        except OSError as e:
            assert str(e) == "OS Error"

    # Test with requests.RequestException
    with (
        patch.object(
            service, "_collect_feedback_files", return_value=[Path("/tmp/test.json")]
        ),
        patch.object(service, "_collect_transcript_files", return_value=[]),
        patch.object(
            service,
            "_create_and_send_tarball",
            side_effect=requests.RequestException("Request Error"),
        ),
    ):
        try:
            service._perform_collection()
            assert False, "Expected RequestException"
        except requests.RequestException as e:
            assert str(e) == "Request Error"

    # Test with tarfile.TarError
    with (
        patch.object(
            service, "_collect_feedback_files", return_value=[Path("/tmp/test.json")]
        ),
        patch.object(service, "_collect_transcript_files", return_value=[]),
        patch.object(
            service,
            "_create_and_send_tarball",
            side_effect=tarfile.TarError("Tar Error"),
        ),
    ):
        try:
            service._perform_collection()
            assert False, "Expected TarError"
        except tarfile.TarError as e:
            assert str(e) == "Tar Error"


def test_cleanup_files_success() -> None:
    """Test successful file cleanup."""
    service = DataCollectorService()
    files = [Path("/tmp/test1.json"), Path("/tmp/test2.json")]

    with patch.object(Path, "unlink") as mock_unlink:
        service._cleanup_files(files)
        assert mock_unlink.call_count == 2


def test_cleanup_files_with_error() -> None:
    """Test file cleanup with error."""
    service = DataCollectorService()
    files = [Path("/tmp/test1.json")]

    with patch.object(Path, "unlink") as mock_unlink:
        mock_unlink.side_effect = OSError("Permission denied")
        service._cleanup_files(files)
        mock_unlink.assert_called_once()


def test_cleanup_tarball_success() -> None:
    """Test successful tarball cleanup."""
    service = DataCollectorService()

    with patch.object(Path, "unlink") as mock_unlink:
        service._cleanup_tarball(Path("/tmp/test.tar.gz"))
        mock_unlink.assert_called_once()


def test_cleanup_tarball_with_error() -> None:
    """Test tarball cleanup with error."""
    service = DataCollectorService()

    with patch.object(Path, "unlink") as mock_unlink:
        mock_unlink.side_effect = OSError("Permission denied")
        service._cleanup_tarball(Path("/tmp/test.tar.gz"))
        mock_unlink.assert_called_once()


@patch("services.data_collector.configuration")
def test_cleanup_empty_directories_disabled(mock_config) -> None:
    """Test directory cleanup when transcripts disabled."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.transcripts_disabled = True

    service._cleanup_empty_directories()


@patch("services.data_collector.configuration")
def test_cleanup_empty_directories_success(mock_config) -> None:
    """Test successful directory cleanup."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.transcripts_disabled = False
    mock_config.user_data_collection_configuration.transcripts_storage = (
        "/tmp/transcripts"
    )

    transcripts_dir = MagicMock()
    user_dir = MagicMock()
    conv_dir = MagicMock()

    transcripts_dir.exists.return_value = True
    transcripts_dir.iterdir.return_value = [user_dir]
    user_dir.is_dir.return_value = True
    user_dir.iterdir.side_effect = [
        [conv_dir],
        [],
    ]  # First call returns conv_dir, second call empty
    conv_dir.is_dir.return_value = True
    conv_dir.iterdir.return_value = []  # Empty directory

    with patch("services.data_collector.Path", return_value=transcripts_dir):
        service._cleanup_empty_directories()

        conv_dir.rmdir.assert_called_once()
        user_dir.rmdir.assert_called_once()


@patch("services.data_collector.configuration")
def test_cleanup_empty_directories_with_errors(mock_config) -> None:
    """Test directory cleanup when rmdir operations fail."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.transcripts_disabled = False
    mock_config.user_data_collection_configuration.transcripts_storage = (
        "/tmp/transcripts"
    )

    transcripts_dir = MagicMock()
    user_dir = MagicMock()
    conv_dir = MagicMock()

    transcripts_dir.exists.return_value = True
    transcripts_dir.iterdir.return_value = [user_dir]
    user_dir.is_dir.return_value = True
    user_dir.iterdir.side_effect = [[conv_dir], []]
    conv_dir.is_dir.return_value = True
    conv_dir.iterdir.return_value = []

    # Both rmdir operations fail
    conv_dir.rmdir.side_effect = OSError("Permission denied")
    user_dir.rmdir.side_effect = OSError("Permission denied")

    with patch("services.data_collector.Path", return_value=transcripts_dir):
        # Should not raise exception
        service._cleanup_empty_directories()

        conv_dir.rmdir.assert_called_once()
        user_dir.rmdir.assert_called_once()


@patch("services.data_collector.configuration")
def test_cleanup_empty_directories_directory_not_exists(mock_config) -> None:
    """Test directory cleanup when transcripts directory doesn't exist."""
    service = DataCollectorService()
    mock_config.user_data_collection_configuration.transcripts_disabled = False
    mock_config.user_data_collection_configuration.transcripts_storage = (
        "/tmp/transcripts"
    )

    with patch("services.data_collector.Path") as mock_path:
        mock_path.return_value.exists.return_value = False

        service._cleanup_empty_directories()


@patch("services.data_collector.configuration")
def test_perform_collection_with_transcript_files(mock_config) -> None:
    """Test _perform_collection with transcript files only."""
    service = DataCollectorService()

    transcript_files = [Path("/tmp/transcripts/file1.json")]

    with (
        patch.object(service, "_collect_feedback_files", return_value=[]),
        patch.object(
            service, "_collect_transcript_files", return_value=transcript_files
        ),
        patch.object(service, "_create_and_send_tarball", return_value=1),
    ):
        service._perform_collection()
