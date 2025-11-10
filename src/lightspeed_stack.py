"""Entry point to the Lightspeed Core Stack REST API service.

This source file contains entry point to the service. It is implemented in the
main() function.
"""

import logging
import os
from argparse import ArgumentParser

from rich.logging import RichHandler

from log import get_logger
from configuration import configuration
from authorization.azure_token_manager import AzureEntraIDTokenManager
from llama_stack_configuration import generate_configuration
from runners.uvicorn import start_uvicorn
from runners.quota_scheduler import start_quota_scheduler

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

logger = get_logger(__name__)


def create_argument_parser() -> ArgumentParser:
    """Create and configure argument parser object."""
    parser = ArgumentParser()
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        help="make it verbose",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-d",
        "--dump-configuration",
        dest="dump_configuration",
        help="dump actual configuration into JSON file and quit",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config_file",
        help="path to configuration file (default: lightspeed-stack.yaml)",
        default="lightspeed-stack.yaml",
    )
    parser.add_argument(
        "-g",
        "--generate-llama-stack-configuration",
        dest="generate_llama_stack_configuration",
        help="generate Llama Stack configuration based on LCORE configuration",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-i",
        "--input-config-file",
        dest="input_config_file",
        help="Llama Stack input configuration file",
        default="run.yaml",
    )
    parser.add_argument(
        "-o",
        "--output-config-file",
        dest="output_config_file",
        help="Llama Stack output configuration file",
        default="run_.yaml",
    )

    return parser


def main() -> None:
    """Entry point to the web service."""
    logger.info("Lightspeed Core Stack startup")
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

    # -g or --generate-llama-stack-configuration CLI flags are used to (re)generate
    # configuration for Llama Stack
    if args.generate_llama_stack_configuration:
        try:
            generate_configuration(
                args.input_config_file,
                args.output_config_file,
                configuration.configuration,
            )
            logger.info(
                "Llama Stack configuration generated and stored into %s",
                args.output_config_file,
            )
        except Exception as e:
            logger.error("Failed to generate Llama Stack configuration: %s", e)
            raise SystemExit(1) from e
        return

    # Store config path in env so each uvicorn worker can load it
    # (step is needed because process context isn’t shared).
    os.environ["LIGHTSPEED_STACK_CONFIG_PATH"] = args.config_file

    # start the runners
    start_quota_scheduler(configuration.configuration)
    if configuration.azure_entra_id:
        AzureEntraIDTokenManager().set_config(configuration.azure_entra_id)
    # if every previous steps don't fail, start the service on specified port
    start_uvicorn(configuration.service_configuration)
    logger.info("Lightspeed Core Stack finished")


if __name__ == "__main__":
    main()
