import logging
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
from rich.text import Text


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
    handlers: list = [RichHandler(markup=markup)]
    if log_file:
        rotatating_handler = RotatingFileHandler(
            log_name, maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8"
        )
        rotatating_handler.setLevel(logging.WARNING)
        handlers.append(rotatating_handler)
    logging.getLogger("nodriver").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        # format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
