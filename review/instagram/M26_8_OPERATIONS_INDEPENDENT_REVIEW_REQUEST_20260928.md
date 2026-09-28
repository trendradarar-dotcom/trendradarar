# Independent Operations Review — Instagram M26.8

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
REVIEW TYPE: Fresh Independent Operations Evidence Review
MODE: Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## Governing application anchor

The application code anchor remains the independently retested R5 target:

R5 EXACT CODE TARGET:
d41c1c1cdaa7cf374989e2b059db6a640cb51eef

R5 EXACT CODE TREE:
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d

Prior independent R5 verdict:
HIGH-01 = CLOSED
MEDIA_BYTE_PREFLIGHT = PASS
FIRST_PUBLIC_ACTIVATION_ELIGIBLE = NO

Do not reopen previously closed code findings unless this operations work introduces a directly evidenced regression.

## Operations evidence target

OPERATIONS EXACT TARGET:
0a68c4003261f1fe216140fb52665f1d91585d3f

OPERATIONS EXACT TREE:
8561d105562ecf0d0ce8d3fa9f467bf7411af53d

OPERATIONS DRILL RUN:
36442457664

Expected run result:
completed / success

The documentation commit containing this request is a direct child of the operations exact target and must contain documentation only. Verify that independently.

## Mandatory exact-evidence gate

Before assessing operational requirements:

1. Verify Git objects for the R5 target, operations target, and documentation commit.
2. Verify the operations target tree exactly.
3. Verify the documentation commit is a direct child of the operations target.
4. Verify the target-to-documentation delta contains documentation only.
5. Verify workflow run 36442457664:
   - head_sha = 0a68c4003261f1fe216140fb52665f1d91585d3f
   - status = completed
   - conclusion = success
6. Verify all three artifacts bind to that same run/head SHA.
7. Recompute each artifact SHA-256 and all internal EVIDENCE_SHA256SUMS.
8. Do not rely on result.txt or manifests alone.

## Final producer evidence artifacts

### Live read-only monitor
Artifact:
instagram-live-readonly-monitor-evidence

Artifact ID:
10979362046

Expected GitHub artifact SHA-256:
025b345c88922632d41c4aec97c8d48e61a8df3b404a7f1c57015d3f52c01d95

### Isolated backup/restore/DR
Artifact:
instagram-isolated-backup-restore-dr-evidence

Artifact ID:
10979142245

Expected GitHub artifact SHA-256:
2babcf369d7e661429ab7607e0614265c76c73f759957d15334dacf727f2108f

### Trusted-source rebuild
Artifact:
instagram-trusted-source-rebuild-evidence

Artifact ID:
10978428465

Expected GitHub artifact SHA-256:
a7a9201d35a8401291a512c8fbcc08e4476e09f254bec6d70f8130e04f1fe9f1

## A. Trusted-source rebuild — mandatory independent retest

Producer evidence claims:
- exact R5 source was checked out by immutable SHA;
- the exact R5 wheelhouse was downloaded from R5 CI run 36422824796;
- wheel SHA-256 values were verified;
- Python runtime dependencies were installed with --no-index from the captured wheelhouse only;
- pip check passed;
- all exact R5 acceptance suites passed;
- PostgreSQL image digest was recorded.

Independently verify and, where practical, reproduce these claims.

Required output:
TRUSTED_SOURCE_REBUILD =
CAPTURED_WHEELHOUSE_REBUILD =
EXACT_R5_TESTS_AFTER_REBUILD =

Do not interpret this as full byte-for-byte reproduction of Render infrastructure unless that is separately proven.

## B. Isolated backup/restore drill — mandatory independent retest

The producer drill intentionally did NOT connect to or mutate the production Render database.

The drill:
- created the actual Instagram application schema using R5 application functions;
- seeded synthetic governed states only;
- included VERIFIED, UNKNOWN, and CONTAINER_CREATE_REQUESTED publication states;
- created a PostgreSQL 18 custom-format backup;
- restored into a newly created clean database;
- compared canonical rows, columns, types, defaults, constraints, and indexes;
- verified required duplicate-prevention unique indexes;
- verified restored CONTAINER_CREATE_REQUESTED reconciles to UNKNOWN;
- verified zero provider calls during restored ambiguity reconciliation;
- verified preexisting UNKNOWN remains UNKNOWN;
- corrupted the backup and required restore failure.

Independently reproduce or inspect the drill implementation and evidence.

Required output:
ISOLATED_BACKUP_CREATE =
ISOLATED_RESTORE_TO_CLEAN_DB =
RESTORED_SCHEMA_DATA_CONSTRAINT_INDEX_INTEGRITY =
RESTORED_FAIL_CLOSED_AMBIGUITY_SEMANTICS =
CORRUPTED_BACKUP_REJECTED =

Important distinction:
An isolated CI restore PASS does NOT automatically prove that a backup of the current production Render database has been taken and successfully restored.

Therefore judge these separately:
PRODUCTION_BACKUP_RESTORE_DRILL =
PRODUCTION_DISASTER_RECOVERY_DRILL =

Do not collapse isolated and production drill results into one status.

## C. Live read-only monitoring logic

The live monitor uses GET only and bounded retries.

Producer evidence says it observed:
- backend health HTTP 200;
- gateway health HTTP 200;
- backend live revision = M26.6-R4-PRODUCTION-ADMISSION-20260928;
- public_publish_authorized = false;
- instagram_publish_enabled = false;
- browser_public_publish_enabled = false;
- exact_account_binding_configured = true;
- oauth_relink_hard_disabled = true;
- persistence_configured = true;
- persistence_required = true;
- publisher_m2m_configured = true.

Independently inspect/reproduce the read-only monitor.

Required output:
LIVE_MONITOR_LOGIC =
LIVE_READONLY_PROBE =

Alert delivery is a separate requirement:
ALERT_DELIVERY_DRILL =

Do not give ALERT_DELIVERY_DRILL = PASS merely because monitoring logic can detect a bad state.

## D. Production database boundary

The production Render PostgreSQL metadata currently has external IP allowlist closed.

The producer review did not open the allowlist and did not query or mutate production data for this drill.

Verify the workflow contains no production database credential or network mutation.

Required output:
PRODUCTION_DB_UNTOUCHED_BY_DRILL =

Do not weaken the production database network boundary for this review.

## E. Supply-chain scope

Evidence now includes:
- exact R5 source SHA/tree;
- captured runtime wheelhouse with wheel SHA-256;
- Python dependency installation from captured wheels only;
- pinned GitHub Actions commit SHAs;
- a concrete PostgreSQL image digest recorded by the drill.

Assess what this proves and what it does not.

Required output:
PYTHON_DEPENDENCY_BYTE_REPRODUCIBILITY =
POSTGRES_IMAGE_IMMUTABILITY_EVIDENCE =
FULL_ENVIRONMENT_REPRODUCIBILITY =

If Render OS/runtime/build environment is not proven byte-for-byte immutable, keep FULL_ENVIRONMENT_REPRODUCIBILITY = NOT VERIFIED.

## F. Golden/LKG candidate

Review:
review/instagram/M26_8_GOLDEN_LKG_CANDIDATE_20260928.md

This is deliberately a CANDIDATE only.

It must not be treated as promoted Golden/LKG without an independent promotion decision and required evidence.

Required output:
GOLDEN_LKG_CANDIDATE_VALID =
GOLDEN_BASELINE_PROMOTED =

## G. Owner / human / cold-engineer recovery

Review:
review/instagram/M26_8_RECOVERY_HANDOVER_CANDIDATE_20260928.md

The document contains no secrets and is a candidate handoff.

Do not convert documentation existence to drill PASS.

Required output:
OWNER_RECOVERY_PACKAGE =
HUMAN_TAKEOVER =
COLD_ENGINEER_HANDOVER =

These should remain NOT VERIFIED unless a real independent person executes the required handover/recovery exercise.

## H. Requirements that remain separate unless independently evidenced

Do not infer PASS for:

TOKEN_SECRET_SECURITY =
ALERT_DELIVERY_DRILL =
PRODUCTION_BACKUP_RESTORE_DRILL =
PRODUCTION_DISASTER_RECOVERY_DRILL =
FULL_ENVIRONMENT_REPRODUCIBILITY =
GOLDEN_BASELINE_PROMOTED =
OWNER_RECOVERY_PACKAGE =
HUMAN_TAKEOVER =
COLD_ENGINEER_HANDOVER =
PENETRATION_TEST =

A producer CI drill or documentation file is not sufficient on its own for these broader requirements.

## Safety constraints

No remediation during review.
No R5 deployment.
No public Reel.
No enabling publication gates.
No OAuth re-link.
No production DB allowlist change.
No production database destructive test.

Required safety state remains:
INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
INSTAGRAM_PUBLISH_ENABLED=false
PUBLIC INSTAGRAM PUBLISHING=HOLD

## Required final matrix

EXACT_OPERATIONS_TARGET_VERIFIED =
EXACT_OPERATIONS_TREE_VERIFIED =
OPERATIONS_RUN_VERIFIED =
DOCUMENTATION_ONLY_DELTA_VERIFIED =
ARTIFACT_HASHES_VERIFIED =

TRUSTED_SOURCE_REBUILD =
CAPTURED_WHEELHOUSE_REBUILD =
EXACT_R5_TESTS_AFTER_REBUILD =

ISOLATED_BACKUP_CREATE =
ISOLATED_RESTORE_TO_CLEAN_DB =
RESTORED_SCHEMA_DATA_CONSTRAINT_INDEX_INTEGRITY =
RESTORED_FAIL_CLOSED_AMBIGUITY_SEMANTICS =
CORRUPTED_BACKUP_REJECTED =

LIVE_MONITOR_LOGIC =
LIVE_READONLY_PROBE =
ALERT_DELIVERY_DRILL =

PRODUCTION_DB_UNTOUCHED_BY_DRILL =
PRODUCTION_BACKUP_RESTORE_DRILL =
PRODUCTION_DISASTER_RECOVERY_DRILL =

PYTHON_DEPENDENCY_BYTE_REPRODUCIBILITY =
POSTGRES_IMAGE_IMMUTABILITY_EVIDENCE =
FULL_ENVIRONMENT_REPRODUCIBILITY =

GOLDEN_LKG_CANDIDATE_VALID =
GOLDEN_BASELINE_PROMOTED =

TOKEN_SECRET_SECURITY =
OWNER_RECOVERY_PACKAGE =
HUMAN_TAKEOVER =
COLD_ENGINEER_HANDOVER =
PENETRATION_TEST =

FIRST_PUBLIC_ACTIVATION_ELIGIBLE =
INDEPENDENT_OPERATIONS_VERDICT =

Use PASS / FAIL / NOT VERIFIED / N/A for requirements.

Even if all isolated producer drills are independently reproduced, FIRST_PUBLIC_ACTIVATION_ELIGIBLE must remain NO while required production/human/security evidence remains NOT VERIFIED.
