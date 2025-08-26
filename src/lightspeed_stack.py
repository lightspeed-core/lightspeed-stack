"""Entry point to the Lightspeed Core Stack REST API service.

This source file contains entry point to the service. It is implemented in the
main() function.
"""

from argparse import ArgumentParser
import asyncio
import logging
from rich.logging import RichHandler

from runners.uvicorn import start_uvicorn
from configuration import configuration
from client import AsyncLlamaStackClientHolder
from utils.llama_stack_version import check_llama_stack_version

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

    # -d or --dump-configuration CLI flags are used to dump the actual configuration
    # to a JSON file w/o doing any other operation
    if args.dump_configuration:
        try:
            configuration.configuration.dump()
            logger.info("Configuration dumped to configuration.json")
        except Exception as e:
            logger.error("Failed to dump configuration: %s", e)
            raise SystemExit(1) from e
        return

    logger.info("Creating AsyncLlamaStackClient")
    asyncio.run(
        AsyncLlamaStackClientHolder().load(configuration.configuration.llama_stack)
    )
    client = AsyncLlamaStackClientHolder().get_client()

    # check if the Llama Stack version is supported by the service
    asyncio.run(check_llama_stack_version(client))

    start_uvicorn(configuration.service_configuration)
    logger.info("Lightspeed stack finished")


if __name__ == "__main__":
    main()
