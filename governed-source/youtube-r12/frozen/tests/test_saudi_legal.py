from pathlib import Path

import pytest

from tests.test_c1_c3_prepublication import make_chain, review_evidence
from trend_hunter.compliance import ComplianceService
from trend_hunter.ledger import LedgerError
from trend_hunter.saudi_legal import SAUDI_CONTENT_RULE_IDS, SaudiCybercrimeReviewService
from trend_hunter.api import create_app


def decisions(status: str = "PASS"):
    return [{"rule_id": rule_id, "status": status, "reason": "specialist reviewed this rule"} for rule_id in sorted(SAUDI_CONTENT_RULE_IDS)]


def test_saudi_review_requires_sa_target(tmp_path: Path):
    ledger, target, opp, elig, creative = make_chain(tmp_path, natural="non-sa", language="en", region="US")
    with pytest.raises(LedgerError, match="region SA"):
        SaudiCybercrimeReviewService(ledger).review(
            creative.state_id, reviewer="specialist", determinations=decisions(), source_checked_at="2026-09-12"
        )


def test_saudi_review_is_complete_and_fail_closed(tmp_path: Path):
    ledger, target, opp, elig, creative = make_chain(tmp_path, natural="sa-incomplete", language="ar", region="SA")
    with pytest.raises(LedgerError, match="incomplete"):
        SaudiCybercrimeReviewService(ledger).review(
            creative.state_id, reviewer="specialist", determinations=decisions()[:-1], source_checked_at="2026-09-12"
        )


def test_saudi_block_flows_into_strict_compliance(tmp_path: Path):
    ledger, target, opp, elig, creative = make_chain(tmp_path, natural="sa-block", language="ar", region="SA")
    service = SaudiCybercrimeReviewService(ledger)
    reviewed = decisions()
    reviewed[0] = {**reviewed[0], "status": "BLOCK", "reason": "specialist found prohibited material"}
    evidence = service.review(
        creative.state_id, reviewer="specialist", determinations=reviewed, source_checked_at="2026-09-12"
    )
    platform = review_evidence(ledger, creative.state_id, dimension="platform", key="youtube")
    finding = service.compliance_finding(evidence.state_id)
    with pytest.raises(LedgerError, match="PASS cannot be asserted|BLOCK finding requires BLOCK"):
        ComplianceService(ledger).assess(
            creative.state_id, elig.state_id, target=target,
            legal_findings=[finding],
            platform_findings=[{"status":"PASS", "evidence_state_ids":[platform.state_id]}],
            coverage_state="SUFFICIENT", gate_decision="PASS", strict_c1=True,
        )
    result = ComplianceService(ledger).assess(
        creative.state_id, elig.state_id, target=target,
        legal_findings=[finding],
        platform_findings=[{"status":"PASS", "evidence_state_ids":[platform.state_id]}],
        coverage_state="SUFFICIENT", gate_decision="BLOCK", strict_c1=True,
    )
    assert ledger.get_state(result.state_id)["payload"]["gate_decision"] == "BLOCK"


def test_saudi_pass_can_supply_strict_legal_evidence(tmp_path: Path):
    ledger, target, opp, elig, creative = make_chain(tmp_path, natural="sa-pass", language="ar", region="SA")
    service = SaudiCybercrimeReviewService(ledger)
    evidence = service.review(
        creative.state_id, reviewer="specialist", determinations=decisions(), source_checked_at="2026-09-12"
    )
    platform = review_evidence(ledger, creative.state_id, dimension="platform", key="youtube")
    result = ComplianceService(ledger).assess(
        creative.state_id, elig.state_id, target=target,
        legal_findings=[service.compliance_finding(evidence.state_id)],
        platform_findings=[{"status":"PASS", "evidence_state_ids":[platform.state_id]}],
        coverage_state="SUFFICIENT", gate_decision="PASS", strict_c1=True,
    )
    assert ledger.get_state(result.state_id)["payload"]["gate_decision"] == "PASS"


def test_saudi_policy_is_visible_in_status_and_catalog(tmp_path: Path, make_test_client):
    client = make_test_client(create_app(str(tmp_path / "api.db")))
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["saudi_legal_filter"]["status"] == "INSTALLED"
    catalog = client.get("/api/compliance/saudi-cybercrime/policy")
    assert catalog.status_code == 200
    assert len(catalog.json()["rules"]) == len(SAUDI_CONTENT_RULE_IDS)
