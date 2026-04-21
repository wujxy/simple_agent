from __future__ import annotations

import logging
import os

_LEVEL_MAP = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING}


def get_logger(name: str = "simple_agent") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(handler)
        level_str = os.environ.get("SIMPLE_AGENT_LOG", "info").lower()
        logger.setLevel(_LEVEL_MAP.get(level_str, logging.INFO))
    return logger
