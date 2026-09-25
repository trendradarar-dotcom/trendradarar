import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict

CORRELATION_RE = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")

_logger = logging.getLogger("trendradar.snapchat")
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
_logger.setLevel(logging.INFO)
_logger.propagate = False

_ALLOWED_FIELDS = {
    "correlation_id",
    "publication_id",
    "trend_id",
    "market",
    "provider",
    "status",
    "error",
    "http_status",
    "route",
    "external_publication_side_effect",
}


def safe_correlation_id(value: str | None) -> str | None:
    if value and CORRELATION_RE.fullmatch(value):
        return value
    return None


def audit(event: str, **fields: Any) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    for key, value in fields.items():
        if key in _ALLOWED_FIELDS and value is not None:
            record[key] = value
    _logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return record
