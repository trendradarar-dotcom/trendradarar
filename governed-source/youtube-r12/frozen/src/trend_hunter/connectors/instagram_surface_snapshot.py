from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .base import SourceItem
from ..util import utcnow


class InstagramSurfaceSnapshotConnector:
    """
    Imports an operator-supplied CSV snapshot from an Instagram-visible surface.

    No undocumented network endpoint is used.
    Source columns are preserved verbatim and their semantics are not strengthened.
    """

    name = "instagram_surface_snapshot"

    def __init__(
        self,
        path: str,
        region: str | None = None,
        language: str | None = None,
    ):
        self.path = path
        self.region = region
        self.language = language

    def fetch(self) -> list[SourceItem]:
        p = Path(self.path)
        raw = p.read_bytes()
        text = raw.decode("utf-8-sig")
        rows = list(csv.DictReader(text.splitlines()))

        out: list[SourceItem] = []

        title_aliases = {
            "hashtag",
            "trend",
            "topic",
            "keyword",
            "query",
            "title",
        }

        for i, row in enumerate(rows):
            title = next(
                (
                    row[k]
                    for k in row
                    if k
                    and k.lower().strip() in title_aliases
                    and row.get(k)
                ),
                None,
            )

            external = hashlib.sha256(
                (str(i) + str(title) + str(row)).encode("utf-8")
            ).hexdigest()

            out.append(
                SourceItem(
                    self.name,
                    external,
                    utcnow(),
                    {
                        "title": title,
                        "region": self.region,
                        "language": self.language,
                        "platform": "instagram",
                        "source_columns": row,
                        "provider_surface": "Instagram operator snapshot",
                        "observed_at_basis": (
                            "INGESTION_TIME_UNLESS_SOURCE_COLUMN_IS_LATER_GOVERNED"
                        ),
                        "origin_not_asserted": True,
                        "manual_snapshot": True,
                        "snapshot_semantics_not_strengthened": True,
                    },
                    raw_bytes=str(row).encode("utf-8"),
                )
            )

        return out