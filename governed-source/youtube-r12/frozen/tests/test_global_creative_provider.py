from __future__ import annotations

import json
import pytest

from trend_hunter.global_creative import GlobalCreativeProvider
from trend_hunter.ledger import LedgerError
from trend_hunter.publishing_target import build_publication_target


class FakeAnalyzer:
    model = "test-model"

    def __init__(self, result):
        self.result = result
        self.body = None

    def _post(self, body):
        self.body = body
        return {
            "id": "resp_test_1",
            "status": "completed",
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                self.result,
                                ensure_ascii=False,
                            ),
                        }
                    ]
                }
            ],
        }


def target(language="fr", jurisdiction="GLOBAL"):
    return build_publication_target(
        source_language="ko",
        publication_language=language,
        target_market="GLOBAL" if jurisdiction == "GLOBAL" else jurisdiction,
        jurisdiction=jurisdiction,
        platform="youtube",
        discovery_market="KR",
    )


def ready(language="fr"):
    return {
        "generation_status": "READY",
        "hold_reason": None,
        "publication_language": language,
        "title": "Titre",
        "hook": "Accroche",
        "body": "Contenu",
        "description": "Description",
        "hashtags": ["#trend"],
        "cta": None,
        "content_format": "short_form_video",
        "source_facts_used": ["fact"],
        "localization_notes": ["adapted"],
    }


def test_reuses_existing_responses_transport_contract():
    fake = FakeAnalyzer(ready("fr"))
    provider = GlobalCreativeProvider(
        target=target("fr"),
        analyzer=fake,
    )
    result = provider.generate(
        {"trend": "example", "facts": ["fact"]}
    )
    assert result["publication_language"] == "fr"
    assert result["_generation"]["automatic"] is True
    assert result["_generation"]["manual_content_input"] is False
    assert fake.body["model"] == "test-model"
    assert '"publication_language":"fr"' in fake.body["input"]


def test_source_language_does_not_restrict_output_language():
    fake = FakeAnalyzer(ready("es"))
    provider = GlobalCreativeProvider(
        target=target("es"),
        analyzer=fake,
    )
    result = provider.generate(
        {"source_language": "ko", "facts": ["fact"]}
    )
    assert result["publication_language"] == "es"
    assert result["target"]["source_language"] == "ko"


def test_hold_fails_closed():
    fake = FakeAnalyzer(
        {
            "generation_status": "HOLD",
            "hold_reason": "missing factual evidence",
            "publication_language": "en",
        }
    )
    provider = GlobalCreativeProvider(
        target=target("en"),
        analyzer=fake,
    )
    with pytest.raises(LedgerError, match="HOLD"):
        provider.generate({"trend": "ambiguous"})


def test_language_mismatch_fails_closed():
    fake = FakeAnalyzer(ready("en"))
    provider = GlobalCreativeProvider(
        target=target("fr"),
        analyzer=fake,
    )
    with pytest.raises(
        LedgerError,
        match="publication_language",
    ):
        provider.generate({"facts": ["fact"]})
