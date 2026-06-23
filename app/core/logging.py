import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    fmt = "%(asctime)s  %(levelname)-7s  %(name)-32s  %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)
    for noisy in ("httpx", "httpcore", "sqlalchemy.engine", "openai", "anthropic"):
        logging.getLogger(noisy).setLevel("WARNING")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
