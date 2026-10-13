from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_json_bytes(value: Any) -> bytes:
    return json_dumps(value).encode("utf-8")


def hash_bytes(data: bytes, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    h.update(data)
    return h.hexdigest()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
