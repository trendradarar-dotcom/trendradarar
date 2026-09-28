# EXACT TARGET RE-OPEN — TikTok R2

This gate binds the independent retest to the R2 candidate only.

## Frozen target

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-independent-retest-candidate-20260928-r2`

EXACT COMMIT:
`4b1c68a305b80738b0338b601e4cebd48ce1c0bb`

EXACT TREE:
`ce176732e850c3c229734f17ca1a929eedfa9cfc`

## Path A — Git bundle

From the extracted package directory:

```bash
BUNDLE="$PWD/exact_target/TikTok-R2-Exact-Target-4b1c68a3.bundle"

rm -rf /tmp/tiktok-r2-bundle-verify /tmp/tiktok-r2-exact
git init -q /tmp/tiktok-r2-bundle-verify
git -C /tmp/tiktok-r2-bundle-verify bundle verify "$BUNDLE"

git clone -q "$BUNDLE" /tmp/tiktok-r2-exact

git -C /tmp/tiktok-r2-exact rev-parse HEAD
git -C /tmp/tiktok-r2-exact rev-parse 'HEAD^{tree}'
```

Required:

```text
HEAD = 4b1c68a305b80738b0338b601e4cebd48ce1c0bb
HEAD^{tree} = ce176732e850c3c229734f17ca1a929eedfa9cfc
```

## Path B — full snapshot root-tree reconstruction

```bash
SNAPSHOT="$PWD/exact_target/full-repository-snapshot.tar"

rm -rf /tmp/tiktok-r2-snapshot
mkdir -p /tmp/tiktok-r2-snapshot
tar -xf "$SNAPSHOT" -C /tmp/tiktok-r2-snapshot

git -C /tmp/tiktok-r2-snapshot init -q
git -C /tmp/tiktok-r2-snapshot config core.autocrlf false
git -C /tmp/tiktok-r2-snapshot add -A
git -C /tmp/tiktok-r2-snapshot write-tree
```

Required:

```text
ce176732e850c3c229734f17ca1a929eedfa9cfc
```

## Package integrity

```bash
sha256sum -c MANIFEST_SHA256.txt
```

All entries must be OK.

## Fail-Closed rule

If bundle commit, bundle tree, or reconstructed snapshot tree differs:
- EXACT TARGET = NOT VERIFIED
- stop before finding closure/retest acceptance.

Only after PASS continue to `INDEPENDENT_REVIEW_README.md`.

Producer text/CI is not independent proof.
