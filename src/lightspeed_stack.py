"""Entry point to the Lightspeed Core Stack REST API service.

This source file contains entry point to the service. It is implemented in the
main() function.
"""

import logging
import os
import sys
from argparse import ArgumentParser

from log import get_logger, resolve_log_level, create_log_handler
from configuration import configuration
from runners.uvicorn import start_uvicorn
from runners.quota_scheduler import start_quota_scheduler
from utils import schema_dumper
from constants import LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR

# Resolve log level and handler from centralized logging utilities
log_level = resolve_log_level()

# Configure root logger. basicConfig(force=True) is intentionally root-logger-specific.
# RichHandler needs format="%(message)s" to prevent double-formatting by the root Formatter.
handler = create_log_handler()
if sys.stderr.isatty():
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
        force=True,
    )
else:
    logging.basicConfig(
        level=log_level,
        handlers=[handler],
        force=True,
    )

logger = get_logger(__name__)


def create_argument_parser() -> ArgumentParser:
    """Create and configure argument parser object.

    The parser includes these options:
    - -v / --verbose: enable verbose output
    - -d / --dump-configuration: dump the loaded configuration to JSON and exit
    - -s / --dump-schema: dump the configuration schema to OpenAPI JSON and exit
    - -c / --config: path to the configuration file (default "lightspeed-stack.yaml")
    - -g / --generate-llama-stack-configuration: generate a Llama Stack
                                                 configuration from the service configuration
    - -i / --input-config-file: Llama Stack input configuration filename (default "run.yaml")
    - -o / --output-config-file: Llama Stack output configuration filename (default "run_.yaml")

    Returns:
        Configured ArgumentParser for parsing the service CLI options.
    """
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
        "-s",
        "--dump-schema",
        dest="dump_schema",
        help="dump configuration schema into OpenAPI-compatible file and quit",
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
    """Entry point to the web service.

    Start the Lightspeed Core Stack service process based on CLI flags and configuration.

    Parses command-line arguments, loads the configured settings, and then:
    - If --verbose is provided, sets application loggers to DEBUG level.
    - If --dump-configuration is provided, writes the active configuration to
      configuration.json and exits (exits with status 1 on failure).
    - If --dump-schema is provided, writes the active configuration schema to
      schema.json and exits (exits with status 1 on failure).
    - If --generate-llama-stack-configuration is provided, generates and stores
      the Llama Stack configuration to the specified output file and exits
      (exits with status 1 on failure).
    - Otherwise, sets LIGHTSPEED_STACK_CONFIG_PATH for worker processes, starts
      the quota scheduler, and starts the Uvicorn web service.

    Raises:
        SystemExit: when configuration dumping or Llama Stack generation fails
                    (exits with status 1).
    """
    logger.info("Lightspeed Core Stack startup")
    parser = create_argument_parser()
    args = parser.parse_args()

    if args.verbose:
        os.environ[LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR] = "DEBUG"
        logging.getLogger().setLevel(logging.DEBUG)
        for logger_name in logging.Logger.manager.loggerDict:
            existing_logger = logging.getLogger(logger_name)
            if isinstance(existing_logger, logging.Logger):
                existing_logger.setLevel(logging.DEBUG)

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

    # -s or --dump-schema CLI flags are used to dump configuration schema
    # into a JSON file that is compatible with OpenAPI schema specification
    if args.dump_schema:
        try:
            schema_dumper.dump_schema("schema.json")
            logger.info("Configuration schema dumped to schema.json")
        except Exception as e:
            logger.error("Failed to dump configuration schema: %s", e)
            raise SystemExit(1) from e
        return

    # Store config path in env so each uvicorn worker can load it
    # (step is needed because process context isn't shared).
    os.environ["LIGHTSPEED_STACK_CONFIG_PATH"] = args.config_file

    # start the runners
    start_quota_scheduler(configuration.configuration)
    # if every previous steps don't fail, start the service on specified port
    start_uvicorn(configuration.service_configuration)
    logger.info("Lightspeed Core Stack finished")


if __name__ == "__main__":
    main()
