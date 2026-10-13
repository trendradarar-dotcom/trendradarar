from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

from .connectors.gdelt import GDELTDocConnector
from .connectors.youtube import YouTubeSearchConnector
from .connectors.http import ConnectorHTTPError
from .security import SecretResolver, SecurityError
from .util import utcnow


FAILURE_DISPOSITION = {
    "CREDENTIAL_MISSING": "EXTERNAL_DEPENDENCY",
    "DNS_UNAVAILABLE": "EXTERNAL_DEPENDENCY",
    "NETWORK_UNAVAILABLE": "EXTERNAL_DEPENDENCY",
    "RATE_LIMITED": "EXTERNAL_DEPENDENCY",
    "UPSTREAM_5XX": "EXTERNAL_DEPENDENCY",
    "UPSTREAM_AUTH_FAILURE": "EXTERNAL_DEPENDENCY",
    "UPSTREAM_CONTRACT_CHANGED": "EXTERNAL_DEPENDENCY",
    "RESPONSE_PARSE_FAILURE": "INTERNAL_ENGINEERING_BLOCKER",
    "INTERNAL_CONNECTOR_DEFECT": "INTERNAL_ENGINEERING_BLOCKER",
    "UNKNOWN_FAILURE": "UNRESOLVED",
}


def _failure(provider: str, started: str, failure_class: str, exc: Exception, **extra: Any) -> dict[str, Any]:
    return {
        "provider": provider,
        "ok": False,
        "status": FAILURE_DISPOSITION.get(failure_class, "UNRESOLVED"),
        "failure_class": failure_class,
        "error": f"{type(exc).__name__}: {exc}",
        "started_at": started,
        "finished_at": utcnow(),
        **extra,
    }


def connector_smoke(provider: str, *, query: str = "technology", region: str | None = None, language: str | None = None) -> dict[str, Any]:
    provider = provider.lower().strip()
    started = utcnow()
    try:
        if provider == "gdelt":
            items = GDELTDocConnector(query, maxrecords=1, timeout=15).fetch()
            return {"provider": provider, "ok": True, "status": "PASS", "failure_class": None, "started_at": started, "finished_at": utcnow(), "result_count": len(items), "credential_required": False}
        if provider == "youtube":
            key = SecretResolver.resolve("env://YOUTUBE_API_KEY")
            items = YouTubeSearchConnector(key, query, region_code=region, relevance_language=language, max_results=1, timeout=15, include_statistics=False).fetch()
            return {"provider": provider, "ok": True, "status": "PASS", "failure_class": None, "started_at": started, "finished_at": utcnow(), "result_count": len(items), "credential_required": True, "secret_ref": "env://YOUTUBE_API_KEY"}
        raise ValueError("provider must be gdelt or youtube")
    except SecurityError as exc:
        return _failure(provider, started, "CREDENTIAL_MISSING", exc)
    except ConnectorHTTPError as exc:
        return _failure(provider, started, exc.failure_class, exc, http_status_code=exc.status_code, attempts=exc.attempts)
    except (json.JSONDecodeError, UnicodeDecodeError, ET.ParseError) as exc:
        return _failure(provider, started, "RESPONSE_PARSE_FAILURE", exc)
    except (KeyError, TypeError, AttributeError, AssertionError) as exc:
        return _failure(provider, started, "INTERNAL_CONNECTOR_DEFECT", exc)
    except Exception as exc:
        return _failure(provider, started, "UNKNOWN_FAILURE", exc)
