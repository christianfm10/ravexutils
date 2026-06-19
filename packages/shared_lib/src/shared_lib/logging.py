import logging
import os
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
from rich.text import Text

TRACE_LEVEL = 15

LOG_LEVELS = {
    "TRACE": TRACE_LEVEL,
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class ForceRichHandler(RichHandler):
    """
    Este Handler intercepta el registro ANTES de que Python
    lo convierta en un string plano.
    """

    def emit(self, record):
        # Si el mensaje ya es un objeto Text, saltamos el formateo de Python
        if isinstance(record.msg, Text):
            message = record.msg
        else:
            # Si es un string normal, usamos el comportamiento estándar
            message = self.format(record)

        # Enviamos directamente a la consola de Rich
        self.console.print(message)


def setup_logging(
    log_file: bool = False, log_name: str = "temp.log", markup: bool = False
):
    handlers: list = [RichHandler(markup=markup, show_path=True)]
    log_file = log_file or os.getenv("LOG_FILE", "False").lower() == "true"
    if log_file:
        rotating_handler = RotatingFileHandler(
            log_name, maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(filename)s - %(message)s", datefmt="%H:%M:%S"
        )
        rotating_handler.setFormatter(formatter)
        rotating_handler.setLevel(logging.WARNING)
        handlers.append(rotating_handler)
    logging.addLevelName(TRACE_LEVEL, "TRACE")
    logging.getLogger("nodriver").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    level = LOG_LEVELS.get(
        os.getenv("LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )
    logging.basicConfig(
        level=level,
        format="%(message)s",
        # datefmt="[%Y-%m-%d %H:%M:%S.%f]",
        datefmt="[%Y-%m-%d %H:%M:%S]",
        # format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
