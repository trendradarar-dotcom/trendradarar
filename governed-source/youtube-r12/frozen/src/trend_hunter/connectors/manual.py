from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import SourceItem
from ..util import utcnow


class ManualJSONConnector:
    """Imports user-supplied JSON/JSONL without inventing missing fields.

    Required per item: source_name, external_id, payload.
    Optional: observed_at. Missing observed_at is set to ingestion time and the
    payload receives `_observed_at_basis=INGESTION_TIME`, so it is never
    confused with source event time.
    """
    name = "manual_json"

    def __init__(self, path: str):
        self.path = path

    def fetch(self) -> list[SourceItem]:
        p=Path(self.path)
        text=p.read_text(encoding="utf-8")
        if p.suffix.lower()==".jsonl":
            data=[json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            obj=json.loads(text)
            data=obj if isinstance(obj,list) else [obj]
        out=[]
        for i,item in enumerate(data):
            for key in ("source_name","external_id","payload"):
                if key not in item:
                    raise ValueError(f"item {i} missing required field {key}")
            observed=item.get("observed_at") or utcnow()
            payload=dict(item["payload"])
            if "observed_at" not in item:
                payload.setdefault("_observed_at_basis","INGESTION_TIME")
            out.append(SourceItem(
                source_name=item["source_name"], external_id=str(item["external_id"]),
                observed_at=observed, payload=payload,
                raw_bytes=json.dumps(item,ensure_ascii=False,sort_keys=True).encode("utf-8"),
            ))
        return out
