"""Lightspeed stack."""

import logging
from runners.uvicorn import start_uvicorn
from configuration import configuration

from rich.logging import RichHandler

FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)  # set level=20 or logging.INFO to turn off debug
logger = logging.getLogger("rich")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Lightspeed stack startup")
    configuration.load_configuration("lightspeed-config.yaml")
    logger.info("Configuration: %s", configuration.configuration)
    logger.info(
        "Llama stack configuration: %s", configuration.configuration.llama_stack
    )
    start_uvicorn()
    logger.info("Lightspeed stack finished")
