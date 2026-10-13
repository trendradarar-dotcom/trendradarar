from __future__ import annotations

import json
from pathlib import Path

from .db import connect
from .util import hash_bytes, json_dumps, utcnow

TABLES = [
    'schema_migration',
    'artifact_identity','canonicalization_profile','content_descriptor','artifact_state','provenance_edge',
    'governance_contract_version','governance_contract_reference','governance_authority_grant','delegation_edge','governance_event','effectivity_binding',
    'methodology_version','audit_corpus_snapshot','normalization_assertion','normalization_assertion_artifact','correspondence_judgment','correspondence_judgment_artifact','adjudication_target','adjudication_target_fingerprint',
    'evidentiary_entitlement','adjudication','adjudication_consumed_artifact','dependency_change_policy','dependency_binding',
    'invalidation_reconciliation_event','integrity_incident','current_view_projection','execution_configuration',
    'monetization_configuration','monetization_activation_requirement','monetization_activation_record','domain_record'
]


def export_snapshot(db_path: str, output_path: str) -> dict:
    bundle={'exported_at':utcnow(),'tables':{}}
    with connect(db_path) as conn:
        for t in TABLES:
            rows=[dict(r) for r in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')]
            bundle['tables'][t]=rows
    payload=json_dumps(bundle).encode('utf-8')
    digest=hash_bytes(payload)
    out={'snapshot':bundle,'sha256':digest}
    Path(output_path).write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    return {'path':output_path,'sha256':digest,'table_count':len(TABLES),'row_count':sum(len(v) for v in bundle['tables'].values())}
