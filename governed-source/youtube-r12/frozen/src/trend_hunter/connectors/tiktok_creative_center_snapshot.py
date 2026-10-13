from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .base import SourceItem
from ..util import utcnow


class TikTokCreativeCenterSnapshotConnector:
    """
    Imports a governed user-supplied CSV snapshot derived from the
    TikTok Creative Center Trends surface.

    This connector intentionally does not hard-code or claim an
    undocumented TikTok network API or export endpoint.

    Source columns are preserved verbatim in `source_columns`.
    Provider-visible values are not strengthened beyond their source semantics.
    """

    name = "tiktok_creative_center_snapshot"

    def __init__(
        self,
        path: str,
        *,
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

        for i, row in enumerate(rows):
            title = next(
                (
                    row[k]
                    for k in row
                    if k
                    and k.lower().strip()
                    in {
                        "hashtag",
                        "trend",
                        "trend name",
                        "name",
                        "topic",
                        "keyword",
                    }
                    and row[k]
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
                        "platform": "tiktok",
                        "source_columns": row,
                        "provider_surface": "TikTok Creative Center",
                        "observed_at_basis": "INGESTION_TIME_UNLESS_SOURCE_COLUMN_IS_LATER_GOVERNED",
                        "origin_not_asserted": True,
                        "manual_snapshot": True,
                        "snapshot_semantics_not_strengthened": True,
                    },
                    raw_bytes=str(row).encode("utf-8"),
                )
            )

        return out