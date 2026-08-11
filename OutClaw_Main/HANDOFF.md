# OutClaw Project Handoff

**Context:** Criminal defense support for the defendant.
**Goal:** Develop an accessible, one-shot "Case Analysis Dashboard" that ingests multiple legal documents (PDF/TXT), audits them for citation fraud and procedural inconsistencies, and passes findings through the "So Fucking What?" filter.

## Current Status
- **Backend:** Core auditing pipeline (`outclaw_unified`, `orchestrator`) is functional. `pypdf` is installed.
- **Batch compiler:** `compile_case_docs.py` is integrated with the canonical legacy `outclaw_validator.py` evidence-consistency API. It emits review packets, audit sidecars, and a manifest; it does not generate pleadings.
- **Builder status:** `outclaw_builder.py` is absent from the canonical tree. The permanent DRAFT block remains enabled.
- **Validation:** 113 tests pass with 1 skipped; regression suite is 11/11; blocked batches return a nonzero CLI status; transactional compiler CLI smoke passes.
- **Latest local commit:** `3309229` (`feat: publish case review batches transactionally`).
- **Recovery parent:** `758a595` remains the prior native record-review checkpoint and is an ancestor of the latest commit.
- **Repository visibility:** GitHub repository is private; the latest build was not pushed. Secondary recovery manifest: Nat snapshot `snap_2b4de97333ea` for `OutClaw_Main`.
- **Frontend:** Dashboard (`web_app.py`, `index.html`) is running but experiencing `SecurityViolation: Path contains invalid characters` during multi-file ingestion.
- **Architecture:** Transitioning from file-by-file CLI to a multi-agent tiered architecture (Ingestion -> Analysis -> Cross-Reference -> Filter).

## Known Issues (Next Steps for Buffy/Freebuff)
1. **File Ingestion Security:** Dashboard ingestion triggers `SecurityViolation` in `SecureInput.validate_file_path` for multi-file `FormData` uploads. Reproduce and fix only the temporary-upload path contract in `dashboard/security.py`; do not weaken traversal or injection protections.
2. **Aggregate Findings:** Finalize and test the merge logic in `web_app.py` so multiple uploaded files produce one accurate dashboard result.
3. **Validator separation:** Explicitly separate legacy evidence consistency from citation-fraud auditing before adding more validator behavior.
4. **Evidence provenance and disposition:** Add safe source metadata and human-review disposition fields with explicit retention/cleanup rules.
5. **Operational hardening:** The transactional compiler is POSIX-lock based and uses manifest-last publication; add `fsync` or cross-platform locking only if those requirements are accepted.

See `NEXT_BUILD_TODO.md` for the prioritized checklist.

## Protocol for Next Build
- Treat `ROADMAP.md` and `QRD.md` as the current scope boundary.
- Do not call an evidence match legal validation or filing authorization.
- Shift focus to making the dashboard "one-click" portable via the provided Docker setup.
- Prioritize stabilizing the `SecurityViolation` path checks over new feature implementation.
- All analysis must be objective, factual, and strictly aligned with the "So Fucking What?" filter to ensure legal relevance.
