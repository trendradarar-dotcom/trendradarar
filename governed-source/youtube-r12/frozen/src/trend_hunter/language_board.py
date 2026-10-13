from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from .db import connect
from .ledger import GovernanceLedger, LedgerError
from .publishing_target import APPROVED_PUBLICATION_LANGUAGES, canonical_publication_language


LANGUAGE_BOARD_SCHEMA_VERSION = "LANGUAGE_BOARD_V1"


@dataclass(frozen=True)
class LanguageBoard:
    language_code: str
    priority_markets: list[dict[str, Any]]
    local_trends: dict[str, list[dict[str, Any]]]
    global_top_6: list[dict[str, Any]]
    evidence_contract: dict[str, Any]
    schema_version: str = LANGUAGE_BOARD_SCHEMA_VERSION


class LanguageBoardService:
    """Read-only governed projection over real opportunity records.

    No synthetic popularity score is created. Priority-market ordering is based only
    on the count of current governed opportunities that explicitly carry the language
    and market in their own evidence/scope, with recency used only as a stable tie-break.
    """

    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    @staticmethod
    def _extract_language(payload: dict[str, Any], scope: dict[str, Any]) -> str | None:
        fa = payload.get("factor_assertions") if isinstance(payload.get("factor_assertions"), dict) else {}
        candidates = [
            scope.get("language"),
            payload.get("language"),
            fa.get("language"),
            fa.get("source_language"),
        ]
        for value in candidates:
            raw = str(value or "").strip()
            if not raw:
                continue
            try:
                return canonical_publication_language(raw)
            except Exception:
                continue
        return None

    @staticmethod
    def _extract_market(payload: dict[str, Any], scope: dict[str, Any]) -> str | None:
        fa = payload.get("factor_assertions") if isinstance(payload.get("factor_assertions"), dict) else {}
        candidates = [
            scope.get("market"), scope.get("region"),
            payload.get("target_market"), payload.get("region"),
            fa.get("market"), fa.get("region"),
        ]
        for value in candidates:
            raw = str(value or "").strip().upper()
            if raw == "GLOBAL" or (len(raw) == 2 and raw.isalpha()):
                return raw
        return None

    @staticmethod
    def _title(payload: dict[str, Any]) -> str:
        fa = payload.get("factor_assertions") if isinstance(payload.get("factor_assertions"), dict) else {}
        return str(
            fa.get("observed_title")
            or payload.get("title")
            or payload.get("candidate_key")
            or ""
        ).strip()

    def _current_opportunities(self) -> list[dict[str, Any]]:
        with connect(self.ledger.db_path) as conn:
            rows = conn.execute(
                """
                SELECT s.id,s.identity_id,s.payload_json,s.recorded_at,s.committed_at,d.scope_json,d.record_state
                FROM artifact_state s
                JOIN domain_record d ON d.artifact_state_id=s.id
                WHERE d.stage='OPPORTUNITY'
                  AND s.version=(SELECT MAX(s2.version) FROM artifact_state s2 WHERE s2.identity_id=s.identity_id)
                ORDER BY s.committed_at DESC,s.recorded_at DESC
                """
            ).fetchall()
        out=[]
        for row in rows:
            try:
                payload=json.loads(row["payload_json"])
                scope=json.loads(row["scope_json"] or "{}")
            except Exception:
                continue
            if payload.get("fixture") is True:
                continue
            lang=self._extract_language(payload,scope)
            market=self._extract_market(payload,scope)
            if not lang or not market:
                continue
            out.append({
                "opportunity_state_id":str(row["id"]),
                "opportunity_identity_id":str(row["identity_id"]),
                "language_code":lang,
                "market_code":market,
                "title":self._title(payload),
                "thesis":str(payload.get("thesis") or ""),
                "factor_assertions":payload.get("factor_assertions") or {},
                "scope":scope,
                "record_state":row["record_state"],
                "committed_at":row["committed_at"],
            })
        return out

    def build(self, language_code: str, *, top_markets: int = 6, global_limit: int = 6) -> LanguageBoard:
        language=canonical_publication_language(language_code)
        if language not in APPROVED_PUBLICATION_LANGUAGES:
            raise LedgerError("Language is not approved for global publishing")
        rows=[x for x in self._current_opportunities() if x["language_code"] == language]

        counts=Counter(x["market_code"] for x in rows)
        latest_by_market: dict[str,str] = {}
        for x in rows:
            latest_by_market.setdefault(x["market_code"],str(x.get("committed_at") or ""))
        market_order=sorted(counts, key=lambda m:(-counts[m], latest_by_market.get(m,""), m))[:max(1,int(top_markets))]
        priority=[{
            "market_code":m,
            "governed_opportunity_count":counts[m],
            "ranking_basis":"CURRENT_GOVERNED_OPPORTUNITY_COUNT_WITH_RECENCY_TIE_BREAK_ONLY",
            "not_a_popularity_score":True,
        } for m in market_order]

        local: dict[str,list[dict[str,Any]]] = defaultdict(list)
        for x in rows:
            if x["market_code"] in market_order:
                local[x["market_code"]].append(x)
        local = {m:items[:6] for m,items in local.items()}
        global_top=rows[:max(1,min(6,int(global_limit)))]

        return LanguageBoard(
            language_code=language,
            priority_markets=priority,
            local_trends=local,
            global_top_6=global_top,
            evidence_contract={
                "real_governed_opportunities_only":True,
                "fixtures_excluded":True,
                "unknown_language_or_market_excluded":True,
                "universal_score":None,
                "global_top_6_basis":"MOST_RECENT_CURRENT_GOVERNED_OPPORTUNITIES_FOR_LANGUAGE_ONLY",
                "global_top_6_is_not_popularity_ranking":True,
                "one_public_creative_one_audience_language":True,
            },
        )


class LanguageBoardPresentationAdapter:
    @staticmethod
    def adapt(board: LanguageBoard, mode: str) -> dict[str, Any]:
        mode_norm=str(mode or "").strip().lower()
        if mode_norm not in {"mobile_short_form","snapchat_spotlight","youtube_wide"}:
            raise LedgerError("Unsupported language-board presentation mode")
        return {
            "schema_version":"LANGUAGE_BOARD_PRESENTATION_V1",
            "mode":mode_norm,
            "language_code":board.language_code,
            "priority_markets":board.priority_markets,
            "local_trends":board.local_trends,
            "global_top_6":board.global_top_6,
            "presentation_is_not_source_of_truth":True,
            "source_schema_version":board.schema_version,
        }
