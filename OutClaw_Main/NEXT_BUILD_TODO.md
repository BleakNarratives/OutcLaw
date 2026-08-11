# OutClaw Next-Build Todo

Active work list — updated 2026-08-11 after the round-3 completion pass
(deep contradiction scan + semantic cascade path validation; suite now
**159 passed, 1 skipped**).

## Completed and checked off

- [x] Local recovery branch and checkpoint preserved.
- [x] Repository made private; no code push performed.
- [x] Native record-review extraction added without third-party runtime branding.
- [x] Advisory `extraction_metadata` kept separate from semantic findings and the hard DRAFT gate.
- [x] Fail-closed batch review compiler added.
- [x] Review packets, audit sidecars, and manifest added.
- [x] Transactional batch publication added:
  - [x] same-directory staging;
  - [x] manifest-last publication marker;
  - [x] POSIX process lock;
  - [x] recovery journal;
  - [x] all-or-nothing validation failure behavior;
  - [x] conservative cleanup and rollback tests.
- [x] Validation completed for the latest build: 113 tests passed, 1 skipped, 11/11 regression cases, CLI smoke passed.
- [x] Latest build was committed locally; it was not pushed to GitHub.

## extraction integration — DONE (2026-08-11, branch agent/extraction-integration-20260811)

- [x] Vendored the vendored extraction layer core modules into `extraction_kit/` (MIT, self-contained; provenance in `extraction_kit/README.md`)
- [x] Applied one documented regex fix: reporter class widened to accept digits (F.3d-style citations now match)
- [x] Added `outclaw_extraction.py` integration layer (citation extraction, deposition ingest + SOF validation, cross-reference, chronology, contradiction leads, semantic citation check)
- [x] Wired advisory `extraction_metadata["extraction"]` into `outclaw_unified.audit_text` — does not touch `safe_to_draft`
- [x] Added `outclaw_tests/test_extraction_integration.py` (25 tests); full suite 138 passed, 1 skipped
- [x] Utility surfaces: `record-audit` CLI subcommand (outclaw_cli.py) + advisory `extraction` in compile_case_docs audit sidecars (fail-closed)
- [x] Uninstalled `the vendored extraction layer` from the system — vendored `extraction_kit/` is the only copy

## Round-3 completion — DONE (2026-08-11)

- [x] Enabled/validated the model-backed semantic path: `semantic_citation_check` is exercised end-to-end with a faked cascade (enabled → semantic verdict; disabled/failing/unrecognized → lexical fallback; bool confidence rejected). Real cascade keys activate it at runtime (`OUTCLAW_CASCADE=1` + any provider key); `semantic_cascade_status()` reports availability without network calls.
- [x] Deepened `detect_factual_contradictions` beyond did/did-not: `deep_contradiction_scan` adds deterministic date/time/amount/negation conflict leads, composes under `detect_contradictions`, stays advisory, and is covered by 11 tests.

## Repo integrity guard — DONE (2026-08-11)

- [x] Added `outclaw_guard.py`: fails the build (exit 1) if any private client
      identifier or third-party product name ever reappears in the working
      tree. Scans file contents + paths, case-insensitive; skips
      `.git`/venv/site-packages/`__pycache__` and binary/oversized files (ext +
      2MB cap) for speed (~0.3s on full repo). Self-skips its own file and its
      test file (which use the identifiers as fixtures). Forward guardrail only
      — does not purge git history/remote cache (that stays a separate
      destructive step).
- [x] Wired into `.github/workflows/ci.yml` as a `Repo integrity guard` step.
- [x] Added `outclaw_tests/test_guard.py` (6 tests): clean repo pass, clean
      temp tree, content-leak catch, path-leak catch, venv-skip, JSON output.
      Full suite now **182 passed, 1 skipped** (was 176).

## Priority 1 — stabilize dashboard ingestion

- [ ] Reproduce the known multi-file `SecurityViolation: Path contains invalid characters` failure.
- [ ] Trace the browser-upload path through `dashboard/web_app.py` and `dashboard/security.py`.
- [ ] Accept only server-created temporary upload paths; continue rejecting traversal, shell metacharacters, control characters, and arbitrary filesystem paths.
- [ ] Add tests for one upload, multiple uploads, traversal attempts, and malformed paths.
- [ ] Verify multi-file findings aggregate correctly before rendering.

## Priority 2 — separate validator responsibilities

- [ ] Document the exact boundary between legacy evidence consistency and citation-fraud auditing.
- [ ] Give each API explicit names and result fields; do not silently substitute one validator for another.
- [ ] Add contract tests for both APIs, including disagreement cases.
- [ ] Preserve the wording: evidence matches are leads for human review, not legal validation or filing authorization.

## Priority 3 — improve evidence provenance safely

- [ ] Add source path, size, modification time, and SHA-256 metadata where appropriate.
- [ ] Use immutable evidence references instead of unnecessary raw-text duplication.
- [ ] Define retention and explicit cleanup for source-derived packets, staging directories, and failed recovery material.
- [ ] Avoid adding raw case material, credentials, databases, or generated artifacts to Git.

## Priority 4 — add human review disposition

- [ ] Add operator annotation fields to audit sidecars.
- [ ] Add disposition values such as `unreviewed`, `confirmed`, `rejected`, and `needs-attorney-review`.
- [ ] Record reviewer/time metadata without claiming legal approval.
- [ ] Keep every artifact clearly labeled as human-review material.

## Priority 5 — release hardening

- [ ] Review disclaimer wording in README, dashboard guide, runbook, and output packets.
- [ ] Run a repository-wide secret/raw-evidence audit before any publication decision.
- [ ] Add `fsync` crash durability only if power-loss recovery is required.
- [ ] Add a Windows/Termux locking strategy only if those platforms are actually supported.
- [ ] Keep GitHub repository private until tests and disclaimers are accepted.

## Priority 6 — jurisdiction-aware trial-prep curriculum (product vision)

North star: make OutClaw THE go-to tool for pro se litigants — everything a
self-represented person needs to prepare for trial, not just audit documents.
Foundation for this already exists on disk (`jurisdiction.py` state detection,
`outclaw_objections_engine.py`, `outclaw_irac.py`); the course/guide content
system does not. Build it in this order:

- [ ] Design the jurisdiction curriculum registry: per-jurisdiction
      (KS/OK/MO/CO/NE/TX/CA…) prep tracks keyed off `jurisdiction.py` detection,
      with the trial-prep topics below as reusable lesson modules.
- [ ] Trial prep track: oral argument structure and practice scripts;
      opening statements; closing arguments; direct and cross-examination
      questioning plans; deposition prep (questioning strategy, not just
      ingest/search).
- [ ] Wire the objections engine into the questioning module so practice
      sessions surface live objections with the correct rule basis.
- [ ] Add a pro-se checklist per track (evidence admission, hearsay
      exceptions, impeachment, jury selection) with jurisdiction-specific
      caveats flagged as advisory, never as legal advice.
- [ ] Surface the curriculum in `record-audit`/CLI and the dashboard as
      an advisory "prep pack" alongside the audit output.

## Fixed constraints — locked

- [x] Do not remove or bypass the permanent DRAFT safety gate.
- [x] Do not generate unsupervised pleadings.
- [x] Do not write directly to court e-filing systems.
- [x] Do not call evidence matches legal validation.
- [x] Do not modify quarantine or unrelated project trees.
