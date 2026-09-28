# المطلوب من المراجع المستقل — TikTok R4

راجع فقط:

`COMMIT = dd8e9bac48c8208f3f51bcc83b916db402050d42`

`TREE = 3beafc241aa5e54f933b4ec4f2a49b8c424c2c2f`

`BRANCH = tiktok-production-admission-candidate-20260929-r4`

الهدف من R4 هو **Production-Admission Pre-Qualification** فقط، وليس فتح الإنتاج.

1. أثبت Exact Target من الـbundle والـsnapshot.
2. أعد Regression مركزًا لـF-01..F-05 حتى لا يحدث تراجع عن R3.
3. اختبر أداة recovery qualification محليًا عبر عمليات منفصلة: marker -> reopen -> backup -> isolated restore -> verify.
4. اختبر watchdog على webhook محلي/وهمي: healthy=no alert، degraded=alert، HMAC صحيح، delivery failure يفشل.
5. راجع وثائق recovery/owner/cold-handover من الصفر.
6. نفذ Independent Architecture Pre-Review.
7. لا تعتبر local SQLite test دليلاً على Render production persistence.
8. لا تعتبر وجود webhook code دليلاً على external alert delivery.
9. إذا لم ينفذ شخص مستقل بارد Cold Engineer drill فعليًا، اتركه NOT VERIFIED.
10. لا Deploy ولا Merge ولا Render changes ولا TikTok Recall/Resubmit ولا Public Posting.

استخدم فقط:
`PASS / FAIL / NOT VERIFIED / N/A`

حتى لو نجح R4 محليًا، المتوقع أن يبقى:
`FINAL PRODUCTION AUTO-PUBLISH ACCEPTANCE = NOT VERIFIED / NOT AUTHORIZED`
إلى أن تُنشأ البنية الإنتاجية المصرح بها وتُختبر مستقلًا.
