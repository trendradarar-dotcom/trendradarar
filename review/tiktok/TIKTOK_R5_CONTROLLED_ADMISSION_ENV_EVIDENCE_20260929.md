# TikTok R5 — Controlled Admission Environment Evidence

Date: 2026-09-29
Scope: TikTok only

## Owner authorization

Owner explicitly approved R5 execution including the minimum required paid persistent infrastructure, while keeping public posting disabled.

## Isolated R5 service created

A NEW isolated Render service was created. The existing live TikTok review service was not modified.

Service:
- name: `trendradar-tiktok-r5-admission`
- service ID: `srv-datgpumk1f9s7387ai70`
- URL: `https://trendradar-tiktok-r5-admission.onrender.com`
- region: Frankfurt
- auto deploy: OFF
- branch: `tiktok-production-prequal-r4-2-retest-candidate-20260929`
- exact deployed commit: `ece8039623ee82176d756591af9495414a80d3d6`
- current Render plan: free
- public auto-publish: NOT AUTHORIZED

No non-TikTok infrastructure was reused.

## Safety configuration applied

The following non-secret controls were applied to the isolated R5 service:
- `TIKTOK_STATE_DB_PATH=/var/data/tiktok/state.sqlite3`
- `TIKTOK_MUTATIONS_ENABLED=false`
- `TIKTOK_KILL_SWITCH=true`
- `TIKTOK_AUDIT_APPROVED=false`
- `TIKTOK_SCOPES=video.publish,video.upload`

No TikTok production client secret/token was added to this admission environment.

## Python/runtime compatibility evidence

Initial Render builds used default Python 3.14.3 and failed the hash-locked dependency gate because the lockfile's cffi wheel hash was the independently validated Python 3.12 artifact.

Producer compared the CI runtime and found:
- GitHub CI accepted runtime: CPython 3.12.14
- CI hash-locked install: PASS

The isolated Render service was therefore explicitly pinned with:
- `PYTHON_VERSION=3.12.14`

Subsequent Render build:
- exact commit: `ece8039623ee82176d756591af9495414a80d3d6`
- hash-locked dependency install: PASS
- build: PASS
- deploy ID: `dep-datgqmnlot8c73fgop40`
- deploy status: LIVE

This is production-admission evidence, not public-posting authorization.

## Remaining R5 hard blockers

The environment is live only as a NO-PUBLISH admission service.

Still NOT VERIFIED:
1. persistent disk/volume is not yet attached;
2. service plan remains free;
3. `TIKTOK_STATE_ENCRYPTION_KEY` is not yet configured;
4. persistence across restart/replacement is not yet proven;
5. off-runtime backup/restore is not yet proven;
6. real external alert destination/delivery is not yet proven;
7. cold-engineer/owner takeover is not yet proven;
8. final architecture/security acceptance is not yet performed.

## Tooling limitation encountered

The available Render connector can create the isolated service and update non-secret environment variables, but it does not expose persistent-disk attachment or service-plan upgrade actions. Secret-value environment update for the encryption key is also blocked by the execution safety layer.

Therefore the next step requires a minimal Render Dashboard owner action:
- upgrade ONLY the isolated R5 admission service to the minimum plan supporting persistent disk;
- attach the smallest suitable persistent disk at `/var/data`;
- add one generated Fernet encryption key as `TIKTOK_STATE_ENCRYPTION_KEY`.

No change is required to the existing `trendradar-tiktok-oauth` service.
