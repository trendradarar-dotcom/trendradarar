# طلب مراجعة مستقلة — Instagram M26.10 Operations Closure Candidates

**PROJECT:** TrendHunter / Trend Radar  
**SCOPE:** Instagram فقط  
**REVIEW TYPE:** Independent Operations Closure Re-Review  
**MODE:** Fresh / Independent / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## 1. الهدف

هذه الجولة لا تعيد فتح R5 ولا HIGH-01 ولا Live R5 Equivalence.

الهدف هو مراجعة ثلاث مجموعات أدلة تشغيلية جديدة فقط:

1. Golden / Last-Known-Good promotion record.
2. End-to-End monitoring-to-alert channel delivery drill.
3. Instagram-scoped token/secret plaintext exposure evidence.

لا تمنح هذه الجولة إذنًا بالنشر العام.

## 2. Exact M26.10 Operations Closure Target

M26_10_EXACT_TARGET_COMMIT:
138a5d99004020027f5483d6aa154824556ef061

M26_10_EXACT_TARGET_TREE:
041a6403dda560d4ae3ca4c368ff758e5da137b5

M26_10_EVIDENCE_RUN:
36497828343

Expected run result:
completed / success

الـReview Request commit الذي يحتوي هذه الوثيقة يجب أن يكون direct child من Exact Target أعلاه، وأن يكون الفرق documentation-only.

## 3. Governing application/live anchors

R5_EXACT_TARGET_COMMIT:
d41c1c1cdaa7cf374989e2b059db6a640cb51eef

R5_EXACT_TARGET_TREE:
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d

LIVE_DEPLOYMENT_BRANCH:
instagram-production-review-20260924

LIVE_SYNC_COMMIT:
d2477d9397643c789fa4b27dbcf669a83b1acd2a

LIVE_SYNC_TREE:
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d

Previous independent state:
- HIGH_01_STATUS = CLOSED
- MEDIA_BYTE_PREFLIGHT = PASS
- LIVE_R5_EQUIVALENCE = PASS
- LIVE_REGRESSION_FOUND = NO
- FIRST_PUBLIC_ACTIVATION_ELIGIBLE = NO
- PUBLIC_INSTAGRAM_PUBLISHING = HOLD

## 4. Exact Target Gate

قبل تقييم أي بند:

1. تحقق من M26.10 Exact Target commit.
2. أعد حساب Tree.
3. تحقق من Evidence Run 36497828343 وربطه بالـhead_sha نفسه.
4. تحقق أن الوظائف الثلاث انتهت SUCCESS:
   - golden-lkg-promotion-evidence
   - token-secret-history-evidence
   - alert-channel-delivery-drill
5. تحقق من Review Request commit وأنه direct child وdocumentation-only.
6. أعد حساب SHA-256 للـArtifacts.
7. لا تعتمد على result.txt وحده؛ افحص الأدلة الخام.

المطلوب:
M26_10_EXACT_TARGET_VERIFIED =
M26_10_EXACT_TREE_VERIFIED =
M26_10_EVIDENCE_RUN_VERIFIED =
DOCUMENTATION_ONLY_REVIEW_DELTA_VERIFIED =
EVIDENCE_INTEGRITY_VERIFIED =

## 5. Golden / LKG Promotion

راجع:
review/instagram/M26_10_GOLDEN_LKG_PROMOTION_20260929.md

تحقق مستقلًا من أن promotion record يربط:
- R5 exact target/tree.
- Live sync commit/tree.
- tree identity.
- prior independent R5 and live-equivalence prerequisites.
- mandatory fail-closed recovery posture.
- explicit statement that public activation is not authorized.

تحقق أن السجل نفسه موجود في commit ثابت ومحدد ويمكن إعادة التحقق منه.

افصل بين:
GOLDEN_LKG_PROMOTION_RECORD =
GOLDEN_BASELINE_PROMOTED =

إذا اعتبرت أن سجل الترقية الحاكم والـimmutable commit يكفيان كعملية Promotion فعلية، يمكن تقييم GOLDEN_BASELINE_PROMOTED وفق الدليل.
أما إذا كانت الحوكمة تتطلب tag/release أو إجراء خارجي آخر غير موجود، فلا تفترض PASS؛ سجل المتطلب المتبقي بدقة.

لا تحول Golden promotion إلى Public Activation.

## 6. End-to-End Monitoring / Alert Drill

هذه الجولة الثانية من Alert drill، والحاكمة هي Run 36497828343 فقط.

المطلوب التحقق من التسلسل الكامل:

A. controlled monitor failure
- شُغّل live_readonly_monitor.py مع expected revision خاطئ عمدًا.
- يجب أن يفشل monitor.
- يجب إثبات non-zero exit.
- لا يتم تغيير Live أو Render.

B. alert generation
- بعد failure يتم إنشاء GitHub Issue تلقائيًا.
- correlation:
  M26.10-E2E-ALERT-138a5d990040

C. channel delivery / receipt
- تحقق من GitHub Issue #6 مباشرة.
- يجب أن يكون قد أُنشئ بواسطة github-actions[bot].
- body يجب أن يذكر أنها synthetic drill ولا توجد production incident.
- correlation يجب أن يطابق الدليل.

D. recovery
- شُغّل monitor ثانية على:
  M26.7-R5-FULL-DECODE-PREFLIGHT-20260928
- يجب أن ينجح مع fail-closed assertions الحية.

E. recovery notification
- تحقق من comment الفعلي على Issue #6.
- يجب أن يذكر RECOVERY DRILL ونفس correlation.
- يجب أن يكون Issue مغلقًا بعد recovery.

المطلوب:
CONTROLLED_MONITOR_FAILURE_DETECTED =
ALERT_GENERATED =
ALERT_CHANNEL_DELIVERY =
ALERT_CHANNEL_RECEIPT_CONFIRMED =
RECOVERY_MONITOR_PASS =
RECOVERY_NOTIFICATION_DELIVERED =
END_TO_END_MONITOR_TO_ALERT_DRILL =
HUMAN_ALERT_ACKNOWLEDGEMENT =

مهم:
وجود Issue واسترجاعه عبر GitHub API يثبت وصوله لقناة GitHub Issues.
لكنه لا يثبت أن إنسانًا قرأه أو أقره.
لذلك لا تمنح HUMAN_ALERT_ACKNOWLEDGEMENT = PASS بدون دليل بشري فعلي.

بعد ذلك قيّم:
ALERT_DELIVERY_DRILL =
MONITORING_ALERTING =

على أساس تعريف المتطلب الفعلي، واذكر بوضوح إذا كان Human acknowledgement شرطًا منفصلًا.

## 7. Token / Secret Evidence

راجع:
ops/instagram/secret_history_scan.py

والـArtifact:
instagram-m26-10-token-secret-scan-evidence

الـproducer evidence يدعي:

- Instagram-scoped Git history scanned.
- 108 commits considered.
- 121 unique historical text blobs scanned.
- findings = [].
- governing CI logs/artifacts scanned.
- no matching plaintext secret findings.
- rotation history is explicitly NOT VERIFIED.

المطلوب إعادة فحص:
1. نطاق المسارات داخل scanner.
2. regex patterns.
3. exclusions / safe markers.
4. هل يمكن أن توجد false negatives مهمة بسبب التصميم؟
5. git history coverage.
6. current-tree coverage.
7. governing CI log coverage.
8. governing artifact coverage.
9. عدم طباعة secret values في evidence.

افصل النتائج إلى:
INSTAGRAM_GIT_HISTORY_SECRET_SCAN =
GOVERNING_CI_LOG_SECRET_SCAN =
GOVERNING_ARTIFACT_SECRET_SCAN =
PLAINTEXT_SECRET_EXPOSURE_FOUND = YES / NO / NOT VERIFIED
SECRET_ROTATION_HISTORY =
TOKEN_SECRET_SECURITY =

لا تمنح TOKEN_SECRET_SECURITY = PASS فقط لأن scan لم يجد plaintext leak.
إذا بقي rotation/lifecycle/revocation evidence غير مثبت، أبقِ الحكم الأوسع NOT VERIFIED مع توضيح أن plaintext exposure scan اجتاز.

## 8. البنود التي تبقى خارج هذه الجولة

لا تغير تلقائيًا:

FULL_ENVIRONMENT_REPRODUCIBILITY
PRODUCTION_BACKUP_RESTORE_DRILL
PRODUCTION_DISASTER_RECOVERY_DRILL
RECOVERY_RUNBOOK_EXECUTION
OWNER_RECOVERY_PACKAGE_EXECUTION
HUMAN_TAKEOVER
COLD_ENGINEER_HANDOVER
PENETRATION_TEST

هذه الجولة لا تحتوي تنفيذًا بشريًا أو Production DR أو Pen Test مستقل.

## 9. Human / Cold Engineer Checklist

راجع:
review/instagram/M26_10_HUMAN_COLD_ENGINEER_DRILL_CHECKLIST_20260929.md

هذه الوثيقة Checklist فقط وليست Evidence PASS.

يجب أن تبقى:
HUMAN_TAKEOVER = NOT VERIFIED
COLD_ENGINEER_HANDOVER = NOT VERIFIED
OWNER_RECOVERY_PACKAGE_EXECUTION = NOT VERIFIED
RECOVERY_RUNBOOK_EXECUTION = NOT VERIFIED

ما لم توجد أدلة تنفيذ بشرية فعلية مستقلة خارج الوثيقة.

## 10. Safety state

تحقق Read-Only أن الحالة لا تزال:

INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
INSTAGRAM_PUBLISH_ENABLED=false

PUBLIC_INSTAGRAM_PUBLISHING=HOLD
FIRST_PUBLIC_ACTIVATION_ELIGIBLE=NO

لا تنشر Reel.
لا تغير Render.
لا تغير secrets.
لا تفتح Production DB.
لا تنفذ Remediation.

## 11. الجدول المطلوب

| البند | الحالة | الدليل |
|---|---|---|
| M26_10_EXACT_TARGET_VERIFIED | PASS / FAIL / NOT VERIFIED / N/A | |
| M26_10_EXACT_TREE_VERIFIED | | |
| M26_10_EVIDENCE_RUN_VERIFIED | | |
| EVIDENCE_INTEGRITY_VERIFIED | | |
| GOLDEN_LKG_PROMOTION_RECORD | | |
| GOLDEN_BASELINE_PROMOTED | | |
| CONTROLLED_MONITOR_FAILURE_DETECTED | | |
| ALERT_GENERATED | | |
| ALERT_CHANNEL_DELIVERY | | |
| ALERT_CHANNEL_RECEIPT_CONFIRMED | | |
| RECOVERY_MONITOR_PASS | | |
| RECOVERY_NOTIFICATION_DELIVERED | | |
| END_TO_END_MONITOR_TO_ALERT_DRILL | | |
| HUMAN_ALERT_ACKNOWLEDGEMENT | | |
| ALERT_DELIVERY_DRILL | | |
| MONITORING_ALERTING | | |
| INSTAGRAM_GIT_HISTORY_SECRET_SCAN | | |
| GOVERNING_CI_LOG_SECRET_SCAN | | |
| GOVERNING_ARTIFACT_SECRET_SCAN | | |
| PLAINTEXT_SECRET_EXPOSURE_FOUND | YES / NO / NOT VERIFIED | |
| SECRET_ROTATION_HISTORY | | |
| TOKEN_SECRET_SECURITY | | |
| HUMAN_TAKEOVER | | |
| COLD_ENGINEER_HANDOVER | | |
| OWNER_RECOVERY_PACKAGE_EXECUTION | | |
| RECOVERY_RUNBOOK_EXECUTION | | |
| PRODUCTION_BACKUP_RESTORE_DRILL | | |
| PRODUCTION_DISASTER_RECOVERY_DRILL | | |
| PENETRATION_TEST | | |

## 12. المصفوفة النهائية

M26_10_EXACT_TARGET_VERIFIED =
M26_10_EXACT_TREE_VERIFIED =
M26_10_EVIDENCE_RUN_VERIFIED =
EVIDENCE_INTEGRITY_VERIFIED =

GOLDEN_LKG_PROMOTION_RECORD =
GOLDEN_BASELINE_PROMOTED =

END_TO_END_MONITOR_TO_ALERT_DRILL =
ALERT_DELIVERY_DRILL =
MONITORING_ALERTING =
HUMAN_ALERT_ACKNOWLEDGEMENT =

INSTAGRAM_GIT_HISTORY_SECRET_SCAN =
GOVERNING_CI_LOG_SECRET_SCAN =
GOVERNING_ARTIFACT_SECRET_SCAN =
PLAINTEXT_SECRET_EXPOSURE_FOUND =
SECRET_ROTATION_HISTORY =
TOKEN_SECRET_SECURITY =

PRODUCTION_BACKUP_RESTORE_DRILL =
PRODUCTION_DISASTER_RECOVERY_DRILL =
RECOVERY_RUNBOOK_EXECUTION =
OWNER_RECOVERY_PACKAGE_EXECUTION =
HUMAN_TAKEOVER =
COLD_ENGINEER_HANDOVER =
PENETRATION_TEST =

FIRST_PUBLIC_ACTIVATION_ELIGIBLE = NO
PUBLIC_INSTAGRAM_PUBLISHING = HOLD

INDEPENDENT_M26_10_VERDICT =

استخدم فقط PASS / FAIL / NOT VERIFIED / N/A للمتطلبات، وYES / NO / NOT VERIFIED للمتغيرات الثنائية.

## 13. الخاتمة المطلوبة

أجب صراحة:
1. هل Golden/LKG promotion أصبح مثبتًا بما يكفي؟
2. هل End-to-End alert delivery أصبح PASS؟
3. هل Monitoring + Alerting أصبح قابلًا للإغلاق، أم بقي شرط Human acknowledgement؟
4. ماذا يثبت secret scan تحديدًا، وماذا لا يثبت؟
5. هل TOKEN_SECRET_SECURITY يمكن إغلاقه أم يبقى NOT VERIFIED؟
6. كم متطلبًا حاكمًا بقي قبل First Public Activation؟
7. هل ظهر أي سبب لـRemediation كودي جديد؟
8. ما الخطوة التالية الوحيدة المنطقية بعد M26.10؟

لا تنفذ Remediation. أصدر فقط الحكم المستقل.
