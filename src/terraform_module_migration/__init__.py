import logging
from typing import Optional

LOG_FORMAT = "%(asctime)s.%(msecs)05d [%(levelname)-5s] - %(message)s"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    if name is None:
        name = __name__

    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

    handler = logging.StreamHandler()
    formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
