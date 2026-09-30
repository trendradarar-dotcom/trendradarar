# طلب مراجعة مستقلة — Instagram TOKEN_SECRET_SECURITY Residual-Only Review

**PROJECT:** TrendHunter / Trend Radar  
**SCOPE:** Instagram فقط  
**REVIEW TYPE:** Residual-Only Independent Token / Secret Security Review  
**MODE:** Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

هذه الجولة لا تعيد Secret Scan ولا M26.1 ولا M26.10 ولا M26.11 من الصفر.  
الهدف الوحيد هو تحديد ما الذي أصبح مثبتًا فعليًا، وما المتبقي حصريًا لإغلاق:

`TOKEN_SECRET_SECURITY`

ولا يُسمح بأي Remediation أو Production mutation أثناء المراجعة.

---

## 1. العزل الحاكم

هذه الجولة تخص Instagram فقط.

ممنوع استخدام أو لمس:
- YouTube
- TikTok
- Snapchat
- أي قناة أخرى
- أي مشروع آخر
- أي Database/Secret/Service خارج Instagram

---

## 2. Exact Residual Target

```text
EXACT_TARGET_COMMIT =
9bdec0e323e46503aee2845d15976e89b5060668

EXACT_TARGET_TREE =
cf0f8efb976f17ee8ee5b96bdfa9f12e6e32e9be

BASE =
0f6101f540c3b8dc9afe4166a93218bd03371da1
```

Expected delta from BASE:
```text
.github/workflows/instagram-token-secret-security-residual.yml
ops/instagram/token_secret_residual_drill.py
```

No application/runtime code file should differ from governed R5 because of this residual drill.

Governing R5 anchors:
```text
R5_EXACT_COMMIT =
d41c1c1cdaa7cf374989e2b059db6a640cb51eef

R5_EXACT_TREE =
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d
```

---

## 3. Governing Final Evidence Run

Use **only** the final governing run:

```text
RUN_ID =
36711589527

HEAD_SHA =
9bdec0e323e46503aee2845d15976e89b5060668

STATUS =
completed

CONCLUSION =
success
```

Expected job:
```text
synthetic-rotation-revocation-preflight = success
```

Final artifact:
```text
ARTIFACT_ID =
11094038800

ARTIFACT_DIGEST =
sha256:e3046e944e9ced96e143c779918a573f98ef1aac8157f1e6db20faedd7053eed
```

The supplied ZIP must independently hash to the exact same digest.

Inside the ZIP, require:
```text
sha256sum -c SHA256SUMS.txt
```

Expected:
```text
token-secret-residual-drill.py = OK
token-secret-residual-drill.json = OK
manifest.txt = OK
```

---

## 4. Final Drill Boundary

The final evidence explicitly states:

```text
PRODUCTION_SECRETS_USED=NO
PRODUCTION_DATABASE_TOUCHED=NO
RENDER_MUTATION=NO
PROVIDER_MUTATION=NO
PUBLICATION_MUTATION=NO
```

Therefore this evidence can prove **rotation capability / fail-closed behavior**, but it must not be silently reclassified as proof that real Production credentials were already rotated or revoked.

---

## 5. Synthetic Rotation Tests

Independently verify all 27 result entries.

The drill must prove:

### App Secret
- old accepted before rotation
- new rejected before rotation
- old rejected after rotation
- new accepted after rotation

### Publisher M2M Secret
- old accepted before rotation
- new rejected before rotation
- old rejected after rotation
- new accepted after rotation

### OAuth Gateway Secret
- old accepted before rotation
- new rejected before rotation
- old rejected after rotation
- new accepted after rotation
- gateway process loads the rotated value
- browser OAuth remains fail-closed

### Refresh Secret
- old gets beyond auth before rotation
- new is rejected before rotation
- old is rejected after rotation
- new gets beyond auth after rotation

The expected post-auth synthetic response may be HTTP 503 because no Production DB is provided. That is acceptable only if 403 vs non-403 proves the secret boundary and no external provider/DB mutation occurs.

### Session Secret
- state signed with old secret validates before rotation
- old state is rejected after rotation
- state signed with new secret validates after rotation

### Token Encryption Key
Verify that:
- naive key replacement makes old ciphertext unreadable
- decrypt-old → encrypt-new preserves plaintext
- old key cannot decrypt migrated ciphertext

### PostgreSQL Credential
On isolated PostgreSQL 18.6 / Debian 12:
- old credential accepted before rotation
- old credential rejected after rotation
- new credential accepted after rotation

---

## 6. Historical Evidence That Must Be Reconciled

Do not ignore earlier independently verified evidence.

### M26.10
Already established:
```text
INSTAGRAM_GIT_HISTORY_SECRET_SCAN = PASS
GOVERNING_CI_LOG_SECRET_SCAN = PASS
GOVERNING_ARTIFACT_SECRET_SCAN = PASS
PLAINTEXT_SECRET_EXPOSURE_FOUND = NO
```

But also explicitly left:
```text
SECRET_ROTATION_HISTORY = NOT VERIFIED
TOKEN_SECRET_SECURITY = NOT VERIFIED
```

### M26.1
Historical provider/runtime evidence established:
```text
ENCRYPTED_PERSISTENCE = PASS
FAIL_CLOSED_PERSISTENCE_REQUIRED = PASS
RESTART_RELOAD = PASS
VERIFIED_DELETION_PERSISTENCE = PASS
REFRESH_FUNCTIONAL_VERIFICATION = PASS
FINAL_CLEAN_RESTART = PASS
```

Provider refresh evidence:
```text
status = REFRESHED_VERIFIED
username = trendradarar
account_type = BUSINESS
professional_user_id = 17841428134382903
expires_in = 5184000
public_publish_authorized = false
```

Relevant commits/deploys:
```text
deauthorization durable-delete commit =
4bd4531ebc838173004792ac894b81afd60af409

M26.1 close commit =
003b232af717aaf22c93b09c812e36916f9e4d65

provider refresh deploy =
dep-daspkfrbc2fs738ap4kg

clean restart deploy =
dep-daspl0m0tbcc738ftkmg
```

### M26.11
Already established:
```text
SECRET_HANDLING_WITHOUT_DISCLOSURE = PASS
```

Production secrets were not printed or required for the independent recovery drill.

---

## 7. Current Lifecycle Automation Observation

A task named:
`Instagram Token Maintenance`

exists with weekly Wednesday 06:00 Asia/Riyadh intent to execute:
- refresh
- identity verification
- encrypted persistence
- clean restart
- fail-closed on failure
- public publishing remains false

However the current task state observed during this residual review was:
```text
is_enabled = false
```

and no fresh Render deploy/log was found in the checked current execution window proving a new successful periodic maintenance cycle.

Do not infer:
`CURRENT_PERIODIC_TOKEN_MAINTENANCE = PASS`
from task existence alone.

---

## 8. Previous Non-Governing Harness Attempts

Do not hide them.

### Run 36710896174
Failed in the isolated DB-rotation harness because:
`ALTER ROLE ... PASSWORD $1`
is invalid PostgreSQL DDL parameterization.

Classify whether:
- PRODUCT FINDING, or
- REVIEW HARNESS FINDING.

No application code was modified.

### Run 36711027193
Synthetic tests passed, but the evidence package contained non-portable SHA256SUMS paths.

### Run 36711412813
Synthetic tests passed again, but still used the non-portable package layout.

Only final run:
`36711589527`
is governing because it also fixes evidence portability and independently passes internal SHA verification.

---

## 9. Questions the Reviewer Must Answer

Use only:
`PASS / FAIL / NOT VERIFIED / N/A`

And for binary observations:
`YES / NO / NOT VERIFIED`

Evaluate:

```text
EXACT_TARGET_VERIFIED =
EXACT_TREE_VERIFIED =
RESIDUAL_DELTA_BOUNDED =
R5_APPLICATION_BYTES_UNCHANGED =
FINAL_EVIDENCE_RUN_VERIFIED =
FINAL_ARTIFACT_DIGEST_VERIFIED =
INTERNAL_SHA256SUMS_VERIFIED =

SECRET_SCAN_HISTORY_ALREADY_CLOSED =
PLAINTEXT_SECRET_EXPOSURE_FOUND =

ENCRYPTED_TOKEN_PERSISTENCE =
PROVIDER_LONG_LIVED_TOKEN_REFRESH_EXECUTED =
DURABLE_DEAUTHORIZATION_DELETE =
SECRET_HANDLING_WITHOUT_DISCLOSURE =

APP_SECRET_ROTATION_CAPABILITY =
M2M_SECRET_ROTATION_CAPABILITY =
GATEWAY_SECRET_ROTATION_CAPABILITY =
REFRESH_SECRET_ROTATION_CAPABILITY =
SESSION_SECRET_ROTATION_CAPABILITY =
TOKEN_ENCRYPTION_KEY_ROTATION_CAPABILITY =
DATABASE_CREDENTIAL_ROTATION_CAPABILITY =

OLD_CREDENTIAL_REJECTION_AFTER_ROTATION =
NEW_CREDENTIAL_ACCEPTANCE_AFTER_ROTATION =
FAIL_CLOSED_DURING_ROTATION =
SECRET_VALUE_DISCLOSURE_FOUND =

PRODUCTION_SECRET_ROTATION_HISTORY =
PROVIDER_TOKEN_REVOCATION_HISTORY =
CURRENT_PERIODIC_TOKEN_MAINTENANCE =

SYNTHETIC_ROTATION_CAPABILITY =
ROTATION_REVOCATION_LIFECYCLE_RESIDUALS_CLOSED =

TOKEN_SECRET_SECURITY =

NEW_PRODUCT_FINDING =
CODE_REMEDIATION_REQUIRED =

FIRST_PUBLIC_ACTIVATION_ELIGIBLE = NO
PUBLIC_INSTAGRAM_PUBLISHING = HOLD

INDEPENDENT_TOKEN_SECRET_RESIDUAL_VERDICT =
```

---

## 10. Governing Decision Boundary

The critical question is not whether rotation **can** be simulated.

The reviewer must decide exactly whether the existing combination of:

1. historical real provider refresh,
2. encrypted persistence,
3. durable deauthorization deletion,
4. successful secret scans,
5. safe secret handling,
6. synthetic rotation of all internal secret classes,
7. isolated DB credential rotation,
8. documented emergency revoke/rotate procedure,

is sufficient for:
`TOKEN_SECRET_SECURITY = PASS`

or whether one or more of the following remain mandatory:

- actual Production App Secret rotation,
- actual Production M2M/Gateway/Session/Refresh rotation,
- actual Production encryption-key migration,
- actual Production DB credential rotation,
- actual provider-side Instagram token revocation and recovery,
- re-enabling and proving periodic token maintenance.

If any are mandatory, name **only the minimal remaining residual actions**, and explain why the existing evidence does not satisfy them.

Do not prescribe unnecessary re-execution of already-PASS scans or refresh tests.

---

## 11. Safety State

Must remain:
```text
INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
INSTAGRAM_PUBLISH_ENABLED=false

FIRST_PUBLIC_ACTIVATION_ELIGIBLE=NO
PUBLIC_INSTAGRAM_PUBLISHING=HOLD
```

Do not:
- publish a Reel,
- open public OAuth,
- mutate Render,
- touch Production DB,
- use Production secrets,
- revoke the current provider token,
- rotate Production credentials,
- perform remediation.

This review is Read-Only.

---

## 12. Final Required Conclusion

Answer explicitly:

1. Did the exact residual target/evidence verify?
2. Were the 27 synthetic rotation checks valid and independently reproducible?
3. Are the earlier M26.1/M26.10/M26.11 facts consistent with the new evidence?
4. Which token/secret sub-requirements are now PASS?
5. Which remain NOT VERIFIED?
6. Is `TOKEN_SECRET_SECURITY` now PASS?
7. If not, list the **minimal exact residual actions only**.
8. Is any Production credential rotation actually required, or would that be unnecessary risk?
9. Is actual provider-side token revocation required?
10. Does periodic token maintenance need to be re-enabled/proven?
11. Did either earlier harness failure expose a Product Finding?
12. Is code remediation required?
13. What should be executed next, and what must remain untouched?

Issue only the independent verdict and evidence reasoning.
