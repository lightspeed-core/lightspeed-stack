"""Data archival service for packaging and sending feedback and transcripts."""

import asyncio
import logging
import tarfile
import tempfile
from datetime import datetime, UTC
from pathlib import Path
from typing import List, Optional

import requests

from configuration import configuration

logger = logging.getLogger(__name__)


class DataCollectorService:
    """Service for collecting and sending user data to ingress server."""

    def __init__(self):
        """Initialize the data collection service."""
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the periodic data collection task."""
        if self._is_running:
            logger.warning("Data collection service is already running")
            return

        collector_config = configuration.user_data_collection_configuration.data_collector

        if not collector_config.enabled:
            logger.info("Data collection is disabled")
            return

        logger.info("Starting data collection service")
        self._is_running = True
        self._task = asyncio.create_task(self._collection_loop())

    async def stop(self) -> None:
        """Stop the periodic collection task."""
        if not self._is_running:
            return

        logger.info("Stopping data collection service")
        self._is_running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _collection_loop(self) -> None:
        """Main loop for periodic collection."""
        collector_config = configuration.user_data_collection_configuration.data_collector

        while self._is_running:
            try:
                await self._perform_collection()
                logger.info(f"Next collection scheduled in {collector_config.collection_interval} seconds")
                await asyncio.sleep(collector_config.collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during collection process: {e}", exc_info=True)
                await asyncio.sleep(300) # Wait 5 minutes before retrying on error


    async def _perform_collection(self) -> None:
        """Perform a single collection operation."""
        logger.info("Starting data collection process")

        # Collect files to archive
        feedback_files = self._collect_feedback_files()
        transcript_files = self._collect_transcript_files()

        if not feedback_files and not transcript_files:
            logger.info("No files to collect")
            return

        logger.info(f"Found {len(feedback_files)} feedback files and {len(transcript_files)} transcript files to collect")

        # Create and send archives
        collections_sent = 0
        try:
            if feedback_files:
                collections_sent += await self._create_and_send_tarball(feedback_files, "feedback")
            if transcript_files:
                collections_sent += await self._create_and_send_tarball(transcript_files, "transcripts")

            logger.info(f"Successfully sent {collections_sent} collections to ingress server")
        except Exception as e:
            logger.error(f"Failed to create or send collections: {e}", exc_info=True)
            raise

    def _collect_feedback_files(self) -> List[Path]:
        """Collect all feedback files that need to be collected."""
        udc_config = configuration.user_data_collection_configuration

        if udc_config.feedback_disabled or not udc_config.feedback_storage:
            return []

        feedback_dir = Path(udc_config.feedback_storage)
        if not feedback_dir.exists():
            return []

        return list(feedback_dir.glob("*.json"))

    def _collect_transcript_files(self) -> List[Path]:
        """Collect all transcript files that need to be collected."""
        udc_config = configuration.user_data_collection_configuration

        if udc_config.transcripts_disabled or not udc_config.transcripts_storage:
            return []

        transcripts_dir = Path(udc_config.transcripts_storage)
        if not transcripts_dir.exists():
            return []

        # Recursively find all JSON files in the transcript directory structure
        return list(transcripts_dir.rglob("*.json"))

    async def _create_and_send_tarball(self, files: List[Path], data_type: str) -> int:
        """Create a single tarball from all files and send to ingress server."""
        if not files:
            return 0

        collector_config = configuration.user_data_collection_configuration.data_collector

        # Create one tarball with all files
        tarball_path = await self._create_tarball(files, data_type)
        try:
            await self._send_tarball(tarball_path)
            if collector_config.cleanup_after_send:
                await self._cleanup_files(files)
                self._cleanup_empty_directories()
            return 1
        finally:
            self._cleanup_tarball(tarball_path)

    async def _create_tarball(self, files: List[Path], data_type: str) -> Path:
        """Create a tarball containing the specified files."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        tarball_name = f"{data_type}_{timestamp}.tar.gz"

        # Create tarball in a temporary directory
        temp_dir = Path(tempfile.gettempdir())
        tarball_path = temp_dir / tarball_name

        logger.info(f"Creating tarball {tarball_path} with {len(files)} files")

        # Use asyncio to avoid blocking the event loop
        def _create_tar():
            with tarfile.open(tarball_path, "w:gz") as tar:
                for file_path in files:
                    try:
                        # Add file with relative path to maintain directory structure
                        arcname = str(file_path.relative_to(file_path.parents[-2]))
                        tar.add(file_path, arcname=arcname)
                    except Exception as e:
                        logger.warning(f"Failed to add {file_path} to tarball: {e}")

        await asyncio.get_event_loop().run_in_executor(None, _create_tar)
        
        logger.info(f"Created tarball {tarball_path} ({tarball_path.stat().st_size} bytes)")
        return tarball_path

    async def _send_tarball(self, tarball_path: Path) -> None:
        """Send the tarball to the ingress server."""
        collector_config = configuration.user_data_collection_configuration.data_collector

        headers = {
            "Content-Type": "application/gzip",
            "X-Archive-Timestamp": datetime.now(UTC).isoformat(),
            "X-Archive-Source": "lightspeed-stack",
        }

        if collector_config.ingress_server_auth_token:
            headers["Authorization"] = f"Bearer {collector_config.ingress_server_auth_token}"

        def _send_request():
            with open(tarball_path, "rb") as f:
                data = f.read()

            logger.info(f"Sending tarball {tarball_path.name} to {collector_config.ingress_server_url}")

            response = requests.post(
                collector_config.ingress_server_url,
                data=data,
                headers=headers,
                timeout=collector_config.connection_timeout_seconds,
            )

            if response.status_code >= 400:
                raise Exception(
                    f"Failed to send tarball to ingress server. "
                    f"Status: {response.status_code}, Response: {response.text}"
                )

            logger.info(f"Successfully sent tarball {tarball_path.name} to ingress server")

        await asyncio.get_event_loop().run_in_executor(None, _send_request)

    async def _cleanup_files(self, files: List[Path]) -> None:
        """Remove files after successful transmission."""
        for file_path in files:
            try:
                file_path.unlink()
                logger.debug(f"Removed file {file_path}")
            except OSError as e:
                logger.warning(f"Failed to remove file {file_path}: {e}")

    def _cleanup_empty_directories(self) -> None:
        """Remove empty directories from transcript storage."""
        udc_config = configuration.user_data_collection_configuration

        if udc_config.transcripts_disabled or not udc_config.transcripts_storage:
            return

        transcripts_dir = Path(udc_config.transcripts_storage)
        if not transcripts_dir.exists():
            return

        # Remove empty directories (conversation and user directories)
        for user_dir in transcripts_dir.iterdir():
            if user_dir.is_dir():
                for conv_dir in user_dir.iterdir():
                    if conv_dir.is_dir() and not any(conv_dir.iterdir()):
                        try:
                            conv_dir.rmdir()
                            logger.debug(f"Removed empty directory {conv_dir}")
                        except OSError:
                            pass

                # Remove user directory if empty
                if not any(user_dir.iterdir()):
                    try:
                        user_dir.rmdir()
                        logger.debug(f"Removed empty directory {user_dir}")
                    except OSError:
                        pass

    def _cleanup_tarball(self, tarball_path: Path) -> None:
        """Remove the temporary tarball file."""
        try:
            tarball_path.unlink()
            logger.debug(f"Removed temporary tarball {tarball_path}")
        except OSError as e:
            logger.warning(f"Failed to remove temporary tarball {tarball_path}: {e}")


# Global instance
data_collector_service = DataCollectorService()