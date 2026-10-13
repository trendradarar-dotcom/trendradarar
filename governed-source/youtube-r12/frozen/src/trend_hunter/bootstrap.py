from __future__ import annotations

from .ledger import GovernanceLedger
from .util import utcnow
from .db import connect, tx
from .util import json_dumps, new_id


def _existing_contract(db_path: str, key: str, version: int) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM governance_contract_version WHERE contract_key=? AND version=?",
            (key, version),
        ).fetchone()
        return row["id"] if row else None


def ensure_contract(ledger: GovernanceLedger, key: str, version: int, payload: dict, *, effective_from: str) -> str:
    existing = _existing_contract(ledger.db_path, key, version)
    if existing:
        return existing
    return ledger.create_contract(key, version, payload, status="ACTIVE", effective_from=effective_from)


def bootstrap_governance(ledger: GovernanceLedger, adoption_effective_from: str | None = None) -> dict[str, str]:
    now = utcnow()
    governance_effective_from = adoption_effective_from or now
    ids: dict[str, str] = {}

    ids["U1_PURPOSE_ANCHOR@V1"] = ensure_contract(ledger, "U1_PURPOSE_ANCHOR", 1, {
        "purpose": "When an effective Cross-Market Gap contract independently designates a role-bound scope requiring saturation-related evaluation, require an interpretable governed characterization of that exact scope/reference frame/time-state under at least one admitted saturation-bearing dimension.",
        "forbidden_inferences": [
            "universal_saturation_ontology",
            "opportunity_attractiveness",
            "profitability",
            "priority",
            "recommendation",
        ],
        "orientation_semantics": "dimension-local only",
    }, effective_from=governance_effective_from)

    ids["K_GAP@V1"] = ensure_contract(ledger, "K_GAP_EVALUATED_SCOPE_SATURATION_CHARACTERIZATION", 1, {
        "class": "K_GAP_EVALUATED_SCOPE_SATURATION_CHARACTERIZATION",
        "requires": "U1-qualified saturation-related characterization for every independently designated role-bound scope instance",
        "does_not_mandate": ["competition","demand","capacity","occupancy","utilization","causal_effect","opportunity_value"],
        "role_neutrality": True,
        "origin_inference_forbidden": True,
    }, effective_from=governance_effective_from)

    ids["K_GAP_SATISFACTION@V1"] = ensure_contract(ledger, "K_GAP_SATISFACTION", 1, {
        "satisfied_if": "for every applicable role-bound scope there exists at least one realization admitted by U1_ADMISSIBLE_REALIZATION_FOR_K_GAP@V1 and sufficient under U1_SUFFICIENT_REALIZATION_FOR_K_GAP@V1",
        "required_characterization_fields": [
            "subject","reference_frame","time_state","dimension","reference_basis","orientation",
            "epistemic_status","coverage","uncertainty","provenance","applicability"
        ],
        "universal_scalar_not_required": True,
    }, effective_from=governance_effective_from)

    ids["U1_ADMISSIBLE_REALIZATION_FOR_K_GAP@V1"] = ensure_contract(ledger, "U1_ADMISSIBLE_REALIZATION_FOR_K_GAP", 1, {
        "requirements": [
            "satisfies_U1_PURPOSE_ANCHOR@V1",
            "respects_K_GAP@V1_semantic_boundary",
            "declares_exact_dimension_reference_orientation_result_domain_coverage_provenance",
            "routing_and_reference_selection_are_outcome_independent",
        ],
        "forbidden": ["hidden_unowned_ontology","opportunity_value","candidate_favorable_reference_selection"],
    }, effective_from=governance_effective_from)

    ids["U1_SUFFICIENT_REALIZATION_FOR_K_GAP@V1"] = ensure_contract(ledger, "U1_SUFFICIENT_REALIZATION_FOR_K_GAP", 1, {
        "sufficiency": "result is interpretable for the exact K instance under pinned frame/time/reference and reports epistemic status, coverage, uncertainty and applicability",
        "universal_classification_not_required": True,
    }, effective_from=governance_effective_from)

    ids["U1_E_V1_COVERAGE@V1"] = ensure_contract(ledger, "U1_E_V1_COVERAGE", 1, {
        "coverage": "all applicable K_GAP@V1 role-bound scope instances",
        "failure_mode": "NOT_EVALUABLE_OR_UNRESOLVED; never silently drop an applicable instance",
    }, effective_from=governance_effective_from)

    ids["U1_ROUTING_COMBINATION_RULE@V1"] = ensure_contract(ledger, "U1_ROUTING_COMBINATION_RULE", 1, {
        "routing": "predeclared_versioned_outcome_independent",
        "multiple_realizations": "may coexist without implicit composition or comparability",
        "forbidden": ["favorable_ontology_cherry_picking","dynamic_obligation_narrowing_to_fit_implementation"],
    }, effective_from=governance_effective_from)

    ids["U1_EFFECTIVE_ENVELOPE@V1"] = ensure_contract(ledger, "U1_EFFECTIVE_ENVELOPE", 1, {
        "purpose_anchor": "U1_PURPOSE_ANCHOR@V1",
        "mandatory_classes": ["K_GAP_EVALUATED_SCOPE_SATURATION_CHARACTERIZATION@V1"],
        "class_satisfaction_contract": "K_GAP_SATISFACTION@V1",
        "admissibility_predicate": "U1_ADMISSIBLE_REALIZATION_FOR_K_GAP@V1",
        "sufficiency_predicate": "U1_SUFFICIENT_REALIZATION_FOR_K_GAP@V1",
        "coverage_formula": "U1_E_V1_COVERAGE@V1",
        "routing_combination_rule": "U1_ROUTING_COMBINATION_RULE@V1",
        "other_classes": "not mandatory under E@V1 unless separately adopted; no global forever inference",
        "effectivity": "forward_only_no_retroactivity",
    }, effective_from=governance_effective_from)

    # Structural exact-state pinning for E@V1.  The human-readable labels in the
    # contract payload are not relied upon as the sole identity of referenced contracts.
    for role, child_key in {
        "PURPOSE_ANCHOR": "U1_PURPOSE_ANCHOR@V1",
        "MANDATORY_CLASS_K_GAP": "K_GAP@V1",
        "CLASS_SATISFACTION": "K_GAP_SATISFACTION@V1",
        "ADMISSIBILITY_PREDICATE": "U1_ADMISSIBLE_REALIZATION_FOR_K_GAP@V1",
        "SUFFICIENCY_PREDICATE": "U1_SUFFICIENT_REALIZATION_FOR_K_GAP@V1",
        "COVERAGE_FORMULA": "U1_E_V1_COVERAGE@V1",
        "ROUTING_COMBINATION_RULE": "U1_ROUTING_COMBINATION_RULE@V1",
    }.items():
        ledger.bind_contract_reference(ids["U1_EFFECTIVE_ENVELOPE@V1"], role, ids[child_key])

    ids["SRCA@V1"] = ensure_contract(ledger, "SATURATION_RELATED_CHARACTERIZATION_AUTHORITY", 1, {
        "owner": "SRCA",
        "owns": "reference-relative governed saturation-related characterization",
        "does_not_own": ["trend_measurement","opportunity_value","demand","competition","capacity"],
        "reference_integrity": "precommitted or selected by versioned outcome-independent rule",
        "universal_saturation_score_forbidden": True,
    }, effective_from=governance_effective_from)

    ids["R_SUPPLY@V1"] = ensure_contract(ledger, "CONTENT_SUPPLY_OCCUPANCY_RELATIVE_TO_SCOPE_BASELINE", 1, {
        "dimension": "content_supply_occupancy_relative_to_scope_baseline",
        "requires": [
            "exact_eligible_content_population","exact_scope","exact_time_state","exact_baseline",
            "baseline_selection_rule","occupancy_or_density_functional","reference_orientation",
            "result_domain","coverage","uncertainty","provenance","applicability"
        ],
        "baseline_semantic_closure_excludes": [
            "contestability","substitutability","competitive_population","demand_serving_suitability","competitive_arena"
        ],
        "admissible_for_K_GAP@V1": True,
        "sufficient_for_K_GAP@V1": True,
        "semantic_dependency_on_competition": False,
    }, effective_from=governance_effective_from)

    ids["POLITICAL_RISK@V1"] = ensure_contract(ledger, "POLITICAL_JURISDICTIONAL_RISK_EXCLUSION", 1, {
        "political_opposition_activism_mobilization": "INELIGIBLE_FOR_GENERATION_AND_PUBLICATION",
        "broader_state_sensitive_content": "HUMAN_REVIEW_OR_BLOCK_WHEN_MATERIAL_RISK_OR_AMBIGUITY",
        "truth_independent": True,
        "jurisdiction_aware": True,
        "platform_aware": True,
    }, effective_from=governance_effective_from)

    ids["CROSS_AUTHORITY_DEP@V1"] = ensure_contract(ledger, "CROSS_AUTHORITY_DEPENDENCY_INVALIDATION", 1, {
        "rule": "prospective downstream authority binds exact materially consumed upstream states",
        "material_change": "apply governed DependencyChangePolicy",
        "historical_records": "immutable",
        "gate_laundering_forbidden": True,
        "override_requires": ["explicit_contract","competence","scope_binding","effectivity","auditability"],
    }, effective_from=governance_effective_from)

    ids["EXECUTION_SCENARIO@V1"] = ensure_contract(ledger, "EXECUTION_CONFIGURATION_INTERFACE", 1, {
        "ordering": "ExecutionConfiguration exists before EconomicExpectation and Feasibility sibling assessments",
        "same_candidate_not_same_scenario": True,
        "future_state_dependency_forbidden": True,
    }, effective_from=governance_effective_from)

    ids["MCAA@V1"] = ensure_contract(ledger, "MONETIZATION_CONFIGURATION_ACTIVATION_AUTHORITY", 1, {
        "configuration_lifecycle": ["DRAFT","CONFIGURED","READY_FOR_ACTIVATION","SUPERSEDED","RETIRED"],
        "activation_lifecycle": ["PENDING","ACTIVE","SUSPENDED","TERMINATED","FAILED"],
        "configuration_may_precede_creative": True,
        "activation_requires_mechanism_specific_dependencies": True,
        "configuration_not_activation": True,
    }, effective_from=governance_effective_from)

    ids["P3B_CLOSURE@V1"] = ensure_contract(ledger, "P3B_U1_NECESSITY_CLOSURE", 1, {
        "p3b1_status": "PASS_CLOSED",
        "p3b_status": "PASS_CLOSED",
        "effective_envelope": "U1_EFFECTIVE_ENVELOPE@V1",
        "competition_current_u1_e_v1": "NOT_REQUIRED",
        "counterexample_realization": "CONTENT_SUPPLY_OCCUPANCY_RELATIVE_TO_SCOPE_BASELINE@V1",
        "counterexample_proof": {
            "admissible": True,
            "sufficient": True,
            "semantic_dependency_on_competition": False,
            "baseline_competition_semantic_closure_excluded": True,
        },
        "global_competition_status": "OPTIONAL_DEFERRED",
        "global_status_provenance": "PARENT_LEVEL_REQUIREMENT_SCAN",
        "future_independently_effective_obligation_may_reopen_prospectively": True,
    }, effective_from=governance_effective_from)

    ids["CURRENT_VIEW_POLICY@V1"] = ensure_contract(ledger, "CURRENT_VIEW_PROJECTION_POLICY", 1, {
        "source_of_truth": False,
        "derived": True,
        "rebuildable": True,
        "latest_decision_wins": False,
        "replacement_requires_same_exact_governed_adjudication_target": True,
        "historical_adjudications_remain_immutable": True,
    }, effective_from=governance_effective_from)

    ids["PARENT_ROADMAP_CLOSURE@V1"] = ensure_contract(ledger, "PARENT_ROADMAP_RESPONSIBILITY_OWNERSHIP_CLOSURE", 1, {
        "status": "PASS_CLOSED",
        "semantic_governance_architecture": "COMPLETE",
        "next_architectural_owner": "NONE",
        "scope": "currently confirmed required semantic/governance responsibilities",
        "does_not_mean": ["ENGINEERING_COMPLETE","OPERATIONALLY_LIVE","ECONOMICALLY_VALIDATED"],
        "reopen_only_for": ["PROVEN_EXECUTION_CONTRADICTION","INTEGRITY_DEFECT","NEW_FORWARD_GOVERNANCE_EVENT"],
    }, effective_from=governance_effective_from)

    for key, payload in {
        "OPPORTUNITY_AUTHORITY": {
            "boundary": "candidate-relative opportunity semantics only",
            "forbidden": ["hidden_universal_score","eligibility","compliance","realized_economics"],
        },
        "OPPORTUNITY_ELIGIBILITY_JURISDICTIONAL_RISK_AUTHORITY": {
            "outcomes": ["ELIGIBLE","INELIGIBLE","HUMAN_REVIEW_REQUIRED","NOT_EVALUABLE"],
            "truth_independent": True,
            "political_risk_contract": "POLITICAL_JURISDICTIONAL_RISK_EXCLUSION@V1",
        },
        "ECONOMIC_EXPECTATION_AUTHORITY": {
            "requires": ["exact_execution_configuration","monetization_mechanism_or_scenario","horizon","governed_assumptions"],
            "prediction_not_outcome": True,
            "opaque_universal_score_forbidden": True,
        },
        "EXECUTION_FEASIBILITY_AUTHORITY": {
            "configuration_precedes_verdict": True,
            "outcomes": ["FEASIBLE","FEASIBLE_WITH_CONSTRAINTS","NOT_FEASIBLE","UNRESOLVED"],
        },
        "PRIORITIZATION_RESOURCE_ALLOCATION_AUTHORITY": {
            "requires_same_or_governed_comparable_execution_configuration": True,
            "hidden_universal_score_forbidden": True,
        },
        "CREATIVE_LOCALIZATION_CONTENT_AUTHORITY": {
            "publication_authority": False,
            "uncertainty_strengthening_forbidden": True,
            "blocked_candidate_generation_forbidden": True,
        },
        "DISTRIBUTION_COMPLIANCE_AUTHORITY": {
            "coverage_states": ["SUFFICIENT","PARTIAL","UNKNOWN"],
            "gate_decisions": ["PASS","WARNING","HUMAN_REVIEW","BLOCK"],
            "legal_rules_distinct_from_platform_policy": True,
            "compliance_not_truth": True,
        },
        "PUBLICATION_RECOMMENDATION_HUMAN_AUTHORITY": {
            "recommendations": ["RECOMMEND_PUBLISH","RECOMMEND_REVISE","RECOMMEND_HOLD","DO_NOT_RECOMMEND"],
            "human_final_authorization_required_v1": True,
            "material_content_change_requires_reauthorization_when_contract_says_so": True,
        },
        "EXECUTION_PUBLICATION_RECORD_AUTHORITY": {
            "append_only": True,
            "bind_exact_content_authorization_channel_result": True,
        },
        "ECONOMIC_OUTCOME_LEARNING_AUTHORITY": {
            "separates": ["PerformanceObservation","RevenueObservation","CostObservation","AttributionAssertion","RealizedEconomicOutcome","LearningUpdateProposal"],
            "revenue_not_profit": True,
            "historical_prediction_not_rewritten": True,
            "learning_forward_versions_only": True,
        },
        "C1_ECONOMIC_EVIDENCE_SOURCE_BINDING": {
            "generic_nonmanual_source_is_not_financial_authority": True,
            "requires_exact_connector_and_source_name_binding": True,
            "allowed_roles_are_explicit": ["REVENUE", "COST"],
            "currency_scope_is_explicit": True,
            "manual_and_synthetic_sources_cannot_be_granted_authority": True,
            "stale_or_revoked_binding_fails_closed": True,
            "source_record_and_authority_binding_are_separate": True,
        },
    }.items():
        ids[f"{key}@V1"] = ensure_contract(ledger, key, 1, payload, effective_from=governance_effective_from)

    ids["PIPELINE_ORDER@V1"] = ensure_contract(ledger, "GOVERNED_PIPELINE_ORDER", 1, {
        "order": [
            "Sources","Artifacts/Signals","Evidence/Claims","Entity","Story","Trend",
            "Saturation Characterization","Opportunity","Eligibility/Risk","ExecutionConfiguration",
            "Economic Expectation || Execution Feasibility","Prioritization/Allocation",
            "Monetization Configuration","Creative/Localization","Distribution Compliance",
            "Publication Recommendation","Human Final Authorization",
            "Monetization Activation where required","Execution/Publication","Performance",
            "Revenue","Cost","Profit","Learning"
        ],
        "future_state_dependency_forbidden": True,
        "gate_laundering_forbidden": True,
    }, effective_from=governance_effective_from)

    ids["EVIDENCE_RESOLUTION_PROCEDURE@V1"] = ensure_contract(ledger, "HISTORICAL_AUTHORITY_EFFECTIVITY_EVIDENCE_RESOLUTION_PROCEDURE", 1, {
        "sequence": [
            "record_provenance_integrity",
            "proposition_relative_evidentiary_entitlement",
            "frozen_effectivity_evidence_classification",
            "provenance_preserving_exact_semantic_state_normalization",
            "historical_competence_authority_chain",
            "exact_content_adoption_actuality",
            "effectivity_rule_and_trigger",
            "later_change_clarification_suspension_supersession",
            "exact_semantic_conflict_test",
            "historically_authoritative_precedence_conflict_rule",
            "corpus_bound_adjudication",
            "current_view_update_same_exact_target_only",
        ],
        "invariants": [
            "evidentiary_entitlement_is_proposition_relative",
            "authentic_record_ne_authoritative_record",
            "record_multiplicity_ne_independent_corroboration",
            "normalization_must_not_manufacture_correspondence",
            "apparent_textual_disagreement_ne_authoritative_semantic_conflict",
            "current_precedence_rule_not_backdated",
            "new_evidence_creates_new_adjudication",
            "evidence_evolution_ne_integrity_defect",
            "current_view_not_latest_decision_wins",
        ],
    }, effective_from=governance_effective_from)

    ids["HISTORICAL_EFFECTIVITY_CURRENT_STATUS@V1"] = ensure_contract(ledger, "HISTORICAL_EFFECTIVITY_CURRENT_STATUS", 1, {
        "historical_authoritative_obligation_actuality": "NOT_PROVABLE_FROM_REVIEWED_AVAILABLE_RECORD",
        "original_governing_adoption": "NOT_PROVABLE_FROM_REVIEWED_AVAILABLE_RECORD",
        "original_effectivity_start": "NOT_PROVABLE_FROM_REVIEWED_AVAILABLE_RECORD",
        "continuous_historical_effectivity": "NOT_PROVEN",
        "later_neutrality_clarification": "ESTABLISHED_AS_LATER_GOVERNANCE_ONLY",
        "semantics": "corpus_bound_negative_result_not_FALSE_and_not_NEVER_EXISTED",
        "independent_reproduction_note": "This delivery encodes the accepted governance result; the original reviewed conversation corpus is not bundled, so the historical adjudication itself is not claimed as independently reproduced by this package.",
    }, effective_from=governance_effective_from)

    # Frozen historical audit methodology itself.
    with connect(ledger.db_path) as conn:
        row = conn.execute(
            "SELECT id FROM methodology_version WHERE methodology_key='EFFECTIVITY_EVIDENCE_AUDIT' AND version=1"
        ).fetchone()
    if row:
        ids["EFFECTIVITY_EVIDENCE_AUDIT@V1"] = row["id"]
    else:
        ids["EFFECTIVITY_EVIDENCE_AUDIT@V1"] = ledger.create_methodology("EFFECTIVITY_EVIDENCE_AUDIT", 1, {
            "status": "PASS_CLOSED_FROZEN",
            "invariants": [
                "content_documented_ne_content_authoritative",
                "authority_not_proven_ne_authority_disproven",
                "recorded_approval_ne_governing_adoption",
                "approval_scope_ne_document_scope",
                "current_competence_ne_historical_competence",
                "adoption_actuality_ne_effectivity_actuality",
                "effectivity_rule_ne_trigger_satisfaction",
                "authoritative_state_at_T2_ne_original_adoption_at_T2",
                "no_supersession_proven_ne_continuous_effectivity",
                "not_provable_from_corpus_ne_globally_unprovable",
                "authority_provenance_acyclic_scope_preserving_effectivity_bound",
                "normalization_provenance_and_meaning_preserving",
                "adjudication_bound_to_exact_consumed_derived_artifacts",
            ],
        })

    # Standard dependency policies.
    existing = {}
    with connect(ledger.db_path) as conn:
        for row in conn.execute("SELECT policy_key,id FROM dependency_change_policy"):
            existing[row["policy_key"]] = row["id"]
    for key, effect, rule in [
        ("MATERIAL_UPSTREAM_INVALIDATES", "INVALIDATE", {"material": True}),
        ("UPSTREAM_REQUIRES_RECONCILIATION", "RECONCILE", {"identity_or_reference_drift": True}),
        ("UPSTREAM_REQUIRES_REASSESSMENT", "REASSESS", {"assessment_input_changed": True}),
        ("NON_MATERIAL_NO_EFFECT", "NO_EFFECT", {"material": False}),
    ]:
        if key in existing:
            ids[key] = existing[key]
        else:
            ids[key] = ledger.create_dependency_policy(key, 1, effect, rule, {"scope": "declared_by_binding"}, effective_from=(governance_effective_from or now))

    # Bind every bootstrapped governance contract forward-effectively.  This remains
    # separate from historical effectivity and never backdates the historical obligation.
    with connect(ledger.db_path) as conn:
        existing_effectivity = {(r["target_id"], r["rule_type"], r["effective_from"]) for r in conn.execute(
            "SELECT target_id,rule_type,effective_from FROM effectivity_binding WHERE target_type='GOVERNANCE_CONTRACT_VERSION'"
        )}
    for label, target_id in list(ids.items()):
        if not (isinstance(target_id, str) and (label.endswith('@V1') or label in {"MATERIAL_UPSTREAM_INVALIDATES","UPSTREAM_REQUIRES_RECONCILIATION","UPSTREAM_REQUIRES_REASSESSMENT","NON_MATERIAL_NO_EFFECT"})):
            continue
        # Dependency policy ids are not governance contract versions; skip them.
        if label in {"MATERIAL_UPSTREAM_INVALIDATES","UPSTREAM_REQUIRES_RECONCILIATION","UPSTREAM_REQUIRES_REASSESSMENT","NON_MATERIAL_NO_EFFECT"}:
            continue
        key = (target_id, "FORWARD_FROM_CURRENT_ADOPTION", governance_effective_from)
        if key not in existing_effectivity and label != "EFFECTIVITY_EVIDENCE_AUDIT@V1":
            ledger.create_effectivity_binding(
                "GOVERNANCE_CONTRACT_VERSION", target_id, "FORWARD_FROM_CURRENT_ADOPTION",
                trigger={"type": "CURRENT_AUTHORIZED_GOVERNANCE_ADOPTION", "no_retroactivity": True},
                effective_from=governance_effective_from,
            )

    return ids
