from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from .base import SourceItem

DEFAULT_MARKETS: tuple[str, ...] = (
    "US","CA","MX","BR","AR","CL","CO","PE","UY","PY","BO","EC","CR","PA","GT","DO","PR","JM","TT","HN","SV","NI",
    "GB","IE","FR","DE","ES","IT","PT","NL","BE","CH","AT","SE","NO","DK","FI","IS","PL","CZ","SK","HU","RO","BG","GR","HR","SI","RS","BA","MK","AL","EE","LV","LT","UA","MD","TR","CY","MT","LU",
    "SA","AE","QA","KW","BH","OM","JO","LB","IL","EG","MA","DZ","TN","ZA","NG","KE","GH","UG","TZ","ET","SN","CI","CM",
    "IN","PK","BD","LK","NP","ID","MY","SG","TH","VN","PH","JP","KR","TW","HK","MN","KZ","UZ","KG","GE","AM","AZ",
    "AU","NZ",
)

def _utcnow(): return datetime.now(timezone.utc).isoformat()
def _pubdate_iso(v):
    if not v: return _utcnow()
    try:
        d=parsedate_to_datetime(v)
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception: return _utcnow()
def _local_name(tag): return tag.rsplit('}',1)[-1].lower()

class GoogleTrendsLiveConnector:
    # Historical governance key retained for compatibility; transport is LIVE_RSS.
    name='google_trends_export'
    live_source_name='google_trends_live'
    def __init__(self,region:str,*,timeout_seconds:int=15):
        region=str(region or '').strip().upper()
        if len(region)!=2 or not region.isalpha(): raise ValueError('region must be ISO alpha-2')
        self.region=region; self.timeout_seconds=int(timeout_seconds)
    @property
    def url(self): return 'https://trends.google.com/trending/rss?'+urlencode({'geo':self.region})
    def fetch(self)->list[SourceItem]:
        req=Request(self.url,headers={'User-Agent':'TrendHunter/1.0 autonomous-global-trend-discovery','Accept':'application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.1'})
        with urlopen(req,timeout=self.timeout_seconds) as resp: raw=resp.read()
        root=ET.fromstring(raw); out=[]
        for node in root.findall('.//item'):
            title=(node.findtext('title') or '').strip()
            if not title: continue
            pub=(node.findtext('pubDate') or '').strip() or None
            traffic=None
            for child in list(node):
                if _local_name(child.tag)=='approx_traffic': traffic=(child.text or '').strip() or None; break
            raw_item=ET.tostring(node,encoding='utf-8')
            ext=hashlib.sha256(f'{self.region}|{title}|{pub or ""}'.encode('utf-8')).hexdigest()
            payload={
                'title':title,'region':self.region,'platform':'google_search','provider':'google_trends',
                'source_name':self.live_source_name,'connector':self.name,'source_surface':'google_trends_trending_now_rss',
                'source_transport':'LIVE_RSS','source_url':self.url,'published_at':pub,'approx_traffic':traffic,
                'provider_literal':True,'origin_not_asserted':True,
                'observed_at_basis':'PROVIDER_RSS_PUBDATE_WHEN_PRESENT_ELSE_INGESTION_TIME',
                'source_semantics':'Provider-reported Trending Now observation for one market; not a universal or cross-platform popularity score.',
                'operator_action_required':False,
            }
            out.append(SourceItem(self.name,ext,_pubdate_iso(pub),payload,raw_bytes=raw_item))
        return out