# طلب مراجعة مستقلة — Instagram M26.12 Full Environment Reproducibility

**PROJECT:** TrendHunter / Trend Radar  
**SCOPE:** Instagram فقط  
**REVIEW TYPE:** Independent Environment Reproducibility Review  
**MODE:** Fresh / Independent / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## 1. الهدف الوحيد

تحديد ما إذا كانت بوابة:

`FULL_ENVIRONMENT_REPRODUCIBILITY`

يمكن إغلاقها الآن بناءً على الـruntime artifact الحتمية والمثبتة بالـdigest، أو يجب أن تبقى `NOT VERIFIED` لأن Live Render الحالي ما زال Native Python وليس OCI runtime نفسها.

لا تعِد فتح R5 أو HIGH-01 أو M26.9/M26.10/M26.11 دون Regression جديد مباشر.

لا تنفذ Remediation ولا Deploy.

---

## 2. Exact M26.12 Target

```text
M26_12_EXACT_TARGET_COMMIT =
0f6101f540c3b8dc9afe4166a93218bd03371da1

M26_12_EXACT_TARGET_TREE =
f96bdadf854dc200d3f02b68c7cc645ff784cd2b

M26_12_EVIDENCE_RUN =
36528470991
```

Expected run:

```text
status = completed
conclusion = success
```

Expected jobs:

```text
rebuild (a) = success
rebuild (b) = success
compare-independent-rebuilds = success
```

---

## 3. R5 Governing Anchors

```text
R5_EXACT_TARGET_COMMIT =
d41c1c1cdaa7cf374989e2b059db6a640cb51eef

R5_EXACT_TARGET_TREE =
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d

R5_WHEELHOUSE_ARTIFACT_ID =
10969998558

R5_WHEELHOUSE_DIGEST =
sha256:35b42a06c35ab660c0a792d93d16542f5584d1798fd697e4d2d4e189805da068
```

---

## 4. Exact Reproducible Runtime Anchors

### Python application runtime

```text
platform = linux/amd64

python_version =
3.14.3

PYTHON_IMAGE =
python@sha256:f21c0d5a44c56805654c15abccc1b2fd576c8d93aca0a3f74b4aba2dc92510e2
```

Expected runtime evidence:

```text
implementation = CPython
python_version = 3.14.3
OpenSSL = 3.0.18
Python binary SHA-256 =
3fbc4d6c766a7a5d56c4bcc80d3325181a05f1b64596eb7cf622f0ec056dd546
```

Expected application userland:

```text
Debian GNU/Linux 12 (bookworm)
glibc 2.36
```

### PostgreSQL recovery/test runtime

```text
POSTGRES_IMAGE =
postgres@sha256:3725f4e2499eef5134592b3b4ab79a543ed7f8e533b05b5b637af926630f6650
```

Expected:

```text
PostgreSQL 18.6
Debian 12 / bookworm
package build = 18.6-1.pgdg12+2
```

---

## 5. Production Runtime Parity — Read-Only Verification Required

تحقق مستقلًا من Render، ولا تعتمد على Producer statement فقط.

### Backend

```text
service =
trendradar-instagram-oauth

service_id =
srv-daqed80u01pc73fs6rgg

live deploy =
dep-datf23g93c1s73abu5k0

live commit =
d2477d9397643c789fa4b27dbcf669a83b1acd2a

branch =
instagram-production-review-20260924
```

Expected Render build evidence:

```text
Python = 3.14.3
build command =
pip install -r instagram_oauth_service/requirements.txt

start command =
gunicorn --chdir instagram_oauth_service app:app
```

### Gateway

```text
service =
trendradar-connect

service_id =
srv-dar4l3k9v7es739flr0g

live deploy =
dep-datf24g93c1s73abuau0

live commit =
d2477d9397643c789fa4b27dbcf669a83b1acd2a
```

Expected Render build evidence:

```text
Python = 3.14.3
build command =
pip install -r instagram_oauth_gateway/requirements.txt

start command =
gunicorn --chdir instagram_oauth_gateway app:app
```

### Production PostgreSQL

```text
database =
trendradar-instagram-postgres

postgres_id =
dpg-das2sqbbc2fs7393j0pg-a
```

Producer Read-Only Render log observation:

```text
PostgreSQL 18.6
Debian package =
18.6-1.pgdg12+2
architecture =
x86_64-pc-linux-gnu
```

مهم:

Production DB IP allowlist فارغ ومغلق.

لا تفتح allowlist ولا تنفذ اتصال SQL خارجي لهذه المراجعة.

استخدم فقط Render metadata/logs الموجودة أصلًا.

---

## 6. Governing Evidence Artifacts — Final Run Only

راجع حصريًا Run:

`36528470991`

### Rebuild A

```text
Artifact ID =
11015920893

Artifact digest =
sha256:e0829d303277712408151bb7b84337a00a770858a4d436a4536057b7acc2bfc2
```

### Rebuild B

```text
Artifact ID =
11015845994

Artifact digest =
sha256:3ae8253b4e3d70eb3d467017cae80ce23db466e6554d16e4698a9f00ce6c11b8
```

### Independent comparison

```text
Artifact ID =
11015398329

Artifact digest =
sha256:ea9252680f1361c6927758c46a4a0dc22678a1ce6f92526cf5a9118c629e339b
```

لا تعتمد على `result.txt` وحده.

أعد التحقق من:

- outer Artifact SHA-256.
- internal `SHA256SUMS.txt`.
- exact source commit/tree.
- wheelhouse digest.
- Python image digest.
- PostgreSQL image digest.
- Python binary hash.
- OS/userland manifest.
- package inventory.
- pip check.
- source manifest.
- deterministic OCI tar hash.
- OCI manifest/config/layer digests.
- exact R5 acceptance suites.

---

## 7. Expected Raw Evidence

Expected source:

```text
R5 commit =
d41c1c1cdaa7cf374989e2b059db6a640cb51eef

R5 tree =
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d
```

Expected OCI tar SHA-256 from both A and B:

```text
dd03a088558689a712b1796fe66783c4c410fe4cee3a5badd9ed80c3f8212987
```

Expected OCI index manifest digest:

```text
sha256:ff4b8f368a97f679d0a035f9e5f5edaf25087b56398dfb786d759f73972028ed
```

Expected OCI config digest:

```text
sha256:f53364934882fbccf730afa8c348b8f9ccea1e99aa5f7d68507081c937e7fa7f
```

Expected runtime:

```text
Python = 3.14.3
PostgreSQL = 18.6 (Debian 18.6-1.pgdg12+2)
```

Expected producer comparison:

```text
INDEPENDENT_REBUILD_A=PASS
INDEPENDENT_REBUILD_B=PASS

DETERMINISTIC_OCI_TAR_MATCH=PASS
OCI_MANIFEST_DIGEST_MATCH=PASS

PYTHON_RUNTIME_MANIFEST_MATCH=PASS
OS_USERLAND_MANIFEST_MATCH=PASS
PYTHON_BINARY_HASH_MATCH=PASS
PYTHON_PACKAGE_SET_MATCH=PASS

SOURCE_MANIFEST_MATCH=PASS
WHEELHOUSE_MANIFEST_MATCH=PASS
POSTGRES_IMAGE_MATCH=PASS

EXACT_R5_ACCEPTANCE_SUITES_BOTH=PASS
```

Also observed:

```text
LOCAL_DOCKER_IMAGE_ID=DIFF_NON_GOVERNING
LOCAL_DOCKER_ROOTFS_DIFFIDS=DIFF_NON_GOVERNING
```

تحقق مستقلًا مما إذا كان هذا التصنيف صحيحًا تقنيًا.

الـartifact الحاكم هو deterministic OCI export، وليس local daemon image object.

---

## 8. Reproducibility Isolation Requirements

تحقق من أن:

- source مأخوذ من R5 Exact Target فقط.
- Python dependencies من captured wheelhouse فقط.
- `pip --no-index` مستخدم.
- build يستخدم `--network=none`.
- PostgreSQL test network internal-only.
- Python runtime pinned by digest.
- PostgreSQL runtime pinned by digest.
- لا Production secrets.
- لا Production DB access.
- لا Render mutation.
- لا publish-gate mutation.
- لا external package fallback أثناء build.

أصدر:

```text
BUILD_NETWORK_DISABLED =
DEPENDENCY_NETWORK_FALLBACK_DISABLED =
TEST_NETWORK_INTERNAL_ONLY =
PRODUCTION_SECRET_USED =
PRODUCTION_DATABASE_TOUCHED =
RENDER_MUTATION_FOUND =
PUBLISH_GATE_MUTATION_FOUND =
```

---

## 9. Cross-Project / Cross-Channel Isolation Gate

هذه الجولة **Instagram فقط**.

قارن:

```text
BASE =
138a5d99004020027f5483d6aa154824556ef061

M26.12 EXACT TARGET =
0f6101f540c3b8dc9afe4166a93218bd03371da1
```

Expected delta only:

```text
.github/workflows/instagram-m26-12-runtime-reproducibility.yml
ops/instagram/Dockerfile.reproducible-r5
```

لا يجوز وجود أي تعديل في:

- YouTube
- TikTok
- Snapchat
- Tanoub Travel
- TCC
- WhatsApp Offers
- أي مشروع أو قناة أخرى.

أصدر:

```text
INSTAGRAM_SCOPE_ISOLATION =
CROSS_PROJECT_CONTAMINATION_FOUND =
CROSS_CHANNEL_CONTAMINATION_FOUND =
```

---

## 10. Governing Boundary Question

افصل بين:

```text
REPRODUCIBLE_PINNED_OCI_RUNTIME =
DOUBLE_REBUILD_REPRODUCIBILITY =
LIVE_RUNTIME_COMPONENT_PARITY =
CURRENT_LIVE_RENDER_RUNTIME_NATIVE_PYTHON =
LIVE_RUNTIME_BOUND_TO_PINNED_OCI =
FULL_ENVIRONMENT_REPRODUCIBILITY =
```

السؤال الحاكم:

> هل وجود deterministic OCI runtime قابلة لإعادة البناء مرتين بنفس البتات/manifest، مع مطابقة source وPython 3.14.3 وdependencies وPostgreSQL 18.6/Bookworm واختبارات R5، يكفي لتعريف FULL_ENVIRONMENT_REPRODUCIBILITY في هذا المشروع، رغم أن Render Live الحالي يعمل Native Python وليس نفس OCI artifact؟

لا توسع PASS أكثر من الأدلة.

إذا كان معيار `FULL_ENVIRONMENT_REPRODUCIBILITY` يشترط أن **بيئة الإنتاج الفعلية نفسها** تكون مرتبطة بالـOCI artifact المثبتة، فابقِها `NOT VERIFIED`.

إذا كان المعيار يعني وجود **بيئة تشغيل/استرداد كاملة محددة بالـdigest وقابلة لإعادة الإنتاج مستقلًا مع parity مثبتة للمكونات الحاكمة**، فقيّم PASS فقط إذا أثبتت الأدلة ذلك كاملًا.

---

## 11. Previous M26.12 Harness Failures

لا تخفِ المحاولات السابقة.

صنف ما إذا كانت Product Findings أو Review-Harness Findings، ومنها:

- shell harness استخدم `sh -lc set -euo pipefail` على Debian `/bin/sh` وأوقف التنفيذ قبل الاختبارات.
- تم إصلاح أسلوب الـharness فقط.
- OCI exporter الأول تحت Docker driver لم يكن مناسبًا للـdeterministic export.
- تم الانتقال إلى isolated `docker-container` buildx builder.
- local Docker daemon IDs/diffIDs ظلت مختلفة رغم تطابق deterministic OCI artifact والeffective runtime evidence.
- PostgreSQL الأول كان 18.6 على Debian 13؛ تم رفضه كـfinal evidence بعد مقارنة Production logs، ثم استبداله في Final Run بـ18.6/Bookworm المطابق لـProduction package build `pgdg12+2`.

حدد إن كان أي من ذلك Product Finding فعليًا.

---

## 12. Required Status Matrix

استخدم فقط:

`PASS / FAIL / NOT VERIFIED / N/A`

وللملاحظات الثنائية:

`YES / NO / NOT VERIFIED`

```text
M26_12_EXACT_TARGET_VERIFIED =
M26_12_EXACT_TREE_VERIFIED =
M26_12_EVIDENCE_RUN_VERIFIED =
EVIDENCE_INTEGRITY_VERIFIED =

INSTAGRAM_SCOPE_ISOLATION =
CROSS_PROJECT_CONTAMINATION_FOUND =
CROSS_CHANNEL_CONTAMINATION_FOUND =

R5_SOURCE_TREE_PINNED =
R5_WHEELHOUSE_PINNED =

PYTHON_3_14_3_PINNED =
PYTHON_BASE_IMAGE_PINNED_BY_DIGEST =
PYTHON_BINARY_HASH_STABLE =

POSTGRES_18_6_PINNED =
POSTGRES_BOOKWORM_PINNED =
POSTGRES_PRODUCTION_VERSION_PARITY =

BUILD_NETWORK_DISABLED =
DEPENDENCY_NETWORK_FALLBACK_DISABLED =
TEST_NETWORK_INTERNAL_ONLY =

INDEPENDENT_REBUILD_A =
INDEPENDENT_REBUILD_B =

DETERMINISTIC_OCI_TAR_MATCH =
OCI_MANIFEST_DIGEST_MATCH =
PYTHON_RUNTIME_MANIFEST_MATCH =
OS_USERLAND_MANIFEST_MATCH =
PYTHON_BINARY_HASH_MATCH =
PYTHON_PACKAGE_SET_MATCH =
SOURCE_MANIFEST_MATCH =
WHEELHOUSE_MANIFEST_MATCH =
POSTGRES_IMAGE_MATCH =
EXACT_R5_ACCEPTANCE_SUITES_BOTH =

LOCAL_DOCKER_IMAGE_ID_MATCH =
LOCAL_DOCKER_ROOTFS_DIFFIDS_MATCH =

REPRODUCIBLE_PINNED_OCI_RUNTIME =
DOUBLE_REBUILD_REPRODUCIBILITY =
LIVE_RUNTIME_COMPONENT_PARITY =

CURRENT_LIVE_RENDER_RUNTIME_NATIVE_PYTHON =
LIVE_RUNTIME_BOUND_TO_PINNED_OCI =

FULL_ENVIRONMENT_REPRODUCIBILITY =

NEW_PRODUCT_FINDING =
CODE_REMEDIATION_REQUIRED =

FIRST_PUBLIC_ACTIVATION_ELIGIBLE = NO
PUBLIC_INSTAGRAM_PUBLISHING = HOLD

INDEPENDENT_M26_12_VERDICT =
```

---

## 13. Required Conclusion

أجب صراحة:

1. هل Exact M26.12 Target/Evidence صحيحان؟
2. هل العزل عن كل مشروع وقناة أخرى مثبت؟
3. هل Python 3.14.3 مثبتة حرفيًا؟
4. هل Python runtime pinned by immutable digest؟
5. هل PostgreSQL 18.6/Bookworm pinned by immutable digest؟
6. هل PostgreSQL evidence يطابق Production PostgreSQL version/package family؟
7. هل build A وB مستقلان وناجحان؟
8. هل أنتجا نفس deterministic OCI tar حرفيًا؟
9. هل source/wheelhouse/runtime/package/userland manifests متطابقة؟
10. هل R5 acceptance tests نجحت في البناءين؟
11. هل اختلاف local Docker image ID/diffIDs يؤثر على الحكم؟
12. هل Live Render components لها parity كافية مع runtime المعاد بناؤها؟
13. هل Live Render يستخدم نفس OCI artifact فعليًا؟
14. ما الحكم الصحيح لـ `FULL_ENVIRONMENT_REPRODUCIBILITY`؟
15. هل ظهر Product Finding جديد؟
16. هل يلزم Code Remediation؟
17. كم بوابة حاكمة تبقى قبل First Public Activation بعد هذا الحكم؟
18. ما الخطوة التالية الوحيدة المنطقية؟

لا تنفذ Remediation أو Deploy أو DB access أو publish mutation.

أصدر الحكم المستقل فقط.
