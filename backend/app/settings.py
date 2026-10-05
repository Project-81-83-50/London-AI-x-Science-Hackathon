"""Run-time settings read from the environment, and the API's logging setup, in one place.

File-system locations live in paths.py; this module holds everything else that can be configured:
  LOG_LEVEL   level of the API's own log messages (DEBUG, INFO, WARNING, ...; default INFO)
  V3_PYTHON   Python with PyTorch that runs sem_pipeline (read on every use; see v3_python_override)
"""

import logging
import os

# Allow the local Vite page and other frontends to call this API during development.
# For a public production deployment, replace "*" with the approved frontend origin.
CORS_ALLOW_ORIGINS = ["*"]

# `python -m app.main` (or `python app/main.py`) starts the local development API here.
# scripts/start_website.bat and scripts/start_website.sh run uvicorn on port 8002 instead.
DEV_HOST = "0.0.0.0"
DEV_PORT = 8000

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def _parse_log_level(value: str) -> int | None:
    """A logging level from a name ("debug", "INFO") or a number ("10"); None when it is neither."""
    value = value.strip().upper()
    if value.isdigit():
        return int(value)
    level = logging.getLevelName(value)
    return level if isinstance(level, int) else None


def configure_logging() -> None:
    """Send the API's log messages (loggers under "app") to stderr, next to uvicorn's own output.

    The level comes from LOG_LEVEL (default INFO). logging.basicConfig only adds a handler when the root
    logger has none, so a host that configures logging itself (a test runner, a deployment) keeps control."""
    raw = os.environ.get("LOG_LEVEL", "")
    level = _parse_log_level(raw) if raw.strip() else logging.INFO
    logging.basicConfig(level=level or logging.INFO, format=LOG_FORMAT)
    logging.getLogger("app").setLevel(level or logging.INFO)
    if level is None:
        logging.getLogger(__name__).warning("LOG_LEVEL=%r is not a logging level; using INFO", raw)


def v3_python_override() -> str | None:
    """V3_PYTHON when set (read each time, so it can be changed without re-importing the API)."""
    return os.environ.get("V3_PYTHON") or None
