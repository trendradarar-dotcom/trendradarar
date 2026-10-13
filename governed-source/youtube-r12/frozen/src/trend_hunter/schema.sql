PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_migration (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    schema_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_identity (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    natural_key TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_artifact_identity_kind_natural
ON artifact_identity(kind, natural_key) WHERE natural_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS canonicalization_profile (
    id TEXT PRIMARY KEY,
    profile_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    rules_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(profile_key, version)
);

CREATE TABLE IF NOT EXISTS content_descriptor (
    id TEXT PRIMARY KEY,
    raw_hash_algorithm TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    raw_size_bytes INTEGER NOT NULL,
    raw_storage_ref TEXT NOT NULL,
    canonical_hash_algorithm TEXT,
    canonical_hash TEXT,
    canonicalization_profile_id TEXT,
    canonical_storage_ref TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(canonicalization_profile_id) REFERENCES canonicalization_profile(id)
);

CREATE TABLE IF NOT EXISTS artifact_state (
    id TEXT PRIMARY KEY,
    identity_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    state_type TEXT NOT NULL,
    content_descriptor_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'COMMITTED',
    recorded_at TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    effective_from TEXT,
    effective_to TEXT,
    source_asserted_at TEXT,
    observed_at TEXT,
    supersedes_state_id TEXT,
    FOREIGN KEY(identity_id) REFERENCES artifact_identity(id),
    FOREIGN KEY(content_descriptor_id) REFERENCES content_descriptor(id),
    FOREIGN KEY(supersedes_state_id) REFERENCES artifact_state(id),
    UNIQUE(identity_id, version)
);
CREATE INDEX IF NOT EXISTS ix_artifact_state_identity ON artifact_state(identity_id, version);

CREATE TABLE IF NOT EXISTS provenance_edge (
    id TEXT PRIMARY KEY,
    from_state_id TEXT NOT NULL,
    to_state_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    materially_consumed INTEGER NOT NULL DEFAULT 1 CHECK(materially_consumed IN (0,1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(from_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(to_state_id) REFERENCES artifact_state(id)
);
CREATE INDEX IF NOT EXISTS ix_prov_from ON provenance_edge(from_state_id);
CREATE INDEX IF NOT EXISTS ix_prov_to ON provenance_edge(to_state_id);

CREATE TABLE IF NOT EXISTS governance_contract_version (
    id TEXT PRIMARY KEY,
    contract_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    artifact_state_id TEXT NOT NULL,
    status TEXT NOT NULL,
    effective_from TEXT,
    effective_to TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id),
    UNIQUE(contract_key, version)
);

CREATE TABLE IF NOT EXISTS governance_authority_grant (
    id TEXT PRIMARY KEY,
    grantee_type TEXT NOT NULL,
    grantee_key TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    can_delegate INTEGER NOT NULL DEFAULT 0 CHECK(can_delegate IN (0,1)),
    root_basis_state_id TEXT,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(root_basis_state_id) REFERENCES artifact_state(id)
);

CREATE TABLE IF NOT EXISTS delegation_edge (
    id TEXT PRIMARY KEY,
    delegator_grant_id TEXT NOT NULL,
    delegatee_grant_id TEXT NOT NULL,
    delegated_scope_json TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(delegator_grant_id) REFERENCES governance_authority_grant(id),
    FOREIGN KEY(delegatee_grant_id) REFERENCES governance_authority_grant(id),
    CHECK(delegator_grant_id <> delegatee_grant_id)
);

CREATE TABLE IF NOT EXISTS governance_event (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    actor_or_process TEXT NOT NULL,
    authority_grant_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    effective_at TEXT,
    FOREIGN KEY(authority_grant_id) REFERENCES governance_authority_grant(id)
);

CREATE TABLE IF NOT EXISTS effectivity_binding (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    trigger_json TEXT NOT NULL DEFAULT '{}',
    effective_from TEXT,
    effective_to TEXT,
    governance_event_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(governance_event_id) REFERENCES governance_event(id)
);

CREATE TABLE IF NOT EXISTS methodology_version (
    id TEXT PRIMARY KEY,
    methodology_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    artifact_state_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id),
    UNIQUE(methodology_key, version)
);

CREATE TABLE IF NOT EXISTS audit_corpus_snapshot (
    id TEXT PRIMARY KEY,
    methodology_version_id TEXT NOT NULL,
    review_boundary_json TEXT NOT NULL,
    item_ids_json TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    corpus_hash_algorithm TEXT NOT NULL,
    corpus_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(methodology_version_id) REFERENCES methodology_version(id)
);

CREATE TABLE IF NOT EXISTS normalization_assertion (
    id TEXT PRIMARY KEY,
    source_state_id TEXT NOT NULL,
    normalized_state_id TEXT NOT NULL,
    mapping_contract_id TEXT,
    assertion_state TEXT NOT NULL,
    rationale_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(normalized_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(mapping_contract_id) REFERENCES governance_contract_version(id)
);

CREATE TABLE IF NOT EXISTS correspondence_judgment (
    id TEXT PRIMARY KEY,
    left_state_id TEXT NOT NULL,
    right_state_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    judgment_state TEXT NOT NULL,
    methodology_version_id TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(left_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(right_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(methodology_version_id) REFERENCES methodology_version(id)
);

CREATE TABLE IF NOT EXISTS adjudication_target (
    id TEXT PRIMARY KEY,
    target_key TEXT NOT NULL UNIQUE,
    proposition_type TEXT NOT NULL,
    subject_identity_id TEXT,
    semantic_scope_json TEXT NOT NULL DEFAULT '{}',
    time_basis_json TEXT NOT NULL DEFAULT '{}',
    applicability_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(subject_identity_id) REFERENCES artifact_identity(id)
);

CREATE TABLE IF NOT EXISTS adjudication (
    id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    methodology_version_id TEXT NOT NULL,
    corpus_snapshot_id TEXT NOT NULL,
    decision_state TEXT NOT NULL,
    decision_payload_json TEXT NOT NULL,
    integrity_status TEXT NOT NULL DEFAULT 'VALID',
    recorded_at TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    prior_current_adjudication_id TEXT,
    FOREIGN KEY(target_id) REFERENCES adjudication_target(id),
    FOREIGN KEY(methodology_version_id) REFERENCES methodology_version(id),
    FOREIGN KEY(corpus_snapshot_id) REFERENCES audit_corpus_snapshot(id),
    FOREIGN KEY(prior_current_adjudication_id) REFERENCES adjudication(id)
);
CREATE INDEX IF NOT EXISTS ix_adjudication_target ON adjudication(target_id, committed_at);

CREATE TABLE IF NOT EXISTS adjudication_consumed_artifact (
    adjudication_id TEXT NOT NULL,
    artifact_state_id TEXT NOT NULL,
    consumption_role TEXT NOT NULL,
    exact_raw_hash TEXT NOT NULL,
    exact_canonical_hash TEXT,
    PRIMARY KEY(adjudication_id, artifact_state_id, consumption_role),
    FOREIGN KEY(adjudication_id) REFERENCES adjudication(id),
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id)
);

CREATE TABLE IF NOT EXISTS dependency_change_policy (
    id TEXT PRIMARY KEY,
    policy_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    effect TEXT NOT NULL CHECK(effect IN ('INVALIDATE','RECONCILE','REASSESS','NO_EFFECT')),
    materiality_rule_json TEXT NOT NULL,
    affected_semantics_json TEXT NOT NULL DEFAULT '{}',
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(policy_key, version)
);

CREATE TABLE IF NOT EXISTS dependency_binding (
    id TEXT PRIMARY KEY,
    downstream_state_id TEXT NOT NULL,
    upstream_state_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL,
    change_policy_id TEXT NOT NULL,
    materiality_basis_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(downstream_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(upstream_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(change_policy_id) REFERENCES dependency_change_policy(id)
);

CREATE TABLE IF NOT EXISTS invalidation_reconciliation_event (
    id TEXT PRIMARY KEY,
    dependency_binding_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('INVALIDATED','RECONCILIATION_REQUIRED','REASSESSMENT_REQUIRED','NO_EFFECT_CONFIRMED')),
    upstream_old_state_id TEXT NOT NULL,
    upstream_new_state_id TEXT,
    affected_downstream_state_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    FOREIGN KEY(dependency_binding_id) REFERENCES dependency_binding(id),
    FOREIGN KEY(upstream_old_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(upstream_new_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(affected_downstream_state_id) REFERENCES artifact_state(id)
);

CREATE TABLE IF NOT EXISTS integrity_incident (
    id TEXT PRIMARY KEY,
    incident_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS current_view_projection (
    projection_key TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    current_state_id TEXT,
    current_adjudication_id TEXT,
    rebuilt_at TEXT NOT NULL,
    FOREIGN KEY(current_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(current_adjudication_id) REFERENCES adjudication(id)
);

CREATE TABLE IF NOT EXISTS execution_configuration (
    artifact_state_id TEXT PRIMARY KEY,
    opportunity_identity_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    channel TEXT,
    live_channel_binding_state_id TEXT,
    content_form TEXT NOT NULL,
    production_route TEXT NOT NULL,
    actionable_from TEXT,
    actionable_to TEXT,
    required_resources_json TEXT NOT NULL,
    capital_assumption_json TEXT NOT NULL,
    operational_mode TEXT NOT NULL,
    monetization_configuration_state_id TEXT,
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(opportunity_identity_id) REFERENCES artifact_identity(id),
    FOREIGN KEY(live_channel_binding_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(monetization_configuration_state_id) REFERENCES artifact_state(id)
);

CREATE TABLE IF NOT EXISTS monetization_configuration (
    artifact_state_id TEXT PRIMARY KEY,
    opportunity_identity_id TEXT NOT NULL,
    mechanism TEXT NOT NULL,
    provider TEXT,
    account_ref TEXT,
    offer_or_product_ref TEXT,
    campaign_ref TEXT,
    tracked_destination TEXT,
    attribution_json TEXT NOT NULL DEFAULT '{}',
    payout_terms_json TEXT NOT NULL DEFAULT '{}',
    currency TEXT,
    lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('DRAFT','CONFIGURED','READY_FOR_ACTIVATION','SUPERSEDED','RETIRED')),
    commercial_authorization_ref TEXT,
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(opportunity_identity_id) REFERENCES artifact_identity(id)
);

CREATE TABLE IF NOT EXISTS monetization_activation_record (
    artifact_state_id TEXT PRIMARY KEY,
    monetization_configuration_state_id TEXT NOT NULL,
    activation_state TEXT NOT NULL CHECK(activation_state IN ('PENDING','ACTIVE','SUSPENDED','TERMINATED','FAILED')),
    activated_at TEXT,
    provider_result_ref TEXT,
    dependency_snapshot_json TEXT NOT NULL,
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(monetization_configuration_state_id) REFERENCES artifact_state(id)
);

-- Generic domain stage registry. The authoritative payload remains in artifact_state.
CREATE TABLE IF NOT EXISTS domain_record (
    artifact_state_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    owner_authority TEXT NOT NULL,
    subject_identity_id TEXT,
    scope_json TEXT NOT NULL DEFAULT '{}',
    record_state TEXT NOT NULL,
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(subject_identity_id) REFERENCES artifact_identity(id)
);
CREATE INDEX IF NOT EXISTS ix_domain_stage ON domain_record(stage, record_state);



-- V2 hardening: exact consumed derived-artifact identity, proposition-relative entitlement,
-- target fingerprints, exact contract pinning, and mechanism-specific activation requirements.
CREATE TABLE IF NOT EXISTS governance_contract_reference (
    parent_contract_version_id TEXT NOT NULL,
    reference_role TEXT NOT NULL,
    child_contract_version_id TEXT NOT NULL,
    child_artifact_state_id TEXT NOT NULL,
    exact_raw_hash TEXT NOT NULL,
    exact_canonical_hash TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY(parent_contract_version_id, reference_role, child_contract_version_id),
    FOREIGN KEY(parent_contract_version_id) REFERENCES governance_contract_version(id),
    FOREIGN KEY(child_contract_version_id) REFERENCES governance_contract_version(id),
    FOREIGN KEY(child_artifact_state_id) REFERENCES artifact_state(id)
);

CREATE TABLE IF NOT EXISTS normalization_assertion_artifact (
    normalization_assertion_id TEXT PRIMARY KEY,
    artifact_state_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY(normalization_assertion_id) REFERENCES normalization_assertion(id),
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id)
);

CREATE TABLE IF NOT EXISTS correspondence_judgment_artifact (
    correspondence_judgment_id TEXT PRIMARY KEY,
    artifact_state_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY(correspondence_judgment_id) REFERENCES correspondence_judgment(id),
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id)
);

CREATE TABLE IF NOT EXISTS adjudication_target_fingerprint (
    target_id TEXT PRIMARY KEY,
    authority_role TEXT,
    target_hash_algorithm TEXT NOT NULL,
    target_hash TEXT NOT NULL UNIQUE,
    canonical_target_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(target_id) REFERENCES adjudication_target(id)
);

CREATE TABLE IF NOT EXISTS evidentiary_entitlement (
    id TEXT PRIMARY KEY,
    record_state_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    methodology_version_id TEXT,
    entitlement_state TEXT NOT NULL CHECK(entitlement_state IN ('ENTITLED','NOT_ENTITLED','UNRESOLVED')),
    proposition_strength TEXT NOT NULL,
    basis_json TEXT NOT NULL DEFAULT '{}',
    artifact_state_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY(record_state_id) REFERENCES artifact_state(id),
    FOREIGN KEY(target_id) REFERENCES adjudication_target(id),
    FOREIGN KEY(methodology_version_id) REFERENCES methodology_version(id),
    FOREIGN KEY(artifact_state_id) REFERENCES artifact_state(id)
);

CREATE TABLE IF NOT EXISTS monetization_activation_requirement (
    monetization_configuration_state_id TEXT NOT NULL,
    requirement_key TEXT NOT NULL,
    required_state_type TEXT NOT NULL,
    accepted_values_json TEXT NOT NULL DEFAULT '{}',
    payload_path TEXT,
    required INTEGER NOT NULL DEFAULT 1 CHECK(required IN (0,1)),
    created_at TEXT NOT NULL,
    PRIMARY KEY(monetization_configuration_state_id, requirement_key),
    FOREIGN KEY(monetization_configuration_state_id) REFERENCES artifact_state(id)
);

-- Append-only triggers. current_view_projection is intentionally rebuildable/mutable.

CREATE TRIGGER IF NOT EXISTS trg_artifact_identity_no_update
BEFORE UPDATE ON artifact_identity
BEGIN
    SELECT RAISE(ABORT, 'artifact_identity is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_artifact_identity_no_delete
BEFORE DELETE ON artifact_identity
BEGIN
    SELECT RAISE(ABORT, 'artifact_identity is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_canonicalization_profile_no_update
BEFORE UPDATE ON canonicalization_profile
BEGIN
    SELECT RAISE(ABORT, 'canonicalization_profile is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_canonicalization_profile_no_delete
BEFORE DELETE ON canonicalization_profile
BEGIN
    SELECT RAISE(ABORT, 'canonicalization_profile is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_content_descriptor_no_update
BEFORE UPDATE ON content_descriptor
BEGIN
    SELECT RAISE(ABORT, 'content_descriptor is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_content_descriptor_no_delete
BEFORE DELETE ON content_descriptor
BEGIN
    SELECT RAISE(ABORT, 'content_descriptor is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_artifact_state_no_update
BEFORE UPDATE ON artifact_state
BEGIN
    SELECT RAISE(ABORT, 'artifact_state is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_artifact_state_no_delete
BEFORE DELETE ON artifact_state
BEGIN
    SELECT RAISE(ABORT, 'artifact_state is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_provenance_edge_no_update
BEFORE UPDATE ON provenance_edge
BEGIN
    SELECT RAISE(ABORT, 'provenance_edge is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_provenance_edge_no_delete
BEFORE DELETE ON provenance_edge
BEGIN
    SELECT RAISE(ABORT, 'provenance_edge is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_governance_contract_version_no_update
BEFORE UPDATE ON governance_contract_version
BEGIN
    SELECT RAISE(ABORT, 'governance_contract_version is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_governance_contract_version_no_delete
BEFORE DELETE ON governance_contract_version
BEGIN
    SELECT RAISE(ABORT, 'governance_contract_version is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_governance_authority_grant_no_update
BEFORE UPDATE ON governance_authority_grant
BEGIN
    SELECT RAISE(ABORT, 'governance_authority_grant is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_governance_authority_grant_no_delete
BEFORE DELETE ON governance_authority_grant
BEGIN
    SELECT RAISE(ABORT, 'governance_authority_grant is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_delegation_edge_no_update
BEFORE UPDATE ON delegation_edge
BEGIN
    SELECT RAISE(ABORT, 'delegation_edge is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_delegation_edge_no_delete
BEFORE DELETE ON delegation_edge
BEGIN
    SELECT RAISE(ABORT, 'delegation_edge is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_governance_event_no_update
BEFORE UPDATE ON governance_event
BEGIN
    SELECT RAISE(ABORT, 'governance_event is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_governance_event_no_delete
BEFORE DELETE ON governance_event
BEGIN
    SELECT RAISE(ABORT, 'governance_event is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_effectivity_binding_no_update
BEFORE UPDATE ON effectivity_binding
BEGIN
    SELECT RAISE(ABORT, 'effectivity_binding is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_effectivity_binding_no_delete
BEFORE DELETE ON effectivity_binding
BEGIN
    SELECT RAISE(ABORT, 'effectivity_binding is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_methodology_version_no_update
BEFORE UPDATE ON methodology_version
BEGIN
    SELECT RAISE(ABORT, 'methodology_version is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_methodology_version_no_delete
BEFORE DELETE ON methodology_version
BEGIN
    SELECT RAISE(ABORT, 'methodology_version is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_corpus_snapshot_no_update
BEFORE UPDATE ON audit_corpus_snapshot
BEGIN
    SELECT RAISE(ABORT, 'audit_corpus_snapshot is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_audit_corpus_snapshot_no_delete
BEFORE DELETE ON audit_corpus_snapshot
BEGIN
    SELECT RAISE(ABORT, 'audit_corpus_snapshot is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_normalization_assertion_no_update
BEFORE UPDATE ON normalization_assertion
BEGIN
    SELECT RAISE(ABORT, 'normalization_assertion is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_normalization_assertion_no_delete
BEFORE DELETE ON normalization_assertion
BEGIN
    SELECT RAISE(ABORT, 'normalization_assertion is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_correspondence_judgment_no_update
BEFORE UPDATE ON correspondence_judgment
BEGIN
    SELECT RAISE(ABORT, 'correspondence_judgment is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_correspondence_judgment_no_delete
BEFORE DELETE ON correspondence_judgment
BEGIN
    SELECT RAISE(ABORT, 'correspondence_judgment is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjudication_target_no_update
BEFORE UPDATE ON adjudication_target
BEGIN
    SELECT RAISE(ABORT, 'adjudication_target is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_adjudication_target_no_delete
BEFORE DELETE ON adjudication_target
BEGIN
    SELECT RAISE(ABORT, 'adjudication_target is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjudication_no_update
BEFORE UPDATE ON adjudication
BEGIN
    SELECT RAISE(ABORT, 'adjudication is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_adjudication_no_delete
BEFORE DELETE ON adjudication
BEGIN
    SELECT RAISE(ABORT, 'adjudication is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjudication_consumed_artifact_no_update
BEFORE UPDATE ON adjudication_consumed_artifact
BEGIN
    SELECT RAISE(ABORT, 'adjudication_consumed_artifact is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_adjudication_consumed_artifact_no_delete
BEFORE DELETE ON adjudication_consumed_artifact
BEGIN
    SELECT RAISE(ABORT, 'adjudication_consumed_artifact is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_dependency_change_policy_no_update
BEFORE UPDATE ON dependency_change_policy
BEGIN
    SELECT RAISE(ABORT, 'dependency_change_policy is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_dependency_change_policy_no_delete
BEFORE DELETE ON dependency_change_policy
BEGIN
    SELECT RAISE(ABORT, 'dependency_change_policy is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_dependency_binding_no_update
BEFORE UPDATE ON dependency_binding
BEGIN
    SELECT RAISE(ABORT, 'dependency_binding is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_dependency_binding_no_delete
BEFORE DELETE ON dependency_binding
BEGIN
    SELECT RAISE(ABORT, 'dependency_binding is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_invalidation_reconciliation_event_no_update
BEFORE UPDATE ON invalidation_reconciliation_event
BEGIN
    SELECT RAISE(ABORT, 'invalidation_reconciliation_event is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_invalidation_reconciliation_event_no_delete
BEFORE DELETE ON invalidation_reconciliation_event
BEGIN
    SELECT RAISE(ABORT, 'invalidation_reconciliation_event is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_integrity_incident_no_update
BEFORE UPDATE ON integrity_incident
BEGIN
    SELECT RAISE(ABORT, 'integrity_incident is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_integrity_incident_no_delete
BEFORE DELETE ON integrity_incident
BEGIN
    SELECT RAISE(ABORT, 'integrity_incident is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_execution_configuration_no_update
BEFORE UPDATE ON execution_configuration
BEGIN
    SELECT RAISE(ABORT, 'execution_configuration is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_execution_configuration_no_delete
BEFORE DELETE ON execution_configuration
BEGIN
    SELECT RAISE(ABORT, 'execution_configuration is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_monetization_configuration_no_update
BEFORE UPDATE ON monetization_configuration
BEGIN
    SELECT RAISE(ABORT, 'monetization_configuration is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_monetization_configuration_no_delete
BEFORE DELETE ON monetization_configuration
BEGIN
    SELECT RAISE(ABORT, 'monetization_configuration is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_monetization_activation_record_no_update
BEFORE UPDATE ON monetization_activation_record
BEGIN
    SELECT RAISE(ABORT, 'monetization_activation_record is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_monetization_activation_record_no_delete
BEFORE DELETE ON monetization_activation_record
BEGIN
    SELECT RAISE(ABORT, 'monetization_activation_record is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_domain_record_no_update
BEFORE UPDATE ON domain_record
BEGIN
    SELECT RAISE(ABORT, 'domain_record is append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_domain_record_no_delete
BEFORE DELETE ON domain_record
BEGIN
    SELECT RAISE(ABORT, 'domain_record is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_schema_migration_no_update
BEFORE UPDATE ON schema_migration
BEGIN SELECT RAISE(ABORT, 'schema_migration is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_schema_migration_no_delete
BEFORE DELETE ON schema_migration
BEGIN SELECT RAISE(ABORT, 'schema_migration is append-only'); END;


-- V2 append-only hardening tables.
CREATE TRIGGER IF NOT EXISTS trg_governance_contract_reference_no_update
BEFORE UPDATE ON governance_contract_reference BEGIN SELECT RAISE(ABORT, 'governance_contract_reference is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_governance_contract_reference_no_delete
BEFORE DELETE ON governance_contract_reference BEGIN SELECT RAISE(ABORT, 'governance_contract_reference is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_normalization_assertion_artifact_no_update
BEFORE UPDATE ON normalization_assertion_artifact BEGIN SELECT RAISE(ABORT, 'normalization_assertion_artifact is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_normalization_assertion_artifact_no_delete
BEFORE DELETE ON normalization_assertion_artifact BEGIN SELECT RAISE(ABORT, 'normalization_assertion_artifact is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_correspondence_judgment_artifact_no_update
BEFORE UPDATE ON correspondence_judgment_artifact BEGIN SELECT RAISE(ABORT, 'correspondence_judgment_artifact is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_correspondence_judgment_artifact_no_delete
BEFORE DELETE ON correspondence_judgment_artifact BEGIN SELECT RAISE(ABORT, 'correspondence_judgment_artifact is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_adjudication_target_fingerprint_no_update
BEFORE UPDATE ON adjudication_target_fingerprint BEGIN SELECT RAISE(ABORT, 'adjudication_target_fingerprint is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_adjudication_target_fingerprint_no_delete
BEFORE DELETE ON adjudication_target_fingerprint BEGIN SELECT RAISE(ABORT, 'adjudication_target_fingerprint is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_evidentiary_entitlement_no_update
BEFORE UPDATE ON evidentiary_entitlement BEGIN SELECT RAISE(ABORT, 'evidentiary_entitlement is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_evidentiary_entitlement_no_delete
BEFORE DELETE ON evidentiary_entitlement BEGIN SELECT RAISE(ABORT, 'evidentiary_entitlement is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_monetization_activation_requirement_no_update
BEFORE UPDATE ON monetization_activation_requirement BEGIN SELECT RAISE(ABORT, 'monetization_activation_requirement is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_monetization_activation_requirement_no_delete
BEFORE DELETE ON monetization_activation_requirement BEGIN SELECT RAISE(ABORT, 'monetization_activation_requirement is append-only'); END;
