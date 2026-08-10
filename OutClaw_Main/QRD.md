# OutClaw QRD — Quick Rundown

## Purpose
OutClaw audits legal text and evidence relationships for human review. It is not a lawyer, filing service, or autonomous pleading generator.

## Canonical integration

- `outclaw_validator.py`: legacy evidence-consistency API (`extract_metadata`, `validate_document`).
- `compile_case_docs.py`: batch compiler that writes review packets, audit sidecars, and a manifest.
- `outclaw_safety.py`: human-in-the-loop safety surface and permanent DRAFT block.
- `outclaw_builder.py`: currently absent from the canonical tree.

## Output semantics

- `EVIDENCE MATCH — HUMAN REVIEW REQUIRED` means the legacy validator found a matching evidence reference.
- `BLOCKED — EVIDENCE REVIEW REQUIRED` means no matching evidence was established.
- Neither status authorizes filing or implies legal sufficiency.
- Outputs are written to `~/akasha/court_filings/` by default, or to an explicit test/output directory.

## Guardrails

1. Never invent a pleading from an audit result.
2. Never weaken or bypass the DRAFT block.
3. Preserve source SHA-256 and audit provenance.
4. Treat blocked/nonzero CLI status as an automation stop signal.
5. Review output labels and `WHO_DID_WHAT.md` after every compiler change.
