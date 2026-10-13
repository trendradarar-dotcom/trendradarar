from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .c1_youtube import YouTubePublicationService
from .db import connect
from .execution import ExecutionService
from .ledger import GovernanceLedger, LedgerError
from .media_renderer import LocalCreativeVideoRenderer, renderer_contract_fingerprint
from .operational import OperationalBindingService
from .single_action_resolution import SingleActionPublicationInputs, resolve_single_action_publication_inputs
from .util import utcnow


BUNDLE_SERVICE_VERSION = "PUBLICATION_BUNDLE_PREPARATION_V1"


@dataclass(frozen=True)
class PreparedPublicationBundle:
    creative_state_id: str
    eligibility_state_id: str
    execution_configuration_state_id: str
    channel_binding_state_id: str
    media_descriptor_state_id: str
    media_path: str
    renderer_version: str


class PublicationBundlePreparationService:
    """Prepare exact execution/channel/media inputs before human authorization.

    Channel bindings are operational assets and may have their own governed subject.
    The content subject remains authoritative for creative, eligibility, execution
    configuration and media descriptor. The exact cross-subject relationship is
    explicitly governed through EXECUTION_CONFIGURATION provenance.
    """

    def __init__(self, ledger: GovernanceLedger, *, project_root: str | Path | None = None):
        self.ledger = ledger
        self.execution = ExecutionService(ledger)
        self.bindings = OperationalBindingService(ledger)
        self.youtube = YouTubePublicationService(ledger)
        self.project_root = Path(project_root or Path(ledger.db_path).resolve().parent)

    @staticmethod
    def _payload(state: dict[str, Any]) -> dict[str, Any]:
        payload = state.get("payload")
        if not isinstance(payload, dict):
            raise LedgerError("governed state requires structured payload")
        return payload

    def _assert_latest_state(self, state_id: str, expected_type: str) -> dict[str, Any]:
        state = self.ledger.get_state(state_id)
        if state.get("state_type") != expected_type:
            raise LedgerError(f"Expected {expected_type}")
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                "SELECT id FROM artifact_state WHERE identity_id=? ORDER BY version DESC LIMIT 1",
                (state["identity_id"],),
            ).fetchone()
        if not row or row["id"] != state_id:
            raise LedgerError(f"{expected_type} is stale/superseded")
        return state

    def _current_active_channels(self, platform: str) -> list[dict[str, Any]]:
        platform = str(platform or "").strip().lower()
        with connect(self.ledger.db_path) as conn:
            rows = conn.execute(
                """
                SELECT s.id
                FROM artifact_state s
                JOIN domain_record d ON d.artifact_state_id=s.id
                WHERE d.stage='LIVE_CHANNEL_BINDING'
                  AND s.version=(SELECT MAX(s2.version) FROM artifact_state s2 WHERE s2.identity_id=s.identity_id)
                ORDER BY s.recorded_at DESC
                """
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                state = self.bindings.assert_current_channel_binding(str(row["id"]))
            except LedgerError:
                continue
            payload = self._payload(state)
            if str(payload.get("platform") or "").strip().lower() == platform:
                out.append(state)
        return out

    def _select_channel(self, creative_payload: dict[str, Any], explicit_channel_state_id: str | None) -> dict[str, Any]:
        target = creative_payload.get("target") if isinstance(creative_payload.get("target"), dict) else {}
        platform = str(target.get("platform") or "").strip().lower()
        if not platform:
            raise LedgerError("Creative publication target lacks platform")

        if explicit_channel_state_id:
            channel = self.bindings.assert_current_channel_binding(explicit_channel_state_id)
            if str(self._payload(channel).get("platform") or "").strip().lower() != platform:
                raise LedgerError("Explicit channel platform does not match creative target")
            return channel

        channels = self._current_active_channels(platform)
        if len(channels) != 1:
            raise LedgerError(
                f"Publication bundle requires exactly one current ACTIVE {platform} channel binding; found {len(channels)}"
            )
        return channels[0]

    def _find_exact_configuration(self, subject_id: str, eligibility_state_id: str, channel_state_id: str, platform: str) -> list[str]:
        with connect(self.ledger.db_path) as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.payload_json
                FROM artifact_state s
                JOIN domain_record d ON d.artifact_state_id=s.id
                WHERE d.stage='EXECUTION_CONFIGURATION'
                  AND d.subject_identity_id=?
                  AND s.version=(SELECT MAX(s2.version) FROM artifact_state s2 WHERE s2.identity_id=s.identity_id)
                ORDER BY s.recorded_at DESC
                """,
                (subject_id,),
            ).fetchall()
        import json
        matches: list[str] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                continue
            if (
                str(payload.get("eligibility_state_id") or "") == eligibility_state_id
                and str(payload.get("live_channel_binding_state_id") or "") == channel_state_id
                and str(payload.get("platform") or "").lower() == platform
            ):
                matches.append(str(row["id"]))
        return matches

    def _ensure_configuration(self, creative_state_id: str, eligibility_state_id: str, channel: dict[str, Any]) -> str:
        creative = self.ledger.get_state(creative_state_id)
        cp = self._payload(creative)
        subject_id = self.ledger.subject_identity_for_state(creative_state_id)
        eligibility = self._assert_latest_state(eligibility_state_id, "ELIGIBILITY_ASSESSMENT")
        ep = self._payload(eligibility)
        if ep.get("outcome") != "ELIGIBLE":
            raise LedgerError("Publication bundle requires current ELIGIBLE eligibility state")
        if self.ledger.subject_identity_for_state(eligibility_state_id) != subject_id:
            raise LedgerError("Creative and eligibility belong to different governed subjects")

        opportunity_state_id = str(ep.get("opportunity_state_id") or "").strip()
        if not opportunity_state_id:
            raise LedgerError("Eligibility lacks exact opportunity_state_id")
        self._assert_latest_state(opportunity_state_id, "OPPORTUNITY")

        target = cp.get("target") if isinstance(cp.get("target"), dict) else {}
        platform = str(target.get("platform") or "").strip().lower()
        channel_id = str(channel["id"])
        matches = self._find_exact_configuration(subject_id, eligibility_state_id, channel_id, platform)
        if len(matches) > 1:
            raise LedgerError("More than one current exact execution configuration exists for the publication bundle")
        if len(matches) == 1:
            return matches[0]

        content_form = str(cp.get("content_format") or cp.get("content_type") or "short_form_video").strip()
        ref = self.execution.define_configuration(
            opportunity_state_id,
            eligibility_state_id,
            platform=platform,
            channel=str(self._payload(channel).get("channel_ref") or ""),
            content_form=content_form,
            production_route="LOCAL_GOVERNED_RENDERER",
            actionable_from=None,
            actionable_to=None,
            required_resources={"local_renderer": True, "renderer_contract_sha256": renderer_contract_fingerprint()},
            capital_assumption={"amount": 0, "currency": "SAR", "basis": "local renderer"},
            operational_mode="GOVERNED_AUTOMATED_PREPARATION",
            monetization_scenario=None,
            live_channel_binding_state_id=channel_id,
            require_live_channel_binding=True,
        )
        return ref.state_id

    def _current_media_descriptors(self, creative_state_id: str) -> list[str]:
        subject = self.ledger.subject_identity_for_state(creative_state_id)
        with connect(self.ledger.db_path) as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.payload_json
                FROM artifact_state s
                JOIN domain_record d ON d.artifact_state_id=s.id
                WHERE d.stage='PUBLICATION_MEDIA_DESCRIPTOR'
                  AND d.subject_identity_id=?
                  AND s.version=(SELECT MAX(s2.version) FROM artifact_state s2 WHERE s2.identity_id=s.identity_id)
                ORDER BY s.recorded_at DESC
                """,
                (subject,),
            ).fetchall()
        import json
        out=[]
        for row in rows:
            try: payload=json.loads(row["payload_json"])
            except Exception: continue
            if str(payload.get("creative_state_id") or "") == creative_state_id:
                out.append(str(row["id"]))
        return out

    def _media_output_path(self, creative_state_id: str) -> Path:
        root = self.project_root / "runtime" / "publication_media" / creative_state_id
        root.mkdir(parents=True, exist_ok=True)
        return root / "publication.mp4"

    def _ensure_media(self, creative_state_id: str) -> tuple[str, str]:
        creative = self._assert_latest_state(creative_state_id, "CREATIVE_ARTIFACT")
        cp = self._payload(creative)
        target = cp.get("target") if isinstance(cp.get("target"), dict) else {}
        if str(target.get("platform") or "").strip().lower() != "youtube":
            raise LedgerError("P0 governed local renderer currently supports youtube target only")

        descriptors = self._current_media_descriptors(creative_state_id)
        media_path = self._media_output_path(creative_state_id)
        if len(descriptors) > 1:
            raise LedgerError("More than one current exact publication media descriptor exists for creative")
        if len(descriptors) == 1 and media_path.is_file():
            try:
                self.youtube.assert_media_matches(descriptors[0], media_path, creative_state_id=creative_state_id)
                return descriptors[0], str(media_path)
            except LedgerError:
                pass

        renderer = LocalCreativeVideoRenderer()
        rendered = renderer.render(cp, media_path)
        receipt = self.ledger.record_domain(
            "PUBLICATION_MEDIA_RENDER_RECEIPT",
            "Governed Local Media Rendering Authority",
            {
                "creative_state_id": creative_state_id,
                "renderer_version": rendered.renderer_version,
                "renderer_contract_sha256": renderer_contract_fingerprint(),
                "sha256": rendered.sha256,
                "size_bytes": rendered.size_bytes,
                "duration_seconds": rendered.duration_seconds,
                "width": rendered.width,
                "height": rendered.height,
                "fps": rendered.fps,
                "remote_assets_used": False,
                "factual_content_added": False,
                "rendered_at": utcnow(),
            },
            natural_key=f"publication-media-render:{creative_state_id}:{rendered.sha256}",
            subject_identity_id=self.ledger.subject_identity_for_state(creative_state_id),
            record_state="RENDERED",
            upstream_states=[(creative_state_id, "MEDIA_RENDER_EXACT_CREATIVE")],
        )
        descriptor = self.youtube.create_media_descriptor(
            creative_state_id,
            media_path,
            title=str(cp.get("title") or "TrendHunter").strip()[:100],
            description=str(cp.get("description") or cp.get("body") or "").strip()[:5000],
        )
        self.ledger.add_provenance(receipt.state_id, descriptor.state_id, "MEDIA_DESCRIPTOR_RENDER_RECEIPT")
        return descriptor.state_id, str(media_path)

    def prepare(
        self,
        creative_state_id: str,
        *,
        channel_binding_state_id: str | None = None,
    ) -> PreparedPublicationBundle:
        creative = self._assert_latest_state(creative_state_id, "CREATIVE_ARTIFACT")
        cp = self._payload(creative)
        if cp.get("fixture") is True:
            raise LedgerError("Publication bundle preparation refuses fixture creative")
        eligibility_state_id = str(cp.get("eligibility_state_id") or "").strip()
        if not eligibility_state_id:
            raise LedgerError("Creative lacks exact eligibility_state_id")
        self._assert_latest_state(eligibility_state_id, "ELIGIBILITY_ASSESSMENT")

        channel = self._select_channel(cp, channel_binding_state_id)
        channel_id = str(channel["id"])
        cfg_id = self._ensure_configuration(creative_state_id, eligibility_state_id, channel)
        media_id, media_path = self._ensure_media(creative_state_id)

        resolved: SingleActionPublicationInputs = resolve_single_action_publication_inputs(
            self.ledger,
            creative_state_id,
            execution_configuration_state_id=cfg_id,
            channel_binding_state_id=channel_id,
            media_descriptor_state_id=media_id,
        )
        return PreparedPublicationBundle(
            creative_state_id=creative_state_id,
            eligibility_state_id=eligibility_state_id,
            execution_configuration_state_id=resolved.execution_configuration_state_id,
            channel_binding_state_id=resolved.channel_binding_state_id,
            media_descriptor_state_id=resolved.media_descriptor_state_id,
            media_path=media_path,
            renderer_version="TRENDHUNTER_LOCAL_CARD_VIDEO_V1",
        )
