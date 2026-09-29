# المطلوب من المراجع — TikTok R4.2

راجع حصريًا:

`COMMIT = ece8039623ee82176d756591af9495414a80d3d6`

`TREE = f4fbd1ab5273c0e66decca5b68674e2a1d2ed532`

ابدأ بـExact Target.

ثم اختبر فقط:
1. R4-02 watchdog strict counter validation.
2. R4-03 documentation completeness.
3. focused regression لما قد يتأثر.

الاختبار الحاكم:
أي قيمة count ليست **JSON integer حقيقيًا غير سالب** يجب أن تفشل مغلقًا. اختبر 0.5، -0.5، 1.0، "1"، bool، negative int، nonnumeric، missing.

أعد أيضًا probes السابقة: UNKNOWN/stale مع healthy flags، 404، 429، 429+{}, incomplete 200، healthy 2xx، unreachable، webhook failure، HMAC، secret exclusion، no TikTok mutation.

لا تعِد فتح F-01..F-05 دون دليل جديد؛ R3 يبقى PASS.

لا Deploy ولا Merge ولا Render ولا Paid Infra ولا Recall/Resubmit ولا Public Posting.

حتى مع نجاح R4.2:
`FINAL PRODUCTION AUTO-PUBLISH = NOT AUTHORIZED`
حتى البوابات الإنتاجية الفعلية.
