#!/usr/bin/env python3
import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

ROOTS = [Path("snapchat_publisher_service"), Path("snapchat_oauth_service")]
ALWAYS_PATTERNS = [
    ("private_key", re.compile(r"BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
]
SENSITIVE_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?P<key>
      client[_-]?secret|
      refresh[_-]?token|
      access[_-]?token|
      owner[_-]?key|
      state[_-]?secret|
      token[_-]?encryption[_-]?key
    )
    ["']?\s*[:=]\s*
    ["'](?P<value>[^"'\r\n]{12,})["']
    """
)
SAFE_MARKERS = ("test", "dummy", "example", "placeholder", "fake", "sample", "unit")


def looks_test_value(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in SAFE_MARKERS)


def entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def scan_text(text: str, source: str, findings: list[str], added_only: bool = False) -> None:
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw
        if added_only:
            if not line.startswith("+") or line.startswith("+++"):
                continue
            line = line[1:]

        for name, pattern in ALWAYS_PATTERNS:
            if pattern.search(line):
                findings.append(f"{source}:{line_no}:{name}")

        match = SENSITIVE_ASSIGNMENT.search(line)
        if not match:
            continue
        value = match.group("value").strip()
        if looks_test_value(value):
            continue

        if any(token in value for token in ("os.getenv", "os.environ", "${", "{{", "<", ">")):
            continue
        if len(value) >= 24 and entropy(value) >= 3.2:
            findings.append(f"{source}:{line_no}:sensitive_literal:{match.group('key').lower()}")


def current_tree() -> int:
    findings: list[str] = []
    for root in ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in {".pyc", ".bin"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            scan_text(text, str(path), findings)

    if findings:
        print("Potential credential material detected in current Snapchat tree:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("Snapchat current-tree credential scan passed.")
    return 0


def history() -> int:
    command = [
        "git", "log", "--all", "-p", "--",
        "snapchat_publisher_service", "snapchat_oauth_service",
    ]
    proc = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    findings: list[str] = []
    scan_text(proc.stdout, "git-history", findings, added_only=True)
    if findings:
        print("Potential credential material detected in Snapchat git history:")
        for finding in findings[:100]:
            print(f"  {finding}")
        if len(findings) > 100:
            print(f"  ... plus {len(findings) - 100} additional findings")
        return 1
    print("Snapchat git-history credential scan passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("current-tree", "history"))
    args = parser.parse_args()
    return current_tree() if args.mode == "current-tree" else history()


if __name__ == "__main__":
    sys.exit(main())
