# OutClaw Roadmap

## Current release slice — 2026-08-08

- [x] Confirm the canonical `outclaw_validator.py` integration contract.
- [x] Detect that `outclaw_builder.py` is absent from `OutClaw/OutClaw_Main/`.
- [x] Add `compile_case_docs.py` as a fail-closed batch review-packet compiler.
- [x] Write provenance sidecars and a batch manifest under `~/akasha/court_filings/` by default.
- [x] Preserve the permanent DRAFT block: no unsupervised pleading generation.
- [x] Add focused tests for evidence matches, blocked evidence, missing input, and blocked CLI exit status.
- [x] Use unique same-directory temporary files and paired rollback for output writes.

## Next safe tracks

1. **Validator separation**
   - Decouple legacy evidence consistency from citation-fraud auditing.
   - Keep both APIs explicit; do not silently substitute one for the other.
2. **Transactional batch publication**
   - [x] Add a same-directory staging-directory commit protocol and manifest-last publication.
   - [x] Define recovery behavior for process crashes between renames with a durable recovery journal.
   - [x] Add process locking for concurrent `--force` runs; readers should treat `compile_manifest.json` as the publication marker. The current lock is POSIX-only; retained rollback material may contain duplicate packet text until recovery succeeds, and unjournaled staging/backup directories are left for manual inspection.
3. **Evidence provenance**
   - Add source-file metadata and immutable evidence references without copying sensitive material unnecessarily.
4. **Human review workflow**
   - Add operator annotations and review disposition fields to sidecars.
   - Keep all generated artifacts labeled as review material until a human approves them.
5. **Builder decision**
   - Reassess whether a builder is needed only after the validator and review workflow are stable.
   - Any future builder must remain behind the existing safety gate and human acknowledgment.

## Explicit non-goals

- Do not remove the hard DRAFT block.
- Do not call evidence matches legal validation or filing authorization.
- Do not write directly to court e-filing systems.
- Do not modify quarantine or unrelated project trees as part of this roadmap.
