from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel, Field

from .bootstrap import bootstrap_governance
from .db import connect, init_db
from .ledger import GovernanceLedger, LedgerError
from .operations import OperationsService
from .pipeline import SyntheticPilotRunner
from .signals import SignalNormalizationService
from .story import StoryService
from .measurement import TrendMeasurementService
from .saturation import SaturationCharacterizationService
from .opportunity import OpportunityService
from .eligibility import EligibilityService
from .execution import ExecutionService
from .economics import EconomicExpectationService
from .prioritization import PrioritizationService
from .monetization import MonetizationService
from .creative import CreativeService, ManualCreativeProvider
from .compliance import ComplianceService
from .platform_auto_review import PlatformPolicyAutoReviewService
from .platform_compliance_bridge import PlatformComplianceBridge
from .saudi_legal import SAUDI_ANTI_CYBERCRIME_POLICY, SaudiCybercrimeReviewService
from .recommendation import PublicationRecommendationService
from .saudi_publication_orchestrator import SaudiPublicationAuthorizationOrchestrator
from .single_action_resolution import resolve_single_action_publication_inputs
from .connectors.base import SourceItem
from .ingest import IngestionService
from .util import utcnow
from .security import HMACTokenAuthority, SecurityError, AuthenticatedActor
from .runtime import configure_runtime_logging, log_event
from .operational import GovernedAuthorizationResolver
from .global_creative import GlobalCreativeProvider
from .publication_bundle import PublicationBundlePreparationService
from .c1_youtube import YouTubeOAuthService, YouTubePublicationService, WindowsDPAPIRefreshTokenStore, EnvironmentRefreshTokenStore
from .language_board import LanguageBoardPresentationAdapter, LanguageBoardService


def _youtube_refresh_token_store_from_runtime() -> object:
    """Select the refresh-token store explicitly for the current runtime.

    Windows keeps the R11 DPAPI behavior by default for backward compatibility.
    Linux/Render must opt in explicitly to the environment-backed secret store.
    Unsupported or missing Linux configuration fails closed.
    """
    backend = str(os.environ.get("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN_STORE") or "").strip().lower()
    if backend == "environment":
        return EnvironmentRefreshTokenStore()
    if backend in {"", "windows-dpapi"}:
        # Preserve R11's Windows default. On Linux this class itself fails closed,
        # so Render must explicitly select the environment backend to proceed.
        return WindowsDPAPIRefreshTokenStore()
    raise LedgerError("Unsupported YouTube refresh-token store backend")


class HumanAuthorizationIn(BaseModel):
    recommendation_state_id: str
    execution_configuration_state_id: str | None = None
    channel_binding_state_id: str | None = None
    media_descriptor_state_id: str | None = None
    authorizer: str | None = None
    decision: str
    notes: str = ""


class SaudiSingleActionAuthorizationIn(BaseModel):
    creative_state_id: str
    reviewer: str
    determinations: list[dict]
    source_checked_at: str
    execution_configuration_state_id: str | None = None
    channel_binding_state_id: str | None = None
    media_descriptor_state_id: str | None = None
    notes: str = ""


class CommercialAuthorizationIn(BaseModel):
    monetization_configuration_state_id: str
    authorizer: str | None = None
    decision: str
    notes: str = ""


class MonetizationActivationIn(BaseModel):
    monetization_configuration_state_id: str
    dependency_state_ids: list[str] = Field(default_factory=list)
    provider_result_ref: str | None = None


class PublicationExecutionIn(BaseModel):
    creative_state_id: str
    authorization_state_id: str
    channel_binding_state_id: str | None = None
    channel: str | None = None
    external_result_ref: str
    monetization_activation_state_id: str | None = None


class YouTubePrivateUploadIn(BaseModel):
    creative_state_id: str
    authorization_state_id: str
    oauth_grant_state_id: str
    oauth_client_id: str
    monetization_activation_state_id: str | None = None


class OutcomeIn(BaseModel):
    publication_state_id: str
    performance: dict[str, Any]
    revenue: dict[str, Any]
    costs: list[dict[str, Any]]
    attribution: dict[str, Any]
    evidence_state_ids: list[str] = Field(default_factory=list)



class ManualSourceItemIn(BaseModel):
    source_name: str
    external_id: str
    observed_at: str | None = None
    payload: dict[str, Any]

class ManualSourceBatchIn(BaseModel):
    items: list[ManualSourceItemIn]

class SignalFromSourceIn(BaseModel):
    source_state_id: str

class StoryBindIn(BaseModel):
    story_key: str
    source_or_claim_state_ids: list[str]
    basis: str
    human_reviewed: bool = False

class TrendMeasureIn(BaseModel):
    story_state_id: str
    signal_state_ids: list[str]
    scope: dict[str, Any]
    window: dict[str, Any]

class SaturationIn(BaseModel):
    trend_state_id: str
    eligible_supply_value: float | None = None
    baseline_value: float | None = None
    baseline_contract: dict[str, Any]
    coverage: str
    uncertainty: dict[str, Any] | str

class OpportunityIn(BaseModel):
    candidate_key: str
    story_state_id: str
    role_bound_scope: dict[str, Any]
    thesis: str
    factor_state_ids: list[str]
    factor_assertions: dict[str, Any]

class EligibilityIn(BaseModel):
    opportunity_state_id: str
    target: dict[str, Any]
    political_risk_determination: str | None = None
    other_findings: list[dict[str, Any]] = Field(default_factory=list)

class ExecutionConfigurationIn(BaseModel):
    opportunity_state_id: str
    eligibility_state_id: str
    platform: str
    channel: str | None = None
    content_form: str
    production_route: str
    actionable_from: str | None = None
    actionable_to: str | None = None
    required_resources: dict[str, Any] = Field(default_factory=dict)
    capital_assumption: dict[str, Any] = Field(default_factory=dict)
    operational_mode: str
    monetization_scenario: dict[str, Any] | None = None
    live_channel_binding_state_id: str | None = None

class EconomicExpectationIn(BaseModel):
    execution_configuration_state_id: str
    mechanism: str
    horizon: str
    scenarios: list[dict[str, Any]]
    coverage: str
    uncertainty: dict[str, Any]

class FeasibilityIn(BaseModel):
    execution_configuration_state_id: str
    constraints: dict[str, Any]
    outcome: str
    rationale: dict[str, Any]

class PrioritizationIn(BaseModel):
    economic_state_id: str
    feasibility_state_id: str
    policy_key: str
    policy_version: int
    decision: str
    rationale: dict[str, Any]

class MonetizationConfigIn(BaseModel):
    priority_state_id: str
    mechanism: str
    provider: str | None = None
    account_ref: str | None = None
    offer_or_product_ref: str | None = None
    campaign_ref: str | None = None
    tracked_destination: str | None = None
    attribution: dict[str, Any] = Field(default_factory=dict)
    payout_terms: dict[str, Any] = Field(default_factory=dict)
    currency: str | None = None
    commercial_authorization_ref: str | None = None
    requires_commercial_authorization: bool = False
    activation_requirements: list[dict[str, Any]] | None = None

class ManualCreativeIn(BaseModel):
    eligibility_state_id: str
    monetization_configuration_state_id: str | None = None
    target: dict[str, Any]
    brief: dict[str, Any]
    content: dict[str, Any]

class AutoCreativeIn(BaseModel):
    eligibility_state_id: str
    monetization_configuration_state_id: str | None = None
    target: dict[str, Any]
    brief: dict[str, Any]


class ComplianceIn(BaseModel):
    creative_state_id: str
    eligibility_state_id: str
    target: dict[str, Any]
    legal_findings: list[dict[str, Any]] = Field(default_factory=list)
    platform_findings: list[dict[str, Any]] = Field(default_factory=list)
    coverage_state: str
    gate_decision: str
    strict_c1: bool = False

class PublicationBundlePrepareIn(BaseModel):
    creative_state_id: str
    channel_binding_state_id: str | None = None


class SaudiCybercrimeReviewIn(BaseModel):
    creative_state_id: str
    reviewer: str
    determinations: list[dict[str, Any]]
    source_checked_at: str
    notes: str = ""

class RecommendationIn(BaseModel):
    creative_state_id: str
    eligibility_state_id: str
    compliance_state_id: str

def create_app(db_path: str, *, auth_required: bool | None = None) -> FastAPI:
    init_db(db_path)
    ledger = GovernanceLedger(db_path)
    bootstrap_governance(ledger)
    ops = OperationsService(ledger)
    signal_service = SignalNormalizationService(ledger)
    story_service = StoryService(ledger)
    trend_service = TrendMeasurementService(ledger)
    saturation_service = SaturationCharacterizationService(ledger)
    opportunity_service = OpportunityService(ledger)
    eligibility_service = EligibilityService(ledger)
    execution_service = ExecutionService(ledger)
    economics_service = EconomicExpectationService(ledger)
    prioritization_service = PrioritizationService(ledger)
    monetization_service = MonetizationService(ledger)
    creative_service = CreativeService(ledger)
    compliance_service = ComplianceService(ledger)
    platform_auto_review_service = PlatformPolicyAutoReviewService(ledger)
    platform_compliance_bridge = PlatformComplianceBridge(ledger, compliance_service, platform_auto_review_service)
    platform_compliance_bridge.enforce_governed_saudi_review = True
    saudi_legal_service = SaudiCybercrimeReviewService(ledger)
    recommendation_service = PublicationRecommendationService(ledger)
    ingestion_service = IngestionService(ledger)
    project_root = Path(db_path).resolve().parent.parent if Path(db_path).resolve().parent.name.lower() == "data" else Path(db_path).resolve().parent
    publication_bundle_service = PublicationBundlePreparationService(ledger, project_root=project_root)
    language_board_service = LanguageBoardService(ledger)

    app = FastAPI(title="صيّاد الترند — Global Trend Opportunity Engine", version="0.4.5-saudi-legal-review-ui")
    if auth_required is None:
        auth_required = os.environ.get("TREND_HUNTER_AUTH_REQUIRED", "0").lower() in {"1", "true", "yes", "on"}
    token_authority = HMACTokenAuthority.from_env() if auth_required else None
    authz_resolver = GovernedAuthorizationResolver(ledger) if auth_required else None
    runtime_logger = configure_runtime_logging()

    # PUBLIC_HEALTH_MINIMAL is the only unauthenticated operational HTTP surface when auth is enabled.
    def _route_policy(request: Request) -> tuple[str, str] | None:
        path = request.url.path
        method = request.method.upper()
        if path == "/health":
            return None
        if method in {"GET", "HEAD"}:
            return ("reader", "internal:read")
        post = {
            "/api/demo/run": ("operator", "demo:run"),
            "/api/source/manual": ("operator", "source:write"),
            "/api/signal/from-source": ("operator", "signal:write"),
            "/api/story/bind": ("operator", "story:write"),
            "/api/trend/measure": ("operator", "trend:write"),
            "/api/saturation/characterize": ("operator", "saturation:write"),
            "/api/opportunity/candidate": ("operator", "opportunity:write"),
            "/api/eligibility/assess": ("operator", "eligibility:write"),
            "/api/execution/configure": ("operator", "execution:configure"),
            "/api/economics/estimate": ("operator", "economics:write"),
            "/api/feasibility/assess": ("operator", "feasibility:write"),
            "/api/prioritization/decide": ("operator", "prioritization:write"),
            "/api/monetization/configure": ("operator", "monetization:configure"),
            "/api/creative/manual": ("operator", "creative:write"),
            "/api/compliance/assess": ("operator", "compliance:write"),
            "/api/compliance/saudi-cybercrime/review": ("operator", "compliance:write"),
            "/api/publication/recommend": ("operator", "recommendation:write"),
            "/api/human-authorization": ("publisher_authorizer", "publication:authorize"),
            "/api/commercial-authorization": ("commercial_authorizer", "commercial:authorize"),
            "/api/monetization/activate": ("commercial_operator", "monetization:activate"),
            "/api/publication/execute": ("publication_operator", "publication:execute"),
            "/api/youtube/private-upload": ("publication_operator", "publication:execute"),
            "/api/outcome": ("finance_operator", "economics:record"),
            "/api/compliance/saudi-cybercrime/authorize": ("publisher_authorizer", "publication:authorize"),
            "/api/publication/bundle/prepare": ("operator", "publication:prepare"),
        }
        return post.get(path, ("operator", "internal:mutate"))

    def _request_peer_host(request: Request) -> str:
        return str(request.client.host if request.client else "").strip().lower()

    def _is_loopback_peer(request: Request) -> bool:
        peer = _request_peer_host(request)
        if peer in {"testclient", "localhost"}:
            return True
        try:
            return ipaddress.ip_address(peer).is_loopback
        except ValueError:
            return False

    def _transport_boundary_allows(request: Request) -> tuple[bool, str | None]:
        host = (request.url.hostname or "").lower()
        local_hosts = {"127.0.0.1", "localhost", "::1", "testserver"}
        # A client-controlled Host header is not evidence of loopback origin.
        if host in local_hosts and _is_loopback_peer(request):
            return True, None
        mode = os.environ.get("TREND_HUNTER_TRANSPORT_SECURITY", "LOOPBACK_ONLY").strip().upper()
        payload: dict[str, Any] = {}
        with connect(db_path) as conn:
            row = conn.execute(
                """SELECT s.payload_json,d.record_state FROM artifact_identity i
                   JOIN artifact_state s ON s.identity_id=i.id
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE i.kind='NETWORK_TRANSPORT_SECURITY_BINDING' AND i.natural_key='network-transport-security'
                   ORDER BY s.version DESC LIMIT 1"""
            ).fetchone()
        bound_mode = None
        if row and row["record_state"] == "ACTIVE":
            try:
                payload = json.loads(row["payload_json"]); bound_mode = str(payload.get("mode") or "").upper() if payload.get("status") == "ACTIVE" else None
            except Exception:
                payload = {}; bound_mode = None
        if mode != bound_mode:
            return False, "Runtime transport mode is not backed by the current governed transport-security binding"

        endpoint = str(payload.get("endpoint") or "").strip()
        if endpoint:
            parsed = urlparse(endpoint)
            expected_host = (parsed.hostname or "").lower()
            expected_port = parsed.port
            request_port = request.url.port
            if expected_host and host != expected_host:
                return False, "Request Host does not match the governed transport endpoint"
            if expected_port is not None and request_port != expected_port:
                return False, "Request port does not match the governed transport endpoint"

        if mode == "DIRECT_TLS":
            return (request.url.scheme.lower() == "https", "DIRECT_TLS requires HTTPS request scheme")
        if mode == "TRUSTED_TLS_TERMINATING_REVERSE_PROXY":
            trusted_headers = os.environ.get("TREND_HUNTER_TRUST_PROXY_HEADERS", "0").lower() in {"1","true","yes","on"}
            forwarded = request.headers.get("X-Forwarded-Proto", "").lower() == "https"
            trusted_proxy_ips = {str(x).strip() for x in (payload.get("metadata") or {}).get("trusted_proxy_ips", []) if str(x).strip()}
            peer_trusted = _request_peer_host(request) in trusted_proxy_ips
            return (
                trusted_headers and forwarded and peer_trusted,
                "Trusted reverse-proxy mode requires explicitly trusted proxy headers, X-Forwarded-Proto=https, and an exact governed proxy peer IP",
            )
        return False, "Non-loopback exposure is forbidden in LOOPBACK_ONLY mode"

    @app.middleware("http")
    async def governed_authentication_boundary(request: Request, call_next):
        request.state.actor = None
        request.state.bound_authorization = None

        # Transport safety is not optional merely because application authentication was disabled.
        # LOOPBACK_ONLY may run structurally without auth for local development, but any non-loopback
        # request requires BOTH governed authentication and a governed secure-transport mode.
        host = (request.url.hostname or "").lower()
        local_hosts = {"127.0.0.1", "localhost", "::1", "testserver"}
        local_request = host in local_hosts and _is_loopback_peer(request)
        if not local_request and not auth_required:
            return JSONResponse(
                status_code=503,
                content={"detail": "Non-loopback exposure requires governed authentication plus governed secure transport"},
            )
        if auth_required:
            allowed, reason = _transport_boundary_allows(request)
            if not allowed:
                return JSONResponse(status_code=503, content={"detail": reason or "Network transport security boundary not satisfied"})
        policy = _route_policy(request) if auth_required else None
        if auth_required and policy is not None:
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return JSONResponse(status_code=401, content={"detail": "Authenticated bearer identity required for internal/read or mutation surface"})
            try:
                actor = token_authority.verify(header[7:].strip()) if token_authority else None
                bound = authz_resolver.require(actor, policy[0], policy[1]) if authz_resolver and actor else None
            except SecurityError as exc:
                return JSONResponse(status_code=401, content={"detail": str(exc)})
            except LedgerError as exc:
                return JSONResponse(status_code=403, content={"detail": str(exc)})
            request.state.actor = actor
            request.state.bound_authorization = bound
        actor = getattr(request.state, "actor", None)
        bound = getattr(request.state, "bound_authorization", None)
        log_event(
            runtime_logger, "request_start", method=request.method, path=request.url.path,
            actor=actor.subject if actor else None,
            operator_binding_state_id=bound.operator_binding_state_id if bound else None,
        )
        response = await call_next(request)
        log_event(
            runtime_logger, "request_end", method=request.method, path=request.url.path, status_code=response.status_code,
            actor=actor.subject if actor else None,
            operator_binding_state_id=bound.operator_binding_state_id if bound else None,
        )
        return response

    def require_role(request: Request, role: str):
        if not auth_required:
            return None
        bound = getattr(request.state, "bound_authorization", None)
        if bound is None:
            raise HTTPException(401, "Authenticated governed operator binding required")
        if bound.authorized_role != role:
            raise HTTPException(403, f"Governed role required: {role}")
        return bound

    @app.get("/health")
    def health():
        # Deliberately minimal public health surface; governance state is internal/authenticated.
        result = ledger.integrity_check()
        return {"status": "ok" if result["ok"] else "degraded"}

    def _build_source_status(conn):
        catalog = [
            {"key": "youtube", "name": "YouTube", "mode": "LIVE API / GLOBAL"},
            {"key": "google_trends", "name": "Google Trends", "mode": "LIVE RSS"},
            {"key": "gdelt", "name": "GDELT", "mode": "LIVE API / GLOBAL"},
            {"key": "tiktok", "name": "TikTok Creative Center", "mode": "SNAPSHOT"},
            {"key": "instagram", "name": "Instagram", "mode": "SNAPSHOT"},
            {"key": "snapchat", "name": "Snapchat Spotlight", "mode": "SNAPSHOT"},
        ]
        state = {
            item["key"]: {
                **item,
                "record_count": 0,
                "status": "NOT_TESTED" if item["mode"] == "LIVE API" else "READY_NO_DATA",
                "failure_class": None,
            }
            for item in catalog
        }

        def source_key(value):
            text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
            if not text:
                return None
            if "youtube" in text:
                return "youtube"
            if "gdelt" in text:
                return "gdelt"
            if "google" in text and "trend" in text:
                return "google_trends"
            if "tiktok" in text:
                return "tiktok"
            if "instagram" in text:
                return "instagram"
            if "snapchat" in text:
                return "snapchat"
            return None

        def find_source(obj):
            if isinstance(obj, dict):
                for key in ("source_name", "provider", "connector", "source", "platform"):
                    if key in obj:
                        found = source_key(obj.get(key))
                        if found:
                            return found
                for value in obj.values():
                    found = find_source(value)
                    if found:
                        return found
            elif isinstance(obj, list):
                for value in obj:
                    found = find_source(value)
                    if found:
                        return found
            return None

        try:
            rows = conn.execute(
                """
                SELECT d.rowid,d.stage,d.record_state,a.payload_json
                FROM domain_record AS d
                JOIN artifact_state AS a
                  ON a.id = d.artifact_state_id
                WHERE d.stage IN ('SOURCE_RECORD','LIVE_CONNECTOR_SMOKE')
                ORDER BY d.rowid
                """
            ).fetchall()
        except Exception:
            rows = []

        for row in rows:
            item = dict(row)
            try:
                payload = json.loads(item.get("payload_json") or "{}")
            except Exception:
                payload = {}

            key = find_source(payload)
            if not key or key not in state:
                continue

            if item.get("stage") == "SOURCE_RECORD":
                state[key]["record_count"] += 1
                if state[key]["mode"] != "LIVE API":
                    state[key]["status"] = "DATA_AVAILABLE"
                elif state[key]["status"] == "NOT_TESTED":
                    state[key]["status"] = "OBSERVED"

            if item.get("stage") == "LIVE_CONNECTOR_SMOKE":
                failure = str(payload.get("failure_class") or "").strip().upper() or None
                raw_status = str(payload.get("status") or "").strip().upper()
                ok = payload.get("ok")
                if failure and ("RATE" in failure or "THROTT" in failure):
                    status = "RATE_LIMITED"
                elif raw_status in {"PASS", "OK", "SUCCESS"} or ok is True:
                    status = "PASS"
                elif raw_status in {"FAIL", "FAILED", "ERROR"} or ok is False:
                    status = "FAIL"
                else:
                    status = "UNKNOWN"
                state[key]["status"] = status
                state[key]["failure_class"] = failure

        return [state[item["key"]] for item in catalog]

    @app.get("/api/status")
    def status():
        with connect(db_path) as conn:
            contracts = [dict(r) for r in conn.execute(
                "SELECT contract_key,version,status,effective_from,effective_to FROM governance_contract_version ORDER BY contract_key,version"
            )]
            stages = [dict(r) for r in conn.execute(
                "SELECT stage,record_state,count(*) n FROM domain_record GROUP BY stage,record_state ORDER BY stage,record_state"
            )]
            methods = [dict(r) for r in conn.execute(
                "SELECT methodology_key,version,status FROM methodology_version ORDER BY methodology_key,version"
            )]
            source_status = _build_source_status(conn)
        return {
            "architecture": "COMPLETE",
            "engineering": "IMPLEMENTATION_DELIVERY_CANDIDATE",
            "current_stage": "OPERATIONALIZATION_ENFORCEMENT_READINESS_O1_1",
            "production_auth_required": bool(auth_required),
            "production_auth_configured": token_authority is not None,
            "contracts": contracts,
            "methodologies": methods,
            "domain_counts": stages,
                "source_status": source_status,
            "saudi_legal_filter": {
                "status": "INSTALLED",
                "policy_key": SAUDI_ANTI_CYBERCRIME_POLICY["policy_key"],
                "version": SAUDI_ANTI_CYBERCRIME_POLICY["version"],
                "rule_count": len(SAUDI_ANTI_CYBERCRIME_POLICY["rules"]),
                "automated_legal_clearance": False,
            },
        }

    @app.get("/api/language-board/{language_code}")
    def language_board(language_code: str, mode: str = "youtube_wide"):
        try:
            board = language_board_service.build(language_code)
            return LanguageBoardPresentationAdapter.adapt(board, mode)
        except (LedgerError, ValueError) as e:
            raise HTTPException(400, str(e))

    @app.get("/api/compliance/saudi-cybercrime/policy")
    def saudi_cybercrime_policy():
        return SAUDI_ANTI_CYBERCRIME_POLICY

    @app.post("/api/demo/run")
    def run_demo():
        try:
            res = SyntheticPilotRunner(ledger).run()
            return res.__dict__
        except LedgerError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/artifact/{state_id}")
    def artifact(state_id: str):
        try:
            state = ledger.get_state(state_id)
        except LedgerError as e:
            raise HTTPException(404, str(e))
        with connect(db_path) as conn:
            inbound = [dict(r) for r in conn.execute("SELECT * FROM provenance_edge WHERE to_state_id=?", (state_id,))]
            outbound = [dict(r) for r in conn.execute("SELECT * FROM provenance_edge WHERE from_state_id=?", (state_id,))]
        return {"state": state, "provenance_in": inbound, "provenance_out": outbound}

    @app.get("/api/domain/{stage}")
    def domain(stage: str, limit: int = 100):
        limit = max(1, min(limit, 500))
        with connect(db_path) as conn:
            rows = conn.execute(
                """SELECT d.*, s.version,s.state_type,s.recorded_at,s.committed_at,s.effective_from,s.effective_to,s.payload_json
                   FROM domain_record d JOIN artifact_state s ON s.id=d.artifact_state_id
                   WHERE d.stage=? ORDER BY s.committed_at DESC LIMIT ?""",
                (stage, limit),
            ).fetchall()
        out=[]
        for r in rows:
            x=dict(r); x["payload"] = json.loads(x.pop("payload_json")); out.append(x)
        return out


    @app.post("/api/source/manual")
    def source_manual(req: ManualSourceBatchIn):
        items=[]
        for x in req.items:
            observed=x.observed_at or utcnow()
            payload=dict(x.payload)
            if x.observed_at is None:
                payload.setdefault("_observed_at_basis","INGESTION_TIME")
            items.append(SourceItem(x.source_name,x.external_id,observed,payload))
        try:
            refs=ingestion_service.ingest(items,"manual_api")
            return [r.__dict__ for r in refs]
        except (LedgerError,ValueError) as e:
            raise HTTPException(400,str(e))

    @app.post("/api/signal/from-source")
    def signal_from_source(req: SignalFromSourceIn):
        try:
            return signal_service.from_source(req.source_state_id).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/story/bind")
    def story_bind(req: StoryBindIn):
        try:
            return story_service.bind_story(req.story_key,req.source_or_claim_state_ids,basis=req.basis,human_reviewed=req.human_reviewed).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/trend/measure")
    def trend_measure(req: TrendMeasureIn):
        try:
            return trend_service.measure(req.story_state_id,req.signal_state_ids,scope=req.scope,window=req.window).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/saturation/characterize")
    def saturation_characterize(req: SaturationIn):
        try:
            return saturation_service.content_supply_occupancy(req.trend_state_id,eligible_supply_value=req.eligible_supply_value,baseline_value=req.baseline_value,baseline_contract=req.baseline_contract,coverage=req.coverage,uncertainty=req.uncertainty).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/opportunity/candidate")
    def opportunity_candidate(req: OpportunityIn):
        try:
            return opportunity_service.create_candidate(req.candidate_key,story_state_id=req.story_state_id,role_bound_scope=req.role_bound_scope,thesis=req.thesis,factor_state_ids=req.factor_state_ids,factor_assertions=req.factor_assertions).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/eligibility/assess")
    def eligibility_assess(req: EligibilityIn):
        try:
            return eligibility_service.assess(req.opportunity_state_id,target=req.target,political_risk_determination=req.political_risk_determination,other_findings=req.other_findings).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/execution/configure")
    def execution_configure(req: ExecutionConfigurationIn):
        try:
            return execution_service.define_configuration(req.opportunity_state_id,req.eligibility_state_id,platform=req.platform,channel=req.channel,content_form=req.content_form,production_route=req.production_route,actionable_from=req.actionable_from,actionable_to=req.actionable_to,required_resources=req.required_resources,capital_assumption=req.capital_assumption,operational_mode=req.operational_mode,monetization_scenario=req.monetization_scenario,live_channel_binding_state_id=req.live_channel_binding_state_id,require_live_channel_binding=bool(auth_required)).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/economics/estimate")
    def economics_estimate(req: EconomicExpectationIn):
        try:
            return economics_service.estimate(req.execution_configuration_state_id,mechanism=req.mechanism,horizon=req.horizon,scenarios=req.scenarios,coverage=req.coverage,uncertainty=req.uncertainty).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/feasibility/assess")
    def feasibility_assess(req: FeasibilityIn):
        try:
            return execution_service.assess_feasibility(req.execution_configuration_state_id,constraints=req.constraints,outcome=req.outcome,rationale=req.rationale).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/prioritization/decide")
    def prioritization_decide(req: PrioritizationIn):
        try:
            return prioritization_service.decide(req.economic_state_id,req.feasibility_state_id,policy_key=req.policy_key,policy_version=req.policy_version,decision=req.decision,rationale=req.rationale).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/monetization/configure")
    def monetization_configure(req: MonetizationConfigIn):
        try:
            return monetization_service.configure(req.priority_state_id,mechanism=req.mechanism,provider=req.provider,account_ref=req.account_ref,offer_or_product_ref=req.offer_or_product_ref,campaign_ref=req.campaign_ref,tracked_destination=req.tracked_destination,attribution=req.attribution,payout_terms=req.payout_terms,currency=req.currency,commercial_authorization_ref=req.commercial_authorization_ref,requires_commercial_authorization=req.requires_commercial_authorization,activation_requirements=req.activation_requirements).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/creative/manual")
    def creative_manual(req: ManualCreativeIn):
        try:
            return creative_service.create(req.eligibility_state_id,req.monetization_configuration_state_id,target=req.target,brief=req.brief,provider=ManualCreativeProvider(req.content)).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/creative/auto")
    def creative_auto(req: AutoCreativeIn):
        try:
            provider = GlobalCreativeProvider(target=req.target)
            return creative_service.create(
                req.eligibility_state_id,
                req.monetization_configuration_state_id,
                target=req.target,
                brief=req.brief,
                provider=provider,
            ).__dict__
        except (LedgerError, RuntimeError, ValueError) as e:
            raise HTTPException(400, str(e))

    @app.post("/api/compliance/assess")
    def compliance_assess(req: ComplianceIn):
        try:
            return platform_compliance_bridge.assess(
                creative_state_id=req.creative_state_id,
                eligibility_state_id=req.eligibility_state_id,
                target=req.target,
                legal_findings=req.legal_findings,
                coverage_state=req.coverage_state,
                gate_decision=req.gate_decision,
                strict_c1=req.strict_c1,
            ).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/publication/bundle/prepare")
    def publication_bundle_prepare(req: PublicationBundlePrepareIn):
        try:
            return publication_bundle_service.prepare(
                req.creative_state_id,
                channel_binding_state_id=req.channel_binding_state_id,
            ).__dict__
        except LedgerError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/publication/bundle/media/{creative_state_id}")
    def publication_bundle_media(creative_state_id: str):
        try:
            state = ledger.get_state(creative_state_id)
            if state.get("state_type") != "CREATIVE_ARTIFACT":
                raise LedgerError("Expected CREATIVE_ARTIFACT")
            media_path = publication_bundle_service._media_output_path(creative_state_id)
            if not media_path.is_file():
                raise LedgerError("Publication media has not been prepared yet")
            return FileResponse(str(media_path), media_type="video/mp4", filename=media_path.name)
        except LedgerError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/compliance/saudi-cybercrime/review")
    def saudi_cybercrime_review(req: SaudiCybercrimeReviewIn):
        try:
            review = saudi_legal_service.review(
                req.creative_state_id, reviewer=req.reviewer,
                determinations=req.determinations, source_checked_at=req.source_checked_at,
                notes=req.notes,
            )
            return {**review.__dict__, "legal_finding": saudi_legal_service.compliance_finding(review.state_id)}
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/compliance/saudi-cybercrime/authorize")
    def saudi_cybercrime_authorize(req: SaudiSingleActionAuthorizationIn, request: Request):
        bound = require_role(request, "publisher_authorizer")

        authorizer = (
            bound.actor.subject
            if bound is not None
            else str(req.reviewer or "").strip()
        )

        if not authorizer:
            raise HTTPException(
                400,
                "Saudi reviewer identity is required for local single-action authorization",
            )

        if (
            bound is not None
            and str(req.reviewer or "").strip()
            and str(req.reviewer).strip() != str(authorizer).strip()
        ):
            raise HTTPException(
                400,
                "Saudi reviewer must match the authenticated governed publisher authorizer",
            )

        try:
            creative = ledger.get_state(req.creative_state_id)
            creative_payload = creative.get("payload") or {}
            eligibility_state_id = str(
                creative_payload.get("eligibility_state_id") or ""
            ).strip()

            if not eligibility_state_id:
                raise LedgerError(
                    "Creative artifact lacks the exact eligibility state required for single-action authorization"
                )

            if (
                req.execution_configuration_state_id
                and req.channel_binding_state_id
                and req.media_descriptor_state_id
            ):
                publication_inputs = resolve_single_action_publication_inputs(
                    ledger,
                    req.creative_state_id,
                    execution_configuration_state_id=req.execution_configuration_state_id,
                    channel_binding_state_id=req.channel_binding_state_id,
                    media_descriptor_state_id=req.media_descriptor_state_id,
                )
            else:
                prepared = publication_bundle_service.prepare(
                    req.creative_state_id,
                    channel_binding_state_id=req.channel_binding_state_id,
                )
                publication_inputs = resolve_single_action_publication_inputs(
                    ledger,
                    req.creative_state_id,
                    execution_configuration_state_id=prepared.execution_configuration_state_id,
                    channel_binding_state_id=prepared.channel_binding_state_id,
                    media_descriptor_state_id=prepared.media_descriptor_state_id,
                )

            orchestrator = SaudiPublicationAuthorizationOrchestrator(
                ledger,
                saudi_legal_service,
                platform_compliance_bridge,
                recommendation_service,
                ops,
            )

            result = orchestrator.approve_and_authorize(
                creative_state_id=req.creative_state_id,
                eligibility_state_id=eligibility_state_id,
                reviewer=authorizer,
                authorizer=authorizer,
                determinations=req.determinations,
                source_checked_at=req.source_checked_at,
                execution_configuration_state_id=publication_inputs.execution_configuration_state_id,
                channel_binding_state_id=publication_inputs.channel_binding_state_id,
                media_descriptor_state_id=publication_inputs.media_descriptor_state_id,
                notes=req.notes,
                auth_context=bound.audit_context() if bound is not None else None,
            )

            return result.__dict__

        except LedgerError as e:
            raise HTTPException(400, str(e))


    @app.post("/api/publication/recommend")
    def publication_recommend(req: RecommendationIn):
        try:
            return recommendation_service.recommend(req.creative_state_id,req.eligibility_state_id,req.compliance_state_id).__dict__
        except LedgerError as e: raise HTTPException(400,str(e))

    @app.post("/api/human-authorization")
    def human_authorization(req: HumanAuthorizationIn, request: Request):
        bound = require_role(request, "publisher_authorizer")
        authorizer = bound.actor.subject if bound else (req.authorizer or "LOCAL_UNAUTHENTICATED_STRUCTURAL_ONLY")
        try:
            ref = ops.record_human_authorization(
                req.recommendation_state_id, authorizer, req.decision, notes=req.notes,
                auth_context=bound.audit_context() if bound else None,
                execution_configuration_state_id=req.execution_configuration_state_id,
                channel_binding_state_id=req.channel_binding_state_id,
                media_descriptor_state_id=req.media_descriptor_state_id,
                require_exact_channel=bool(auth_required),
                require_exact_media=bool(req.media_descriptor_state_id),
            )
            return ref.__dict__
        except LedgerError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/commercial-authorization")
    def commercial_authorization(req: CommercialAuthorizationIn, request: Request):
        bound = require_role(request, "commercial_authorizer")
        authorizer = bound.actor.subject if bound else (req.authorizer or "LOCAL_UNAUTHENTICATED_STRUCTURAL_ONLY")
        try:
            ref = ops.record_commercial_authorization(req.monetization_configuration_state_id, authorizer, req.decision, notes=req.notes, auth_context=bound.audit_context() if bound else None)
            return ref.__dict__
        except LedgerError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/monetization/activate")
    def monetize(req: MonetizationActivationIn, request: Request):
        bound = require_role(request, "commercial_operator")
        try:
            ref = ops.activate_monetization(req.monetization_configuration_state_id, dependency_state_ids=req.dependency_state_ids, provider_result_ref=req.provider_result_ref, auth_context=bound.audit_context() if bound else None)
            return ref.__dict__
        except LedgerError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/youtube/private-upload")
    def youtube_private_upload(req: YouTubePrivateUploadIn, request: Request):
        # Real C1 call path, disabled by default pending separate activation.
        if not auth_required or os.environ.get("TREND_HUNTER_YOUTUBE_PRIVATE_UPLOAD_ENABLED") != "1":
            raise HTTPException(423, "YouTube private uploader is wired but activation remains on HOLD")
        bound = require_role(request, "publication_operator")
        expected_channel = "UCPm6nbktPc2Egr05AV-zPhA"
        try:
            auth = ledger.get_state(req.authorization_state_id)
            grant = ledger.get_state(req.oauth_grant_state_id)
            channel_id = str(auth["payload"].get("channel_binding_state_id") or "")
            if not channel_id or grant["payload"].get("channel_binding_state_id") != channel_id:
                raise LedgerError("Exact human authorization and OAuth channel do not match")
            channel = publication_bundle_service.bindings.assert_current_channel_binding(channel_id)
            if channel["payload"].get("platform") != "youtube" or channel["payload"].get("channel_ref") != expected_channel:
                raise LedgerError("Only the exact Trend Radar YouTube channel is permitted")
            # Cheap fail-closed replay preflight before OAuth refresh. The C1
            # atomic authorization claim remains definitive for concurrent calls.
            ledger.assert_youtube_private_authorization_available(req.authorization_state_id)
            media_path = project_root / "runtime" / "publication_media" / req.creative_state_id / "publication.mp4"
            youtube_oauth = YouTubeOAuthService(ledger)
            oauth_token = youtube_oauth.refresh_access_token(
                req.oauth_grant_state_id, client_id=req.oauth_client_id,
                client_secret=None, refresh_store=_youtube_refresh_token_store_from_runtime(),
            )
            result = YouTubePublicationService(ledger).execute_authorized_private_upload(
                operations=ops, creative_state_id=req.creative_state_id,
                authorization_state_id=req.authorization_state_id,
                oauth_grant_state_id=req.oauth_grant_state_id, oauth_token=oauth_token,
                media_path=media_path,
                monetization_activation_state_id=req.monetization_activation_state_id,
                auth_context=bound.audit_context(),
            )
            return {"provider_result": result["provider_result"],
                    "proof": result["proof"].__dict__, "execution": result["execution"].__dict__}
        except LedgerError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/publication/execute")
    def execute(req: PublicationExecutionIn, request: Request):
        bound = require_role(request, "publication_operator")
        try:
            ref = ops.record_publication_execution(
                req.creative_state_id, req.authorization_state_id,
                channel=req.channel, channel_binding_state_id=req.channel_binding_state_id,
                external_result_ref=req.external_result_ref,
                monetization_activation_state_id=req.monetization_activation_state_id,
                require_bound_channel=bool(auth_required),
                auth_context=bound.audit_context() if bound else None,
            )
            return ref.__dict__
        except LedgerError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/outcome")
    def outcome(req: OutcomeIn, request: Request):
        bound = require_role(request, "finance_operator")
        try:
            result = ops.record_economic_outcome(
                req.publication_state_id, performance=req.performance, revenue=req.revenue,
                costs=req.costs, attribution=req.attribution, evidence_state_ids=req.evidence_state_ids,
                auth_context=bound.audit_context() if bound else None,
            )
            return {k: v.__dict__ for k,v in result.items()}
        except LedgerError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/integrity")
    def integrity():
        return ledger.integrity_check()

    @app.get("/api/current-views")
    def current_views():
        with connect(db_path) as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM current_view_projection ORDER BY projection_key")]

    @app.get("/", response_class=HTMLResponse)
    def home():
        return DASHBOARD_HTML

    return app


DASHBOARD_HTML = r'''<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>صيّاد الترند</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Tahoma,sans-serif;margin:0;background:#f5f7fb;color:#18202a;line-height:1.65}
header{background:#111827;color:#fff;padding:22px 28px} h1{margin:0;font-size:25px}.sub{opacity:.82;margin-top:6px}
main{max-width:1120px;margin:24px auto;padding:0 18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.card{background:white;border:1px solid #e5e7eb;border-radius:14px;padding:18px;box-shadow:0 2px 8px #0000000a}.big{font-size:26px;font-weight:700}.ok{color:#087f5b}.warn{color:#b7791f}.muted{color:#667085}.rows{margin-top:18px}.stage{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid #eee;padding:8px 0}.small{font-size:13px;color:#667085}.guide{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px;margin-top:18px}.guide h3{margin-top:0}.steps{margin:0;padding-right:21px}.steps li{margin:7px 0}.now{border-right:4px solid #087f5b}.profit{border-right:4px solid #2563eb}.promise{background:#eef6ff;border:1px solid #cfe2ff;border-radius:10px;padding:10px 12px;margin-top:12px}.notice{background:#fff8e6;border:1px solid #f6d98f;border-radius:10px;padding:10px 12px;margin-top:12px}.result{background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:12px;margin-top:12px}.result strong{display:block;margin-bottom:3px}button{border:0;border-radius:10px;padding:10px 14px;background:#111827;color:white;cursor:pointer;font-weight:700}pre{direction:ltr;text-align:left;white-space:pre-wrap;background:#0b1020;color:#dce7ff;padding:14px;border-radius:12px;overflow:auto}.tech summary{cursor:pointer;font-weight:700;margin-top:12px}.tag{display:inline-block;background:#eef2ff;border-radius:999px;padding:2px 8px;font-size:12px;margin-right:4px}
button:disabled{opacity:.5;cursor:not-allowed}input,select,textarea{font:inherit;border:1px solid #cbd5e1;border-radius:8px;padding:8px;background:#fff;box-sizing:border-box;width:100%}textarea{min-height:70px;resize:vertical}.formrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:12px 0}.rule{border:1px solid #e5e7eb;border-radius:10px;padding:12px;margin:10px 0}.rulehead{font-weight:700;margin-bottom:8px}.rulegrid{display:grid;grid-template-columns:180px 1fr;gap:10px;margin-top:8px}@media(max-width:650px){.rulegrid{grid-template-columns:1fr}}
</style>
</head>
<body><header><h1>صيّاد الترند — محرك الفرص العالمية</h1><div class="sub">يكتشف الإشارات، يتحقق من مصدرها، يقيّم الفرصة، ويمنع التنفيذ المادي حتى تمر الحوكمة والموافقة البشرية.</div></header>
<main>
<div class="grid">
 <div class="card"><div class="small">حالة المعمارية</div><div class="big ok" id="arch">جارٍ الفحص…</div></div>
 <div class="card"><div class="small">سلامة السجل</div><div class="big" id="integrity">جارٍ الفحص…</div></div>
 <div class="card"><div class="small">عقود الحوكمة</div><div class="big" id="contracts">…</div></div>
 <div class="card"><div class="small">سجلات المسار</div><div class="big" id="records">…</div></div>
 <div class="card"><div class="small">الفلتر القانوني السعودي</div><div class="big" id="saudiLegal">جارٍ الفحص…</div><div class="small" id="saudiLegalDetail"></div></div>
</div>

<div class="guide">
 <div class="card now">
  <h3>ماذا أفعل الآن؟</h3>
  <ol class="steps">
   <li><b>الآن:</b> نحن نتحقق من التشغيل المحلي الآمن على جهازك.</li>
   <li>بعد نجاحه نفعّل <b>مصادر حقيقية</b> مثل Google Trends export وGDELT وYouTube وفق ما يتاح ويُعتمد.</li>
   <li>يعرض النظام الفرص مع الأدلة والمخاطر بدل أن يخمّن.</li>
   <li>أي نشر أو تفعيل تجاري مادي يتطلب <b>موافقة بشرية نهائية</b> وربط الحساب/القناة الصحيحة.</li>
  </ol>
 </div>
 <div class="card">
  <h3>لغات وأسواق الصيد</h3>
  <p>واجهة التطبيق والتعليمات لك <b>بالعربية</b>، لكن نطاق الصيد التجاري ليس عربيًا فقط.</p>
  <p><b>لغات النشر العالمية المعتمدة:</b> العربية، الإنجليزية، الفرنسية، الهندية، الصينية المبسطة، والإسبانية.</p>
  <div class="notice">المحتوى والدليل يبقيان بلغتهما الأصلية. الترجمة العربية للعرض لا تُعامل كدليل مستقل ولا تُستخدم لدمج فرص من لغتين مختلفتين بلا مراجعة دلالية محكومة.</div>
 </div>
 <div class="card profit">
  <h3>كيف يتحول إلى أرباح؟</h3>
  <ol class="steps">
   <li>اكتشاف فرصة حقيقية مبكرًا والتحقق من مصدرها.</li>
   <li>اختيار مسار تحقيق الدخل المناسب للفرصة والحساب المتاح لديك.</li>
   <li>تنفيذ المحتوى/العرض/القناة بعد الموافقة البشرية فقط.</li>
   <li>إدخال أو ربط دليل <b>الإيراد الفعلي والتكلفة الفعلية</b>.</li>
   <li>يحسب النظام صافي النتيجة ويتعلم فقط من النتائج المثبتة؛ ثم نكرر ما ثبت نجاحه ونوقف ما لم ينجح.</li>
  </ol>
  <div class="promise"><b>وعد التسليم الوظيفي:</b> لا يتوقف «صياد الترند» عند اكتشاف الترند؛ المسار المصمم يمتد حتى التنفيذ والقياس الاقتصادي والتعلم من النتيجة المحققة.</div>
  <div class="notice"><b>تنبيه:</b> هذا ليس ضمانًا لربح مالي أو وعدًا بعائد. الربح لا يُسجَّل كربح مُثبت إلا إذا وُجدت أدلة حقيقية قابلة للربط على الإيراد والتكلفة وبعملة قابلة للمقارنة.</div>
 </div>
</div>

<div class="card rows" id="languageBoardCard">
 <h3>لوحة اللغة والأسواق</h3>
 <p class="small">عرض محكوم من الفرص الحقيقية الحالية فقط. لا تُنشأ أرقام شعبية أو ترتيب تجاري مصطنع.</p>
 <div class="formrow"><label>لغة اللوحة<select id="boardLanguage"><option value="ar">العربية</option><option value="en">English</option><option value="fr">Français</option><option value="hi">हिन्दी</option><option value="zh-Hans">简体中文</option><option value="es">Español</option></select></label><label>العرض<select id="boardMode"><option value="youtube_wide">YouTube Wide</option><option value="mobile_short_form">Mobile / Short Form</option><option value="snapchat_spotlight">Snapchat Spotlight</option></select></label></div>
 <div id="boardResult" class="result">جارٍ تحميل اللوحة…</div>
</div>

<div class="card rows"><h3>سجلات مراحل العمل</h3><div id="stages"></div></div>
<div class="card rows" id="saudiReviewer">
 <h3>المقيّم القانوني للمحتوى السعودي</h3>
 <p class="small">مراجعة بشرية محكومة وفق القواعد المختارة من نظام مكافحة جرائم المعلوماتية، وليست تصريحًا قانونيًا آليًا.</p>
 <div class="formrow">
  <label>المحتوى السعودي<select id="saCreative"><option value="">جارٍ البحث…</option></select></label>
  <label>اسم المختص<input id="saReviewer" placeholder="اسم المراجع المختص"></label>
  <label>تاريخ التحقق من المصدر<input id="saSourceDate" type="date"></label>
 </div>
 <div id="saNoCreative" class="notice" hidden>لا يوجد حاليًا محتوى سعودي حقيقي مؤهل للمراجعة. سيظهر هنا تلقائيًا بعد إنشائه في المسار الحقيقي.</div>
 <div id="saCreativeDetails" hidden style="margin:12px 0;padding:14px;border:1px solid #d8e0ea;border-radius:10px;background:#f8fafc"></div>
 <div id="saMediaPreview" class="result" hidden><strong>معاينة الفيديو الفعلي قبل التفويض</strong><div id="saBundleStatus" class="small">جارٍ تجهيز حزمة النشر…</div><video id="saVideo" controls playsinline style="width:100%;max-height:640px;margin-top:10px;background:#000;border-radius:10px"></video></div>
 <div id="saRules"></div>
 <button id="saSubmit" onclick="submitSaudiReview()" disabled>اعتماد المراجعة والتفويض للنشر</button>
 <div class="result" id="saResult">لم تُحفظ مراجعة بعد.</div>
</div>
<div class="card rows"><h3>اختبار تجريبي آمن</h3><p class="small">هذا اختبار هندسي مصطنع فقط؛ لا يمثل بيانات سوق حقيقية، ولا ينشر، ولا يفعّل ربحًا أو حسابًا خارجيًا.</p><button onclick="runDemo()">تشغيل الاختبار</button><div class="result" id="demoSummary">لم يُشغّل الاختبار بعد.</div><details class="tech"><summary>إظهار التفاصيل التقنية</summary><pre id="demo">لم يُشغّل بعد.</pre></details></div>
</main>
<script>
const stageArabic={
 'SOURCE_RECORD':'مصدر/بيانات أولية','SIGNAL':'إشارة ترند','NORMALIZED_SIGNAL':'إشارة موحّدة','CORRESPONDENCE':'مطابقة/مراسلة','TREND_MEASUREMENT':'قياس الترند','SATURATION_CHARACTERIZATION':'تقدير التشبع','OPPORTUNITY':'فرصة','ELIGIBILITY_ASSESSMENT':'تقييم الأهلية','EXECUTION_CONFIGURATION':'تهيئة التنفيذ','ECONOMIC_EXPECTATION':'التوقع الاقتصادي','FEASIBILITY_ASSESSMENT':'تقييم الجدوى','PRIORITY_DECISION':'قرار الأولوية','MONETIZATION_CONFIGURATION':'تهيئة تحقيق الدخل','CREATIVE_ARTIFACT':'مادة/أصل إبداعي','COMPLIANCE_ASSESSMENT':'تقييم الامتثال','PUBLICATION_RECOMMENDATION':'توصية بالنشر','HUMAN_FINAL_AUTHORIZATION':'الموافقة البشرية النهائية','MONETIZATION_ACTIVATION':'تفعيل تحقيق الدخل','PUBLICATION_EXECUTION':'تنفيذ النشر','ECONOMIC_OUTCOME':'النتيجة الاقتصادية','LEARNING':'التعلم من النتيجة'
};
const stateArabic={'ACTIVE':'نشط','ACCEPTED':'مقبول','COMPLETE':'مكتملة','DRAFT':'مسودة','BLOCKED':'محظور','INELIGIBLE':'غير مؤهل','ELIGIBLE':'مؤهل','HUMAN_REVIEW_REQUIRED':'تحتاج مراجعة بشرية','NOT_EVALUABLE':'غير قابلة للتقييم'};
function arStage(x){return stageArabic[x]||x.replaceAll('_',' ')}
function arState(x){return stateArabic[x]||x.replaceAll('_',' ')}
function boardEsc(v){return saEsc(v);}
async function loadLanguageBoard(){
 try{
  const lang=(document.getElementById('boardLanguage')||{}).value||'ar';
  const mode=(document.getElementById('boardMode')||{}).value||'youtube_wide';
  const res=await fetch('/api/language-board/'+encodeURIComponent(lang)+'?mode='+encodeURIComponent(mode));
  const b=await res.json(); if(!res.ok) throw new Error(b.detail||('HTTP '+res.status));
  const markets=(b.priority_markets||[]).map(x=>`<span class="tag">${boardEsc(x.market_code)} · ${Number(x.governed_opportunity_count||0)}</span>`).join(' ')||'<span class="small">لا توجد أسواق مثبتة لهذه اللغة بعد.</span>';
  const top=(b.global_top_6||[]).map((x,i)=>`<div class="stage"><span>${i+1}. ${boardEsc(x.title||x.opportunity_state_id)}</span><span class="tag">${boardEsc(x.market_code||'')}</span></div>`).join('')||'<span class="small">لا توجد فرص حقيقية ذات لغة/سوق صريحين بعد.</span>';
  boardResult.innerHTML='<strong>أسواق الأولوية المبنية على السجلات الحالية</strong><div style="margin:8px 0">'+markets+'</div><strong>Global Top 6 — عرض أحدث السجلات المحكومة لهذه اللغة</strong>'+top+'<div class="small" style="margin-top:8px">هذا ليس ترتيب شعبية عالميًا ولا درجة موحدة.</div>';
 }catch(e){boardResult.textContent='تعذر تحميل لوحة اللغة: '+e.message;}
}

async function load(){
 try{
  const statusRes=await fetch('/api/status');
  if(!statusRes.ok) throw new Error('status HTTP '+statusRes.status);
  const s=await statusRes.json();
  arch.textContent=s.architecture==='COMPLETE'?'مكتملة':arState(s.architecture);
  contracts.textContent=s.contracts.length; records.textContent=s.domain_counts.reduce((a,x)=>a+x.n,0);
  const sl=s.saudi_legal_filter||{}; saudiLegal.textContent=sl.status==='INSTALLED'?'مثبّت':'غير مثبّت'; saudiLegal.className='big '+(sl.status==='INSTALLED'?'ok':'warn'); saudiLegalDetail.textContent=sl.rule_count?`${sl.rule_count} قواعد محكومة — القرار النهائي بشري`:'';
  stages.innerHTML=s.domain_counts.map(x=>`<div class="stage"><span>${arStage(x.stage)} <span class="tag">${arState(x.record_state)}</span></span><b>${x.n}</b></div>`).join('')||'<span class="small">لا توجد سجلات بعد.</span>';
    let sourceStatusPanel=document.getElementById("sourceStatusPanel");
    if(!sourceStatusPanel){
      sourceStatusPanel=document.createElement("section");
      sourceStatusPanel.id="sourceStatusPanel";
      sourceStatusPanel.style.cssText="margin:16px 0;padding:16px;border:1px solid #d9dee8;border-radius:12px;background:#fff";
      stages.insertAdjacentElement("beforebegin",sourceStatusPanel);
    }
    const srcStatus=Array.isArray(s.source_status)?s.source_status:[];
    const srcLabels={
      PASS:"متصل — آخر فحص ناجح",
      FAIL:"فشل آخر فحص",
      RATE_LIMITED:"محدود مؤقتًا",
      OBSERVED:"بيانات موجودة",
      DATA_AVAILABLE:"بيانات موجودة",
      READY_NO_DATA:"لم تُحمّل بيانات بعد",
      NOT_TESTED:"لم يُختبر حيًا بعد",
      UNKNOWN:"الحالة غير محسومة"
    };
    sourceStatusPanel.innerHTML=
      '<div style="font-weight:700;font-size:18px;margin-bottom:10px">مصادر البيانات</div>'+
      '<div style="color:#667085;font-size:12px;margin-bottom:12px">يعرض الاسم الحقيقي للمصدر، طريقة الإدخال، وآخر حالة مثبتة داخل السجل.</div>'+
      '<div style="display:grid;gap:8px">'+
      srcStatus.map(x=>{
        const label=srcLabels[x.status]||x.status||"غير معروف";
        const count=Number(x.record_count||0);
        const extra=count?(' | سجلات: '+count):'';
        return '<div style="display:grid;grid-template-columns:minmax(180px,1.4fr) minmax(120px,.8fr) minmax(180px,1fr);gap:10px;align-items:center;padding:10px 12px;border:1px solid #eef1f5;border-radius:9px">'+
          '<strong>'+x.name+'</strong>'+
          '<span style="font-size:12px;color:#667085">'+x.mode+'</span>'+
          '<span style="font-size:12px">'+label+extra+'</span>'+
        '</div>';
      }).join('')+
      '</div>';
 }catch(e){
  arch.textContent='تعذر تحميل الحالة'; arch.className='big warn';
  contracts.textContent='—'; records.textContent='—';
  saudiLegal.textContent='تعذر الفحص'; saudiLegal.className='big warn';
 }

 // Integrity is deliberately independent from status rendering.
 // A large governed ledger may make /health expensive; it must not freeze the dashboard.
 integrity.textContent='جارٍ فحص السلامة…'; integrity.className='big warn';
 const controller=new AbortController();
 const timer=setTimeout(()=>controller.abort(),10000);
 try{
  const healthRes=await fetch('/health',{signal:controller.signal});
  if(!healthRes.ok) throw new Error('health HTTP '+healthRes.status);
  const h=await healthRes.json();
  const integrityOk=h.status==='ok';
  integrity.textContent=integrityOk?'سليم':'توجد ملاحظات';
  integrity.className='big '+(integrityOk?'ok':'warn');
 }catch(e){
  integrity.textContent=(e&&e.name==='AbortError')?'فحص السلامة بطيء':'تعذر فحص السلامة';
  integrity.className='big warn';
 }finally{
  clearTimeout(timer);
 }
}
function demoArabic(r){
 if(r.stopped_at==='HUMAN_FINAL_AUTHORIZATION') return '<strong>✅ الاختبار نجح كما هو متوقع</strong>وصل المسار إلى حاجز <b>الموافقة البشرية النهائية</b> وتوقف عمدًا؛ الاختبار المصطنع لا يستطيع اختراع موافقة بشرية أو تنفيذ نشر/ربح حقيقي.';
 if(r.stopped_at) return '<strong>انتهى الاختبار عند:</strong>'+arStage(r.stopped_at);
 return '<strong>اكتمل الاختبار.</strong>';
}
async function runDemo(){demoSummary.textContent='جارٍ تشغيل الاختبار…'; demo.textContent='جارٍ التشغيل…'; try{const res=await fetch('/api/demo/run',{method:'POST'}); const r=await res.json(); if(!res.ok) throw new Error(r.detail||'فشل الاختبار'); demoSummary.innerHTML=demoArabic(r); demo.textContent=JSON.stringify(r,null,2); await load();}catch(e){demoSummary.innerHTML='<strong>تعذر تشغيل الاختبار</strong>'+e.message; demo.textContent=String(e);}}
let saPolicy=null;
let saCreativesById=new Map();
function saEsc(v){
 return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function saList(v){
 if(!Array.isArray(v)||!v.length) return '<span class="small">غير متاح</span>';
 return '<ul style="margin:6px 0 0 18px">'+v.map(x=>'<li>'+saEsc(x)+'</li>').join('')+'</ul>';
}
function renderSaudiCreativeDetails(){
 const box=document.getElementById('saCreativeDetails');
 const row=saCreativesById.get(saCreative.value);
 if(!row){box.hidden=true; box.innerHTML=''; return;}
 const p=row.payload||{}, t=p.target||{}, b=p.brief||{}, f=b.factor_assertions||{};
 const originalTitle=f.observed_title||b.observed_title||'';
 const sourceName=f.source_name||'';
 const title=p.title||originalTitle||'محتوى سعودي';
 const lang=t.publication_language||t.language||'—';
 const market=t.target_market||t.jurisdiction||t.region||'—';
 const platform=t.platform||'—';
 const hook=p.hook||'';
 const body=p.body||'';
 const description=p.description||'';
 const hashtags=Array.isArray(p.hashtags)?p.hashtags:[];
 const cta=p.cta||'';
 const provider=p.provider_key||((p._generation||{}).provider_key)||'—';
 const thesis=b.thesis||'';
 box.hidden=false;
 box.innerHTML=
  '<div style="font-weight:800;font-size:17px;margin-bottom:10px">المحتوى المطلوب مراجعته</div>'+
  '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin-bottom:12px">'+
   '<div><b>عنوان المحتوى</b><br>'+saEsc(title)+'</div>'+
   '<div><b>المنصة</b><br>'+saEsc(platform)+'</div>'+
   '<div><b>السوق</b><br>'+saEsc(market)+'</div>'+
   '<div><b>لغة النشر</b><br>'+saEsc(lang)+'</div>'+
  '</div>'+
  (originalTitle?'<div style="margin:8px 0"><b>عنوان المصدر/الترند الأصلي:</b> '+saEsc(originalTitle)+(sourceName?' <span class="small">('+saEsc(sourceName)+')</span>':'')+'</div>':'')+
  (hook?'<div style="margin:10px 0"><b>الافتتاحية (Hook):</b><div style="white-space:pre-wrap">'+saEsc(hook)+'</div></div>':'')+
  (body?'<div style="margin:10px 0"><b>النص المقترح للنشر:</b><div style="white-space:pre-wrap;padding:10px;background:#fff;border:1px solid #e5e7eb;border-radius:8px">'+saEsc(body)+'</div></div>':'')+
  (description?'<div style="margin:10px 0"><b>الوصف:</b><div style="white-space:pre-wrap">'+saEsc(description)+'</div></div>':'')+
  (hashtags.length?'<div style="margin:10px 0"><b>الوسوم:</b> '+hashtags.map(saEsc).join(' ')+'</div>':'')+
  (cta?'<div style="margin:10px 0"><b>الدعوة لاتخاذ إجراء (CTA):</b> '+saEsc(cta)+'</div>':'')+
  '<details style="margin-top:12px"><summary><b>الأدلة والسياق الحاكم</b></summary>'+
   (thesis?'<div style="margin:8px 0"><b>أساس الفرصة:</b><div style="white-space:pre-wrap">'+saEsc(thesis)+'</div></div>':'')+
   '<div style="margin:8px 0"><b>الوقائع المستخدمة في إنشاء المحتوى:</b>'+saList(p.source_facts_used)+'</div>'+
   '<div style="margin:8px 0"><b>ملاحظات التوطين:</b>'+saList(p.localization_notes)+'</div>'+
   '<div class="small" style="margin-top:10px"><b>مزود الإنشاء:</b> '+saEsc(provider)+'<br><b>معرّف السجل:</b> '+saEsc(row.artifact_state_id||'—')+'</div>'+
  '</details>';
}
const saStatusOptions='<option value="">اختر القرار</option><option value="PASS">سليم</option><option value="WARNING">تحذير</option><option value="BLOCK">منع</option><option value="UNRESOLVED">غير محسوم</option><option value="NOT_APPLICABLE">غير منطبق</option>';
async function loadSaudiReviewer(){
 try{
  const [p,c]=await Promise.all([fetch('/api/compliance/saudi-cybercrime/policy'),fetch('/api/domain/CREATIVE_ARTIFACT?limit=100')]);
  saPolicy=await p.json(); const creatives=await c.json();
  const eligible=creatives.filter(x=>x.payload&&x.payload.fixture!==true&&x.payload.target&&String(x.payload.target.jurisdiction||x.payload.target.region||'').toUpperCase()==='SA');
  saCreativesById=new Map(eligible.map(x=>[x.artifact_state_id,x]));
  saCreative.innerHTML='<option value="">اختر المحتوى</option>'+eligible.map(x=>{
    const p=x.payload||{},t=p.target||{},b=p.brief||{},f=b.factor_assertions||{};
    const title=p.title||f.observed_title||'محتوى سعودي';
    const platform=t.platform||'';
    const lang=t.publication_language||t.language||'';
    const meta=[platform,lang].filter(Boolean).join(' / ');
    return `<option value="${x.artifact_state_id}">${saEsc(title)}${meta?' — '+saEsc(meta):''}</option>`;
  }).join('');
  saNoCreative.hidden=eligible.length>0; saSubmit.disabled=eligible.length===0;
  saCreative.onchange=async()=>{renderSaudiCreativeDetails(); await prepareSaudiBundlePreview();};
  if(eligible.length===1){saCreative.value=eligible[0].artifact_state_id;}
  renderSaudiCreativeDetails();
  if(saCreative.value){await prepareSaudiBundlePreview();}
  saRules.innerHTML=saPolicy.rules.map((r,i)=>`<div class="rule"><div class="rulehead">${r[0]} — ${r[1].replace('article_','المادة ')}</div><div>${r[2]}</div><div class="rulegrid"><select id="saStatus${i}">${saStatusOptions}</select><textarea id="saReason${i}" placeholder="سبب القرار — إلزامي"></textarea></div></div>`).join('');
 }catch(e){saResult.innerHTML='<strong>تعذر تحميل المقيّم</strong>'+e.message;}
}
async function prepareSaudiBundlePreview(){
  const box=document.getElementById('saMediaPreview');
  const status=document.getElementById('saBundleStatus');
  const video=document.getElementById('saVideo');
  if(!saCreative.value){box.hidden=true; video.removeAttribute('src'); return;}
  box.hidden=false; status.textContent='جارٍ تجهيز الفيديو وربطه بالقناة وتهيئة التنفيذ المحكومة…';
  saSubmit.disabled=true;
  try{
    const res=await fetch('/api/publication/bundle/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({creative_state_id:saCreative.value})});
    const data=await res.json().catch(()=>({}));
    if(!res.ok) throw new Error(data.detail||JSON.stringify(data)||('HTTP '+res.status));
    status.textContent='حزمة النشر جاهزة. راجع الفيديو الفعلي أدناه قبل الاعتماد.';
    video.src='/api/publication/bundle/media/'+encodeURIComponent(saCreative.value)+'?v='+Date.now();
    video.load();
    saSubmit.disabled=false;
  }catch(e){
    status.textContent='تعذر تجهيز حزمة النشر: '+e.message;
    video.removeAttribute('src');
    saSubmit.disabled=true;
  }
}

async function submitSaudiReview(){
  if(!saCreative.value||!saReviewer.value.trim()||!saSourceDate.value){
    saResult.textContent='أكمل المادة والمراجع وتاريخ التحقق أولاً.';
    return;
  }

  const determinations=saPolicy.rules.map((r,i)=>({
    rule_id:r.id,
    status:document.getElementById('saStatus'+i).value,
    reason:document.getElementById('saReason'+i).value.trim()
  }));

  if(determinations.some(x=>!x.status||!x.reason)){
    saResult.textContent='أكمل قرار وسبب كل قاعدة سعودية.';
    return;
  }

  saSubmit.disabled=true;
  saResult.textContent='جارٍ اعتماد المراجعة وإنشاء تفويض النشر المحكوم...';

  try{
    const res=await fetch(
      '/api/compliance/saudi-cybercrime/authorize',
      {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          creative_state_id:saCreative.value,
          reviewer:saReviewer.value.trim(),
          source_checked_at:saSourceDate.value,
          determinations:determinations,
          notes:''
        })
      }
    );

    const data=await res.json().catch(()=>({}));

    if(!res.ok){
      throw new Error(data.detail||JSON.stringify(data)||('HTTP '+res.status));
    }

    saResult.textContent=
      'تم اعتماد المراجعة السعودية وإنشاء تفويض النشر المحكوم.\n'+
      JSON.stringify(data,null,2);

    await loadSaudiReviewer();
  }catch(e){
    saResult.textContent='تعذر الاعتماد: '+e.message;
  }finally{
    saSubmit.disabled=false;
  }
}

document.addEventListener('change',e=>{if(e.target&&['boardLanguage','boardMode'].includes(e.target.id)) loadLanguageBoard();});
load(); loadLanguageBoard(); loadSaudiReviewer();
</script></body></html>
'''
