import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings

# <project root>/logs  (logs/ is already in .gitignore)
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)

    # 1. Console: what you see in the terminal
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    # 2. logs/app.log: everything, rotated at 1 MB, keeps 3 old files
    app_file = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    app_file.setFormatter(formatter)

    # 3. logs/errors.log: ERROR and above only (this is the "error monitoring" file)
    error_file = RotatingFileHandler(
        LOG_DIR / "errors.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    error_file.setLevel(logging.ERROR)
    error_file.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    root.handlers.clear()  # no duplicate lines after a reload
    for handler in (console, app_file, error_file):
        root.addHandler(handler)

    # Our middleware writes one line per request (with timing and an id),
    # so uvicorn's own access line would only be a duplicate.
    logging.getLogger("uvicorn.access").disabled = True

    # Quiet libraries that are noisy at DEBUG level
    for noisy in ("multipart", "python_multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)