"""Entry point to the Lightspeed Core Stack REST API service.

This source file contains entry point to the service. It is implemented in the
main() function.
"""

from argparse import ArgumentParser
import asyncio
import logging
import os
from rich.logging import RichHandler

from runners.uvicorn import start_uvicorn, start_diagnostic_uvicorn
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

    return parser


def main() -> None:
    """Entry point to the web service."""
    logger.info("Lightspeed Core Stack startup")
    parser = create_argument_parser()
    args = parser.parse_args()

    # Import app_state from dedicated state module (no circular dependency)
    from app.state import app_state

    try:
        # Step 1: Load configuration
        configuration.load_configuration(args.config_file)
        app_state.mark_check_complete('configuration_loaded', True)
        logger.info("Configuration: %s", configuration.configuration)
        logger.info(
            "Llama stack configuration: %s", configuration.llama_stack_configuration
        )

        # Step 2: Validate configuration (successful parsing indicates validity)
        app_state.mark_check_complete('configuration_valid', True)

    except Exception as e:
        # Configuration loading or validation failed
        error_msg = f"Configuration loading failed: {str(e)}"
        logger.error(error_msg)
        if not configuration.is_loaded():
            app_state.mark_check_complete('configuration_loaded', False, str(e))
        else:
            app_state.mark_check_complete('configuration_valid', False, str(e))
        
        # Start minimal server for diagnostics but don't complete initialization
        logger.warning("Starting server with minimal configuration for health reporting")
        try:
            from models.config import ServiceConfiguration
            diagnostic_port = int(os.getenv("DIAGNOSTIC_PORT", "8090"))
            start_diagnostic_uvicorn(ServiceConfiguration(host="0.0.0.0", port=diagnostic_port))
        except Exception as uvicorn_error:
            logger.error("Failed to start diagnostic server: %s", uvicorn_error)
            raise SystemExit(1) from uvicorn_error
        return

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

    try:
        # Step 3: Initialize Llama Stack Client
        logger.info("Creating AsyncLlamaStackClient")
        asyncio.run(
            AsyncLlamaStackClientHolder().load(configuration.configuration.llama_stack)
        )
        client = AsyncLlamaStackClientHolder().get_client()

        # check if the Llama Stack version is supported by the service
        asyncio.run(check_llama_stack_version(client))
        app_state.mark_check_complete('llama_client_initialized', True)

    except Exception as e:
        error_msg = f"Llama Stack client initialization failed: {str(e)}"
        logger.error(error_msg)
        app_state.mark_check_complete('llama_client_initialized', False, str(e))
        
        # Start minimal server for diagnostics
        logger.warning("Starting server with minimal configuration for health reporting")
        try:
            from models.config import ServiceConfiguration
            diagnostic_port = int(os.getenv("DIAGNOSTIC_PORT", "8090"))
            start_diagnostic_uvicorn(ServiceConfiguration(host="0.0.0.0", port=diagnostic_port))
        except Exception as uvicorn_error:
            logger.error("Failed to start diagnostic server: %s", uvicorn_error)
            raise SystemExit(1) from uvicorn_error
        return

    # Step 4: MCP servers (placeholder - mark as complete for now)
    # TODO: Add actual MCP server registration when implemented
    app_state.mark_check_complete('mcp_servers_registered', True)

    # Mark initialization as complete
    app_state.mark_initialization_complete()

    # Start the service with full configuration
    start_uvicorn(configuration.service_configuration)
    logger.info("Lightspeed Core Stack finished")


if __name__ == "__main__":
    main()
