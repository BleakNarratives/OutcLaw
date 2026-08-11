#!/usr/bin/env python3
"""outclaw_extraction.py — OutClaw integration over the vendored ``extraction`` package.

Strategic split (root ``outclaw_round_3.md``):
  * extraction owns the extraction / ingestion layer (vendored in ``./extraction``).
  * OutClaw's differentiation is semantic fraud scoring on top of it.
  * This module wraps the vendored APIs into OutClaw-shaped, JSON-safe
    outputs so the dashboard / orchestrator can consume them.

ADVISORY ONLY — nothing in this module is a legal validation, a filing
authorization, or a draft gate. All outputs are evidence leads for human
review and are explicitly tagged ``advisory: true``. The semantic citation
classifier in ``outclaw_unified`` remains the source of truth for fraud
findings, and the permanent DRAFT block is untouched.

WRAP AND EXTEND (per round 3):
  * ``validate_citation_accuracy`` in the vendored package scores support
    by bag-of-words word overlap. ``semantic_citation_check`` adds the
    model-backed semantic comparison on top: when ``use_llm`` is enabled
    and the cloud cascade is configured, a semantic verdict replaces the
    overlap-only guess; otherwise it falls back to the lexical score.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

# The vendored extraction/ingestion layer (self-contained, MIT).
from extraction import (
    analyze_text_comprehensive,
    build_chronology,
    clear_deposition_store,
    cross_reference_citations,
    detect_factual_contradictions,
    extract_circuit_law,
    extract_judge_patterns,
    extract_record_facts,
    ingest_deposition,
    list_ingested_depositions,
    search_deposition,
    validate_citation_accuracy as _extraction_validate_citation_accuracy,
    validate_facts_against_record as _extraction_validate_facts,
)

_ADVISORY = {"advisory": True, "evidence_leads_only": True}


# ---------------------------------------------------------------------------
# Semantic comparison (WRAP AND EXTEND)
# ---------------------------------------------------------------------------

# Local prompt for the semantic citation-accuracy pass. Kept local so this
# module is self-contained; mirrors the OPPOSITE_HOLDING_PROMPT shape used
# by outclaw_unified's LLM path.
_SEMANTIC_CITATION_PROMPT = """You are a legal reasoning assistant. Determine whether a proposition in a legal filing is SUPPORTED, OPPOSITE, or UNRELATED to a cited authority's actual holding.

CITED AUTHORITY HOLDING:
{holding}

PROPOSITION IN FILING:
{proposition}

Respond with ONLY this JSON (no other text):
{{"verdict": "supported"|"opposite"|"unrelated", "confidence": 0.0_to_1.0, "reasoning": "one sentence explaining why"}}"""


def _lexical_support_score(proposition: str, holding: str) -> float:
    """Bag-of-words overlap mirroring extraction's validate_citation_accuracy.

    Returns a score in [0, 1] over alpha tokens of length >= 4. This is the
    baseline that the semantic (model-backed) pass replaces when enabled.
    """
    import re

    prop = set(re.findall(r"[a-zA-Z]{4,}", proposition.lower()))
    hold = set(re.findall(r"[a-zA-Z]{4,}", holding.lower()))
    if not prop or not hold:
        return 0.0
    return len(prop & hold) / max(len(prop), len(hold))


def _consult_semantic_model(proposition: str, holding: str) -> Optional[dict[str, Any]]:
    """Model-backed semantic verdict via the existing free-cloud cascade.

    Uses the same cascade entry point as outclaw_unified's LLM path. Returns
    None when the cascade is unavailable, disabled, or returns no data — in
    which case the caller falls back to the lexical score.
    """
    try:
        from OutClaw.outclaw_model_cascade import get_cascade  # type: ignore

        cascade = get_cascade()
        if not cascade.enabled:
            return None
        prompt = _SEMANTIC_CITATION_PROMPT.format(
            proposition=proposition[:1500],
            holding=holding[:1500],
        )
        result = cascade.complete(
            prompt,
            task="citation_support",
            min_confidence=0.60,
            max_tokens=300,
        )
        if result.ok and isinstance(result.data, dict):
            return result.data
        return None
    except Exception:
        return None


def semantic_citation_check(
    proposition: str,
    holding: str,
    use_llm: bool = False,
) -> dict[str, Any]:
    """Check whether a proposition is supported by a holding.

    Extends extraction's bag-of-words matching with a model-backed semantic
    comparison when ``use_llm`` is enabled and the cascade is configured.

    Returns (advisory)::

        {
            "advisory": True,
            "lexical_score": 0..1,
            "semantic_backend": "cascade" | "lexical",
            "semantic_verdict": "supported"|"opposite"|"unrelated"|None,
            "confidence": 0..1 | None,
            "reasoning": str | None,
        }
    """
    lexical = round(_lexical_support_score(proposition, holding), 3)
    verdict: Optional[str] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    backend = "lexical"

    if use_llm:
        model = _consult_semantic_model(proposition, holding)
        if model is not None:
            raw = str(model.get("verdict", "")).strip().lower()
            if raw in ("supported", "opposite", "unrelated"):
                verdict = raw
                backend = "cascade"
                confidence = model.get("confidence")
                reasoning = model.get("reasoning")
                # bool is an int subclass; reject it so `"confidence": true`
                # cannot coerce to 1.0.
                if type(confidence) is int or isinstance(confidence, float):
                    confidence = round(float(confidence), 3)

    return {
        **_ADVISORY,
        "lexical_score": lexical,
        "semantic_backend": backend,
        "semantic_verdict": verdict,
        "confidence": confidence,
        "reasoning": reasoning,
    }


# ---------------------------------------------------------------------------
# Text extraction (STEAL DIRECTLY: text_extraction_core)
# ---------------------------------------------------------------------------


def extract_citation_metadata(text: str) -> dict[str, Any]:
    """Comprehensive citation/statute extraction for one document.

    Advisory extraction metadata: counts and normalized lists, no validity
    judgment. The semantic classifier in ``outclaw_unified`` decides what a
    citation actually supports.
    """
    analysis = analyze_text_comprehensive(text)
    citations = [
        {"citation": cite, "pinpoint_cites": data.get("pinpoint_cites", [])}
        for cite, data in analysis.get("citations", {}).items()
    ]
    statutes = [
        {"statute": statute, "occurrences": count}
        for statute, count in analysis.get("statutes", {}).items()
    ]
    return {
        **_ADVISORY,
        "total_citations": analysis.get("total_citations", 0),
        "total_statutes": analysis.get("total_statutes", 0),
        "citations": sorted(citations, key=lambda c: c["citation"]),
        "statutes": sorted(statutes, key=lambda s: s["statute"]),
        "word_count": analysis.get("word_count", 0),
    }


# ---------------------------------------------------------------------------
# Deposition tools (STEAL DIRECTLY: deposition_tools)
# ---------------------------------------------------------------------------


def ingest_deposition_text(
    transcript_text: str,
    witness_name: str,
    deposition_date: Optional[str] = None,
    case_name: Optional[str] = None,
) -> dict[str, Any]:
    """Parse a deposition transcript into Q/A pairs with page:line citations.

    Stores the parsed deposition in the vendored in-memory store so that
    ``validate_facts_against_record`` can check a Statement of Facts against
    it. Advisory ingestion output.
    """
    return ingest_deposition(
        transcript_text,
        witness_name,
        deposition_date=deposition_date,
        case_name=case_name,
    )


def search_deposition_query(
    query: str,
    witness: Optional[str] = None,
    cite_range_start: Optional[str] = None,
    cite_range_end: Optional[str] = None,
    topics: Optional[list[str]] = None,
    include_context: bool = True,
) -> dict[str, Any]:
    """Search ingested deposition testimony by keyword/topic/citation range."""
    return search_deposition(
        query,
        witness=witness,
        cite_range_start=cite_range_start,
        cite_range_end=cite_range_end,
        topics=topics,
        include_context=include_context,
    )


def validate_facts_against_record(
    statement_of_facts: str,
    record_sources: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Check a Statement of Facts against ingested deposition testimony.

    Returns supported / unsupported / contradicted assertions with the
    supporting page:line citations. These are evidence leads for human
    review — never a legal validation.
    """
    return _extraction_validate_facts(statement_of_facts, record_sources)


def list_depositions() -> dict[str, Any]:
    """List depositions currently held in the in-memory store."""
    return list_ingested_depositions()


def reset_deposition_store() -> dict[str, Any]:
    """Clear the in-memory deposition store (tests / new case)."""
    return clear_deposition_store()


# ---------------------------------------------------------------------------
# Record-level analysis (STEAL DIRECTLY: extraction_validation)
# ---------------------------------------------------------------------------


def cross_reference_documents(documents: Mapping[str, str]) -> dict[str, Any]:
    """Cross-reference citations across multiple documents.

    Finds shared authorities, per-document unique citations, and an overlap
    matrix. Advisory; a discrepancy here is a lead, not a finding.
    """
    return cross_reference_citations(dict(documents))


def build_timeline(documents: Mapping[str, str]) -> dict[str, Any]:
    """Build a chronological timeline from dated events in the record."""
    return build_chronology(dict(documents))


def detect_contradictions(documents: Mapping[str, str]) -> dict[str, Any]:
    """Cross-document factual contradiction scan (omission + did/did-not).

    NOTE (round 3): the vendored contradiction patterns are shallow. Treat
    every hit as a lead for human review, not proof of contradiction.
    """
    return detect_factual_contradictions(dict(documents))


def record_facts(record_text: str, document_name: str = "Record") -> dict[str, Any]:
    """Extract legally significant facts, dates, witnesses, and exhibits."""
    return extract_record_facts(record_text, document_name)


def judge_patterns(
    opinions: list[Mapping[str, str]], judge_name: str
) -> dict[str, Any]:
    """Extract reasoning/citation/procedural patterns across a judge's opinions."""
    return extract_judge_patterns(list(opinions), judge_name)


def circuit_law(cases: list[Mapping[str, str]], circuit: str) -> dict[str, Any]:
    """Extract circuit-specific rules, splits, and controlling cases."""
    return extract_circuit_law(list(cases), circuit)


def validate_citation_accuracy(
    brief_text: str,
    case_texts: Optional[Mapping[str, str]] = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    """Validate that a brief's citations support their claimed propositions.

    WRAP AND EXTEND: delegates to the vendored bag-of-words
    ``validate_citation_accuracy``, then — when ``use_llm`` is enabled and
    case text is available — runs the model-backed semantic comparison
    (``semantic_citation_check``) on each case that has source text.

    Output is advisory: LOW_CONFIDENCE flags are review leads, not proof.
    """
    result = _extraction_validate_citation_accuracy(brief_text, dict(case_texts) if case_texts else None)
    result.update(_ADVISORY)

    if use_llm and case_texts:
        extended = 0
        for cite in result.get("citations", []):
            case_name = cite.get("case_name", "")
            case_text = case_texts.get(case_name)
            if not case_text:
                continue
            check = semantic_citation_check(
                cite.get("claimed_proposition", ""), case_text, use_llm=True
            )
            cite["semantic_extension"] = check
            extended += 1
        result["semantic_extended_count"] = extended
    else:
        result["semantic_extended_count"] = 0
    return result


# ---------------------------------------------------------------------------
# Composed record audit (the wiring target for deposition_tools + citations)
# ---------------------------------------------------------------------------


def extraction_record_audit(
    documents: Mapping[str, str],
    statement_of_facts: Optional[str] = None,
    deposition_transcript: Optional[str] = None,
    witness: Optional[str] = None,
    deposition_date: Optional[str] = None,
    case_name: Optional[str] = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    """Run the extraction extraction/ingestion layer over a case record.

    Composes, in order:
      1. Per-document citation/statute extraction.
      2. Cross-document citation cross-referencing.
      3. Chronology from dated events.
      4. Cross-document factual-contradiction scan.
      5. (Optional) deposition ingest + Statement-of-Facts validation against
         the record, with page:line cites — pass the deposition transcript
         via ``deposition_transcript`` and the deponent name via ``witness``.

    Returns a single advisory report. It never changes ``safe_to_draft`` and
    never authorizes filing; it is the extraction/ingestion layer that
    OutClaw's semantic fraud scoring sits on top of.
    """
    docs = dict(documents)
    report: dict[str, Any] = {
        **_ADVISORY,
        "engine": "the vendored extraction layer 1.0.0 (vendored) + outclaw_extraction",
        "documents_processed": list(docs.keys()),
        "per_document_extraction": {
            name: extract_citation_metadata(text) for name, text in docs.items()
        },
        "cross_reference": cross_reference_documents(docs),
        "chronology": build_timeline(docs),
        "contradiction_leads": detect_contradictions(docs),
        "statement_of_facts_validation": None,
        "semantic_checks": {"use_llm": use_llm},
    }

    if statement_of_facts and deposition_transcript:
        # The composed audit owns the in-memory deposition store while it
        # ingests: reset first so a stale deposition from a previous case
        # (same witness name) can never contaminate this SOF validation.
        # Callers managing their own multi-witness store should use the
        # lower-level ingest/search APIs instead of this composition.
        reset_deposition_store()
        deponent = witness or "Deponent"
        ingest_deposition_text(
            deposition_transcript,
            witness_name=deponent,
            deposition_date=deposition_date,
            case_name=case_name,
        )
        report["statement_of_facts_validation"] = _extraction_validate_facts(
            statement_of_facts, [deponent]
        )

    return report
