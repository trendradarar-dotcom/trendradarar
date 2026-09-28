# EXACT TARGET RE-OPEN INSTRUCTIONS

Reviewer finding being addressed:
Evidence/Target Binding failure only.

The application code is NOT self-declared fixed by this package. This package only repairs the independent proof that the review payload is exactly bound to the frozen Git target.

## Frozen target

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-independent-review-candidate-20260928`

EXACT COMMIT:
`acb5aff7a79de29f82c150428d29136148b51b36`

EXACT TREE:
`56694a061bbd5ca09f1d8db8e014e04200258403`

## Independent verification path

The replacement package contains:
- `exact_target/TikTok-Exact-Target-acb5aff7.bundle` — Git bundle containing the commit/tree/blob objects;
- `exact_target/full-repository-snapshot.tar` — full `git archive` snapshot of the exact commit;
- `exact_target/GIT_SHOW_COMMIT_TREE.txt` — producer-captured command output, informational only;
- `exact_target/BUNDLE_VERIFY_PRODUCER.txt` — producer-captured bundle verification, informational only;
- `EXACT_TARGET.txt` — declared anchors;
- `MANIFEST_SHA256.txt` — package-file integrity manifest.

The reviewer must independently execute:

```bash
git bundle verify exact_target/TikTok-Exact-Target-acb5aff7.bundle
git clone exact_target/TikTok-Exact-Target-acb5aff7.bundle exact-target-repo
cd exact-target-repo
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
```

Required outputs:

```text
HEAD = acb5aff7a79de29f82c150428d29136148b51b36
HEAD^{tree} = 56694a061bbd5ca09f1d8db8e014e04200258403
```

If either differs, stop Fail-Closed.

The reviewer may additionally validate the full snapshot:

```bash
mkdir snapshot-check
tar -xf exact_target/full-repository-snapshot.tar -C snapshot-check
```

The Git bundle is the authoritative independently recomputable commit/tree binding evidence. The full snapshot is supplemental evidence and reviewer convenience.

## Review continuation

Only after the exact-target gate independently passes should the reviewer continue with `START_HERE.md`, `INDEPENDENT_REVIEW_README.md`, and all mandatory security/reliability/recoverability probes.

All prior non-mutation restrictions remain in force.
