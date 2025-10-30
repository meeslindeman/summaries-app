import logging
import os

LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

def setup():
    logging.basicConfig(
        level=LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    return logging.getLogger("summ-app")
