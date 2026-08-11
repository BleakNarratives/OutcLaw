#!/usr/bin/env python3
"""outclaw_guard.py — repo integrity guard.

Fails (non-zero exit) if any forbidden identifier reappears anywhere in the
repository working tree. This is the guardrail that keeps private client
identifiers and third-party product names from ever leaking back into the
codebase after they were removed.

Usage:
    python outclaw_guard.py            # scan repo, exit 1 on any hit
    python outclaw_guard.py --json     # machine-readable hits

Run in CI (see .github/workflows/ci.yml) and as a local unit test
(outclaw_tests/test_guard.py).

The guard is intentionally strict: it scans file *contents* and *paths*,
case-insensitively, for every identifier in FORBIDDEN. It is advisory-only in
the sense that it reports, but it exits non-zero so a build fails rather than
silently shipping a leak.

SCOPE: this is a forward guardrail only. It scans the working tree and fails
future builds if an identifier reappears; it does NOT purge git history or
GitHub's cached objects (that is a separate, destructive purge step).

TRADEOFF: binary/oversized files (by extension and a 2MB cap) are skipped for
speed. A leak in a normal-sized source or doc file is always caught; a leak
hidden in a >2MB text file or a binary blob is not. That is a conscious choice
for a source/docs guardrail.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Files that necessarily contain the forbidden identifiers and must never be
# scanned: this guard itself (FORBIDDEN below) and its own test file (which
# uses the identifiers as fixtures to prove the guard works). Narrowed to the
# exact relative paths so a same-named file elsewhere is never exempted.
_SKIP_FILES = {
    os.path.basename(__file__),  # this script, wherever it lives
    os.path.join("outclaw_tests", "test_guard.py"),
}

# Identifiers that must never appear in the repository. Kept deliberately
# separate and central so the list is easy to audit/extend.
FORBIDDEN = [
    # Private client identifiers (removed 2026-08-11) — never to return.
    "melissa",
    "stewart",
    "srewart",
    "26-548",
    # Third-party product name (removed 2026-08-11) — never to return.
    "extraction",
]

# Paths that are always skipped (build artifacts, vendored third-party deps,
# virtualenvs) — a real leak lives in the project tree, not in a dependency.
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "site-packages",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

# Extensions the guard never reads: a leak lives in source/docs, not in a
# binary blob, and scanning multi-hundred-MB media files is pure waste.
SKIP_EXT = {
    ".wav", ".mp3", ".mp4", ".mov", ".avi", ".mkv", ".flac", ".ogg",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff",
    ".pdf", ".zip", ".gz", ".tar", ".7z", ".rar", ".so", ".dll", ".dylib",
    ".pyc", ".pyo", ".pyd", ".whl", ".egg", ".bin", ".dat", ".db", ".sqlite",
}

# Files larger than this (bytes) are skipped — again, to avoid reading
# giant blobs. A leaked identifier lives in a normal-sized text file.
MAX_FILE_BYTES = 2_000_000


def iter_project_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield os.path.join(dirpath, name)


def check_file(path: str, forbidden_lower: list[str]) -> list[dict]:
    hits: list[dict] = []
    path_lower = path.lower()
    for ident in forbidden_lower:
        if ident in path_lower:
            hits.append({"kind": "path", "identifier": ident, "file": path})
    # Skip binary / oversized files by extension and size before reading.
    if os.path.splitext(path)[1].lower() in SKIP_EXT:
        return hits
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return hits
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().lower()
    except OSError:
        return hits
    for ident in forbidden_lower:
        if ident in content:
            hits.append({"kind": "content", "identifier": ident, "file": path})
    return hits


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent
    as_json = "--json" in argv
    forbidden_lower = [i.lower() for i in FORBIDDEN]

    all_hits: list[dict] = []
    for path in iter_project_files(root):
        rel = os.path.relpath(path, root)
        if rel in _SKIP_FILES:
            continue
        all_hits.extend(check_file(path, forbidden_lower))

    # De-duplicate (a file can hit the same identifier as both path+content).
    seen = set()
    unique: list[dict] = []
    for h in all_hits:
        key = (h["kind"], h["identifier"], h["file"])
        if key not in seen:
            seen.add(key)
            unique.append(h)

    if as_json:
        print(
            json.dumps(
                {
                    "clean": len(unique) == 0,
                    "hits": unique,
                },
                indent=2,
            )
        )
    else:
        if unique:
            print(f"GUARD FAILED — {len(unique)} forbidden identifier(s) found:")
            for h in unique:
                print(f"  [{h['kind']}] {h['identifier']!r} in {h['file']}")
        else:
            print("GUARD OK — no forbidden identifiers in repository.")

    return 0 if not unique else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
