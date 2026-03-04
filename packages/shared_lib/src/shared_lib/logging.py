import logging
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler


def setup_logging(log_file: bool = False, log_name: str = "temp.log"):
    handlers = [RichHandler()]
    if log_file:
        rotatating_handler = RotatingFileHandler(
            log_name, maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8"
        )
        rotatating_handler.setLevel(logging.INFO)
        handlers.append(rotatating_handler)
    logging.getLogger("nodriver").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.basicConfig(
        level=logging.INFO,
        # format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
