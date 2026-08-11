# extraction (vendored) — provenance & wrap points

This package is **not** an OutClaw original. It is a verbatim copy of the
three core extraction modules from **the vendored extraction layer 1.0.0** (MIT License).

| File | Source | Lines | Role |
|---|---|---|---|
| `text_extraction_core.py` | the vendored extraction layer 1.0.0 | 321 | Citation/statute regex extraction (federal, state, regional reporters) |
| `deposition_tools.py` | the vendored extraction layer 1.0.0 | 1078 | Deposition transcript ingest, search, and Statement-of-Facts validation |
| `extraction_validation.py` | the vendored extraction layer 1.0.0 | 4269 | Record facts, chronology, cross-referencing, citation accuracy |

- **Upstream:** https://github.com/daltonjsawyer-png/extraction
- **Installed from pip:** `the vendored extraction layer==1.0.0` on 2026-08-11
- **License:** MIT (retained in each file header)
- **Vendoring reason:** `import extraction_legal` fails (flat wheel, no package
  `__init__.py`), the site-packages copy is user-level and non-portable, and
  OutClaw ships to Docker. Stealing the code directly per the round-3 plan
  makes the extraction layer self-contained.

### Upstream integrity (the vendored extraction layer 1.0.0, installed 2026-08-11)

Base64 SHA-256 hashes from `site-packages/extraction_legal-1.0.0.dist-info/RECORD`
for the three vendored files. The copies in this tree differ from upstream by
**exactly one** documented functional change (the reporter-class digit fix
below) plus the attribution header and intra-package import fixes.

| File | Upstream sha256 (base64) |
|---|---|
| `text_extraction_core.py` | `sctYVRAT1HmfBDJs9ib_p_s6Ako-oWJRY89brgbfNvM` |
| `deposition_tools.py` | `TjEgvkRMF2GlU0luXvWrqAB8xoLU_GFYkSiGjpbSeuo` |
| `extraction_validation.py` | `sEgbbBQOln_ojyT7NgTnjRzHDN0h5AZQblczDQb3FsU` |

## OutClaw wrap points (see `../outclaw_extraction.py`)

Per the strategic split in the root `outclaw_round_3.md`:

- **STEAL DIRECTLY:** `text_extraction_core.py`, `deposition_tools.py`,
  and the extraction functions in `extraction_validation.py`
  (`extract_judge_patterns`, `extract_circuit_law`, `build_chronology`,
  `cross_reference_citations`).
- **WRAP AND EXTEND:** `validate_citation_accuracy` (matching is
  bag-of-words word overlap — `outclaw_extraction.semantic_citation_check`
  adds the model-backed semantic pass on top) and
  `detect_factual_contradictions` (omission/loop detection kept; shallow
  did/did-not contradiction patterns are flagged as leads, not proof).
- **SKIP (not vendored):** `study_aids`, `legal_templates`, `writing_style`,
  `irac_synthesis`, `web_app`.

## Known limitations & applied fixes

### Applied fix (2026-08-11) — reporter class accepts digits

Upstream reporter capture ``[A-Za-z\.\s]+`` excluded digits, so it could
never match ``F.3d`` / ``F.2d`` / ``F. Supp. 2d`` — ``cross_reference_citations``
and the citation-accuracy patterns missed nearly every federal citation.
Widened to ``[A-Za-z0-9\.\s]+`` in ``validate_citation_accuracy``,
``extract_judge_patterns``, and ``cross_reference_citations`` (5 sites, marked
in-file). This is the only functional change to the vendored files.

- ``cross_reference_citations``/``verify_citations`` case-name regex treats
  any sentence lead-in before ``v.`` as part of the case name (e.g. "This
  argument relies on Smith v. Jones" parses the case as "This argument
  relies on Smith"). Inline citations therefore fragment authority names;
  citation-leading sentences extract reliably. Output is advisory leads, and
  OutClaw's own ``CITATION_RE`` (outclaw_unified) is the fraud-finding source.
- ``validate_citation_accuracy`` support scoring is bag-of-words overlap;
  ``outclaw_extraction.semantic_citation_check`` adds the model-backed pass.
- ``detect_factual_contradictions`` did/did-not patterns are shallow — treat
  hits as leads, not proof.

## Guardrails

1. Everything produced here is **extraction output / evidence leads** for
   human review. It is never a legal validation, filing authorization, or
   draft gate.
2. OutClaw's semantic citation classifier (`outclaw_unified`) remains the
   source of truth for fraud findings.
3. The hard DRAFT block is untouched.
4. Vendor diffs are minimal by design: only the attribution header and the
   intra-package import fixes needed to make the copy self-contained.
