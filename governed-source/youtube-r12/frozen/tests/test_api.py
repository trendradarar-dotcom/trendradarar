from pathlib import Path
from fastapi.testclient import TestClient
from trend_hunter.api import create_app


def test_api_health_and_demo(tmp_path: Path, make_test_client):
    app=create_app(str(tmp_path/'api.db'))
    c=make_test_client(app)
    assert c.get('/health').status_code==200
    assert c.get('/health').json() == {'status':'ok'}
    r=c.post('/api/demo/run')
    assert r.status_code==200
    assert r.json()['stopped_at']=='HUMAN_FINAL_AUTHORIZATION'
    s=c.get('/api/status').json()
    assert s['architecture']=='COMPLETE'
    dashboard=c.get('/').text
    assert "const integrityOk=h.status==='ok'" in dashboard
    assert 'h.integrity.ok' not in dashboard
    assert 'كيف يتحول إلى أرباح؟' in dashboard
    assert 'وعد التسليم الوظيفي' in dashboard
    assert 'هذا ليس ضمانًا لربح مالي أو وعدًا بعائد' in dashboard
    assert 'سجلات مراحل العمل' in dashboard
    assert "s.architecture==='COMPLETE'?'مكتملة'" in dashboard

def test_manual_source_api(tmp_path: Path, make_test_client):
    app=create_app(str(tmp_path/'manual.db')); c=make_test_client(app)
    r=c.post('/api/source/manual',json={'items':[{'source_name':'manual','external_id':'x1','payload':{'language':'ar','region':'SA','platform':'manual','title':'x'}}]})
    assert r.status_code==200
    sid=r.json()[0]['state_id']
    s=c.post('/api/signal/from-source',json={'source_state_id':sid})
    assert s.status_code==200


def test_dashboard_is_arabic_but_declares_six_global_publication_languages():
    from trend_hunter.api import DASHBOARD_HTML
    assert '<html lang="ar" dir="rtl">' in DASHBOARD_HTML
    for label in ['العربية','الإنجليزية','الفرنسية','الهندية','الصينية المبسطة','الإسبانية']:
        assert label in DASHBOARD_HTML
    assert 'نطاق الصيد التجاري ليس عربيًا فقط' in DASHBOARD_HTML
    assert 'الترجمة العربية للعرض لا تُعامل كدليل مستقل' in DASHBOARD_HTML
