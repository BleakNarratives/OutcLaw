# extraction_kit (vendored) — provenance & wrap points

This package is **not** an OutClaw original. It is a verbatim copy of three
self-contained extraction modules (MIT License) vendored into OutClaw so the
extraction/ingestion layer ships with the project rather than depending on a
user-level site-packages install.

| File | Lines | Role |
|---|---|---|
| `text_extraction_core.py` | 321 | Citation/statute regex extraction (federal, state, regional reporters) |
| `deposition_tools.py` | 1078 | Deposition transcript ingest, search, and Statement-of-Facts validation |
| `extraction_validation.py` | 4269 | Record facts, chronology, cross-referencing, citation accuracy |

- **License:** MIT (retained in each file header)
- **Vendoring reason:** the upstream wheel is flat (no package `__init__.py`),
  the site-packages copy is user-level and non-portable, and OutClaw ships to
  Docker. Vendoring makes the extraction layer self-contained.

## OutClaw wrap points (see `../outclaw_extraction.py`)

Per the strategic split in the root `outclaw_round_3.md`:

- **STEAL DIRECTLY:** `text_extraction_core.py`, `deposition_tools.py`,
  and the extraction functions in `extraction_validation.py`
  (`extract_judge_patterns`, `extract_circuit_law`, `build_chronology`,
  `cross_reference_citations`).
- **WRAP AND EXTEND:** `validate_citation_accuracy` and
  `validate_facts_against_record` are wrapped by `outclaw_extraction.py`.
  `outclaw_extraction.semantic_citation_check` adds the model-backed pass.

## Known limits

- The vendored case-name regex greedily treats any sentence lead-in before
  "v." as part of the case name, so citations should lead the sentence for
  reliable case-name extraction.
