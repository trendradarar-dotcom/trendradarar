import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path


LOCK = Path("tiktok_oauth_service/requirements.lock")
WORKFLOWS = Path(".github/workflows")


def parse_lock():
    text = LOCK.read_text(encoding="utf-8")
    lines = text.splitlines()
    components = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\\\s]+)\s*\\?$", line)
        if not m:
            i += 1
            continue
        name, version = m.group(1), m.group(2)
        hashes = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            hm = re.search(r"--hash=sha256:([0-9a-fA-F]{64})", nxt)
            if hm:
                hashes.append(hm.group(1).lower())
                j += 1
                continue
            if not nxt or nxt.startswith("--"):
                j += 1
                continue
            break
        if not hashes:
            raise SystemExit(f"missing SHA-256 hash for {name}=={version}")
        components.append({
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{name.lower()}@{version}",
            "hashes": [{"alg": "SHA-256", "content": h} for h in sorted(set(hashes))],
        })
        i = j
    if not components:
        raise SystemExit("no locked Python components found")
    return sorted(components, key=lambda x: (x["name"].lower(), x["version"]))


def parse_actions():
    refs = {}
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-fA-F]{40})(?:\s|$)", text):
            name, sha = m.group(1), m.group(2).lower()
            refs[(name, sha)] = path.as_posix()
        for m in re.finditer(r"uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([^\s#]+)", text):
            ref = m.group(2)
            if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
                raise SystemExit(f"mutable GitHub Action ref found in {path}: {m.group(1)}@{ref}")
    out = []
    for (name, sha), path in sorted(refs.items()):
        out.append({
            "type": "application",
            "name": name,
            "version": sha,
            "purl": f"pkg:github/{name}@{sha}",
            "properties": [{"name": "trendradar:workflow", "value": path}],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    commit = args.commit.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit("commit must be a full 40-hex Git SHA")

    lock_sha = hashlib.sha256(LOCK.read_bytes()).hexdigest()
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"https://github.com/trendradarar-dotcom/trendradarar@{commit}")
    components = parse_lock() + parse_actions()

    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "TrendRadar-TikTok",
                "version": commit,
                "bom-ref": f"pkg:github/trendradarar-dotcom/trendradarar@{commit}",
                "purl": f"pkg:github/trendradarar-dotcom/trendradarar@{commit}",
            },
            "properties": [
                {"name": "trendradar:scope", "value": "TikTok only"},
                {"name": "trendradar:exactCommit", "value": commit},
                {"name": "trendradar:requirementsLockSHA256", "value": lock_sha},
            ],
        },
        "components": components,
    }
    Path(args.output).write_text(
        json.dumps(bom, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
