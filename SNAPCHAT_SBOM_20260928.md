# SNAPCHAT SOFTWARE BILL OF MATERIALS — 2026-09-28

PROJECT: Trend Radar / TrendHunter  
SCOPE: Snapchat remediation candidate  
STATUS: DIRECT DEPENDENCY + BUILD DEPENDENCY INVENTORY; INDEPENDENT SUPPLY-CHAIN REVIEW STILL REQUIRED

## Runtime — direct first-party bridge

Source:
- snapchat_oauth_service/requirements.txt

Pinned direct Python dependencies:
- Flask == 3.1.3
- requests == 2.34.2
- cryptography == 50.0.1
- gunicorn == 26.2.0
- psycopg[binary] == 3.3.6
- imageio-ffmpeg == 0.6.0

## Legacy provider-neutral publisher

Source:
- snapchat_publisher_service/requirements.txt

Its dependencies remain isolated from the direct first-party bridge. It is not selected as current publication authority.

## State platform

Production durable-state requirement:
- PostgreSQL

CI integration target:
- postgres:16.15-bookworm

Observed remediation pull digest:
- sha256:efedf3595f1d6f415c08568ba171029bf54052e754cc9f030e3f2412b21f3d67

The exact final independent run must record and verify its own image identity.

## Build / verification tools

Workflow:
- .github/workflows/snapchat-publisher-ci.yml

Verification tools include:
- pip
- pip check
- pip-audit == 2.10.1
- Python compileall
- Bandit == 1.9.4
- unittest
- PostgreSQL service container
- pg_dump / pg_restore
- .github/scripts/snapchat_secret_scan.py

## GitHub Actions

Pinned by full commit SHA:
- actions/checkout@11d5960a326750d5838078e36cf38b85af677262
- actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065

A runner warning indicates these action revisions target deprecated Node.js 20 but are currently being forced onto Node.js 24 by GitHub Actions. This is a supply-chain maintenance item and must not be silently ignored in future dependency updates.

## External services

Required target/service:
- Snapchat OAuth
- Snapchat Business/Public Profile API

Hosting/evidence:
- Render
- GitHub
- GitHub Actions

Not selected:
- Ayrshare as paid production publisher

## Media tooling

imageio-ffmpeg is used only to probe actual local video metadata before publication admission.

The direct API bridge does not fetch an arbitrary user-supplied media URL.

## Security evidence boundary

Automated checks can establish:
- dependency resolution consistency at a tested point in time;
- known-vulnerability results from pip-audit at that point in time;
- static-analysis results from Bandit;
- exact test results.

They do not establish:
- absence of unknown vulnerabilities;
- independent supply-chain review;
- full transitive provenance;
- full license/compliance review;
- long-term safety after dependency or runner changes.

Any dependency, base image, GitHub Action, or PostgreSQL target change requires exact-target re-verification.
