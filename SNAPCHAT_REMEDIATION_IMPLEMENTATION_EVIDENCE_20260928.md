# SNAPCHAT REMEDIATION IMPLEMENTATION EVIDENCE — 2026-09-28

PROJECT: Trend Radar / TrendHunter  
SCOPE: Snapchat only  
REVIEW BOUNDARY: REMEDIATION EVIDENCE, NOT INDEPENDENT FINAL ACCEPTANCE

## 1. Remediation branch

Branch:
- snapchat-production-remediation-20260928

Base:
- d4f52c3663e53e21fb15a4af6aea8607a7b5adfd

Original production-review services have not been switched to this branch.

## 2. Findings addressed in implementation

Implemented remediation includes:
- durable PostgreSQL OAuth/publication state;
- one-time owner-created OAuth intent;
- browser-bound, one-time OAuth state;
- exact profile ID + username binding;
- read-only authorized-profile verification before token persistence;
- encrypted persisted OAuth credentials;
- restart-safe refresh lifecycle;
- local disconnect/invalidation;
- full direct-path production assurance gates;
- persistent publication ledger;
- immutable publication_id/content_id/job_id/media binding;
- durable duplicate prevention;
- UNKNOWN state persistence;
- no blind retry after uncertain submit;
- deterministic reconciliation rules;
- hard publication limits;
- PostgreSQL advisory concurrency lock;
- actual video metadata probing;
- restricted Snapchat upload host;
- structured audit fields;
- database migration;
- PostgreSQL backup/restore duplicate-prevention probe;
- deterministic current-tree and Git-history credential scanner.

## 3. Current conservative hard limits

- 2 posts/hour
- 10 posts/day
- 1 concurrent publish per profile
- 2 attempts per publication
- 1800-second retry horizon

Production verification flag remains false until independent review.

## 4. CI evidence

The branch workflow performs:
- pinned dependency installation;
- pip dependency consistency;
- pip-audit on both Snapchat services;
- compile;
- Bandit;
- publisher tests;
- direct OAuth/security/recovery tests;
- PostgreSQL 16.15 integration tests;
- PostgreSQL image identity capture;
- pg_dump / pg_restore recovery test;
- restored duplicate-prevention verification;
- current-tree credential scan;
- Git-history credential scan.

Historical implementation runs before final freeze are engineering evidence only. The final independent reviewer must bind conclusions to the exact frozen candidate SHA and exact successful run.

## 5. PostgreSQL evidence

Integration coverage includes:
- OAuth intent/state persistence;
- credential-record persistence across fresh store instance;
- UNKNOWN persistence across restart;
- blind-retry rejection;
- concurrent admission serialized by PostgreSQL advisory lock;
- persistent hourly limit;
- backup/restore of a SUBMITTED publication;
- duplicate rejection after restore.

The CI PostgreSQL image is explicitly versioned at 16.15-bookworm. One observed pulled image digest during remediation was:
- sha256:efedf3595f1d6f415c08568ba171029bf54052e754cc9f030e3f2412b21f3d67

The final independent review should verify the digest recorded by its exact run rather than rely on this historical value.

## 6. Isolated Render candidate evidence

Service:
- trendradar-snapchat-remediation-candidate

Service ID:
- srv-dasrgsm0tbcc738nkhg0

Properties:
- separate remediation branch;
- auto deploy disabled;
- no production Snapchat credentials;
- no project-shared database;
- publication disabled;
- kill switch active;
- emergency read-only active;
- target/reconciliation/alerting/assurance/hard-limit readiness flags false.

Observed candidate health was fail-closed and reported no external publication side effect.

A dedicated free Render PostgreSQL could not be provisioned because the workspace already contained a free-tier database for another project. That database was not reused. No paid database was created.

## 7. Invalidated evidence

A previous grep-based credential scan printed:
- grep: Unmatched [

while the workflow step appeared successful due to shell negation semantics.

That evidence is invalid and must not be cited as a PASS.

It was replaced with:
- .github/scripts/snapchat_secret_scan.py

which fails deterministically on findings or scanner errors and scans both the current Snapchat tree and Git-history additions.

## 8. Items intentionally NOT claimed closed by remediation

Still requires external or independent evidence:
- Snapchat Public Profile API allowlist;
- external alert delivery;
- final dedicated production PostgreSQL provisioning and backup schedule;
- practical owner credential rotation/revocation drill;
- practical independent service-stop/kill-switch drill;
- independent penetration test;
- independent code/architecture retest;
- cold-engineer handover;
- exact final candidate freeze;
- exact final Render deploy verification;
- branch/ruleset protection if required by final deployment governance.

## 9. Publication authority

Current and required state during remediation:
- PUBLICATION_AUTHORITY = ZERO
- NO LIVE SPOTLIGHT TEST IS AUTHORIZED BY THIS DOCUMENT
- SECURITY_RELIABILITY_RECOVERABILITY_ACCEPTANCE = NOT YET PASS

Independent verification must remain separate from remediation.
