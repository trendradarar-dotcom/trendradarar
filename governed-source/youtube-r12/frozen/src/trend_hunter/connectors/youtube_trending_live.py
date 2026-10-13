from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .base import SourceItem


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class YouTubeTrendingLiveConnector:
    """Official YouTube most-popular chart, bound to one content region."""

    name = "youtube"

    def __init__(self, api_key: str, region: str, *, max_results: int = 25, timeout_seconds: int = 20):
        key = str(api_key or "").strip()
        if not key:
            raise ValueError("YouTube API key is required")
        region = str(region or "").strip().upper()
        if len(region) != 2 or not region.isalpha():
            raise ValueError("region must be ISO alpha-2")
        self.api_key = key
        self.region = region
        self.max_results = max(1, min(int(max_results), 50))
        self.timeout_seconds = int(timeout_seconds)

    def fetch(self) -> list[SourceItem]:
        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": self.region,
            "maxResults": self.max_results,
            "key": self.api_key,
        }
        url = "https://www.googleapis.com/youtube/v3/videos?" + urlencode(params)
        safe_url = (
            "https://www.googleapis.com/youtube/v3/videos?"
            + urlencode({k: v for k, v in params.items() if k != "key"})
        )
        req = Request(
            url,
            headers={
                "User-Agent": "TrendHunter/1.0 (+autonomous-global-trend-discovery)",
                "Accept": "application/json",
            },
        )
        with urlopen(req, timeout=self.timeout_seconds) as resp:
            raw = resp.read()
        data = json.loads(raw.decode("utf-8"))

        out: list[SourceItem] = []
        observed = _utcnow()
        for item in data.get("items") or []:
            video_id = str(item.get("id") or "").strip()
            if not video_id:
                continue
            snippet = item.get("snippet") or {}
            statistics = item.get("statistics") or {}
            external_id = f"{self.region}:{video_id}"
            payload = {
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "published_at": snippet.get("publishedAt"),
                "channel_id": snippet.get("channelId"),
                "channel_title": snippet.get("channelTitle"),
                "category_id": snippet.get("categoryId"),
                "tags": snippet.get("tags") or [],
                "statistics": statistics,
                "video_id": video_id,
                "region": self.region,
                "platform": "youtube",
                "provider": "youtube",
                "source_name": "youtube_trending_live",
                "source_surface": "youtube_most_popular_chart",
                "source_transport": "LIVE_API",
                "source_url": safe_url,
                "provider_literal": True,
                "origin_not_asserted": True,
                "operator_action_required": False,
                "source_semantics": (
                    "Official YouTube mostPopular chart observation for a content region; "
                    "not a universal cross-platform score."
                ),
            }
            out.append(SourceItem(self.name, external_id, observed, payload, raw_bytes=None))
        return out