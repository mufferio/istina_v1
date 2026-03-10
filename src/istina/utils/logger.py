"""
Logging configuration.

Purpose:
- Configure Python logging consistently across the project:
  - format (timestamps, level, module)
  - handlers (stdout for CLI)
  - log levels controlled by Settings

Rules:
- Never log secrets (API keys).
- Keep output readable for CLI usage.
"""

import logging
from istina.config.settings import Settings


def configure_logger(settings: Settings) -> logging.Logger:
    """
    Configure Istina logger with consistent format and level.
    Safe to call multiple times.
    """

    logger = logging.getLogger("istina")

    if getattr(logger, "_istina_configured", False):
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    # Convert string → logging level
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)

    logger.propagate = False
    logger._istina_configured = True

    return logger

