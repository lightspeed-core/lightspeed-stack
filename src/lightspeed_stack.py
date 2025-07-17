"""Lightspeed stack.

This source file contains entry point to the service. It is implemented in the
main() function.
"""

from argparse import ArgumentParser
import asyncio
import logging
from rich.logging import RichHandler

from runners.uvicorn import start_uvicorn
from runners.data_collector import start_data_collector
from configuration import configuration
from client import LlamaStackClientHolder, AsyncLlamaStackClientHolder

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

logger = logging.getLogger(__name__)


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
    parser.add_argument(
        "--data-collector",
        dest="start_data_collector",
        help="start data collector service instead of web service",
        action="store_true",
        default=False,
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
    logger.info("Creating LlamaStackClient")
    LlamaStackClientHolder().load(configuration.configuration.llama_stack)
    logger.info("Creating AsyncLlamaStackClient")
    asyncio.run(
        AsyncLlamaStackClientHolder().load(configuration.configuration.llama_stack)
    )

    if args.dump_configuration:
        configuration.configuration.dump()
    elif args.start_data_collector:
        start_data_collector(
            configuration.user_data_collection_configuration.data_collector
        )
    else:
        start_uvicorn(configuration.service_configuration)
    logger.info("Lightspeed stack finished")


if __name__ == "__main__":
    main()
