# EXACT TARGET RE-OPEN INSTRUCTIONS

Reviewer finding being addressed:
Evidence/Target Binding failure only.

This replacement package does NOT self-close any application/security finding. It repairs only the independently recomputable proof that the review payload is bound to the frozen Git target.

## Frozen target

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-independent-review-candidate-20260928`

EXACT COMMIT:
`acb5aff7a79de29f82c150428d29136148b51b36`

EXACT TREE:
`56694a061bbd5ca09f1d8db8e014e04200258403`

## Evidence included

The replacement package contains:

- `exact_target/TikTok-Exact-Target-acb5aff7.bundle`
  - a real Git bundle containing the exact commit/tree/blob objects and complete reachable history;
- `exact_target/full-repository-snapshot.tar`
  - a full `git archive` of the exact commit;
- `candidate/`
  - the full tracked repository snapshot extracted from the exact commit, not a TikTok-only subset;
- `exact_target/FULL_TREE_LS.txt`
  - producer-captured `git ls-tree -r --full-tree HEAD`, informational only;
- `MANIFEST_SHA256.txt`
  - package integrity manifest.

Producer-captured text is NOT independent proof. The reviewer must recompute the bindings below.

## Independent verification path A — Git bundle

Run from the extracted package directory.

```bash
BUNDLE="$PWD/exact_target/TikTok-Exact-Target-acb5aff7.bundle"

rm -rf /tmp/tiktok-bundle-verify /tmp/tiktok-exact-target
git init -q /tmp/tiktok-bundle-verify
git -C /tmp/tiktok-bundle-verify bundle verify "$BUNDLE"

git clone -q "$BUNDLE" /tmp/tiktok-exact-target

git -C /tmp/tiktok-exact-target rev-parse HEAD
git -C /tmp/tiktok-exact-target rev-parse 'HEAD^{tree}'
```

Required outputs:

```text
HEAD = acb5aff7a79de29f82c150428d29136148b51b36
HEAD^{tree} = 56694a061bbd5ca09f1d8db8e014e04200258403
```

If either differs, STOP FAIL-CLOSED.

## Independent verification path B — full snapshot tree reconstruction

This is a second, independent check of the full repository snapshot.

```bash
SNAPSHOT="$PWD/exact_target/full-repository-snapshot.tar"

rm -rf /tmp/tiktok-snapshot-check
mkdir -p /tmp/tiktok-snapshot-check
tar -xf "$SNAPSHOT" -C /tmp/tiktok-snapshot-check

git -C /tmp/tiktok-snapshot-check init -q
git -C /tmp/tiktok-snapshot-check config core.autocrlf false
git -C /tmp/tiktok-snapshot-check add -A
git -C /tmp/tiktok-snapshot-check write-tree
```

Required output:

```text
56694a061bbd5ca09f1d8db8e014e04200258403
```

The earlier reviewer correctly obtained a different tree from package v1 because v1 contained only a selected subset under `candidate/`. Replacement v3 contains the full tracked repository snapshot and a Git bundle, so the root tree is independently recomputable.

## Package integrity

Before target verification:

```bash
sha256sum -c MANIFEST_SHA256.txt
```

Every entry must be `OK`.

## Review continuation

Only after Exact Target PASS:

1. read `START_HERE.md`;
2. read `INDEPENDENT_REVIEW_README.md` in full;
3. execute all mandatory security/reliability/recoverability probes independently;
4. use only `PASS / FAIL / NOT VERIFIED / N/A`;
5. keep all no-deploy/no-merge/no-Recall/no-public-post restrictions in force.

## Closure rule

This Evidence/Target Binding issue may be closed only if the reviewer independently reproduces the expected commit and tree from the bundle/snapshot evidence.

A producer statement, manifest, CI result, or declared SHA alone is not sufficient.
