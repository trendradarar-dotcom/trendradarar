# SNAPCHAT SOFTWARE BILL OF MATERIALS — 2026-09-25

SCOPE: Snapchat branch components only
STATUS: DIRECT-DEPENDENCY INVENTORY + AUTOMATED VULNERABILITY AUDIT EVIDENCE
INDEPENDENT SUPPLY-CHAIN REVIEW: NOT VERIFIED

## Publisher runtime

Direct dependencies:
- Flask == 3.1.3
- gunicorn == 26.2.0
- requests == 2.34.2

Source:
- snapchat_publisher_service/requirements.txt

## Dormant direct first-party bridge

Direct dependencies:
- Flask == 3.1.3
- gunicorn == 26.2.0
- requests == 2.34.2
- cryptography == 50.0.1

Source:
- snapchat_oauth_service/requirements.txt

Current role:
- dormant fallback
- direct API disabled
- no publication authority

## External services

- Snapchat
- Render
- GitHub
- GitHub Actions

Optional evaluated adapter:
- Ayrshare — NOT SELECTED

## Automated supply-chain evidence

Workflow:
- .github/workflows/snapchat-publisher-ci.yml

Latest exact code run:
- run ID: 36147465872
- exact head: 9a55b44bb7e5bada1640c883086f1b57cc9c9df1
- conclusion: SUCCESS

Results:
- dependency consistency: PASS
- pip-audit 2.10.1 — publisher requirements: NO KNOWN VULNERABILITIES FOUND
- pip-audit 2.10.1 — direct bridge requirements: NO KNOWN VULNERABILITIES FOUND
- compile both services: PASS
- publisher/API tests: 26 PASS
- direct fail-closed tests: 5 PASS
- basic committed private-key / AWS-key pattern scan: PASS

## Boundary

This inventory and automated audit do not prove:
- absence of unknown vulnerabilities;
- independent supply-chain review;
- full license/compliance review;
- long-term safety after dependency changes.

Any dependency modification requires a new exact audit/retest before production acceptance.
