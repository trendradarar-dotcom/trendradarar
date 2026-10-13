# YouTube R12 Render Portability Successor — Producer Handoff

Date: 2026-10-09
Project: TrendHunter / Trend Radar
Channel: YouTube only
Candidate: R12 Render portability successor
Review mode required next: Fresh / Independent / Adversarial / Read-Only / Exact-Target-Bound

## 1. Immutable parent

Parent artifact:
- TrendHunter-YouTube-R11-Isolated-Candidate-20261004.zip
- SHA-256: E3293E693E1DB08DFF9BA2E01F1188EABC88DA04A4A02AAF6A13B8F2ADB41531
- Parent manifest: 119 / 119 verified on Linux
- Parent remains unchanged.

## 2. Finding that opened this successor

YT-R11-PORT-01 — Windows-only DPAPI refresh-token store is hard-bound to the real private-upload path.

R11 evidence:
- src/trend_hunter/c1_youtube.py rejects WindowsDPAPIRefreshTokenStore on non-Windows.
- src/trend_hunter/api.py used WindowsDPAPIRefreshTokenStore directly in /api/youtube/private-upload.
- Therefore exact R11 cannot activate the real private-upload path on Render/Linux without a source change.

Disposition:
- R11 direct Render production deployment: NO.
- R12 successor required: YES.
- YouTube production admission: HOLD.

## 3. R12 minimal remediation

R12 changes only the portability boundary needed for Render/Linux and its direct runtime dependencies:

1. Added EnvironmentRefreshTokenStore.
   - owner-controlled secret is read only from TREND_HUNTER_YOUTUBE_REFRESH_TOKEN;
   - ledger reference is env://TREND_HUNTER_YOUTUBE_REFRESH_TOKEN;
   - plaintext refresh token is not written to ledger, repository, package, or app logs;
   - put() is compare-only and cannot mutate provider/runtime secret configuration;
   - missing secret or reference mismatch fails closed.

2. Added explicit runtime store selector in api.py.
   - TREND_HUNTER_YOUTUBE_REFRESH_TOKEN_STORE=environment selects the Render/Linux path.
   - windows-dpapi preserves the Windows store.
   - an unset backend preserves R11 Windows behavior; on non-Windows it fails closed through WindowsDPAPIRefreshTokenStore.
   - unsupported backend fails closed.

3. The real /api/youtube/private-upload path now resolves its refresh-token store through that selector.

4. Added Render/Linux runtime dependencies that R11 used implicitly but did not pin in requirements.lock.txt:
   - Pillow==12.3.0
   - arabic-reshaper==3.0.1
   - python-bidi==0.6.11
   - imageio-ffmpeg==0.6.0

5. Version advanced from 0.4.5 to 0.4.6.

6. Added tests/test_youtube_render_portability_r12.py, including direct wiring coverage of the real /api/youtube/private-upload route with the environment-backed secret store.

## 4. Fail-closed credential migration rule

No real refresh token is included in this candidate.

Before any future production runtime activation:
- Render secret TREND_HUNTER_YOUTUBE_REFRESH_TOKEN must be provisioned out-of-band;
- TREND_HUNTER_YOUTUBE_REFRESH_TOKEN_STORE must be exactly environment;
- the governed OAuth grant must reference env://TREND_HUNTER_YOUTUBE_REFRESH_TOKEN;
- an R11 dpapi-user:// grant reference must NOT be silently reinterpreted as an environment reference;
- migration/re-consent must be separately evidenced and independently reviewed;
- TREND_HUNTER_YOUTUBE_PRIVATE_UPLOAD_ENABLED remains disabled until the later production-admission gate.

## 5. Producer verification evidence

Parent integrity:
- R11 ZIP SHA-256 rechecked: e3293e693e1db08dff9ba2e01f1188eabc88da04a4a02aaf6a13b8f2adb41531
- R11 manifest rechecked on Linux: 119 entries, 0 mismatches.

Linux / WSL2 portability environment:
- Linux x86_64 WSL2
- Python 3.14.4
- R12 targeted YouTube/portability suite: 52 PASS / 0 FAIL
- R12 broad runtime suite excluding inherited packaging test module: 230 PASS / 0 FAIL
- compileall: PASS
- bundled imageio-ffmpeg executable resolved and executable: ffmpeg 7.0.2-static

Windows regression environment:
- Windows
- Python 3.13.7
- R12 targeted YouTube/portability suite: 52 PASS / 0 FAIL

Resolved pinned dependencies in Linux qualification:
- fastapi 0.128.2
- uvicorn 0.48.0
- pydantic 2.13.4
- pytest 9.0.2
- httpx 0.28.1
- Pillow 12.3.0
- arabic-reshaper 3.0.1
- python-bidi 0.6.11
- imageio-ffmpeg 0.6.0

## 6. Inherited packaging-test boundary

A full pytest collection of the isolated R11/R12 artifact includes tests/test_packaging.py, which imports verify_delivery.py and references packaging data that are not present in the R11 isolated candidate.

Observed:
- before runtime dependency remediation, full collection stopped at missing verify_delivery.py;
- after excluding only tests/test_packaging.py, the remaining broad suite passed 229/229.

This handoff does NOT convert that inherited isolated-package omission into a PASS. Independent review must either:
- keep tests/test_packaging.py explicitly outside this Render-portability scope, or
- obtain/reconstruct no missing files only from an approved exact source and review them separately.

No producer-side claim of full-package verification is made.

## 7. Non-goals / holds

This R12 candidate does NOT:
- publish or upload a real YouTube video;
- migrate a real OAuth refresh token;
- create or mutate a Render production runtime;
- enable TREND_HUNTER_YOUTUBE_PRIVATE_UPLOAD_ENABLED;
- change the governed YouTube Channel ID;
- alter TikTok, Instagram, or Snapchat;
- grant production admission;
- perform production cutover.

Channel binding remains:
- YouTube Channel ID: UCPm6nbktPc2Egr05AV-zPhA
- Handle: @TrendRadarAR

## 8. Next independent gate

Required next verdicts:
- EXACT TARGET = PASS / NOT VERIFIED
- R12_MANIFEST = PASS / FAIL
- YT-R11-PORT-01 = CLOSED / OPEN
- R12_LINUX_RENDER_SECRET_STORE = PASS / FAIL
- R12_WINDOWS_NO_REGRESSION = PASS / FAIL
- R12_MEDIA_RUNTIME_DEPENDENCIES = PASS / FAIL
- R12_FAIL_CLOSED_MISSING_SECRET = PASS / FAIL
- R12_FAIL_CLOSED_REFERENCE_MISMATCH = PASS / FAIL
- R12_REAL_PROVIDER_MUTATION = NONE
- YOUTUBE_PRODUCTION_ADMISSION = HOLD

Only after an independent PASS may a YouTube Render runtime candidate be created for runtime-equivalence evidence.
