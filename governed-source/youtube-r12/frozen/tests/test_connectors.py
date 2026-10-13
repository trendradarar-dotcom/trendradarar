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
