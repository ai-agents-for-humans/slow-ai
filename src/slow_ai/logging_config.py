"""
Centralised logging configuration for slow_ai.

Call setup_logging() once at process startup (e.g. in __main__.py).
All modules obtain their logger with logging.getLogger(__name__).
"""

import logging
import sys
from pathlib import Path


def setup_logging(
    log_file: Path | None = None,
    level: int = logging.INFO,
) -> None:
    """
    Configure root logger.

    - Always logs to stderr.
    - If log_file is given, also logs to that file (appended, UTF-8).
    """
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
    ]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        handlers.append(fh)

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,  # override any prior basicConfig (e.g. from pydantic-ai)
    )

    # Silence noisy third-party loggers that flood at INFO
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("git").setLevel(logging.WARNING)
    logging.getLogger("pydantic_ai").setLevel(logging.WARNING)
