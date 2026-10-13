from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .base import SourceItem
from ..util import utcnow


class SnapchatSpotlightSnapshotConnector:
    """
    Imports an operator-captured CSV snapshot from an official Snapchat
    Spotlight / trends-visible surface.

    No undocumented network endpoint is used.
    Source columns are preserved verbatim and their semantics are not
    strengthened beyond what was visible on the captured surface.
    """

    name = "snapchat_spotlight_snapshot"

    def __init__(
        self,
        path: str,
        region: str | None = None,
        language: str | None = None,
    ):
        self.path = path
        self.region = region
        self.language = language

    @staticmethod
    def _pick(row: dict[str, str], names: set[str]) -> str | None:
        wanted = {x.lower().strip() for x in names}
        for key, value in row.items():
            if key and key.lower().strip() in wanted and value:
                return value
        return None

    def fetch(self) -> list[SourceItem]:
        p = Path(self.path)
        text = p.read_text(encoding="utf-8-sig")
        rows = list(csv.DictReader(text.splitlines()))
        out: list[SourceItem] = []

        for i, row in enumerate(rows):
            title = self._pick(
                row,
                {
                    "topic",
                    "trend",
                    "hashtag",
                    "title",
                    "sound",
                    "lens",
                    "event",
                    "search label",
                },
            )

            if not title:
                title = f"snapchat-item-{i + 1}"

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
                        "platform": "snapchat",
                        "source_columns": row,
                        "provider_surface": "Snapchat Spotlight operator snapshot",
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