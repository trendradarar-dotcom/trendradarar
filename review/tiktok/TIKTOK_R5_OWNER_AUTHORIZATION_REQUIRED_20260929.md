# TikTok R5 — Owner Authorization Required

Date: 2026-09-29
Scope: TikTok only

R4.2 local pre-qualification is independently closed.

Before R5 can gather production-bound evidence, explicit owner authorization is required for the actions below because they may change external infrastructure and may incur cost.

## Authorization scope requested

Authorize ONLY the following controlled R5 actions:

1. provision or attach TikTok-dedicated persistent storage suitable for `TIKTOK_STATE_DB_PATH`;
2. if required by Render, upgrade the TikTok service plan only to the minimum plan necessary for persistent storage;
3. deploy the hardened TikTok candidate to a controlled production-admission environment;
4. enforce:
   - `TIKTOK_MUTATIONS_ENABLED=false`
   - `TIKTOK_KILL_SWITCH=true`
   - `TIKTOK_AUDIT_APPROVED=false/unset`
5. configure production-persistence qualification only;
6. configure a real external alert destination only if separately identified/approved by the owner;
7. run persistence / restart / backup / isolated-restore / alert-delivery evidence collection;
8. do NOT enable public posting.

## Still prohibited

Authorization for R5 infrastructure does NOT authorize:
- public TikTok posting;
- `TIKTOK_AUDIT_APPROVED=true`;
- TikTok App Review Recall or Resubmit;
- reuse of Instagram/Snapchat/TCC/Tanoub databases or infrastructure;
- merging to main;
- unrelated project changes.

## Required explicit owner statement

A sufficient authorization is:

> أوافق على تنفيذ R5 لقناة TikTok فقط، بما يشمل إنشاء/ترقية الحد الأدنى من البنية الدائمة اللازمة على Render إذا ترتبت تكلفة، ونشر المرشح المحصّن في وضع NO-PUBLISH مع Kill Switch مفعّل، لغرض إثبات persistence/backup/restore/alerts فقط. لا أوافق على النشر العام أو تفعيل TIKTOK_AUDIT_APPROVED.

Without that explicit authorization, R5 remains preparation-only.
