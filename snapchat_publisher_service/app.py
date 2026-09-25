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


APP_VERSION = "snapchat-publisher-service-20260925.2"

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
        body = request.get_json(force=True) or {}
        envelope = SpotlightEnvelope.from_dict(body)
        schedule_time = body.get("schedule_time")
        errors = validate_envelope(envelope)

        if errors:
            return jsonify({
                "ok": False,
                "errors": errors,
                "market": envelope.market,
                "trend_id": envelope.trend_id,
                "publication_id": envelope.publication_id,
                "provider_validation": "NOT_RUN",
                "external_publication_side_effect": "NONE",
            }), 400

        payload_preview = build_ayrshare_payload(
            envelope,
            schedule_time=schedule_time,
        )

        publisher = selected_publisher()
        if not publisher.api_key:
            return jsonify({
                "ok": True,
                "local_validation": "PASS",
                "provider_validation": "BLOCKED_API_KEY_NOT_CONFIGURED",
                "market": envelope.market,
                "trend_id": envelope.trend_id,
                "publication_id": envelope.publication_id,
                "provider_payload_preview": payload_preview,
                "external_publication_side_effect": "NONE",
            }), 200

        provider_result = publisher.validate_provider(
            envelope,
            schedule_time=schedule_time,
        )
        return jsonify({
            "ok": bool(provider_result.get("ok")),
            "local_validation": "PASS",
            "provider_validation": "PASS" if provider_result.get("ok") else "FAIL",
            "market": envelope.market,
            "trend_id": envelope.trend_id,
            "publication_id": envelope.publication_id,
            "provider_result": provider_result,
            "external_publication_side_effect": "NONE",
        }), (200 if provider_result.get("ok") else 400)

    except (EnvelopeValidationError, ValueError) as exc:
        return jsonify({
            "ok": False,
            "error": "validation_failed",
            "detail": str(exc),
            "external_publication_side_effect": "NONE",
        }), 400
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": "provider_validation_failed",
            "detail": str(exc),
            "external_publication_side_effect": "NONE",
        }), 502


@app.get("/spotlight/status/<post_id>")
def spotlight_status(post_id):
    denied = _require_owner()
    if denied:
        return denied
    try:
        body = selected_publisher().get_post_status(post_id)
        return jsonify({
            "ok": True,
            "provider": "ayrshare",
            "post_id": post_id,
            "provider_status": body,
        })
    except PublicationGateClosed as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": "provider_status_failed",
            "detail": str(exc),
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
            "error": "invalid_request",
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
