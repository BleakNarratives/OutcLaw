# Receipt — third-party name removal (2026-08-11)

Scope: remove every reference to a third-party product name from the OutClaw
repository — file paths, module names, identifiers, metadata keys, docstrings,
prose, commit messages, and git history. The removed name is not written out
here, by design, so it never reappears even in the receipt.

## What was done

**File renames (via `git mv`):**
- `outclaw_<old>.py` → `outclaw_extraction.py`
- `<old>/` → `extraction_kit/`
- `outclaw_tests/test_<old>_integration.py` → `outclaw_tests/test_extraction_kit.py`

**Identifier / content scrub (152 references across 14 files):**
- Package: → `extraction_kit`
- Module: → `outclaw_extraction`
- Functions: → `extraction_record_audit`; `_extraction_validate_citation_accuracy`;
  `_extraction_validate_facts`; `_extraction_section`
- Metadata key: → `"extraction"`
- Sidecar key: → `extraction`
- Rewrote `extraction_kit/README.md` and `extraction_kit/__init__.py` headers
  clean (no third-party names or source URLs), restoring the full
  public-surface re-exports that `outclaw_extraction.py` depends on.

**Git history rewrite (filter-repo, all branches):**
- Rewrote every commit's blobs, paths, and messages to remove the name.
- `master` history verified clean: zero occurrences in any message or blob.
- A local-only branch (never pushed) still carries the name in its branch
  label; it is local-only and not part of the remote.

## Verification

- Working-tree scan (case-insensitive, excluding the guard and its test which
  hold the name as fixtures by design): **0 hits**.
- Full test suite: **182 passed, 1 skipped**.
- Imports resolve in both direct and `OutClaw.*`-namespace modes; CLI
  `record-audit` runs end to end through the renamed module.

## Guardrail

`outclaw_guard.py` (added this pass) fails the build if any private client
identifier or third-party product name ever reappears in the working tree.
Wired into `.github/workflows/ci.yml` and covered by `test_guard.py`. The guard
and its test are the only files that legitimately hold the removed name (as
fixtures) and are self-skipped.

## Notes / caveats

- This is a **forward guardrail** — it prevents future regressions in the
  working tree. GitHub's own object cache may retain pre-rewrite blobs until
  its garbage collection runs; purging that cache requires a GitHub Support
  request, not a repo-level change.
- Nothing has been force-pushed yet. The rewritten `master` is local; pushing
  it overwrites the old remote history.
