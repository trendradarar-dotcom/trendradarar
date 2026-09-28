# المطلوب من المراجع المستقل — TikTok R2

راجع المرشح الجديد فقط:

- Commit: `4b1c68a305b80738b0338b601e4cebd48ce1c0bb`
- Tree: `ce176732e850c3c229734f17ca1a929eedfa9cfc`
- Frozen branch: `tiktok-independent-retest-candidate-20260928-r2`

## 1) Exact Target أولًا

ابدأ من `EXACT_TARGET_REOPEN_INSTRUCTIONS.md`.

أعد بنفسك:
- `git bundle verify`
- clone من الـbundle
- `git rev-parse HEAD`
- `git rev-parse HEAD^{tree}`
- إعادة بناء root tree من `full-repository-snapshot.tar`

أي اختلاف = STOP / NOT VERIFIED.

## 2) أعد اختبار Findings السابقة

اختبر F-01..F-05 كما هي في `INDEPENDENT_REVIEW_README.md`:
- F-01 OAuth callback browser/session binding — High
- F-02 429 reconciliation — High
- F-03 Draft terminal taxonomy — Medium
- F-04 actual H.264 decode validation — Medium
- F-05 repository supply chain — Medium

لا تعتبر أي Finding مغلقًا بسبب كود المنتج أو CI.

## 3) Regression

أعد أيضًا الفحوص الحرجة التي سبق أن اجتازت، للتأكد من عدم حدوث regression:
OAuth replay/expiry, scopes, refresh/open_id, revoke, idempotency, duplicate suppression, concurrency, UNKNOWN, recovery, kill switch, limits, audit, reconciliation, health.

## 4) الحالات المسموحة

لكل بند:
`PASS / FAIL / NOT VERIFIED / N/A`

مع Evidence قابل لإعادة الاختبار.

## 5) لا تغييرات تشغيلية

لا Deploy.
لا Merge.
لا تغيير Render.
لا Recall/Resubmit.
لا Public Posting.
لا تفعيل `TIKTOK_AUDIT_APPROVED`.

## 6) القبول النهائي

حتى لو أغلقت F-01..F-05، لا تمنح Production Auto-Publish PASS قبل إثبات:
- production persistence؛
- production backup/restore؛
- external alert delivery؛
- cold engineer rebuild/recovery؛
- owner recovery؛
- final independent architecture/security acceptance.
