"""Lightspeed stack.

This source file contains entry point to the service. It is implemented in the
main() function.
"""

from argparse import ArgumentParser
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from rich.logging import RichHandler


from runners.uvicorn import start_uvicorn
from configuration import configuration
from client import AsyncLlamaStackClientHolder
from utils import suid
import version

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

logger = logging.getLogger(__name__)


def store_config(cfg_file: str) -> None:
    """Store service configuration in the local filesystem.

    This function stores the original configuration file content once at startup.
    Since the configuration is immutable for a single service deployment,
    this avoids duplicating the same config data in every transcript/feedback.

    Args:
        cfg_file: Path to the original configuration file.
    """
    with open(cfg_file, "r", encoding="utf-8") as f:
        config_content = f.read()

    data_to_store = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service_version": version.__version__,
            "config_file_path": cfg_file,
        },
        "configuration": config_content,
    }

    # Store the data in the local filesystem
    config_storage = configuration.user_data_collection_configuration.config_storage
    if config_storage is None:
        raise ValueError("config_storage must be set when config collection is enabled")
    storage_path = Path(config_storage)
    storage_path.mkdir(parents=True, exist_ok=True)
    config_file_path = storage_path / f"{suid.get_suid()}.json"

    with open(config_file_path, "w", encoding="utf-8") as config_file:
        json.dump(data_to_store, config_file, indent=2)

    logger.info("Service configuration stored in '%s'", config_file_path)


def create_argument_parser() -> ArgumentParser:
    """Create and configure argument parser object."""
    parser = ArgumentParser()
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        help="make it verbose",
        action="store_true",
        default=None,
    )
    parser.add_argument(
        "-d",
        "--dump-configuration",
        dest="dump_configuration",
        help="dump actual configuration into JSON file and quit",
        action="store_true",
        default=None,
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config_file",
        help="path to configuration file (default: lightspeed-stack.yaml)",
        default="lightspeed-stack.yaml",
    )

    return parser


def main() -> None:
    """Entry point to the web service."""
    logger.info("Lightspeed stack startup")
    parser = create_argument_parser()
    args = parser.parse_args()

    configuration.load_configuration(args.config_file)
    logger.info("Configuration: %s", configuration.configuration)
    logger.info(
        "Llama stack configuration: %s", configuration.llama_stack_configuration
    )

    # store service configuration if enabled
    if configuration.user_data_collection_configuration.config_enabled:
        store_config(args.config_file)
    else:
        logger.debug("Config collection is disabled in configuration")

    logger.info("Creating AsyncLlamaStackClient")
    asyncio.run(
        AsyncLlamaStackClientHolder().load(configuration.configuration.llama_stack)
    )

    if args.dump_configuration:
        configuration.configuration.dump()
    else:
        start_uvicorn(configuration.service_configuration)
    logger.info("Lightspeed stack finished")


if __name__ == "__main__":
    main()
