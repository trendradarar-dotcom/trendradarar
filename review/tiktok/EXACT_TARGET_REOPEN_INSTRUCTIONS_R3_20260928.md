# EXACT TARGET RE-OPEN — TikTok R3

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-independent-retest-candidate-20260928-r3`

EXACT COMMIT:
`47be83f732e63ffc04362f19820c9818e3d574a9`

EXACT TREE:
`cf4f045ed253318726ec0aad4b88f7cdac358998`

## Path A — Git bundle

```bash
BUNDLE="$PWD/exact_target/TikTok-R3-Exact-Target-47be83f7.bundle"

rm -rf /tmp/tiktok-r3-bundle-verify /tmp/tiktok-r3-exact
git init -q /tmp/tiktok-r3-bundle-verify
git -C /tmp/tiktok-r3-bundle-verify bundle verify "$BUNDLE"

git clone -q "$BUNDLE" /tmp/tiktok-r3-exact

git -C /tmp/tiktok-r3-exact rev-parse HEAD
git -C /tmp/tiktok-r3-exact rev-parse 'HEAD^{tree}'
```

Required:

```text
HEAD = 47be83f732e63ffc04362f19820c9818e3d574a9
HEAD^{tree} = cf4f045ed253318726ec0aad4b88f7cdac358998
```

## Path B — full snapshot root-tree reconstruction

```bash
SNAPSHOT="$PWD/exact_target/full-repository-snapshot.tar"

rm -rf /tmp/tiktok-r3-snapshot
mkdir -p /tmp/tiktok-r3-snapshot
tar -xf "$SNAPSHOT" -C /tmp/tiktok-r3-snapshot

git -C /tmp/tiktok-r3-snapshot init -q
git -C /tmp/tiktok-r3-snapshot config core.autocrlf false
git -C /tmp/tiktok-r3-snapshot add -A
git -C /tmp/tiktok-r3-snapshot write-tree
```

Required:

```text
cf4f045ed253318726ec0aad4b88f7cdac358998
```

## Package integrity

```bash
sha256sum -c MANIFEST_SHA256.txt
```

All entries must be OK.

If any binding differs:
- EXACT TARGET = NOT VERIFIED
- stop Fail-Closed.

Producer CI/text is not independent proof.
