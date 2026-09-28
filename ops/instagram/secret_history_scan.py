#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

SCOPED_PREFIXES = (
    "instagram_oauth_service/",
    "instagram_oauth_gateway/",
    "review/instagram/",
    "ops/instagram/",
    ".github/workflows/instagram",
)
SCOPED_EXACT = (
    "tests/test_instagram_publisher.py",
    "tests/test_instagram_gateway.py",
    "tests/test_instagram_media_full_decode.py",
    "tests/test_instagram_postgres_integration.py",
    "tests/test_instagram_postgres_runtime.py",
)

PATTERNS = [
    ("private_key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |)?PRIVATE KEY-----")),
    ("github_token", re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("meta_instagram_token", re.compile(rb"\b(?:IGQV|EAA)[A-Za-z0-9_-]{24,}\b")),
    ("postgres_url_password", re.compile(rb"postgres(?:ql)?://[^\s:/]+:([^\s@]{12,})@")),
    (
        "literal_secret_assignment",
        re.compile(
            rb"(?i)\b(?:INSTAGRAM_APP_SECRET|APP_SECRET|ACCESS_TOKEN|"
            rb"INSTAGRAM_TOKEN_ENCRYPTION_KEY|TOKEN_ENCRYPTION_KEY|"
            rb"INSTAGRAM_PUBLISH_M2M_SECRET|PUBLISH_M2M_SECRET|"
            rb"INSTAGRAM_OAUTH_GATEWAY_SECRET|OAUTH_GATEWAY_SECRET|"
            rb"SESSION_SECRET|REFRESH_SECRET|DATABASE_URL)\b"
            rb"\s*[:=]\s*[\"']([^\"'\r\n]{16,})[\"']"
        ),
    ),
]

SAFE_MARKERS = (
    b"synthetic-",
    b"example.invalid",
    b"REDACTED",
    b"<secret>",
    b"secrets.",
    b"os.getenv",
    b"***",
)

def run(*args):
    return subprocess.check_output(args, stderr=subprocess.DEVNULL)

def is_scoped(path):
    return path in SCOPED_EXACT or any(path.startswith(p) for p in SCOPED_PREFIXES)

def printable(data):
    return not data or b"\x00" not in data[:4096]

def redacted_hash(value):
    return hashlib.sha256(value).hexdigest()[:16]

def scan_bytes(data, source, findings):
    if not printable(data):
        return
    for name, pattern in PATTERNS:
        for match in pattern.finditer(data):
            value = match.group(1) if match.lastindex else match.group(0)
            context = data[max(0, match.start() - 80):min(len(data), match.end() + 80)]
            if any(marker.lower() in context.lower() for marker in SAFE_MARKERS):
                continue
            findings.append({
                "pattern": name,
                "source": source,
                "value_sha256_prefix": redacted_hash(value),
                "value_length": len(value),
            })

def scan_repo_history():
    findings = []
    commits = run(
        "git", "rev-list", "--all", "--",
        *SCOPED_PREFIXES, *SCOPED_EXACT
    ).decode().splitlines()
    seen_blobs = set()
    scanned = 0
    for commit in commits:
        raw = run("git", "ls-tree", "-r", commit)
        for line in raw.decode("utf-8", "replace").splitlines():
            try:
                left, path = line.split("\t", 1)
                _mode, _typ, blob = left.split()
            except ValueError:
                continue
            if not is_scoped(path) or blob in seen_blobs:
                continue
            seen_blobs.add(blob)
            size = int(run("git", "cat-file", "-s", blob).decode())
            if size > 2_000_000:
                continue
            data = run("git", "cat-file", "blob", blob)
            scan_bytes(data, f"git:{blob}:{path}", findings)
            scanned += 1
    return {
        "commits_considered": len(commits),
        "unique_text_blobs_scanned": scanned,
        "findings": findings,
    }

def scan_file(path, findings):
    p = Path(path)
    try:
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                for info in z.infolist():
                    if info.is_dir() or info.file_size > 2_000_000:
                        continue
                    try:
                        data = z.read(info)
                    except Exception:
                        continue
                    scan_bytes(data, f"zip:{p.name}:{info.filename}", findings)
        elif p.stat().st_size <= 2_000_000:
            scan_bytes(p.read_bytes(), f"file:{p}", findings)
    except Exception:
        pass

def scan_tree(root):
    findings = []
    scanned = 0
    for p in Path(root).rglob("*"):
        if p.is_file():
            scan_file(p, findings)
            scanned += 1
    return {"files_considered": scanned, "findings": findings}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--root")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.history:
        result = scan_repo_history()
        result["mode"] = "git_history_instagram_scope"
    else:
        if not args.root:
            raise SystemExit("--root is required unless --history is used")
        result = scan_tree(args.root)
        result["mode"] = "artifact_log_tree"

    result["result"] = "PASS" if not result["findings"] else "FAIL"
    Path(args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if result["findings"]:
        print(json.dumps(result, indent=2))
        raise SystemExit(1)

if __name__ == "__main__":
    main()
