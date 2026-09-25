# SNAPCHAT SOFTWARE BILL OF MATERIALS — 2026-09-25

SCOPE: Snapchat branch components only
STATUS: DIRECT-DEPENDENCY INVENTORY + AUTOMATED VULNERABILITY AUDIT EVIDENCE
INDEPENDENT SUPPLY-CHAIN REVIEW: NOT VERIFIED

## Publisher runtime

Source:
- snapchat_publisher_service/requirements.txt

Direct dependencies:
- Flask == 3.1.3
- gunicorn == 26.2.0
- requests == 2.34.2

## Dormant direct first-party OAuth fallback

Source:
- snapchat_oauth_service/requirements.txt

Direct dependencies:
- Flask == 3.1.3
- requests == 2.34.2
- cryptography == 50.0.1
- gunicorn == 26.2.0

Current role:
- dormant fallback
- direct API disabled
- not production publication authority

## External runtime services

- Snapchat Public Profile / Spotlight
- Render
- GitHub
- GitHub Actions

Optional evaluated adapter:
- Ayrshare — NOT SELECTED / no production subscription dependency

## CI supply-chain evidence

Workflow:
- .github/workflows/snapchat-publisher-ci.yml

Evidence run:
- run ID: 36146865617
- exact head: 7d98f9be995423ab9d2ef1ef2f612c23d049dd6e
- conclusion: SUCCESS

Checks:
- pip dependency consistency: PASS
- pip-audit 2.10.1 against publisher requirements: NO KNOWN VULNERABILITIES FOUND
- pip-audit 2.10.1 against dormant direct OAuth requirements: NO KNOWN VULNERABILITIES FOUND
- Python compile for both services: PASS
- basic committed private-key/AWS-key pattern scan: PASS

Test evidence in the same run:
- publisher/API tests: 26 PASS
- dormant direct-bridge fail-closed tests: 3 PASS

## Supply-chain boundaries

This evidence does NOT prove:
- absence of every unknown vulnerability;
- independent supply-chain review;
- license/compliance review;
- provenance of every transitive dependency beyond the package manager / CI environment;
- future safety after dependencies change.

Any dependency change invalidates this narrow evidence until CI/audit is rerun.

## Production requirement

Before a production publication route is opened:
- exact dependency set must have a current vulnerability audit;
- blocking findings must be closed;
- the final production architecture must receive the independent verification appropriate to its risk.
