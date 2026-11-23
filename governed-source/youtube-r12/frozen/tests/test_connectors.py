from pathlib import Path
from trend_hunter.connectors.google_trends_export import GoogleTrendsExportConnector
from trend_hunter.connectors.youtube import YouTubeSearchConnector


def test_google_trends_export_preserves_source_columns(tmp_path: Path):
    p=tmp_path/'trends.csv'
    p.write_text('Trends,Search volume,Started\nalpha,100K+,2 hours ago\n',encoding='utf-8')
    items=GoogleTrendsExportConnector(str(p),region='US').fetch()
    assert items[0].payload['title']=='alpha'
    assert items[0].payload['source_columns']['Search volume']=='100K+'
    assert items[0].payload['origin_not_asserted'] is True


def test_youtube_search_is_discovery_not_popularity(monkeypatch):
    c=YouTubeSearchConnector('k','alpha',max_results=1)
    def fake(endpoint,params):
        if endpoint.endswith('/search'):
            return {'items':[{'id':{'videoId':'v1'},'snippet':{'title':'T','publishedAt':'2026-08-10T00:00:00Z'}}]}
        return {'items':[{'id':'v1','statistics':{'viewCount':'123'}}]}
    monkeypatch.setattr(c,'_get_json',fake)
    items=c.fetch()
    assert items[0].payload['search_result_not_native_popularity'] is True
    assert items[0].payload['statistics']['viewCount']=='123'

def test_google_trends_bucket_strict_syntax():
    from trend_hunter.signals import parse_volume_bucket
    for raw in ("broken 100K+", "100K+ broken", "1,2,3", "100K++", "-100", "1e8", "NaN"):
        assert parse_volume_bucket(raw)["parse_state"] == "UNRESOLVED"
    assert parse_volume_bucket("2.5M+")["value"] == 2500000
    assert parse_volume_bucket("2.5M+")["value_semantics"] == "LOWER_BOUND"
    assert parse_volume_bucket("1,000+")["value"] == 1000
    assert parse_volume_bucket(None) is None


def test_google_trends_csv_normalization_unchanged(tmp_path: Path):
    from trend_hunter.signals import SignalNormalizationService
    p = tmp_path / "trends.csv"
    p.write_text("Trends,Search volume,Started\\nalpha,100K+,2 hours ago\\n", encoding="utf-8")
    item = GoogleTrendsExportConnector(str(p), region="US").fetch()[0]
    class Ledger:
        def get_state(self, state_id):
            return {
                "state_type": "SOURCE_RECORD",
                "payload": {
                    "connector": "google_trends_trending_now_export",
                    "payload": item.payload,
                },
            }
        def record_domain(self, *args, **kwargs):
            return {"args": args, "kwargs": kwargs}
    result = SignalNormalizationService(Ledger()).from_source("csv-source")
    metrics = result["args"][2]["metrics"]
    assert len(metrics) == 1
    assert metrics[0]["metric"] == "google_trends_export_search_volume"
    assert metrics[0]["value"]["raw"] == "100K+"
    assert metrics[0]["value"]["value_semantics"] == "LOWER_BOUND"
    assert result["kwargs"]["record_state"] == "OBSERVED"
