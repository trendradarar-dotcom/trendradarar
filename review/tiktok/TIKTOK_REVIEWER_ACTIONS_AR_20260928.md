# المطلوب من المراجع المستقل — TikTok

التاريخ: 2026-09-28
النطاق: TrendHunter / Trend Radar — TikTok فقط

## الهدف

إصدار حكم مستقل جديد على المرشح المجمد التالي فقط:

- Repository: `trendradarar-dotcom/trendradarar`
- Frozen review branch: `tiktok-independent-review-candidate-20260928`
- EXACT COMMIT: `acb5aff7a79de29f82c150428d29136148b51b36`
- EXACT TREE: `56694a061bbd5ca09f1d8db8e014e04200258403`

أي اختلاف في commit أو tree يعني أن الهدف غير مطابق ويجب إيقاف الحكم على المرشح.

## قواعد المراجع

المراجعة يجب أن تكون:

Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

لا يعتمد المراجع:
- حكم المنتج أو أي PASS سابق؛
- نجاح CI وحده؛
- نجاح Demo سابق وحده؛
- نصوص الوثائق بوصفها إثباتًا لنفسها؛
- ادعاء أن البيئة الإنتاجية تملك تخزينًا دائمًا ما لم يثبت ذلك فعليًا.

## ممنوع على المراجع

- لا Merge إلى `main`.
- لا Deploy للمرشح.
- لا تغيير فرع Render الحي.
- لا تغيير TikTok Developer App Review الجاري.
- لا ضغط Recall.
- لا إعادة Submit.
- لا تفعيل Public Posting.
- لا تفعيل `TIKTOK_AUDIT_APPROVED`.
- لا إجراء اختبار حي قد ينشر عامًا.
- لا اختراع دليل غير موجود.

## أول خطوة إلزامية

قبل مراجعة أي Finding:

1. تحقق أن فرع المراجعة المجمد يشير إلى commit المحدد أعلاه.
2. تحقق أن commit المحدد يشير إلى tree المحدد أعلاه.
3. إذا فشل أي منهما: الحكم = EXACT TARGET NOT VERIFIED ولا يبدأ منح PASS للبنود الأخرى.

## ما يجب مراجعته

المراجع يقرأ أولًا:
- `INDEPENDENT_REVIEW_README.md`
- `candidate/review/tiktok/TIKTOK_SECURITY_RELIABILITY_EVIDENCE_MATRIX_20260928.md`
- `candidate/review/tiktok/TIKTOK_SECURITY_RELIABILITY_REMEDIATION_PLAN_20260928.md`
- `candidate/review/tiktok/TIKTOK_INCIDENT_RECOVERY_RUNBOOK_20260928.md`
- `candidate/review/tiktok/TIKTOK_OWNER_RECOVERY_PACKAGE_20260928.md`

ثم يراجع الكود والاختبارات تحت:
- `candidate/tiktok_oauth_service/`
- `candidate/.github/workflows/tiktok-runtime-remediation-ci.yml`

## التنفيذ المطلوب

المراجع يعيد تشغيل الاختبارات أو يعيد إنتاج مكافئ مستقل لها على الهدف المجمد، ثم ينفذ الفحوص الإلزامية الواردة في `INDEPENDENT_REVIEW_README.md`، وبالأخص:

- OAuth/state replay/expiry/handoff replay.
- Scope enforcement وtoken refresh وopen_id drift.
- revoke/disconnect.
- idempotency ومنع duplicate upload/post.
- concurrent worker races.
- UNKNOWN semantics.
- crash/restart/restore.
- provider 5xx/429/timeout semantics.
- zero automatic retries.
- hard limits / blast radius.
- kill switch / no-publish mode.
- strict media validation.
- audit trail وعدم تسريب الأسرار.
- secret/history/supply-chain review.
- backup/restore/no-duplicate-after-restore.
- monitoring signals.
- architecture review.
- cold-engineer handover / rebuild / recovery.

## صيغة الحكم لكل بند

استخدم فقط:
- PASS
- FAIL
- NOT VERIFIED
- N/A

مع دليل قابل لإعادة الاختبار لكل حكم.

## قاعدة الإغلاق

أي Finding جديد يتبع فقط:

Evidence -> Remediation -> Independent Retest -> Closure Evidence

ولا يجوز اعتبار إصلاح المنتج إغلاقًا ذاتيًا.

## الحكم النهائي

لا يجوز منح:

`SECURITY, RELIABILITY & RECOVERABILITY ACCEPTANCE — PASS`

إلا إذا:
- exact target مثبت؛
- لا يوجد Critical/High مفتوح؛
- البنود الحرجة لها دليل مستقل؛
- الإنتاج الدائم والاسترداد مثبتان؛
- لا يوجد Critical = NOT VERIFIED.

وإلا يبقى الحكم:

`FAIL-CLOSED / NOT AUTHORIZED FOR PRODUCTION AUTO-PUBLISH`

## ملاحظة مهمة

الحزمة تحتوي على أدلة المنتج لمساعدة المراجع في إعادة الإنتاج فقط. لا يجوز اعتبارها مراجعة مستقلة أو اعتمادها دون إعادة اختبار.
