# OutClaw Next-Build Todo

This is the active work list after commit `3309229` (`feat: publish case review batches transactionally`).

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

## Fixed constraints — locked

- [x] Do not remove or bypass the permanent DRAFT safety gate.
- [x] Do not generate unsupervised pleadings.
- [x] Do not write directly to court e-filing systems.
- [x] Do not call evidence matches legal validation.
- [x] Do not modify quarantine or unrelated project trees.
