from __future__ import annotations

from typing import Any

from .ledger import ArtifactRef, GovernanceLedger, LedgerError


SAUDI_ANTI_CYBERCRIME_POLICY = {
    "policy_key": "SAUDI_ANTI_CYBERCRIME_CONTENT_REVIEW",
    "version": 1,
    "jurisdiction": "SA",
    "instrument_ar": "نظام مكافحة جرائم المعلوماتية",
    "royal_decree": "M/17",
    "decree_date_hijri": "1428-03-08",
    "official_source": "https://laws.boe.gov.sa/",
    "rules": (
        ("SA-ACC-3-4", "article_3", "المساس بالحياة الخاصة عن طريق إساءة استخدام الهواتف المزودة بالكاميرا ونحوها"),
        ("SA-ACC-3-5", "article_3", "التشهير بالآخرين أو إلحاق الضرر بهم عبر وسائل تقنيات المعلومات المختلفة"),
        ("SA-ACC-6-1", "article_6", "إنتاج أو نشر أو ترويج ما يمس النظام العام أو القيم الدينية أو الآداب العامة أو حرمة الحياة الخاصة"),
        ("SA-ACC-6-2", "article_6", "إنشاء أو نشر المواد والأنشطة الإباحية أو الترويج لها"),
        ("SA-ACC-6-3", "article_6", "إنشاء أو نشر أو ترويج ما ييسر التعامل بالمخدرات أو المؤثرات العقلية"),
        ("SA-ACC-7-1", "article_7", "إنشاء أو نشر ما يتعلق بالتنظيمات الإرهابية أو تسهيل الاتصال بها أو تمويلها أو الترويج لأفكارها"),
    ),
}

SAUDI_CONTENT_RULE_IDS = frozenset(row[0] for row in SAUDI_ANTI_CYBERCRIME_POLICY["rules"])
_STATUSES = frozenset({"PASS", "WARNING", "BLOCK", "UNRESOLVED", "NOT_APPLICABLE"})


class SaudiCybercrimeReviewService:
    """Records a specialist, content-bound Saudi legal screen.

    This service validates and preserves a human specialist's determinations. It
    deliberately does not infer legal truth from keywords or issue legal advice.
    """

    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def review(
        self,
        creative_state_id: str,
        *,
        reviewer: str,
        determinations: list[dict[str, Any]],
        source_checked_at: str,
        notes: str = "",
    ) -> ArtifactRef:
        creative = self.ledger.get_state(creative_state_id)
        if creative["state_type"] != "CREATIVE_ARTIFACT":
            raise LedgerError("Saudi legal review target must be CREATIVE_ARTIFACT")
        target = creative.get("payload", {}).get("target") or {}
        if str(target.get("jurisdiction") or target.get("region") or "").strip().upper() != "SA":
            raise LedgerError("Saudi legal review requires creative target jurisdiction/region SA")
        if not str(reviewer or "").strip():
            raise LedgerError("Saudi legal review requires an identified specialist reviewer")
        if not str(source_checked_at or "").strip():
            raise LedgerError("Saudi legal review requires source_checked_at")

        by_rule: dict[str, dict[str, Any]] = {}
        for item in determinations:
            if not isinstance(item, dict):
                raise LedgerError("Saudi legal determination must be a structured object")
            rule_id = str(item.get("rule_id") or "").strip().upper()
            status = str(item.get("status") or "").strip().upper()
            reason = str(item.get("reason") or "").strip()
            if rule_id not in SAUDI_CONTENT_RULE_IDS:
                raise LedgerError(f"unknown Saudi content rule: {rule_id}")
            if rule_id in by_rule:
                raise LedgerError(f"duplicate Saudi content rule: {rule_id}")
            if status not in _STATUSES:
                raise LedgerError(f"invalid Saudi legal status for {rule_id}")
            if not reason:
                raise LedgerError(f"Saudi legal determination {rule_id} requires a reason")
            by_rule[rule_id] = {"rule_id": rule_id, "status": status, "reason": reason}

        missing = sorted(SAUDI_CONTENT_RULE_IDS - set(by_rule))
        if missing:
            raise LedgerError("Saudi legal review is incomplete; missing rules: " + ", ".join(missing))

        statuses = {item["status"] for item in by_rule.values()}
        if "BLOCK" in statuses:
            overall = "BLOCK"
        elif "UNRESOLVED" in statuses:
            overall = "UNRESOLVED"
        elif "WARNING" in statuses:
            overall = "WARNING"
        else:
            overall = "PASS"

        payload = {
            "creative_state_id": creative_state_id,
            "review_scope": "legal",
            "verification_status": "HUMAN_REVIEWED",
            "finding_key": SAUDI_ANTI_CYBERCRIME_POLICY["policy_key"],
            "jurisdiction": "SA",
            "policy": SAUDI_ANTI_CYBERCRIME_POLICY,
            "source_checked_at": source_checked_at,
            "reviewer": reviewer.strip(),
            "determinations": [by_rule[key] for key in sorted(by_rule)],
            "status": overall,
            "notes": notes,
            "fixture": False,
            "automated_legal_clearance": False,
        }
        return self.ledger.record_domain(
            "EVIDENCE",
            "Saudi Content Legal Review Authority",
            payload,
            natural_key=f"saudi-cybercrime-review:{creative_state_id}",
            subject_identity_id=self.ledger.subject_identity_for_state(creative_state_id),
            scope=target,
            record_state=overall,
            upstream_states=[(creative_state_id, "SAUDI_LEGAL_REVIEW_TARGET")],
        )

    def compliance_finding(self, review_state_id: str) -> dict[str, Any]:
        state = self.ledger.get_state(review_state_id)
        payload = state.get("payload") or {}
        if state["state_type"] != "EVIDENCE" or payload.get("finding_key") != SAUDI_ANTI_CYBERCRIME_POLICY["policy_key"]:
            raise LedgerError("review_state_id is not a Saudi cybercrime content review")
        return {
            "finding": SAUDI_ANTI_CYBERCRIME_POLICY["policy_key"],
            "status": payload["status"],
            "reason": "specialist determinations recorded against the governed Saudi rule set",
            "evidence_state_ids": [review_state_id],
        }
