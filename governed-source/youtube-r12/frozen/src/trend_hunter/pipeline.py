from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .connectors.synthetic import SyntheticConnector
from .ledger import GovernanceLedger, ArtifactRef, LedgerError
from .util import utcnow
from .db import connect, tx
from .util import json_dumps, new_id


@dataclass
class DemoResult:
    run_id: str
    records: dict[str, list[str]]
    stopped_at: str
    reason: str


class SyntheticPilotRunner:
    """Exercises the governed pipeline using explicit synthetic fixtures only.

    It deliberately stops before Human Final Authorization. No publication,
    monetization activation, revenue or profit is fabricated.
    """

    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger
        self.connector = SyntheticConnector()

    def _r(self, records: dict[str, list[str]], stage: str, ref: ArtifactRef) -> ArtifactRef:
        records.setdefault(stage, []).append(ref.state_id)
        return ref

    def run(self) -> DemoResult:
        run_id = new_id("run")
        records: dict[str, list[str]] = {}
        now = utcnow()
        dependency_policies = {
            "UPSTREAM_REQUIRES_REASSESSMENT": self.ledger.get_dependency_policy("UPSTREAM_REQUIRES_REASSESSMENT", 1),
            "MATERIAL_UPSTREAM_INVALIDATES": self.ledger.get_dependency_policy("MATERIAL_UPSTREAM_INVALIDATES", 1),
        }

        def bind(downstream: str, upstream: str, dep_type: str, policy_key: str, materiality: dict[str, Any]):
            self.ledger.bind_dependency(downstream, upstream, dep_type, dependency_policies[policy_key], materiality)

        source_states: list[ArtifactRef] = []
        for item in self.connector.fetch():
            src = self._r(records, "SOURCE_RECORD", self.ledger.record_domain(
                "SOURCE_RECORD", "Source Adapter Authority", {
                    "run_id": run_id,
                    "source_name": item.source_name,
                    "external_id": item.external_id,
                    "fixture": True,
                    "payload": item.payload,
                }, natural_key=f"{run_id}:{item.external_id}", scope={
                    "language": item.payload["language"],
                    "region": item.payload["region"],
                    "platform": item.payload["platform"],
                }, observed_at=item.observed_at, record_state="OBSERVED"
            ))
            source_states.append(src)

            signal = self._r(records, "SIGNAL", self.ledger.record_domain(
                "SIGNAL", "Signal Authority", {
                    "run_id": run_id,
                    "metric_semantics": {
                        "attention_observed": "fixture-native literal observed count",
                        "eligible_supply_observed": "fixture-native literal eligible supply count",
                        "supply_baseline": "fixture-declared reference baseline",
                    },
                    "values": {
                        "attention_observed": item.payload["attention_observed"],
                        "eligible_supply_observed": item.payload["eligible_supply_observed"],
                        "supply_baseline": item.payload["supply_baseline"],
                    },
                    "fixture": True,
                }, natural_key=f"{run_id}:signal:{item.external_id}", scope={
                    "language": item.payload["language"], "region": item.payload["region"], "platform": item.payload["platform"]
                }, observed_at=item.observed_at, record_state="OBSERVED", upstream_states=[(src.state_id, "OBSERVED_FROM")]
            ))

            evidence = self._r(records, "EVIDENCE", self.ledger.record_domain(
                "EVIDENCE", "Evidence Authority", {
                    "run_id": run_id,
                    "material": "synthetic fixture measurement material",
                    "fixture": True,
                    "does_not_assert_truth": True,
                }, natural_key=f"{run_id}:evidence:{item.external_id}", record_state="AVAILABLE",
                upstream_states=[(signal.state_id, "SUPPORTED_BY_SIGNAL")]
            ))

            claim = self._r(records, "CLAIM", self.ledger.record_domain(
                "CLAIM", "Claim Authority", {
                    "run_id": run_id,
                    "atomic_proposition": f"Fixture scope {item.payload['language']}-{item.payload['region']}-{item.payload['platform']} has the literal observations recorded in its Signal artifact.",
                    "fixture": True,
                    "truth_status": "NOT_ASSESSED",
                }, natural_key=f"{run_id}:claim:{item.external_id}", record_state="ASSERTED",
                upstream_states=[(evidence.state_id, "EVIDENCE_FOR")]
            ))

        # Identity resolution on explicit fixture semantic key, recorded as governed demo correspondence, not an inferred real entity.
        entity_identity = self.ledger.get_or_create_identity("ENTITY", f"{run_id}:demo_subject_alpha")
        entity = self._r(records, "ENTITY", self.ledger.record_domain(
            "ENTITY", "Entity Identity Authority", {
                "run_id": run_id,
                "entity_key": "demo_subject_alpha",
                "fixture": True,
                "identity_basis": "explicit shared fixture semantic_key",
            }, natural_key=f"{run_id}:entity:alpha", subject_identity_id=entity_identity, record_state="IDENTITY_RESOLVED",
            upstream_states=[(sid, "MENTION_RESOLUTION_INPUT") for sid in records["CLAIM"]]
        ))

        story_identity = self.ledger.get_or_create_identity("STORY", f"{run_id}:story:alpha")
        story = self._r(records, "STORY", self.ledger.record_domain(
            "STORY", "Story Cluster Authority", {
                "run_id": run_id,
                "story_key": "demo_story_alpha",
                "fixture": True,
                "semantic_unit": "explicit fixture episode for vertical-pipeline test",
            }, natural_key=f"{run_id}:story:alpha", subject_identity_id=story_identity, record_state="BOUND",
            upstream_states=[(entity.state_id, "STORY_ENTITY_BASIS")]
        ))

        saturation_by_scope: dict[str, ArtifactRef] = {}
        trend_by_scope: dict[str, ArtifactRef] = {}
        for src in source_states:
            payload = self.ledger.get_state(src.state_id)["payload"]["payload"]
            scope_key = f"{payload['language']}-{payload['region']}-{payload['platform']}"
            trend = self._r(records, "TREND_MEASUREMENT", self.ledger.record_domain(
                "TREND_MEASUREMENT", "Trend Measurement Authority", {
                    "run_id": run_id,
                    "story_identity_id": story_identity,
                    "scope_key": scope_key,
                    "observed_attention": payload["attention_observed"],
                    "observed_supply": payload["eligible_supply_observed"],
                    "coverage_state": "SUFFICIENT_FOR_SYNTHETIC_FIXTURE",
                    "fixture": True,
                    "origin_not_asserted": True,
                }, natural_key=f"{run_id}:trend:{scope_key}", subject_identity_id=story_identity,
                scope={"language": payload["language"], "region": payload["region"], "platform": payload["platform"]},
                observed_at=now, record_state="MEASURED", upstream_states=[(story.state_id, "MEASURES_STORY"), (src.state_id, "MEASUREMENT_SOURCE")]
            ))
            trend_by_scope[scope_key] = trend

            baseline = payload["supply_baseline"]
            supply = payload["eligible_supply_observed"]
            occupancy_ratio = supply / baseline if baseline > 0 else None
            sat_state = "DETERMINATE" if occupancy_ratio is not None else "NOT_EVALUABLE"
            sat = self._r(records, "SATURATION_CHARACTERIZATION", self.ledger.record_domain(
                "SATURATION_CHARACTERIZATION", "SRCA", {
                    "run_id": run_id,
                    "realization_contract": "CONTENT_SUPPLY_OCCUPANCY_RELATIVE_TO_SCOPE_BASELINE@V1",
                    "scope_key": scope_key,
                    "eligible_content_population": "synthetic fixture eligible supply",
                    "reference_basis": {"type": "fixture_predeclared_baseline", "value": baseline},
                    "reference_selection": "predeclared_in_fixture_before_result",
                    "occupancy_functional": "observed_supply / supply_baseline",
                    "occupancy_ratio": occupancy_ratio,
                    "orientation": "higher_ratio_means_greater_supply_occupation_relative_to_baseline",
                    "coverage": "SUFFICIENT_FOR_SYNTHETIC_FIXTURE",
                    "uncertainty": "FIXTURE_ONLY",
                    "competition_semantics_used": False,
                    "demand_semantics_used": False,
                    "fixture": True,
                }, natural_key=f"{run_id}:sat:{scope_key}", subject_identity_id=story_identity,
                scope={"language": payload["language"], "region": payload["region"], "platform": payload["platform"]},
                record_state=sat_state, upstream_states=[(trend.state_id, "CHARACTERIZES_MEASUREMENT")]
            ))
            saturation_by_scope[scope_key] = sat

        en = self.ledger.get_state(trend_by_scope["en-US-youtube"].state_id)["payload"]
        ar_sat = self.ledger.get_state(saturation_by_scope["ar-SA-youtube"].state_id)["payload"]
        # Demo policy is explicit and fixture-only. No opaque score.
        candidate_exists = en["observed_attention"] >= 100 and (ar_sat["occupancy_ratio"] is not None and ar_sat["occupancy_ratio"] < 0.5)
        opportunity_identity = self.ledger.get_or_create_identity("OPPORTUNITY", f"{run_id}:gap:alpha:ar-SA-youtube")
        opportunity = self._r(records, "OPPORTUNITY", self.ledger.record_domain(
            "OPPORTUNITY", "Opportunity Authority", {
                "run_id": run_id,
                "candidate_configuration": {
                    "story_identity_id": story_identity,
                    "observed_scope": "en-US-youtube",
                    "evaluated_scope": "ar-SA-youtube",
                    "fixture": True,
                },
                "thesis": "synthetic cross-scope gap candidate",
                "factor_assertions": {
                    "en_attention_at_least_demo_threshold": en["observed_attention"] >= 100,
                    "ar_supply_occupancy_below_demo_threshold": ar_sat["occupancy_ratio"] < 0.5,
                },
                "candidate_state": "CANDIDATE" if candidate_exists else "NOT_CANDIDATE",
                "no_opportunity_score": True,
                "fixture": True,
            }, natural_key=f"{run_id}:opp:alpha:ar", subject_identity_id=opportunity_identity,
            scope={"language": "ar", "region": "SA", "platform": "youtube"},
            record_state="CANDIDATE" if candidate_exists else "NOT_CANDIDATE",
            upstream_states=[
                (trend_by_scope["en-US-youtube"].state_id, "OPPORTUNITY_FACTOR_INPUT"),
                (saturation_by_scope["ar-SA-youtube"].state_id, "OPPORTUNITY_FACTOR_INPUT"),
            ]
        ))

        eligibility = self._r(records, "ELIGIBILITY_ASSESSMENT", self.ledger.record_domain(
            "ELIGIBILITY_ASSESSMENT", "Opportunity Eligibility & Jurisdictional Risk Authority", {
                "run_id": run_id,
                "outcome": "ELIGIBLE",
                "basis": "synthetic fixture explicitly marked non-political-sensitive",
                "truth_independent": True,
                "fixture": True,
            }, natural_key=f"{run_id}:eligibility", subject_identity_id=opportunity_identity,
            record_state="ELIGIBLE", upstream_states=[(opportunity.state_id, "ELIGIBILITY_TARGET")]
        ))

        # ExecutionConfiguration is actual before sibling evaluations.
        exec_identity = self.ledger.get_or_create_identity("EXECUTION_CONFIGURATION", f"{run_id}:exec:short-video")
        exec_payload = {
            "run_id": run_id,
            "opportunity_identity_id": opportunity_identity,
            "opportunity_state_id": opportunity.state_id,
            "eligibility_state_id": eligibility.state_id,
            "platform": "youtube",
            "channel": "demo-channel",
            "content_form": "short_form_video",
            "production_route": "synthetic_demo_manual_edit",
            "actionable_window": {"from": now, "to": None},
            "required_resources": {"editor_minutes": 30},
            "capital_assumption": {"currency": "SAR", "amount": 0, "basis": "synthetic_demo"},
            "operational_mode": "MANUAL_PILOT",
            "monetization_scenario": {"mechanism": "affiliate_synthetic_example", "status": "PROPOSED_FIXTURE"},
            "fixture": True,
        }
        exec_state = self.ledger.create_state(exec_identity, "EXECUTION_CONFIGURATION", exec_payload)
        with tx(self.ledger.db_path) as conn:
            conn.execute(
                """INSERT INTO execution_configuration(
                    artifact_state_id,opportunity_identity_id,platform,channel,content_form,production_route,
                    actionable_from,actionable_to,required_resources_json,capital_assumption_json,operational_mode
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (exec_state.state_id, opportunity_identity, "youtube", "demo-channel", "short_form_video", "synthetic_demo_manual_edit",
                 now, None, json_dumps({"editor_minutes":30}), json_dumps({"currency":"SAR","amount":0,"basis":"synthetic_demo"}), "MANUAL_PILOT"),
            )
            conn.execute(
                "INSERT INTO domain_record(artifact_state_id,stage,owner_authority,subject_identity_id,scope_json,record_state) VALUES(?,?,?,?,?,?)",
                (exec_state.state_id, "EXECUTION_CONFIGURATION", "Execution Feasibility Authority", opportunity_identity, json_dumps({"platform":"youtube"}), "DEFINED"),
            )
        self.ledger.add_provenance(opportunity.state_id, exec_state.state_id, "EXECUTION_CONFIGURATION_FOR")
        self.ledger.add_provenance(eligibility.state_id, exec_state.state_id, "EXECUTION_CONFIGURATION_ELIGIBILITY_GATE")
        bind(exec_state.state_id, opportunity.state_id, "EXECUTION_CONFIGURATION_FOR", "UPSTREAM_REQUIRES_REASSESSMENT", {"fixture":True})
        bind(exec_state.state_id, eligibility.state_id, "EXECUTION_CONFIGURATION_ELIGIBILITY_GATE", "MATERIAL_UPSTREAM_INVALIDATES", {"fixture":True})
        records.setdefault("EXECUTION_CONFIGURATION", []).append(exec_state.state_id)

        economics = self._r(records, "ECONOMIC_EXPECTATION", self.ledger.record_domain(
            "ECONOMIC_EXPECTATION", "Economic Expectation Authority", {
                "run_id": run_id,
                "execution_configuration_state_id": exec_state.state_id,
                "monetization_mechanism": "affiliate_synthetic_example",
                "assumption_status": "SYNTHETIC_FIXTURE_ONLY",
                "horizon": "7d",
                "scenario": {
                    "views": 1000,
                    "click_rate": 0.03,
                    "conversion_rate": 0.05,
                    "payout_per_conversion": {"amount": 20, "currency": "SAR"},
                    "incremental_cost": {"amount": 0, "currency": "SAR"},
                },
                "expected_revenue_formula": "views * click_rate * conversion_rate * payout",
                "expected_revenue": {"amount": 30.0, "currency": "SAR"},
                "expected_contribution": {"amount": 30.0, "currency": "SAR"},
                "prediction_not_outcome": True,
                "fixture": True,
            }, natural_key=f"{run_id}:econ", subject_identity_id=opportunity_identity, record_state="ESTIMATED",
            upstream_states=[(exec_state.state_id, "ECONOMIC_SCENARIO_CONFIGURATION")]
        ))
        bind(economics.state_id, exec_state.state_id, "ECONOMIC_SCENARIO_CONFIGURATION", "UPSTREAM_REQUIRES_REASSESSMENT", {"fixture":True})

        feasibility = self._r(records, "FEASIBILITY_ASSESSMENT", self.ledger.record_domain(
            "FEASIBILITY_ASSESSMENT", "Execution Feasibility Authority", {
                "run_id": run_id,
                "execution_configuration_state_id": exec_state.state_id,
                "outcome": "FEASIBLE",
                "basis": {"fixture_resources_available": True, "capital_required": 0},
                "fixture": True,
            }, natural_key=f"{run_id}:feas", subject_identity_id=opportunity_identity, record_state="FEASIBLE",
            upstream_states=[(exec_state.state_id, "FEASIBILITY_CONFIGURATION")]
        ))
        bind(feasibility.state_id, exec_state.state_id, "FEASIBILITY_CONFIGURATION", "UPSTREAM_REQUIRES_REASSESSMENT", {"fixture":True})

        priority = self._r(records, "PRIORITY_DECISION", self.ledger.record_domain(
            "PRIORITY_DECISION", "Prioritization & Resource Allocation Authority", {
                "run_id": run_id,
                "policy": "synthetic_demo_lexicographic_v1",
                "decision": "SELECTED_FOR_DEMO",
                "no_hidden_universal_score": True,
                "fixture": True,
            }, natural_key=f"{run_id}:priority", subject_identity_id=opportunity_identity, record_state="SELECTED",
            upstream_states=[(economics.state_id, "PRIORITY_ECONOMIC_INPUT"), (feasibility.state_id, "PRIORITY_FEASIBILITY_INPUT")]
        ))
        bind(priority.state_id, economics.state_id, "PRIORITY_ECONOMIC_INPUT", "UPSTREAM_REQUIRES_REASSESSMENT", {"fixture":True})
        bind(priority.state_id, feasibility.state_id, "PRIORITY_FEASIBILITY_INPUT", "UPSTREAM_REQUIRES_REASSESSMENT", {"fixture":True})

        # Configuration only. No activation before gates.
        mon_identity = self.ledger.get_or_create_identity("MONETIZATION_CONFIGURATION", f"{run_id}:monetization")
        mon_payload = {
            "run_id": run_id,
            "opportunity_identity_id": opportunity_identity,
            "mechanism": "affiliate_synthetic_example",
            "provider": "SYNTHETIC_PROVIDER",
            "account_ref": "fixture-account",
            "offer_or_product_ref": "fixture-offer",
            "campaign_ref": "fixture-campaign",
            "tracked_destination": "https://example.invalid/fixture-only",
            "attribution": {"key": "fixture-attribution"},
            "payout_terms": {"amount": 20, "currency": "SAR", "basis": "synthetic_fixture"},
            "currency": "SAR",
            "lifecycle_state": "READY_FOR_ACTIVATION",
            "activation_requirements": [
                {"key":"ELIGIBILITY","required_state_type":"ELIGIBILITY_ASSESSMENT","payload_path":"outcome","accepted_values":["ELIGIBLE"],"required":True},
                {"key":"COMPLIANCE","required_state_type":"COMPLIANCE_ASSESSMENT","payload_path":"gate_decision","accepted_values":["PASS","WARNING"],"required":True},
                {"key":"HUMAN_PUBLICATION_AUTHORIZATION","required_state_type":"HUMAN_AUTHORIZATION","payload_path":"decision","accepted_values":["AUTHORIZED"],"required":True},
                {"key":"EXACT_CREATIVE_BINDING","required_state_type":"CREATIVE_ARTIFACT","payload_path":"monetization_configuration_state_id","accepted_values":["__CONFIG_STATE_ID__"],"required":True},
            ],
            "fixture": True,
        }
        mon_state = self.ledger.create_state(mon_identity, "MONETIZATION_CONFIGURATION", mon_payload)
        with tx(self.ledger.db_path) as conn:
            conn.execute(
                """INSERT INTO monetization_configuration(
                    artifact_state_id,opportunity_identity_id,mechanism,provider,account_ref,offer_or_product_ref,campaign_ref,
                    tracked_destination,attribution_json,payout_terms_json,currency,lifecycle_state
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (mon_state.state_id, opportunity_identity, "affiliate_synthetic_example", "SYNTHETIC_PROVIDER", "fixture-account", "fixture-offer", "fixture-campaign",
                 "https://example.invalid/fixture-only", json_dumps({"key":"fixture-attribution"}), json_dumps({"amount":20,"currency":"SAR","basis":"synthetic_fixture"}), "SAR", "READY_FOR_ACTIVATION"),
            )
            conn.execute(
                "INSERT INTO domain_record(artifact_state_id,stage,owner_authority,subject_identity_id,scope_json,record_state) VALUES(?,?,?,?,?,?)",
                (mon_state.state_id, "MONETIZATION_CONFIGURATION", "MCAA", opportunity_identity, '{}', "READY_FOR_ACTIVATION"),
            )
            for req in mon_payload["activation_requirements"]:
                conn.execute("""INSERT INTO monetization_activation_requirement(
                    monetization_configuration_state_id,requirement_key,required_state_type,accepted_values_json,payload_path,required,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (mon_state.state_id,req["key"],req["required_state_type"],json_dumps(req["accepted_values"]),req["payload_path"],int(req["required"]),now))
        self.ledger.add_provenance(priority.state_id, mon_state.state_id, "MONETIZATION_SELECTION_BASIS")
        bind(mon_state.state_id, priority.state_id, "MONETIZATION_SELECTION_BASIS", "UPSTREAM_REQUIRES_REASSESSMENT", {"fixture":True})
        records.setdefault("MONETIZATION_CONFIGURATION", []).append(mon_state.state_id)

        creative = self._r(records, "CREATIVE_ARTIFACT", self.ledger.record_domain(
            "CREATIVE_ARTIFACT", "Creative / Localization Content Authority", {
                "run_id": run_id,
                "language": "ar",
                "region": "SA",
            "target": {"language": "ar", "region": "SA", "platform": "youtube"},
                "content_type": "short_form_video_script",
                "creative_brief": "Synthetic demonstration only. No real-world claim or publishing intent.",
                "cta": "Fixture CTA bound to fixture monetization configuration",
                "monetization_configuration_state_id": mon_state.state_id,
                "fixture": True,
                "publication_authority": False,
            }, natural_key=f"{run_id}:creative", subject_identity_id=opportunity_identity, record_state="DRAFTED",
            upstream_states=[(mon_state.state_id, "CREATIVE_MONETIZATION_CONTEXT"), (eligibility.state_id, "CREATIVE_ELIGIBILITY_GATE")]
        ))
        bind(creative.state_id, mon_state.state_id, "CREATIVE_MONETIZATION_CONTEXT", "MATERIAL_UPSTREAM_INVALIDATES", {"fixture":True})
        bind(creative.state_id, eligibility.state_id, "CREATIVE_ELIGIBILITY_GATE", "MATERIAL_UPSTREAM_INVALIDATES", {"fixture":True})

        compliance = self._r(records, "COMPLIANCE_ASSESSMENT", self.ledger.record_domain(
            "COMPLIANCE_ASSESSMENT", "Distribution Compliance Authority", {
                "run_id": run_id,
                "target": {"jurisdiction":"SA","platform":"youtube","language":"ar","content_type":"short_form_video","audience":"general"},
                "coverage_state": "SUFFICIENT_FOR_SYNTHETIC_FIXTURE_ONLY",
                "gate_decision": "PASS",
                "basis": "fixture contains no real content and no political-sensitive material",
                "legal_rules_distinct_from_platform_policy": True,
                "fixture": True,
            }, natural_key=f"{run_id}:compliance", subject_identity_id=opportunity_identity, record_state="PASS",
            upstream_states=[(creative.state_id, "COMPLIANCE_CONTENT_TARGET"), (eligibility.state_id, "COMPLIANCE_CANNOT_LAUNDER_ELIGIBILITY")]
        ))
        bind(compliance.state_id, creative.state_id, "COMPLIANCE_CONTENT_TARGET", "UPSTREAM_REQUIRES_REASSESSMENT", {"fixture":True})
        bind(compliance.state_id, eligibility.state_id, "COMPLIANCE_CANNOT_LAUNDER_ELIGIBILITY", "MATERIAL_UPSTREAM_INVALIDATES", {"fixture":True})

        recommendation = self._r(records, "PUBLICATION_RECOMMENDATION", self.ledger.record_domain(
            "PUBLICATION_RECOMMENDATION", "Publication Recommendation Authority", {
                "run_id": run_id,
                "recommendation": "RECOMMEND_PUBLISH_FIXTURE_ONLY",
                "human_final_authorization_required": True,
                "fixture": True,
                "not_a_real_publication_recommendation": True,
            }, natural_key=f"{run_id}:recommendation", subject_identity_id=opportunity_identity, record_state="AWAITING_HUMAN_AUTHORIZATION",
            upstream_states=[(creative.state_id, "RECOMMENDATION_CONTENT"), (compliance.state_id, "RECOMMENDATION_COMPLIANCE")]
        ))
        bind(recommendation.state_id, creative.state_id, "RECOMMENDATION_CONTENT", "MATERIAL_UPSTREAM_INVALIDATES", {"fixture":True})
        bind(recommendation.state_id, compliance.state_id, "RECOMMENDATION_COMPLIANCE", "UPSTREAM_REQUIRES_REASSESSMENT", {"fixture":True})
        bind(recommendation.state_id, eligibility.state_id, "RECOMMENDATION_ELIGIBILITY", "MATERIAL_UPSTREAM_INVALIDATES", {"fixture":True})

        return DemoResult(
            run_id=run_id,
            records=records,
            stopped_at="HUMAN_FINAL_AUTHORIZATION",
            reason="v1 requires an actual human final authorization; synthetic runner does not fabricate it",
        )
