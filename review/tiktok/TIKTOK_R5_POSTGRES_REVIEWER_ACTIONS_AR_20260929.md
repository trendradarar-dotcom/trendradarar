# المطلوب من المراجع المستقل — TikTok R5 PostgreSQL Directed Retest

راجع حصريًا:

`COMMIT = d98ee71e110118dc9fff4710dca6bf61381eeefc`

`TREE = 4e1f7a6240b15f6c7d80a994efe0331e0dfce912`

`BRANCH = tiktok-r5-postgres-independent-retest-candidate-20260929`

ابدأ بـExact Target من الـbundle والـsnapshot.

ثم راجع الجزء المتغير فقط:

1. **PG-01:** Production = PostgreSQL فقط، وSQLite = test/dev فقط، وكل missing/invalid/unavailable PostgreSQL يفشل مغلقًا بلا fallback.
2. **PG-02:** تشفير session/OAuth/handoff/recovery marker وعدم ظهور الأسرار plaintext.
3. **PG-03:** idempotency + transactional admission + concurrency على PostgreSQL حقيقي، مع أكثر من store/connection.
4. **PG-04:** state machine + provider_publish_id uniqueness + UNKNOWN safety + atomic transitions.
5. **PG-05:** encrypted backup إلى artifact ثم restore إلى PostgreSQL ثانٍ نظيف؛ تحقق من PUBLISHED/UNKNOWN/audit/mutation history/duplicate barrier.
6. **PG-06:** hash-lock + Psycopg + SBOM + immutable Actions.
7. Focused no-regression فقط لـF-01..F-05/R4.2 والـkill switch/idempotency/audit.

اختبارات عدائية مهمة:
- PostgreSQL unavailable;
- production مع SQLite;
- missing backend/runtime mode;
- نفس idempotency عبر threads/store instances;
- race على active/global hard limits;
- race على terminal transition;
- duplicate provider_publish_id;
- UNKNOWN بعد reopen;
- redelivery بعد restart;
- wrong key/corrupt backup;
- restore على DB غير فارغة.

لا Deploy، لا Merge، لا Render، لا Cutover، لا استخدام DB خارج TikTok، لا Recall/Resubmit، لا Public Posting.

حتى مع PASS كامل:
`FINAL PRODUCTION AUTO-PUBLISH = NOT VERIFIED / NOT AUTHORIZED`
