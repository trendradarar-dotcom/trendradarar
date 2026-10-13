from __future__ import annotations

import json

from trend_hunter.connectors import youtube_trending_live as mod
from trend_hunter.connectors.youtube_trending_live import YouTubeTrendingLiveConnector


class Resp:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps({
            "items": [{
                "id": "abc123",
                "snippet": {
                    "title": "Example",
                    "publishedAt": "2026-09-13T10:00:00Z",
                    "channelId": "c1",
                    "channelTitle": "Channel",
                    "categoryId": "28"
                },
                "statistics": {"viewCount": "1000"}
            }]
        }).encode("utf-8")


def test_youtube_trending_live_is_region_bound_and_automatic(monkeypatch):
    monkeypatch.setattr(mod, "urlopen", lambda *a, **k: Resp())
    c = YouTubeTrendingLiveConnector("secret", "JP", max_results=10)
    items = c.fetch()
    assert len(items) == 1
    p = items[0].payload
    assert p["region"] == "JP"
    assert p["source_transport"] == "LIVE_API"
    assert p["source_surface"] == "youtube_most_popular_chart"
    assert p["operator_action_required"] is False
    assert "secret" not in p["source_url"]


def test_youtube_trending_live_rejects_invalid_region():
    try:
        YouTubeTrendingLiveConnector("k", "GLOBAL")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid region must fail closed")