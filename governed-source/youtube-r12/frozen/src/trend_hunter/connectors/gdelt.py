from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from .base import SourceItem
from .http import ResilientHTTPClient, HTTPPolicy
from ..util import utcnow


class GDELTDocConnector:
    """GDELT DOC 2.0 ArticleList RSS adapter.

    The adapter records article-list discovery only. It does not treat article
    count as independent evidence and does not infer truth, origin, or trend
    popularity from the returned list.
    """

    name = "gdelt_doc_2"
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, query: str, *, timespan: str = "1h", maxrecords: int = 100, timeout: int = 30, http_client: ResilientHTTPClient | None = None):
        if not query.strip():
            raise ValueError("query is required")
        if not (1 <= maxrecords <= 250):
            raise ValueError("maxrecords must be between 1 and 250")
        self.query=query
        self.timespan=timespan
        self.maxrecords=maxrecords
        self.timeout=timeout
        self.http_client=http_client or ResilientHTTPClient(HTTPPolicy(max_attempts=4, min_interval_seconds=0.25))

    def fetch(self) -> list[SourceItem]:
        params={
            "query": self.query,
            "mode": "artlist",
            "maxrecords": str(self.maxrecords),
            "timespan": self.timespan,
            "sort": "datedesc",
            "format": "rss",
        }
        url=self.endpoint+"?"+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={"User-Agent":"TrendHunterEngine/0.3"})
        raw=self.http_client.open(req,timeout=self.timeout)
        root=ET.fromstring(raw)
        out=[]
        for item in root.findall(".//item"):
            title=(item.findtext("title") or "").strip()
            link=(item.findtext("link") or "").strip()
            pub=(item.findtext("pubDate") or "").strip()
            try:
                observed=parsedate_to_datetime(pub).isoformat() if pub else utcnow()
                observed_basis="SOURCE_PUBDATE" if pub else "INGESTION_TIME"
            except Exception:
                observed=utcnow(); observed_basis="INGESTION_TIME_INVALID_SOURCE_PUBDATE"
            external=link or hashlib.sha256((title+pub).encode("utf-8")).hexdigest()
            out.append(SourceItem(
                source_name=self.name,
                external_id=external,
                observed_at=observed,
                payload={
                    "title": title,
                    "url": link or None,
                    "query": self.query,
                    "timespan": self.timespan,
                    "discovery_channel": "GDELT_DOC_ARTICLE_LIST",
                    "observed_at_basis": observed_basis,
                    "article_list_membership_not_independent_evidence": True,
                    "origin_not_asserted": True,
                    "trend_popularity_not_asserted": True,
                },
                raw_bytes=ET.tostring(item,encoding="utf-8"),
            ))
        return out
