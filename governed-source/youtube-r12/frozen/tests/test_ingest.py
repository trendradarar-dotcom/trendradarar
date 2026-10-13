import json
from pathlib import Path
from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger
from trend_hunter.bootstrap import bootstrap_governance
from trend_hunter.connectors.manual import ManualJSONConnector
from trend_hunter.ingest import IngestionService


def test_manual_json_ingest(tmp_path: Path):
    db=tmp_path/'x.db'; init_db(str(db)); l=GovernanceLedger(str(db),str(tmp_path/'obj')); bootstrap_governance(l)
    p=tmp_path/'items.json'; p.write_text(json.dumps([{'source_name':'s','external_id':'1','payload':{'language':'ar','region':'SA','platform':'manual'}}]),encoding='utf-8')
    c=ManualJSONConnector(str(p)); refs=IngestionService(l).ingest(c.fetch(),c.name)
    assert len(refs)==1
    state=l.get_state(refs[0].state_id)
    assert state['payload']['payload']['_observed_at_basis']=='INGESTION_TIME'
