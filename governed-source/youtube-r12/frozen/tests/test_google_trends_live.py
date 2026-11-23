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
def test_live_rss_normalization_contract():
    from trend_hunter.signals import SignalNormalizationService
    class Ledger:
        def get_state(self, state_id):
            assert state_id == "source-1"
            return {
                "state_type": "SOURCE_RECORD",
                "payload": {
                    "connector": "google_trends_export",
                    "payload": {
                        "source_name": "google_trends_live",
                        "connector": "google_trends_export",
                        "source_transport": "LIVE_RSS",
                        "source_surface": "google_trends_trending_now_rss",
                        "region": "US",
                        "platform": "google_search",
                        "approx_traffic": "100K+",
                    },
                },
                "observed_at": "2026-09-13T19:50:00+00:00",
            }
        def record_domain(self, *args, **kwargs):
            return {"args": args, "kwargs": kwargs}
    result = SignalNormalizationService(Ledger()).from_source("source-1")
    signal = result["args"][2]
    assert signal["connector"] == "google_trends_export"
    assert len(signal["metrics"]) == 1
    value = signal["metrics"][0]["value"]
    assert value["raw"] == "100K+"
    assert value["value"] == 100000
    assert value["value_semantics"] == "LOWER_BOUND"
    assert result["kwargs"]["record_state"] == "OBSERVED"


def test_live_rss_missing_malformed_and_ambiguous_transport():
    from trend_hunter.signals import SignalNormalizationService
    class Ledger:
        payload = {}
        def get_state(self, state_id):
            return {
                "state_type": "SOURCE_RECORD",
                "payload": {"connector": "google_trends_export", "payload": self.payload},
            }
        def record_domain(self, *args, **kwargs):
            return {"args": args, "kwargs": kwargs}
    ledger = Ledger()
    for raw in (None, "", "traffic 100K+ broken", "100K+ extra"):
        ledger.payload = {
            "source_name": "google_trends_live",
            "connector": "google_trends_export",
            "source_transport": "LIVE_RSS",
            "source_surface": "google_trends_trending_now_rss",
            "approx_traffic": raw,
        }
        result = SignalNormalizationService(ledger).from_source("source-1")
        assert result["args"][2]["metrics"] == []
        assert result["kwargs"]["record_state"] == "NO_ASSERTABLE_METRIC"
    ledger.payload["approx_traffic"] = "100K+"
    ledger.payload["source_transport"] = "CSV_EXPORT"
    result = SignalNormalizationService(ledger).from_source("source-1")
    assert result["args"][2]["metrics"] == []
