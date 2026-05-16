import sys
from collections.abc import Generator

from dependency_injector import containers, providers
from loguru import logger


def _init_logging(level: str, colorize: bool, format: str) -> Generator:
    logger.remove()
    logger.add(sys.stdout, colorize=colorize, level=level.upper(), format=format)
    yield logger
    logger.remove()


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    logging = providers.Resource(
        _init_logging,
        level=config.logging.level,
        colorize=config.logging.colorize,
        format=config.logging.format,
    )
