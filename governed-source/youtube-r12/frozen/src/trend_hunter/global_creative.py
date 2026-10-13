from __future__ import annotations

import json
from typing import Any

from .ledger import LedgerError
from .openai_platform_analyzer import OpenAIResponsesAnalyzer
from .publishing_target import normalize_publication_target


GLOBAL_CREATIVE_PROVIDER_VERSION = "GLOBAL_CREATIVE_OPENAI_V1"


class GlobalCreativeProvider:
    provider_key = GLOBAL_CREATIVE_PROVIDER_VERSION

    def __init__(
        self,
        *,
        target: dict[str, Any],
        analyzer: OpenAIResponsesAnalyzer | None = None,
    ):
        self.target = normalize_publication_target(target)
        if self.target.get("global_publication_v1") is not True:
            raise LedgerError(
                "automatic global creative generation requires GLOBAL_PUBLICATION_TARGET_V1"
            )
        self.analyzer = analyzer or OpenAIResponsesAnalyzer()

    @staticmethod
    def _extract_output_text(response: dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        texts: list[str] = []
        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())
        if texts:
            return "\n".join(texts)

        raise LedgerError("OpenAI creative response did not contain output text")

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        clean = str(text or "").strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean = "\n".join(lines).strip()
            if clean.lower().startswith("json"):
                clean = clean[4:].lstrip()

        try:
            obj = json.loads(clean)
        except json.JSONDecodeError as exc:
            raise LedgerError("OpenAI creative response was not valid JSON") from exc

        if not isinstance(obj, dict):
            raise LedgerError("OpenAI creative response must be a JSON object")
        return obj

    @staticmethod
    def _instructions() -> str:
        return (
            "You are the governed global creative-generation engine for TrendHunter. "
            "Create original platform-native content from the supplied brief; do not merely translate it. "
            "The source trend may be in any language. Adapt meaning, framing, idiom, examples, and tone "
            "to the requested publication language and target market while preserving factual meaning. "
            "Never invent names, numbers, events, quotes, sources, product claims, or current facts not supplied "
            "in the brief. If supplied evidence is insufficient for a factual creative, return HOLD. "
            "Do not perform Saudi legal clearance and do not claim platform-policy clearance; those are separate gates. "
            "Return JSON only. Required schema: "
            '{"generation_status":"READY|HOLD","hold_reason":null|string,'
            '"publication_language":"string","title":"string","hook":"string","body":"string",'
            '"description":"string","hashtags":["string"],"cta":null|string,"content_format":"string",'
            '"source_facts_used":["string"],"localization_notes":["string"]}. '
            "When generation_status=READY, title, hook, body, description, and content_format must be non-empty. "
            "When generation_status=HOLD, explain the missing or ambiguous evidence in hold_reason."
        )

    def generate(self, brief: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(brief, dict) or not brief:
            raise LedgerError(
                "automatic creative generation requires a non-empty structured brief"
            )

        publication_language = str(
            self.target.get("publication_language") or ""
        ).strip()
        platform = str(self.target.get("platform") or "").strip().lower()

        payload = {
            "target": self.target,
            "brief": brief,
            "generation_contract": {
                "source_language_may_be_any": True,
                "publication_language": publication_language,
                "platform": platform,
                "localization_mode": "ADAPTIVE_NOT_LITERAL",
            },
        }

        response = self.analyzer._post(
            {
                "model": self.analyzer.model,
                "instructions": self._instructions(),
                "input": json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        )

        if not isinstance(response, dict):
            raise LedgerError("OpenAI creative response must be a dict")
        if str(response.get("status") or "").lower() == "incomplete":
            raise LedgerError("OpenAI creative generation was incomplete")

        result = self._parse_json(self._extract_output_text(response))
        status = str(result.get("generation_status") or "").strip().upper()

        if status == "HOLD":
            reason = str(
                result.get("hold_reason") or "insufficient evidence"
            ).strip()
            raise LedgerError(f"automatic creative generation HOLD: {reason}")

        if status != "READY":
            raise LedgerError("creative generation_status must be READY or HOLD")

        returned_language = str(
            result.get("publication_language") or ""
        ).strip()
        if returned_language != publication_language:
            raise LedgerError(
                "creative publication_language does not match governed target"
            )

        for field in (
            "title",
            "hook",
            "body",
            "description",
            "content_format",
        ):
            if not str(result.get(field) or "").strip():
                raise LedgerError(
                    f"creative response missing required field: {field}"
                )

        if not isinstance(result.get("hashtags"), list):
            raise LedgerError("creative hashtags must be a list")

        result["target"] = dict(self.target)
        result["_generation"] = {
            "provider": "openai",
            "provider_key": self.provider_key,
            "model": self.analyzer.model,
            "response_id": response.get("id"),
            "automatic": True,
            "manual_content_input": False,
        }
        return result
