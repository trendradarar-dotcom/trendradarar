from __future__ import annotations

from dataclasses import dataclass

from .db import connect
from .ledger import GovernanceLedger, LedgerError


@dataclass(frozen=True)
class SingleActionPublicationInputs:
    execution_configuration_state_id: str
    channel_binding_state_id: str
    media_descriptor_state_id: str


def _current_stage_ids(
    ledger: GovernanceLedger,
    *,
    subject_identity_id: str,
    stage: str,
    state_type: str,
) -> list[str]:
    with connect(ledger.db_path) as conn:
        rows = conn.execute(
            """
            SELECT s.id
            FROM domain_record d
            JOIN artifact_state s ON s.id=d.artifact_state_id
            WHERE d.subject_identity_id=?
              AND d.stage=?
              AND s.state_type=?
              AND s.effective_to IS NULL
            ORDER BY s.recorded_at DESC, s.version DESC
            """,
            (subject_identity_id, stage, state_type),
        ).fetchall()
    return [str(row["id"]) for row in rows]


def _assert_subject_state(
    ledger: GovernanceLedger,
    state_id: str,
    *,
    expected_type: str,
    subject_identity_id: str,
) -> dict:
    state = ledger.get_state(state_id)
    if state["state_type"] != expected_type:
        raise LedgerError(
            f"{state_id} is not {expected_type}"
        )
    if ledger.subject_identity_for_state(state_id) != subject_identity_id:
        raise LedgerError(
            f"{expected_type} belongs to a different governed subject"
        )
    return state




def _assert_current_channel_binding(ledger: GovernanceLedger, state_id: str) -> dict:
    state = ledger.get_state(state_id)
    if state["state_type"] != "LIVE_CHANNEL_BINDING":
        raise LedgerError(f"{state_id} is not LIVE_CHANNEL_BINDING")
    payload = state.get("payload") or {}
    if "status" in payload and str(payload.get("status") or "").upper() != "ACTIVE":
        raise LedgerError("Exact live channel binding is not ACTIVE")
    with connect(ledger.db_path) as conn:
        row = conn.execute(
            "SELECT id FROM artifact_state WHERE identity_id=? ORDER BY version DESC LIMIT 1",
            (state["identity_id"],),
        ).fetchone()
    if not row or row["id"] != state_id:
        raise LedgerError("Exact live channel binding is stale/superseded")
    return state

def resolve_single_action_publication_inputs(
    ledger: GovernanceLedger,
    creative_state_id: str,
    *,
    execution_configuration_state_id: str | None = None,
    channel_binding_state_id: str | None = None,
    media_descriptor_state_id: str | None = None,
) -> SingleActionPublicationInputs:
    creative = ledger.get_state(creative_state_id)
    if creative["state_type"] != "CREATIVE_ARTIFACT":
        raise LedgerError(
            "Single-action authorization requires CREATIVE_ARTIFACT"
        )

    subject_id = ledger.subject_identity_for_state(creative_state_id)
    creative_payload = creative.get("payload") or {}
    eligibility_state_id = str(
        creative_payload.get("eligibility_state_id") or ""
    ).strip()

    if not eligibility_state_id:
        raise LedgerError(
            "Creative artifact lacks its exact eligibility state"
        )

    if execution_configuration_state_id:
        cfg = _assert_subject_state(
            ledger,
            execution_configuration_state_id,
            expected_type="EXECUTION_CONFIGURATION",
            subject_identity_id=subject_id,
        )
        if str(
            (cfg.get("payload") or {}).get("eligibility_state_id") or ""
        ).strip() != eligibility_state_id:
            raise LedgerError(
                "Execution configuration is not bound to the creative eligibility state"
            )
        cfg_id = execution_configuration_state_id
    else:
        cfg_matches: list[str] = []
        for state_id in _current_stage_ids(
            ledger,
            subject_identity_id=subject_id,
            stage="EXECUTION_CONFIGURATION",
            state_type="EXECUTION_CONFIGURATION",
        ):
            state = ledger.get_state(state_id)
            if str(
                (state.get("payload") or {}).get("eligibility_state_id") or ""
            ).strip() == eligibility_state_id:
                cfg_matches.append(state_id)

        if len(cfg_matches) != 1:
            raise LedgerError(
                "Single-action authorization requires exactly one current execution configuration for the creative eligibility state"
            )

        cfg_id = cfg_matches[0]
        cfg = ledger.get_state(cfg_id)

    cfg_payload = cfg.get("payload") or {}
    cfg_channel_id = str(
        cfg_payload.get("live_channel_binding_state_id")
        or cfg_payload.get("channel_binding_state_id")
        or ""
    ).strip()

    if channel_binding_state_id:
        _assert_current_channel_binding(ledger, channel_binding_state_id)
        if cfg_channel_id and cfg_channel_id != channel_binding_state_id:
            raise LedgerError(
                "Requested channel binding does not match the execution configuration"
            )
        channel_id = channel_binding_state_id
    else:
        if not cfg_channel_id:
            raise LedgerError(
                "Execution configuration lacks its exact live channel binding"
            )
        _assert_current_channel_binding(ledger, cfg_channel_id)
        channel_id = cfg_channel_id

    if media_descriptor_state_id:
        media = _assert_subject_state(
            ledger,
            media_descriptor_state_id,
            expected_type="PUBLICATION_MEDIA_DESCRIPTOR",
            subject_identity_id=subject_id,
        )
        if str(
            (media.get("payload") or {}).get("creative_state_id") or ""
        ).strip() != creative_state_id:
            raise LedgerError(
                "Publication media descriptor is not bound to the exact creative state"
            )
        media_id = media_descriptor_state_id
    else:
        media_matches: list[str] = []
        for state_id in _current_stage_ids(
            ledger,
            subject_identity_id=subject_id,
            stage="PUBLICATION_MEDIA_DESCRIPTOR",
            state_type="PUBLICATION_MEDIA_DESCRIPTOR",
        ):
            state = ledger.get_state(state_id)
            if str(
                (state.get("payload") or {}).get("creative_state_id") or ""
            ).strip() == creative_state_id:
                media_matches.append(state_id)

        if len(media_matches) != 1:
            raise LedgerError(
                "Single-action authorization requires exactly one current publication media descriptor for the creative state"
            )

        media_id = media_matches[0]

    return SingleActionPublicationInputs(
        execution_configuration_state_id=cfg_id,
        channel_binding_state_id=channel_id,
        media_descriptor_state_id=media_id,
    )