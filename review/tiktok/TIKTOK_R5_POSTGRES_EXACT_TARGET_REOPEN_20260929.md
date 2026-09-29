# Exact Target Reopen — TikTok R5 PostgreSQL Directed Retest

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-r5-postgres-independent-retest-candidate-20260929`

EXACT COMMIT:
`d98ee71e110118dc9fff4710dca6bf61381eeefc`

EXACT TREE:
`4e1f7a6240b15f6c7d80a994efe0331e0dfce912`

## Bundle path

`exact_target/TikTok-R5-Postgres-Exact-Target-d98ee71e.bundle`

Verify independently:

```bash
git init -q /tmp/tiktok-r5-pg-verify
git -C /tmp/tiktok-r5-pg-verify bundle verify "$PWD/exact_target/TikTok-R5-Postgres-Exact-Target-d98ee71e.bundle"

git clone -q "$PWD/exact_target/TikTok-R5-Postgres-Exact-Target-d98ee71e.bundle" /tmp/tiktok-r5-pg-clone

git -C /tmp/tiktok-r5-pg-clone rev-parse HEAD
git -C /tmp/tiktok-r5-pg-clone rev-parse 'HEAD^{tree}'
```

Required:
- HEAD = `d98ee71e110118dc9fff4710dca6bf61381eeefc`
- HEAD^{tree} = `4e1f7a6240b15f6c7d80a994efe0331e0dfce912`

## Snapshot reconstruction

```bash
rm -rf /tmp/tiktok-r5-pg-snapshot
mkdir -p /tmp/tiktok-r5-pg-snapshot
tar -xf "$PWD/exact_target/full-repository-snapshot.tar" -C /tmp/tiktok-r5-pg-snapshot

git -C /tmp/tiktok-r5-pg-snapshot init -q
git -C /tmp/tiktok-r5-pg-snapshot config core.autocrlf false
git -C /tmp/tiktok-r5-pg-snapshot add -A
git -C /tmp/tiktok-r5-pg-snapshot write-tree
```

Required tree:
`4e1f7a6240b15f6c7d80a994efe0331e0dfce912`

Run:
`sha256sum -c MANIFEST_SHA256.txt`

Any mismatch:
`EXACT TARGET = NOT VERIFIED`
and stop Fail-Closed.

Producer CI/package self-check is orientation only and not independent evidence.
