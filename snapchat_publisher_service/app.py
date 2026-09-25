import hmac
import os

from flask import Flask, jsonify, request

from publisher import (
    EnvelopeValidationError,
    PublicationGateClosed,
    SpotlightEnvelope,
    build_ayrshare_payload,
    selected_publisher,
    validate_envelope,
)


APP_VERSION = "snapchat-publisher-service-20260925.1"

app = Flask(__name__)


def _owner_authorized() -> bool:
    expected = os.getenv("SNAPCHAT_OWNER_KEY")
    supplied = request.headers.get("X-Owner-Key")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _require_owner():
    if not _owner_authorized():
        return jsonify({"ok": False, "error": "owner_authorization_required"}), 401
    return None


@app.get("/")
def index():
    publisher = selected_publisher()
    readiness = publisher.readiness()
    return jsonify({
        "service": "Trend Radar Snapchat automated publisher",
        "version": APP_VERSION,
        "provider": readiness["provider"],
        "publication_enabled": readiness["publication_enabled"],
        "normal_runtime_human_actions": 0,
        "public_side_effect_default": "BLOCKED",
    })


@app.get("/health")
def health():
    try:
        readiness = selected_publisher().readiness()
        return jsonify({
            "ok": True,
            "version": APP_VERSION,
            "readiness": readiness,
        })
    except Exception as exc:
        return jsonify({
            "ok": False,
            "version": APP_VERSION,
            "error": str(exc),
        }), 503


@app.post("/spotlight/validate")
def validate_spotlight():
    denied = _require_owner()
    if denied:
        return denied

    try:
        envelope = SpotlightEnvelope.from_dict(request.get_json(force=True) or {})
        errors = validate_envelope(envelope)
        payload_preview = None
        if not errors:
            payload_preview = build_ayrshare_payload(
                envelope,
                schedule_time=request.args.get("schedule_time"),
            )
        return jsonify({
            "ok": not errors,
            "errors": errors,
            "market": envelope.market,
            "trend_id": envelope.trend_id,
            "provider_payload_preview": payload_preview,
            "external_publication_side_effect": "NONE",
        }), (200 if not errors else 400)
    except (EnvelopeValidationError, ValueError) as exc:
        return jsonify({
            "ok": False,
            "error": "validation_failed",
            "detail": str(exc),
            "external_publication_side_effect": "NONE",
        }), 400


@app.post("/spotlight/publish")
def publish_spotlight():
    denied = _require_owner()
    if denied:
        return denied

    try:
        body = request.get_json(force=True) or {}
        envelope = SpotlightEnvelope.from_dict(body)
        schedule_time = body.get("schedule_time")
        result = selected_publisher().publish(
            envelope,
            schedule_time=schedule_time,
        )
        return jsonify(result), 201
    except EnvelopeValidationError as exc:
        return jsonify({
            "ok": False,
            "error": "envelope_validation_failed",
            "errors": exc.errors,
        }), 400
    except PublicationGateClosed as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
            "external_publication_side_effect": "BLOCKED",
        }), 403
    except ValueError as exc:
        return jsonify({
            "ok": False,
            "error": "invalid_schedule_time",
            "detail": str(exc),
        }), 400
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": "provider_publish_failed",
            "detail": str(exc),
        }), 502


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
