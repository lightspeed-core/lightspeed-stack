"""Unit tests for data collector service."""

from pathlib import Path
from unittest.mock import patch, MagicMock
import requests
import tarfile
from services.data_collector import DataCollectorService


def _create_test_service(**kwargs) -> DataCollectorService:
    """Create a DataCollectorService instance with default test parameters."""
    defaults = {
        "feedback_dir": Path("/tmp/feedback"),
        "transcripts_dir": Path("/tmp/transcripts"),
        "collection_interval": 60,
        "ingress_server_url": "http://test-server.com",
        "ingress_server_auth_token": "test-token",
        "ingress_content_service_name": "test-service",
        "connection_timeout": 30,
        "cleanup_after_send": True,
    }
    defaults.update(kwargs)
    return DataCollectorService(**defaults)


def test_data_collector_service_creation() -> None:
    """Test that DataCollectorService can be created."""
    service = _create_test_service()
    assert service is not None
    assert service.feedback_dir == Path("/tmp/feedback")
    assert service.transcripts_dir == Path("/tmp/transcripts")
    assert service.collection_interval == 60


@patch("services.data_collector.time.sleep")
def test_run_normal_operation(mock_sleep) -> None:
    """Test normal operation of the run method."""
    service = _create_test_service()

    with patch.object(service, "_perform_collection") as mock_perform:
        mock_perform.side_effect = [None, KeyboardInterrupt()]

        service.run()

        assert mock_perform.call_count == 2
        mock_sleep.assert_called_once_with(60)


@patch("services.data_collector.time.sleep")
def test_run_with_exception(mock_sleep) -> None:
    """Test run method with exception handling."""
    service = _create_test_service()

    with patch.object(service, "_perform_collection") as mock_perform:
        mock_perform.side_effect = [OSError("Test error"), KeyboardInterrupt()]

        service.run()

        assert mock_perform.call_count == 2
        mock_sleep.assert_called_once_with(
            300
        )  # constants.DATA_COLLECTOR_RETRY_INTERVAL


def test_collect_feedback_files_directory_not_exists() -> None:
    """Test collecting feedback files when directory doesn't exist."""
    service = _create_test_service(feedback_dir=Path("/nonexistent/feedback"))

    result = service._collect_feedback_files()
    assert result == []


def test_collect_feedback_files_success() -> None:
    """Test collecting feedback files successfully."""
    service = _create_test_service()
    mock_files = [Path("/tmp/feedback/file1.json"), Path("/tmp/feedback/file2.json")]

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.glob", return_value=mock_files) as mock_glob,  # noqa: F841
    ):

        result = service._collect_feedback_files()
        assert result == mock_files


def test_collect_transcript_files_directory_not_exists() -> None:
    """Test collecting transcript files when directory doesn't exist."""
    service = _create_test_service(transcripts_dir=Path("/nonexistent/transcripts"))

    result = service._collect_transcript_files()
    assert result == []


def test_collect_transcript_files_success() -> None:
    """Test collecting transcript files successfully."""
    service = _create_test_service()
    mock_files = [Path("/tmp/transcripts/user1/conv1/file1.json")]

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch(
            "pathlib.Path.rglob", return_value=mock_files
        ) as mock_rglob,  # noqa: F841
    ):

        result = service._collect_transcript_files()
        assert result == mock_files


def test_perform_collection_no_files() -> None:
    """Test perform collection when no files are found."""
    service = _create_test_service()

    with (
        patch.object(service, "_collect_feedback_files", return_value=[]),
        patch.object(service, "_collect_transcript_files", return_value=[]),
    ):

        # Should not raise any exceptions and should return early
        service._perform_collection()


def test_perform_collection_with_files() -> None:
    """Test perform collection with files."""
    service = _create_test_service()
    feedback_files = [Path("/tmp/feedback/file1.json")]
    transcript_files = [Path("/tmp/transcripts/user1/conv1/file1.json")]

    with (
        patch.object(service, "_collect_feedback_files", return_value=feedback_files),
        patch.object(
            service, "_collect_transcript_files", return_value=transcript_files
        ),
        patch.object(
            service, "_create_and_send_tarball", return_value=1
        ) as mock_create_send,
    ):

        service._perform_collection()

        # Should be called once for feedback and once for transcripts
        assert mock_create_send.call_count == 2
        mock_create_send.assert_any_call(
            feedback_files, "feedback", service.feedback_dir
        )
        mock_create_send.assert_any_call(
            transcript_files, "transcripts", service.transcripts_dir
        )


def test_perform_collection_with_exception() -> None:
    """Test perform collection with exception."""
    service = _create_test_service()
    feedback_files = [Path("/tmp/feedback/file1.json")]

    with (
        patch.object(service, "_collect_feedback_files", return_value=feedback_files),
        patch.object(service, "_collect_transcript_files", return_value=[]),
        patch.object(
            service, "_create_and_send_tarball", side_effect=OSError("Test error")
        ),
    ):

        # Should re-raise the exception
        try:
            service._perform_collection()
            assert False, "Expected OSError to be raised"
        except OSError as e:
            assert str(e) == "Test error"


def test_create_and_send_tarball_no_files() -> None:
    """Test create and send tarball with no files."""
    service = _create_test_service()

    result = service._create_and_send_tarball([], "feedback", service.feedback_dir)
    assert result == 0


def test_create_and_send_tarball_success() -> None:
    """Test create and send tarball successfully."""
    service = _create_test_service()
    files = [Path("/tmp/feedback/file1.json")]

    with (
        patch.object(
            service, "_create_tarball", return_value=Path("/tmp/test.tar.gz")
        ) as mock_create,
        patch.object(service, "_send_tarball") as mock_send,
        patch.object(service, "_cleanup_files") as mock_cleanup_files,
        patch.object(service, "_cleanup_empty_directories") as mock_cleanup_dirs,
        patch.object(service, "_cleanup_tarball") as mock_cleanup_tarball,
    ):

        result = service._create_and_send_tarball(
            files, "feedback", service.feedback_dir
        )

        assert result == 1
        mock_create.assert_called_once_with(files, "feedback", service.feedback_dir)
        mock_send.assert_called_once_with(Path("/tmp/test.tar.gz"))
        mock_cleanup_files.assert_called_once_with(files)
        mock_cleanup_dirs.assert_called_once()
        mock_cleanup_tarball.assert_called_once_with(Path("/tmp/test.tar.gz"))


def test_create_and_send_tarball_no_cleanup() -> None:
    """Test create and send tarball without cleanup."""
    service = _create_test_service(cleanup_after_send=False)
    files = [Path("/tmp/feedback/file1.json")]

    with (
        patch.object(
            service, "_create_tarball", return_value=Path("/tmp/test.tar.gz")
        ) as mock_create,
        patch.object(service, "_send_tarball") as mock_send,
        patch.object(service, "_cleanup_files") as mock_cleanup_files,
        patch.object(service, "_cleanup_empty_directories") as mock_cleanup_dirs,
        patch.object(service, "_cleanup_tarball") as mock_cleanup_tarball,
    ):

        result = service._create_and_send_tarball(
            files, "feedback", service.feedback_dir
        )

        assert result == 1
        mock_create.assert_called_once_with(files, "feedback", service.feedback_dir)
        mock_send.assert_called_once_with(Path("/tmp/test.tar.gz"))
        # Cleanup should not be called when cleanup_after_send is False
        mock_cleanup_files.assert_not_called()
        mock_cleanup_dirs.assert_not_called()
        # But tarball cleanup should still happen
        mock_cleanup_tarball.assert_called_once_with(Path("/tmp/test.tar.gz"))


@patch("services.data_collector.tarfile.open")
@patch("services.data_collector.tempfile.gettempdir", return_value="/tmp")
@patch("services.data_collector.datetime")
def test_create_tarball_success(
    mock_datetime, mock_gettempdir, mock_tarfile_open
) -> None:
    """Test creating tarball successfully."""
    service = _create_test_service()
    files = [Path("/tmp/feedback/file1.json")]

    # Mock datetime to return predictable timestamp
    mock_datetime.now.return_value.strftime.return_value = "20231201_120000"

    # Mock tarfile
    mock_tar = MagicMock()
    mock_tarfile_open.return_value.__enter__.return_value = mock_tar

    # Mock Path.stat() for the created tarball
    with patch.object(Path, "stat") as mock_stat:
        mock_stat.return_value.st_size = 1024

        result = service._create_tarball(files, "feedback", service.feedback_dir)

        expected_path = Path("/tmp/feedback_20231201_120000.tar.gz")
        assert result == expected_path
        mock_tarfile_open.assert_called_once_with(expected_path, "w:gz")
        mock_tar.add.assert_called_once()


@patch("services.data_collector.tarfile.open")
def test_create_tarball_file_add_error(mock_tarfile_open) -> None:
    """Test creating tarball with file add error."""
    service = _create_test_service()
    files = [Path("/tmp/feedback/file1.json")]

    # Mock tarfile to raise error on add
    mock_tar = MagicMock()
    mock_tar.add.side_effect = OSError("Permission denied")
    mock_tarfile_open.return_value.__enter__.return_value = mock_tar

    with patch.object(Path, "stat") as mock_stat:
        mock_stat.return_value.st_size = 1024

        # Should not raise exception, just log warning
        result = service._create_tarball(files, "feedback", service.feedback_dir)
        assert isinstance(result, Path)


@patch("services.data_collector.requests.post")
def test_send_tarball_success(mock_post) -> None:
    """Test sending tarball successfully."""
    service = _create_test_service()
    tarball_path = Path("/tmp/test.tar.gz")

    # Mock successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    with patch("builtins.open", mock_data=b"test data") as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = b"test data"

        service._send_tarball(tarball_path)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["data"] == b"test data"
        assert "Authorization" in call_args[1]["headers"]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-token"


@patch("services.data_collector.requests.post")
def test_send_tarball_no_auth_token(mock_post) -> None:
    """Test sending tarball without auth token."""
    service = _create_test_service(ingress_server_auth_token="")
    tarball_path = Path("/tmp/test.tar.gz")

    # Mock successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    with patch("builtins.open", mock_data=b"test data") as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = b"test data"

        service._send_tarball(tarball_path)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "Authorization" not in call_args[1]["headers"]


@patch("services.data_collector.requests.post")
def test_send_tarball_http_error(mock_post) -> None:
    """Test sending tarball with HTTP error."""
    service = _create_test_service()
    tarball_path = Path("/tmp/test.tar.gz")

    # Mock error response
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response

    with patch("builtins.open", mock_data=b"test data") as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = b"test data"

        try:
            service._send_tarball(tarball_path)
            assert False, "Expected HTTPError to be raised"
        except requests.HTTPError as e:
            assert "500" in str(e)


def test_send_tarball_missing_url() -> None:
    """Test sending tarball with missing URL."""
    service = _create_test_service(ingress_server_url="")
    tarball_path = Path("/tmp/test.tar.gz")

    with patch("builtins.open", mock_data=b"test data") as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = b"test data"

        # This should raise an exception when requests.post is called with empty URL
        try:
            service._send_tarball(tarball_path)
        except Exception:
            pass  # Expected to fail with empty URL


def test_perform_collection_with_specific_exceptions() -> None:
    """Test perform collection with specific exception types."""
    service = _create_test_service()
    feedback_files = [Path("/tmp/feedback/file1.json")]

    # Test with requests.RequestException
    with (
        patch.object(service, "_collect_feedback_files", return_value=feedback_files),
        patch.object(service, "_collect_transcript_files", return_value=[]),
        patch.object(
            service,
            "_create_and_send_tarball",
            side_effect=requests.RequestException("Network error"),
        ),
    ):

        try:
            service._perform_collection()
            assert False, "Expected RequestException to be raised"
        except requests.RequestException:
            pass

    # Test with tarfile.TarError
    with (
        patch.object(service, "_collect_feedback_files", return_value=feedback_files),
        patch.object(service, "_collect_transcript_files", return_value=[]),
        patch.object(
            service,
            "_create_and_send_tarball",
            side_effect=tarfile.TarError("Tar error"),
        ),
    ):

        try:
            service._perform_collection()
            assert False, "Expected TarError to be raised"
        except tarfile.TarError:
            pass


def test_cleanup_files_success() -> None:
    """Test cleaning up files successfully."""
    service = _create_test_service()
    files = [Path("/tmp/file1.json"), Path("/tmp/file2.json")]

    with patch.object(Path, "unlink") as mock_unlink:
        service._cleanup_files(files)

        assert mock_unlink.call_count == 2


def test_cleanup_files_with_error() -> None:
    """Test cleaning up files with error."""
    service = _create_test_service()
    files = [Path("/tmp/file1.json")]

    with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
        # Should not raise exception, just log warning
        service._cleanup_files(files)


def test_cleanup_tarball_success() -> None:
    """Test cleaning up tarball successfully."""
    service = _create_test_service()
    tarball_path = Path("/tmp/test.tar.gz")

    with patch.object(Path, "unlink") as mock_unlink:
        service._cleanup_tarball(tarball_path)
        mock_unlink.assert_called_once()


def test_cleanup_tarball_with_error() -> None:
    """Test cleaning up tarball with error."""
    service = _create_test_service()
    tarball_path = Path("/tmp/test.tar.gz")

    with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
        # Should not raise exception, just log warning
        service._cleanup_tarball(tarball_path)


def test_cleanup_empty_directories_directory_not_exists() -> None:
    """Test cleanup empty directories when directory doesn't exist."""
    service = _create_test_service(transcripts_dir=Path("/nonexistent"))

    # Should not raise exception
    service._cleanup_empty_directories()


def test_cleanup_empty_directories_success() -> None:
    """Test cleaning up empty directories successfully."""
    service = _create_test_service()

    # Mock directory structure
    mock_user_dir = MagicMock()
    mock_conv_dir = MagicMock()
    mock_conv_dir.is_dir.return_value = True
    mock_conv_dir.iterdir.return_value = []  # Empty directory
    mock_user_dir.is_dir.return_value = True
    mock_user_dir.iterdir.return_value = [mock_conv_dir]

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.iterdir", return_value=[mock_user_dir]),
    ):

        # After removing conv_dir, user_dir should be empty
        mock_user_dir.iterdir.side_effect = [
            [mock_conv_dir],
            [],
        ]  # First call returns conv_dir, second call empty

        service._cleanup_empty_directories()

        mock_conv_dir.rmdir.assert_called_once()
        mock_user_dir.rmdir.assert_called_once()


def test_cleanup_empty_directories_with_errors() -> None:
    """Test cleaning up empty directories with errors."""
    service = _create_test_service()

    # Mock directory structure
    mock_user_dir = MagicMock()
    mock_conv_dir = MagicMock()
    mock_conv_dir.is_dir.return_value = True
    mock_conv_dir.iterdir.return_value = []  # Empty directory
    mock_conv_dir.rmdir.side_effect = OSError("Permission denied")
    mock_user_dir.is_dir.return_value = True
    mock_user_dir.iterdir.return_value = [mock_conv_dir]

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.iterdir", return_value=[mock_user_dir]),
    ):

        # Should not raise exception even with rmdir errors
        service._cleanup_empty_directories()


def test_perform_collection_with_transcript_files() -> None:
    """Test perform collection with only transcript files."""
    service = _create_test_service()
    transcript_files = [Path("/tmp/transcripts/user1/conv1/file1.json")]

    with (
        patch.object(service, "_collect_feedback_files", return_value=[]),
        patch.object(
            service, "_collect_transcript_files", return_value=transcript_files
        ),
        patch.object(
            service, "_create_and_send_tarball", return_value=1
        ) as mock_create_send,
    ):

        service._perform_collection()

        # Should be called once for transcripts only
        mock_create_send.assert_called_once_with(
            transcript_files, "transcripts", service.transcripts_dir
        )
