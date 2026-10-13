from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .base import SourceItem
from ..util import utcnow


class GoogleTrendsExportConnector:
    """Imports a user-exported Google Trends Trending Now CSV.

    This intentionally does not hard-code an undocumented network endpoint.
    Column names are preserved verbatim in `source_columns`; common title/time
    aliases are mapped only when present.
    """
    name = "google_trends_trending_now_export"

    def __init__(self,path: str, *, region: str | None = None):
        self.path=path; self.region=region

    def fetch(self) -> list[SourceItem]:
        p=Path(self.path)
        raw=p.read_bytes()
        text=raw.decode("utf-8-sig")
        rows=list(csv.DictReader(text.splitlines()))
        out=[]
        for i,row in enumerate(rows):
            title=next((row[k] for k in row if k and k.lower().strip() in {"trends","trend","search term","search query","query"} and row[k]),None)
            started=next((row[k] for k in row if k and k.lower().strip() in {"started","start time","started at"} and row[k]),None)
            external=hashlib.sha256((str(i)+str(title)+str(started)+str(row)).encode("utf-8")).hexdigest()
            out.append(SourceItem(
                self.name,external,utcnow(),{
                    "title":title,
                    "region":self.region,
                    "platform":"google_search",
                    "source_columns":row,
                    "observed_at_basis":"INGESTION_TIME_UNLESS_EXPORT_COLUMN_IS_LATER_GOVERNED",
                    "origin_not_asserted":True,
                    "export_semantics_not_strengthened":True,
                },
                raw_bytes=(str(row)).encode("utf-8"),
            ))
        return out
