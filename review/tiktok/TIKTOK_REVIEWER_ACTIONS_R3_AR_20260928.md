# المطلوب من المراجع المستقل — TikTok R3

راجع المرشح الجديد فقط:

- Commit: `47be83f732e63ffc04362f19820c9818e3d574a9`
- Tree: `cf4f045ed253318726ec0aad4b88f7cdac358998`
- Frozen branch: `tiktok-independent-retest-candidate-20260928-r3`

## المطلوب

1. Exact Target أولًا من `EXACT_TARGET_REOPEN_INSTRUCTIONS.md`.
2. بعد PASS، نفذ **اختبارًا عدائيًا عمليًا** لـF-01 وF-04، وليس فحصًا ساكنًا فقط.
3. أعد Regression مختصرًا لـF-02/F-03/F-05 والبنود الحرجة المذكورة في `INDEPENDENT_REVIEW_README.md`.
4. استخدم فقط `PASS / FAIL / NOT VERIFIED / N/A` مع دليل قابل لإعادة التشغيل.

## F-01

نفذ عمليًا:
- callback بدون cookie؛
- callback بـSID مختلف؛
- نقل state بين جلستين؛
- replay بعد الاستهلاك؛
- account/session swapping؛
- سجل عدد مرات token exchange.

PASS فقط إذا ثبت أن المتصفح الذي بدأ OAuth وحده يستطيع إكماله، وأن الحالات المرفوضة لا تستهلك state الشرعية.

## F-04

نفذ corpus وسائط عدائيًا محليًا:
- avc1 مزيف + random/zero mdat؛
- corruption بعد frame أول صالح؛
- truncation بعد frame أول صالح؛
- malformed MP4؛
- HEVC/H.265؛
- bad sample tables/config؛
- policy violations؛
- positive H.264 control.

PASS فقط إذا ثبت أن أي corruption لاحق بعد frame أول يُرفض وأن provider mutation count=0 لكل ملف مرفوض.

## القيود

لا Deploy.
لا Merge.
لا تغيير Render.
لا Recall/Resubmit.
لا Public Posting.
لا تفعيل `TIKTOK_AUDIT_APPROVED`.

حتى مع PASS لـF-01/F-04، القبول الإنتاجي النهائي يبقى محجوبًا حتى بوابات persistence/recovery/alerts/cold takeover.
