# OutClaw Roadmap

## Round-3 completion slice — 2026-08-11

- [x] Deepened `detect_factual_contradictions` beyond the shallow
      did/did-not patterns (`deep_contradiction_scan`: date, time, amount,
      and negation conflicts; deterministic, no API keys; composes under
      `detect_contradictions` and `extraction_record_audit`).
- [x] Validated the model-backed semantic cascade path
      (`semantic_citation_check`) with faked-cascade tests covering
      enabled / disabled / failing / unrecognized-verdict behavior and
      bool-confidence rejection.
- [x] Added `semantic_cascade_status()` (config-only availability probe)
      and surfaced it in `extraction_record_audit.semantic_checks`.
- [x] Deep scan hardened post-review: canonicalized value comparison
      (8:00 a.m. == 8:00 am, $5,000 == $5,000.00), word-boundary negation
      ("never" ≠ "nevertheless"), shared-action-verb anchoring for
      time/date conflicts, and amount-context-noun anchoring.
- [x] Suite at **159 passed, 1 skipped, exit 0** (was 138).

## Current release slice — 2026-08-08

- [x] Confirm the canonical `outclaw_validator.py` integration contract.
- [x] Detect that `outclaw_builder.py` is absent from `OutClaw/OutClaw_Main/`.
- [x] Add `compile_case_docs.py` as a fail-closed batch review-packet compiler.
- [x] Write provenance sidecars and a batch manifest under `~/akasha/court_filings/` by default.
- [x] Preserve the permanent DRAFT block: no unsupervised pleading generation.
- [x] Add focused tests for evidence matches, blocked evidence, missing input, and blocked CLI exit status.
- [x] Use unique same-directory temporary files and paired rollback for output writes.

## Completed next-safe track

- [x] **Transactional batch publication** — implemented in `compile_case_docs.py` and committed as `3309229`.
  - [x] Same-directory staging and manifest-last publication.
  - [x] Durable recovery journal for interrupted replacements.
  - [x] POSIX process locking for concurrent `--force` runs.
  - [x] All-or-nothing batch behavior on validation errors.
  - [x] Recovery and conservative-cleanup tests.

## Next safe tracks

1. **Validator separation**
   - Decouple legacy evidence consistency from citation-fraud auditing.
   - Keep both APIs explicit; do not silently substitute one for the other.

2. **Evidence provenance**
   - Add source-file metadata and immutable evidence references without copying sensitive material unnecessarily.
   - Define retention and cleanup behavior for source-derived artifacts.

3. **Human review workflow**
   - Add operator annotations and review disposition fields to sidecars.
   - Keep all generated artifacts labeled as review material until a human approves them.

4. **Dashboard ingestion stabilization**
   - Reproduce the multi-file `SecurityViolation` path issue in `dashboard/security.py`.
   - Correct temporary-upload path handling without weakening traversal/injection protections.
   - Add multi-file aggregation tests in `web_app.py` and dashboard tests.

5. **Operational hardening**
   - Add crash-durability `fsync` behavior if power-loss recovery becomes a requirement.
   - Add cross-platform locking if Windows/Termux support is required; current batch locking is POSIX-only.
   - Keep the repository private until testing and disclaimers are reviewed.

6. **Builder decision**
   - Reassess whether a builder is needed only after validator separation and review workflow stability.
   - Any future builder must remain behind the existing safety gate and human acknowledgment.

## Explicit non-goals

- Do not remove the hard DRAFT block.
- Do not call evidence matches legal validation or filing authorization.
- Do not write directly to court e-filing systems.
- Do not modify quarantine or unrelated project trees as part of this roadmap.
