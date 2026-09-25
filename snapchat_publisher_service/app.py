import hmac
import os
import uuid

from flask import Flask, g, jsonify, request

from audit import audit, safe_correlation_id
from publisher import (
    DisabledSpotlightPublisher,
    EnvelopeValidationError,
    PublicationGateClosed,
    SpotlightEnvelope,
    build_ayrshare_payload,
    control_state,
    selected_publisher,
    validate_envelope,
)


APP_VERSION = "snapchat-publisher-service-20260925.3"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


@app.before_request
def _start_request_context():
    supplied = safe_correlation_id(request.headers.get("X-Correlation-ID"))
    g.correlation_id = supplied or str(uuid.uuid4())


@app.after_request
def _attach_correlation(response):
    response.headers["X-Correlation-ID"] = getattr(g, "correlation_id", "")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _owner_authorized() -> bool:
    expected = os.getenv("SNAPCHAT_OWNER_KEY")
    supplied = request.headers.get("X-Owner-Key")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _require_owner():
    if not _owner_authorized():
        audit(
            "owner_authorization_denied",
            correlation_id=g.correlation_id,
            route=request.path,
            http_status=401,
            external_publication_side_effect="NONE",
        )
        return jsonify({
            "ok": False,
            "error": "owner_authorization_required",
            "correlation_id": g.correlation_id,
        }), 401
    return None


def _readiness():
    publisher = selected_publisher()
    return publisher, publisher.readiness()


@app.get("/")
def index():
    publisher, readiness = _readiness()
    return jsonify({
        "service": "Trend Radar Snapchat automated publisher",
        "version": APP_VERSION,
        "provider": readiness["provider"],
        "provider_configured": readiness["provider_configured"],
        "publication_enabled": readiness["publication_enabled"],
        "kill_switch": readiness["kill_switch"],
        "emergency_read_only": readiness["emergency_read_only"],
        "normal_runtime_human_actions_target": 0,
        "public_side_effect_default": "BLOCKED",
    })


@app.get("/health")
def health():
    try:
        _, readiness = _readiness()
        return jsonify({
            "ok": True,
            "version": APP_VERSION,
            "readiness": readiness,
            "external_publication_side_effect": "NONE",
        })
    except Exception as exc:
        audit(
            "health_failed",
            correlation_id=g.correlation_id,
            error=type(exc).__name__,
            http_status=503,
            external_publication_side_effect="NONE",
        )
        return jsonify({
            "ok": False,
            "version": APP_VERSION,
            "error": "health_failed",
            "correlation_id": g.correlation_id,
        }), 503


@app.get("/admin/control-state")
def admin_control_state():
    denied = _require_owner()
    if denied:
        return denied
    publisher, readiness = _readiness()
    return jsonify({
        "ok": True,
        "version": APP_VERSION,
        "provider": readiness["provider"],
        "control": control_state(),
        "provider_configured": readiness["provider_configured"],
        "external_publication_side_effect": "NONE",
    })


@app.post("/spotlight/validate")
def validate_spotlight():
    denied = _require_owner()
    if denied:
        return denied

    try:
        body = request.get_json(force=True) or {}
        envelope = SpotlightEnvelope.from_dict(body)
        schedule_time = body.get("schedule_time")
        errors = validate_envelope(envelope)

        if errors:
            audit(
                "spotlight_local_validation_failed",
                correlation_id=g.correlation_id,
                publication_id=envelope.publication_id,
                trend_id=envelope.trend_id,
                market=envelope.market,
                status="FAIL",
                http_status=400,
                external_publication_side_effect="NONE",
            )
            return jsonify({
                "ok": False,
                "errors": errors,
                "market": envelope.market,
                "trend_id": envelope.trend_id,
                "publication_id": envelope.publication_id,
                "provider_validation": "NOT_RUN",
                "correlation_id": g.correlation_id,
                "external_publication_side_effect": "NONE",
            }), 400

        payload_preview = build_ayrshare_payload(
            envelope,
            schedule_time=schedule_time,
        )

        publisher = selected_publisher()
        if isinstance(publisher, DisabledSpotlightPublisher):
            audit(
                "spotlight_local_validation_pass_provider_disabled",
                correlation_id=g.correlation_id,
                publication_id=envelope.publication_id,
                trend_id=envelope.trend_id,
                market=envelope.market,
                provider="disabled",
                status="LOCAL_PASS",
                http_status=200,
                external_publication_side_effect="NONE",
            )
            return jsonify({
                "ok": True,
                "local_validation": "PASS",
                "provider_validation": "BLOCKED_PROVIDER_NOT_SELECTED",
                "market": envelope.market,
                "trend_id": envelope.trend_id,
                "publication_id": envelope.publication_id,
                "provider_payload_preview": payload_preview,
                "correlation_id": g.correlation_id,
                "external_publication_side_effect": "NONE",
            }), 200

        if not publisher.provider_validation_available:
            return jsonify({
                "ok": True,
                "local_validation": "PASS",
                "provider_validation": "BLOCKED_PROVIDER_CREDENTIAL_NOT_CONFIGURED",
                "market": envelope.market,
                "trend_id": envelope.trend_id,
                "publication_id": envelope.publication_id,
                "provider_payload_preview": payload_preview,
                "correlation_id": g.correlation_id,
                "external_publication_side_effect": "NONE",
            }), 200

        provider_result = publisher.validate_provider(
            envelope,
            schedule_time=schedule_time,
        )
        ok = bool(provider_result.get("ok"))
        audit(
            "spotlight_provider_validation",
            correlation_id=g.correlation_id,
            publication_id=envelope.publication_id,
            trend_id=envelope.trend_id,
            market=envelope.market,
            provider=provider_result.get("provider"),
            status="PASS" if ok else "FAIL",
            http_status=200 if ok else 400,
            external_publication_side_effect="NONE",
        )
        return jsonify({
            "ok": ok,
            "local_validation": "PASS",
            "provider_validation": "PASS" if ok else "FAIL",
            "market": envelope.market,
            "trend_id": envelope.trend_id,
            "publication_id": envelope.publication_id,
            "provider_result": provider_result,
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "NONE",
        }), (200 if ok else 400)

    except (EnvelopeValidationError, ValueError) as exc:
        audit(
            "spotlight_validation_exception",
            correlation_id=g.correlation_id,
            error=type(exc).__name__,
            http_status=400,
            external_publication_side_effect="NONE",
        )
        return jsonify({
            "ok": False,
            "error": "validation_failed",
            "detail": str(exc),
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "NONE",
        }), 400
    except Exception as exc:
        audit(
            "spotlight_provider_validation_exception",
            correlation_id=g.correlation_id,
            error=type(exc).__name__,
            http_status=502,
            external_publication_side_effect="NONE",
        )
        return jsonify({
            "ok": False,
            "error": "provider_validation_failed",
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "NONE",
        }), 502


@app.get("/spotlight/status/<post_id>")
def spotlight_status(post_id):
    denied = _require_owner()
    if denied:
        return denied
    try:
        publisher = selected_publisher()
        body = publisher.get_post_status(post_id)
        audit(
            "spotlight_status_read",
            correlation_id=g.correlation_id,
            provider=publisher.provider_name,
            status="PASS",
            http_status=200,
            external_publication_side_effect="NONE",
        )
        return jsonify({
            "ok": True,
            "provider": publisher.provider_name,
            "post_id": post_id,
            "provider_status": body,
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "NONE",
        })
    except PublicationGateClosed as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "NONE",
        }), 403
    except ValueError as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "NONE",
        }), 400
    except Exception as exc:
        audit(
            "spotlight_status_exception",
            correlation_id=g.correlation_id,
            error=type(exc).__name__,
            http_status=502,
            external_publication_side_effect="NONE",
        )
        return jsonify({
            "ok": False,
            "error": "provider_status_failed",
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "NONE",
        }), 502


@app.post("/spotlight/publish")
def publish_spotlight():
    denied = _require_owner()
    if denied:
        return denied

    try:
        body = request.get_json(force=True) or {}
        envelope = SpotlightEnvelope.from_dict(body)
        schedule_time = body.get("schedule_time")
        publisher = selected_publisher()

        audit(
            "spotlight_publish_requested",
            correlation_id=g.correlation_id,
            publication_id=envelope.publication_id,
            trend_id=envelope.trend_id,
            market=envelope.market,
            provider=publisher.provider_name,
            status="REQUESTED",
            external_publication_side_effect="PENDING_GATE",
        )

        result = publisher.publish(
            envelope,
            schedule_time=schedule_time,
        )

        audit(
            "spotlight_publish_accepted",
            correlation_id=g.correlation_id,
            publication_id=envelope.publication_id,
            trend_id=envelope.trend_id,
            market=envelope.market,
            provider=publisher.provider_name,
            status="ACCEPTED",
            http_status=201,
            external_publication_side_effect="PROVIDER_REQUEST_SENT",
        )
        result["correlation_id"] = g.correlation_id
        return jsonify(result), 201

    except EnvelopeValidationError as exc:
        return jsonify({
            "ok": False,
            "error": "envelope_validation_failed",
            "errors": exc.errors,
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "NONE",
        }), 400
    except PublicationGateClosed as exc:
        audit(
            "spotlight_publish_blocked",
            correlation_id=g.correlation_id,
            error=str(exc),
            status="BLOCKED",
            http_status=403,
            external_publication_side_effect="NONE",
        )
        return jsonify({
            "ok": False,
            "error": str(exc),
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "BLOCKED",
        }), 403
    except ValueError as exc:
        return jsonify({
            "ok": False,
            "error": "invalid_request",
            "detail": str(exc),
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "NONE",
        }), 400
    except Exception as exc:
        audit(
            "spotlight_publish_exception",
            correlation_id=g.correlation_id,
            error=type(exc).__name__,
            status="ERROR",
            http_status=502,
            external_publication_side_effect="UNKNOWN_PROVIDER_SIDE_EFFECT",
        )
        return jsonify({
            "ok": False,
            "error": "provider_publish_failed",
            "correlation_id": g.correlation_id,
            "external_publication_side_effect": "UNKNOWN_REQUIRES_RECONCILIATION",
        }), 502


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
