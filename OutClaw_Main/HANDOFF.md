# OutClaw Project Handoff

**Context:** Criminal defense support for the defendant.
**Goal:** Develop an accessible, one-shot "Case Analysis Dashboard" that ingests multiple legal documents (PDF/TXT), audits them for citation fraud and procedural inconsistencies, and passes findings through the "So Fucking What?" filter.

## Current Status
- **Backend:** Core auditing pipeline (`outclaw_unified`, `orchestrator`) is functional. `pypdf` is installed.
- **Batch compiler:** `compile_case_docs.py` is integrated with the canonical legacy `outclaw_validator.py` evidence-consistency API. It emits review packets, audit sidecars, and a manifest; it does not generate pleadings.
- **Builder status:** `outclaw_builder.py` is absent from the canonical tree. The permanent DRAFT block remains enabled.
- **Validation:** Focused compiler and orchestrator tests pass. Blocked batches return a nonzero CLI status.
- **Frontend:** Dashboard (`web_app.py`, `index.html`) is running but experiencing `SecurityViolation: Path contains invalid characters` during multi-file ingestion.
- **Architecture:** Transitioning from file-by-file CLI to a multi-agent tiered architecture (Ingestion -> Analysis -> Cross-Reference -> Filter).

## Known Issues (Next Steps for Buffy/Freebuff)
1. **File Ingestion Security:** Dashboard ingestion triggers `SecurityViolation` in `SecureInput.validate_file_path` for multi-file `FormData` uploads. Need to relax or better sanitize path handling in `dashboard/security.py` for temporary uploaded files.
2. **Path Sanitization:** The validation layer is too strict for browser-uploaded temporary files.
3. **Aggregate Aggregation:** Need to finalize the merge logic in `web_app.py` to correctly consolidate findings from multiple files before rendering in the dashboard.

## Protocol for Next Build
- Treat `ROADMAP.md` and `QRD.md` as the current scope boundary.
- Do not call an evidence match legal validation or filing authorization.
- Shift focus to making the dashboard "one-click" portable via the provided Docker setup.
- Prioritize stabilizing the `SecurityViolation` path checks over new feature implementation.
- All analysis must be objective, factual, and strictly aligned with the "So Fucking What?" filter to ensure legal relevance.
