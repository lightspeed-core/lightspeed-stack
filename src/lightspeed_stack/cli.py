"""Entry point to the Lightspeed Core Stack REST API service.

This source file contains entry point to the service. It is implemented in the
main() function.
"""

import os
from argparse import ArgumentParser

from lightspeed_stack import constants
from lightspeed_stack.configuration import configuration
from lightspeed_stack.constants import LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR
from lightspeed_stack.llama_stack_configuration import migrate_config_dumb
from lightspeed_stack.log import get_logger, setup_logging
from lightspeed_stack.runners.quota_scheduler import start_quota_scheduler
from lightspeed_stack.runners.uvicorn import start_uvicorn
from lightspeed_stack.utils import config_dumper, models_dumper

setup_logging()
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
        "-m",
        "--dump-models",
        dest="dump_models",
        help="dump schemas for all models into OpenAPI-compatible file and quit",
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
        "--synthesized-config-output",
        dest="synthesized_config_output",
        help="path where the synthesized Llama Stack run.yaml is written in "
        "unified library mode (overwritten each boot, mode 0600; default: "
        f"{constants.DEFAULT_SYNTHESIZED_CONFIG_PATH})",
        default=None,
    )
    parser.add_argument(
        "--migrate-config",
        dest="migrate_config",
        help="migrate a legacy two-file config to a unified single file and "
        "exit. Lifts the run.yaml given by --run-yaml into the "
        "llama_stack.config.native_override of the -c lightspeed-stack.yaml "
        "and writes the result to --migrate-output. Replace literal secrets "
        "with ${env.VAR} references before or after migrating.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--run-yaml",
        dest="run_yaml",
        help="path to the legacy Llama Stack run.yaml to migrate "
        "(used with --migrate-config)",
        default=None,
    )
    parser.add_argument(
        "--migrate-output",
        dest="migrate_output",
        help="path to write the unified lightspeed-stack.yaml "
        "(used with --migrate-config)",
        default=None,
    )

    return parser


# pylint: disable=too-many-branches, too-many-statements
def main() -> None:
    """Entry point to the web service.

    Start the Lightspeed Core Stack service process based on CLI flags and configuration.

    Parses command-line arguments, loads the configured settings, and then:
    - If --verbose is provided, sets application loggers to DEBUG level.
    - If --dump-configuration is provided, writes the active configuration to
      configuration.json and exits (exits with status 1 on failure).
    - If --dump-schema is provided, writes the active configuration schema to
      schema.json and exits (exits with status 1 on failure).
    - If --migrate-config is provided, migrates the legacy two-file config
      (--run-yaml plus the -c lightspeed-stack.yaml) into a unified single
      file at --migrate-output and exits (status 1 on failure or missing
      flags).
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
        setup_logging()

    # --migrate-config converts a legacy two-file config to a unified single
    # file and exits. It reads the legacy files raw (the -c config still uses
    # the legacy library_client_config_path shape), so it must run before
    # load_configuration, which would validate against the current schema.
    if args.migrate_config:
        if args.run_yaml is None or args.migrate_output is None:
            logger.error("--migrate-config requires --run-yaml and --migrate-output")
            raise SystemExit(1)
        try:
            migrate_config_dumb(args.run_yaml, args.config_file, args.migrate_output)
            logger.info(
                "Migrated unified configuration written to %s", args.migrate_output
            )
        except Exception as e:
            logger.error("Failed to migrate configuration: %s", e)
            raise SystemExit(1) from e
        return

    configuration.load_configuration(args.config_file)
    logger.info("Configuration: %s", configuration.configuration)
    logger.info(
        "Llama stack configuration: %s", configuration.llama_stack_configuration
    )

    # Deprecation schedule (Decision S2): the legacy two-file path keeps
    # working through 0.6 with this single startup WARN and is removed in 0.7.
    if configuration.llama_stack_configuration.library_client_config_path is not None:
        logger.warning(
            "DEPRECATED: the two-file configuration "
            "(llama_stack.library_client_config_path + external run.yaml) is "
            "deprecated and will be removed in release 0.7. Migrate to the "
            "unified lightspeed-stack.yaml: https://lightspeed-core.github.io"
            "/lightspeed-stack/design/llama-stack-config-merge"
            "/llama-stack-config-merge.html#migration--backwards-compatibility"
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
            config_dumper.dump_schema("schema.json")
            logger.info("Configuration schema dumped to schema.json")
        except Exception as e:
            logger.error("Failed to dump configuration schema: %s", e)
            raise SystemExit(1) from e
        return

    # -m or --dump-models CLI flags are used to dump schema for all models
    # into a JSON file that is compatible with OpenAPI schema specification
    if args.dump_models:
        try:
            models_dumper.dump_models("models.json")
            logger.info("Schema for all models dumped to models.json")
        except Exception as e:
            logger.error("Failed to dump schema for models: %s", e)
            raise SystemExit(1) from e
        return

    # Store config path in env so each uvicorn worker can load it
    # (step is needed because process context isn't shared).
    os.environ[constants.CONFIG_PATH_ENV_VAR] = args.config_file

    # Propagate the synthesized-config-output override to the workers (separate
    # processes), which perform unified-mode library synthesis. When the flag is
    # omitted, clear any inherited value so the workers fall back to
    # constants.DEFAULT_SYNTHESIZED_CONFIG_PATH rather than a stale path.
    if args.synthesized_config_output is not None:
        os.environ[constants.SYNTHESIZED_CONFIG_PATH_ENV_VAR] = (
            args.synthesized_config_output
        )
    else:
        os.environ.pop(constants.SYNTHESIZED_CONFIG_PATH_ENV_VAR, None)

    # start the runners
    start_quota_scheduler(configuration.configuration)
    # if every previous steps don't fail, start the service on specified port
    start_uvicorn(configuration.service_configuration)
    logger.info("Lightspeed Core Stack finished")


if __name__ == "__main__":
    main()
