from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol

@dataclass(frozen=True)
class SourceItem:
    source_name: str
    external_id: str
    observed_at: str
    payload: dict[str, Any]
    raw_bytes: bytes | None = None

class Connector(Protocol):
    name: str
    def fetch(self) -> list[SourceItem]: ...
