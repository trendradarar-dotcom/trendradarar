from trend_hunter.connectors import google_trends_live as mod
from trend_hunter.connectors.google_trends_live import DEFAULT_MARKETS, GoogleTrendsLiveConnector
RSS=b'''<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item><title>alpha topic</title><ht:approx_traffic>100K+</ht:approx_traffic><pubDate>Sun, 13 Sep 2026 12:50:00 -0700</pubDate></item></channel></rss>'''
class R:
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def read(self): return RSS
def test_live_google_trends(monkeypatch):
    monkeypatch.setattr(mod,'urlopen',lambda *a,**k:R())
    x=GoogleTrendsLiveConnector('US').fetch()[0]
    assert x.source_name=='google_trends_export'
    assert x.payload['source_name']=='google_trends_live'
    assert x.payload['source_transport']=='LIVE_RSS'
    assert x.payload['region']=='US'
    assert x.payload['approx_traffic']=='100K+'
    assert x.payload['operator_action_required'] is False
def test_scope_is_global_not_sa_only():
    assert len(DEFAULT_MARKETS)>=80
    for m in ('US','BR','GB','ZA','IN','JP','AU','SA'): assert m in DEFAULT_MARKETS
    assert set(DEFAULT_MARKETS)!={'SA'}