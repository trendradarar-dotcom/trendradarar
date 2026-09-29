# طلب استكمال مراجعة مستقلة — TikTok R5 PostgreSQL Fresh Execution V2

**PROJECT:** TrendHunter / Trend Radar  
**SCOPE:** TikTok فقط  
**ISOLATION:** عزل تام عن أي مشروع أو قناة أو Database أو Secret خارج TikTok.

هذه ليست مراجعة جديدة للكود، وليست Remediation، ولا تعيد فتح البنود المغلقة.

المطلوب فقط استكمال التنفيذ المستقل الناقص على PostgreSQL 16 حقيقي ومعزول ينشئه/يديره المراجع داخل بيئته هو، ثم التخلص منه بعد انتهاء المراجعة.

## Exact Target الحاكم

يبقى المرشح نفسه دون أي تغيير:

`EXACT COMMIT = d98ee71e110118dc9fff4710dca6bf61381eeefc`

`EXACT TREE = 4e1f7a6240b15f6c7d80a994efe0331e0dfce912`

`FROZEN BRANCH = tiktok-r5-postgres-independent-retest-candidate-20260929`

الأحكام السابقة تبقى:

`EXACT TARGET = PASS`

`PG-01 = PASS`

`PG-06 = PASS`

ولا يعاد فحصها إلا عند ظهور تناقض جديد.

## قاعدة التنفيذ المستقلة الجديدة

بدل الاعتماد على أي PostgreSQL أنشأه المنتج أو المالك، يجب على المراجع إنشاء PostgreSQL 16 معزول خاص بالمراجعة داخل بيئته المستقلة.

شروط البيئة:
- PostgreSQL 16 حقيقي.
- لا Mock.
- لا Database من Render الحالية.
- لا Database من أي مشروع آخر.
- لا Production data.
- لا Production TikTok secrets.
- reviewer-generated synthetic secrets only.
- يسمح بإنشاء source DB وrestore target DB مستقلين.
- يسمح بتشغيل عدة connections/store instances.
- يسمح بإغلاق/reopen connections وإعادة تشغيل process إن لزم.
- يسمح بالتخلص الكامل من البيئة بعد نهاية المراجعة.

هذه البيئة لا تصبح جزءًا من Production Architecture ولا من FINAL TRANSITION MANIFEST.

## PG-02 — Encrypted Sensitive State

على PostgreSQL الحقيقي المستقل، استخدم قيمًا صناعية من إنشاء المراجع نفسه لـ:
- access token
- refresh token
- OAuth state/session binding
- handoff session binding
- recovery marker

نفذ:
1. write through real PostgreSQL backend.
2. raw SQL inspection of stored columns.
3. prove original plaintext values are absent.
4. correct key decrypts.
5. wrong key fails closed.
6. corrupted ciphertext fails closed.
7. MultiFernet rotation preserves expected compatibility.
8. audit detail rejects secret-field names.

الحكم:
`PG-02 = PASS / FAIL / NOT VERIFIED`

## PG-03 — Idempotency / Admission / Concurrency

استخدم multiple independent connections/store instances.

نفذ:
- same idempotency key race: exactly one creator.
- no duplicate publication row.
- no duplicate mutation event.
- active-account hard-limit race.
- global active limit race.
- global hourly/day limit race where applicable.
- mutation history survives new connections.
- redelivery after reopen/restart returns existing intent.
- duplicate barrier remains intact.

الحكم:
`PG-03 = PASS / FAIL / NOT VERIFIED`

## PG-04 — State / Provider Binding / UNKNOWN Safety

نفذ:
- valid transitions.
- invalid transition rejection.
- concurrent terminal-transition race.
- provider_publish_id uniqueness.
- duplicate provider ID rejection.
- durable attempt_count.
- UNKNOWN survives reopen/restart.
- UNKNOWN cannot restart upload/publication.
- only allowed reconciliation transitions.
- state/provider/audit transactional coherence.

الحكم:
`PG-04 = PASS / FAIL / NOT VERIFIED`

## PG-05 — Backup / Restore / Audit / Duplicate Barrier

استخدم source PostgreSQL وclean restore target PostgreSQL.

أنشئ synthetic dataset يتضمن:
- PUBLISHED record.
- UNKNOWN record.
- provider IDs.
- mutation events.
- audit events.
- recovery marker.

اختبر:
- consistent backup.
- backup artifact encrypted.
- independent SHA-256.
- synthetic marker/token/provider values not visible plaintext.
- wrong-key backup failure.
- corrupted backup failure.
- malformed/incomplete backup failure.
- non-empty target rejection.
- PUBLISHED survives restore.
- UNKNOWN survives restore.
- provider IDs survive.
- mutation history survives.
- audit history survives.
- recovery marker survives.
- event sequences continue safely.
- duplicate barrier survives.
- UNKNOWN remains unsafe to republish after restore.

الحكم:
`PG-05 = PASS / FAIL / NOT VERIFIED`

## Focused No-Regression

بعد PG-02..PG-05:
- F-01 OAuth browser/session binding.
- F-02 429 -> UNKNOWN -> later success.
- F-03 Draft terminal -> READY.
- F-04 code identity only if unchanged.
- F-05 remains PASS unless contradiction appears.
- R4.2 watchdog unchanged.
- kill switch.
- mutation default fail-closed.
- zero automatic retries.
- audit secret exclusion.
- PostgreSQL idempotency/duplicate prevention.

الحكم:
`FOCUSED NO-REGRESSION = PASS / FAIL / NOT VERIFIED`

## ممنوع

- تغيير candidate code.
- Remediation.
- Deploy.
- Merge.
- Production Cutover.
- استخدام Render PostgreSQL review resource كدليل PASS.
- استخدام أي non-TikTok resource.
- استخدام Production TikTok secrets.
- Public Posting.
- TikTok Recall/Resubmit.
- `TIKTOK_AUDIT_APPROVED=true`.

## Required Final Verdicts

- PG-02
- PG-03
- PG-04
- PG-05
- Focused No-Regression
- PostgreSQL Directed Retest
- Final Production Auto-Publish Acceptance

إذا أصبحت PG-02..PG-05 وFocused No-Regression كلها PASS:

`POSTGRESQL DIRECTED RETEST = PASS`

لكن يبقى:

`FINAL PRODUCTION AUTO-PUBLISH ACCEPTANCE = NOT VERIFIED / NOT AUTHORIZED`

والمرحلة التالية بعد ذلك فقط:

`Runtime Equivalence -> Production Persistence/Restart -> Production Backup/Restore -> External Alerts -> Cold Engineer/Owner Takeover -> Golden Recovery -> Controlled Cutover -> Observation -> FINAL TRANSITION MANIFEST -> R5 Closure`

## Governing transition hold

حتى بعد PASS للـPostgreSQL Directed Retest:

- Production Cutover = HOLD
- Main Architecture Changes = HOLD
- Old Resource = PRESERVE
- Pro / Final Workspace purchase = HOLD

إلى أن تُجمع نتائج TikTok + YouTube + Snapchat في `FINAL TRANSITION MANIFEST`.
