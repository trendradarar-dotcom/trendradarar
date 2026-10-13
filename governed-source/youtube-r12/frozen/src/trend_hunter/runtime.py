from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from .util import utcnow


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": utcnow(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "event_payload", None)
        if isinstance(extra, dict):
            payload["event"] = extra
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_runtime_logging(log_file: str | None = None) -> logging.Logger:
    logger = logging.getLogger("trend_hunter.runtime")
    if getattr(logger, "_trend_hunter_configured", False):
        return logger
    logger.setLevel(logging.INFO)
    handler: logging.Handler
    log_file = log_file or os.environ.get("TREND_HUNTER_LOG_FILE")
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
    else:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    logger._trend_hunter_configured = True
    return logger


def log_event(logger: logging.Logger, event_type: str, **payload: Any) -> None:
    safe = {k: v for k, v in payload.items() if "secret" not in k.lower() and "token" not in k.lower()}
    logger.info(event_type, extra={"event_payload": {"type": event_type, **safe}})
