# المطلوب من المراجع المستقل — TikTok R4.1

راجع فقط:

`COMMIT = 168642cf54a25edf0949f2e61ede457a3ec19f18`

`TREE = 7b5102b6e71fe788cd220db26bc3afb3c1097ce4`

`BRANCH = tiktok-production-prequal-r4-retest-candidate-20260929-r4-1`

ابدأ بـExact Target.

ثم أعد اختبار البندين اللذين فشلا في R4 فقط:

**R4-02 Watchdog**
- UNKNOWN>0 رغم source flags healthy => alert
- stale>0 رغم source flags healthy => alert
- HTTP 404 => alert
- HTTP 429 => alert
- 429 + {} => fail closed
- 200 + incomplete schema => fail closed
- invalid/negative counts => fail closed
- healthy complete response => no alert
- unreachable => alert
- webhook failure => failing exit
- verify HMAC + no secrets + no TikTok mutation

**R4-03 Documentation**
- R3 PASS مثبت كالحالة السابقة الصحيحة
- R4 FAIL مسجل
- watchdog behavior موصوف مطابقًا للكود
- production persistence/backup/alert/cold takeover تبقى NOT VERIFIED
- لا توجد عبارة توحي بفتح الإنتاج
- لا يبقى R2 كأنه baseline الحالي

اعمل focused regression فقط لما قد يتأثر.

لا Deploy، لا Merge، لا Render، لا Paid Infra، لا Recall/Resubmit، لا Public Posting.

حتى لو نجح R4.1:
`FINAL PRODUCTION AUTO-PUBLISH = NOT AUTHORIZED`
حتى إثبات البوابات الإنتاجية الفعلية.
