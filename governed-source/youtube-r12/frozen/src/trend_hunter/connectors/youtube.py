from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .base import SourceItem
from .http import ResilientHTTPClient, HTTPPolicy
from ..util import utcnow


class YouTubeSearchConnector:
    """YouTube Data API v3 discovery adapter.

    Search results are treated as discovery results, never as native trend
    popularity. Optional videos.list statistics remain literal video metrics.
    """

    name = "youtube_data_api_v3"
    search_endpoint = "https://www.googleapis.com/youtube/v3/search"
    videos_endpoint = "https://www.googleapis.com/youtube/v3/videos"

    def __init__(self, api_key: str, query: str, *, region_code: str | None = None, relevance_language: str | None = None, published_after: str | None = None, max_results: int = 25, timeout: int = 30, include_statistics: bool = True, http_client: ResilientHTTPClient | None = None):
        if not api_key:
            raise ValueError("YouTube API key is required")
        if not query.strip():
            raise ValueError("query is required")
        if not (1 <= max_results <= 50):
            raise ValueError("max_results must be 1..50")
        self.api_key=api_key; self.query=query; self.region_code=region_code; self.relevance_language=relevance_language
        self.published_after=published_after; self.max_results=max_results; self.timeout=timeout; self.include_statistics=include_statistics
        self.http_client=http_client or ResilientHTTPClient(HTTPPolicy(max_attempts=4, min_interval_seconds=0.2))

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url=endpoint+"?"+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None})
        req=urllib.request.Request(url,headers={"User-Agent":"TrendHunterEngine/0.3"})
        return json.loads(self.http_client.open(req,timeout=self.timeout).decode("utf-8"))

    def fetch(self) -> list[SourceItem]:
        search=self._get_json(self.search_endpoint,{
            "part":"snippet","q":self.query,"type":"video","maxResults":self.max_results,
            "regionCode":self.region_code,"relevanceLanguage":self.relevance_language,
            "publishedAfter":self.published_after,"order":"date","key":self.api_key,
        })
        video_ids=[x.get("id",{}).get("videoId") for x in search.get("items",[]) if x.get("id",{}).get("videoId")]
        stats: dict[str,dict[str,Any]]={}
        if self.include_statistics and video_ids:
            detail=self._get_json(self.videos_endpoint,{"part":"snippet,statistics","id":",".join(video_ids),"key":self.api_key})
            stats={x["id"]:x for x in detail.get("items",[]) if x.get("id")}
        out=[]
        for item in search.get("items",[]):
            vid=item.get("id",{}).get("videoId")
            if not vid: continue
            sn=item.get("snippet",{})
            detail=stats.get(vid,{})
            published=sn.get("publishedAt") or utcnow()
            payload={
                "video_id":vid,
                "title":sn.get("title"),
                "description":sn.get("description"),
                "channel_id":sn.get("channelId"),
                "channel_title":sn.get("channelTitle"),
                "published_at":sn.get("publishedAt"),
                "query":self.query,
                "region":self.region_code,
                "language":self.relevance_language,
                "platform":"youtube",
                "discovery_channel":"YOUTUBE_SEARCH_LIST",
                "search_result_not_native_popularity":True,
                "origin_not_asserted":True,
                "statistics": detail.get("statistics") if detail else None,
                "statistics_semantics":"literal cumulative video resource statistics when present; not a trend score",
            }
            out.append(SourceItem(self.name,vid,published,payload,json.dumps({"search":item,"detail":detail},ensure_ascii=False,sort_keys=True).encode("utf-8")))
        return out
