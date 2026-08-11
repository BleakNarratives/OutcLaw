# Receipt — repo integrity guard (2026-08-11)

Scope: add a forward guardrail that fails the build if any private client
identifier or third-party product name ever reappears in the repository
working tree. The guarded names are not written out in this prose, by design.

## What was added

**`outclaw_guard.py`** — repo integrity guard:
- Scans file **contents and paths**, case-insensitive, for every entry in its
  `FORBIDDEN` list (private client identifiers + removed third-party name).
- Exits non-zero on any hit so a build fails rather than silently shipping a
  leak; `--json` mode gives machine-readable output.
- Skips `.git`, venvs, `site-packages`, `__pycache__`, and binary/oversized
  files (extension + 2MB cap) for speed (~0.3s on the full repo).
- Self-skips its own file and its test file — the only two files that
  legitimately hold the guarded names (as fixtures).
- Explicit scope note: forward guardrail only (working tree); does not purge
  git history or GitHub's cached objects.

**CI wiring** — `.github/workflows/ci.yml` gains a `Repo integrity guard` step
that runs `python outclaw_guard.py` on every push/PR to `main`.

**Tests** — `outclaw_tests/test_guard.py` (6 tests): clean-repo pass, clean
temp-tree pass, JSON output, content-leak catch, path-leak catch, and
venv/git skip behavior.

## Verification

- Guard passes on the real tree: `GUARD OK`, exit 0.
- Guard suite: **6 tests, OK**.
- Full test suite: **182 passed, 1 skipped**.

## Notes / caveats

- The guard and its test are the only files that contain the guarded names,
  as fixtures, and are self-skipped by design.
- This is a forward guardrail; it does not replace the git-history rewrite or
  a GitHub Support purge request for cached objects.
