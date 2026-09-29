# المطلوب من المراجع — TikTok R5 PostgreSQL Fresh Execution V2

لا تستخدم قاعدة Render التي أنشأها المنتج.

أنشئ أنت PostgreSQL 16 حقيقيًا ومعزولًا داخل بيئتك المستقلة، بمفاتيح وأسرار صناعية من إنشائك، ثم نفذ فقط البنود التي بقيت NOT VERIFIED:

1. **PG-02:** raw PostgreSQL storage + encryption/wrong key/corruption/MultiFernet/audit-secret rejection.
2. **PG-03:** same-idempotency race + account/global hard-limit races + persistence/redelivery.
3. **PG-04:** state transitions + terminal race + provider ID uniqueness + UNKNOWN reopen/reconciliation.
4. **PG-05:** encrypted backup + wrong/corrupt/malformed backup + clean restore + non-empty target refusal + PUBLISHED/UNKNOWN/audit/mutation/provider/marker/sequence + duplicate barrier.
5. **Focused No-Regression:** persistence/state related only.

Exact candidate remains:
`COMMIT d98ee71e110118dc9fff4710dca6bf61381eeefc`
`TREE 4e1f7a6240b15f6c7d80a994efe0331e0dfce912`

Do not modify code, deploy, merge, cut over, use production secrets, use Render review DB, or touch any non-TikTok resource.

Required final:
`PG-02 / PG-03 / PG-04 / PG-05 / FOCUSED NO-REGRESSION / POSTGRESQL DIRECTED RETEST`

Even with full PASS:
`FINAL PRODUCTION AUTO-PUBLISH = NOT VERIFIED / NOT AUTHORIZED`
