"""
extraction — vendored extraction Legal extraction/ingestion layer for OutClaw.

This package is a verbatim copy of the three core modules from
``the vendored extraction layer`` 1.0.0 (MIT License, source: daltonjsawyer-png/extraction),
so OutClaw's extraction/ingestion layer is self-contained and portable
(no dependency on a user-level site-packages install).

Strategic split (see root ``outclaw_round_3.md``):
  * extraction owns the extraction / ingestion layer.
  * OutClaw's differentiation is semantic fraud scoring on top of it —
    the semantic citation classifier in ``outclaw_unified`` stays the
    source of truth for fraud findings. Everything in this package is
    extraction output: evidence leads for human review, never a filing
    authorization or a draft gate.

Public surface (keep this list explicit — do not star-import):
"""

from .text_extraction_core import (
    extract_citations_from_text,
    extract_statutes_from_text,
    search_keywords_in_text,
    analyze_text_comprehensive,
    normalize_citation,
    is_valid_citation,
    format_citations_output,
    format_statutes_output,
)

from .deposition_tools import (
    ingest_deposition,
    search_deposition,
    validate_facts_against_record,
    list_ingested_depositions,
    clear_deposition_store,
    DepositionEntry,
    DepositionData,
)

from .extraction_validation import (
    ExtractionMeta,
    build_extraction_meta,
    validate_citation_accuracy,
    extract_record_facts,
    map_facts_to_elements,
    detect_factual_contradictions,
    extract_procedural_context,
    extract_reasoning_patterns,
    extract_judge_patterns,
    extract_circuit_law,
    build_chronology,
    validate_pleading_elements,
    cross_reference_citations,
    verify_citations,
)

__version__ = "1.0.0-vendored"
__all__ = [
    # text extraction core
    "extract_citations_from_text",
    "extract_statutes_from_text",
    "search_keywords_in_text",
    "analyze_text_comprehensive",
    "normalize_citation",
    "is_valid_citation",
    "format_citations_output",
    "format_statutes_output",
    # deposition tools
    "ingest_deposition",
    "search_deposition",
    "validate_facts_against_record",
    "list_ingested_depositions",
    "clear_deposition_store",
    "DepositionEntry",
    "DepositionData",
    # extraction validation
    "ExtractionMeta",
    "build_extraction_meta",
    "validate_citation_accuracy",
    "extract_record_facts",
    "map_facts_to_elements",
    "detect_factual_contradictions",
    "extract_procedural_context",
    "extract_reasoning_patterns",
    "extract_judge_patterns",
    "extract_circuit_law",
    "build_chronology",
    "validate_pleading_elements",
    "cross_reference_citations",
    "verify_citations",
]
