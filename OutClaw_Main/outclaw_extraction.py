#!/usr/bin/env python3
"""outclaw_extraction.py — OutClaw integration over the vendored ``extraction_kit`` package.

Strategic split (root ``outclaw_round_3.md``):
  * extraction owns the extraction / ingestion layer (vendored in ``./extraction_kit``).
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

import re
from typing import Any, Mapping, Optional

# The vendored extraction/ingestion layer (self-contained, MIT).
from extraction_kit import (
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
    """Bag-of-words overlap mirroring the extraction layer's validate_citation_accuracy.

    Returns a score in [0, 1] over alpha tokens of length >= 4. This is the
    baseline that the semantic (model-backed) pass replaces when enabled.
    """
    import re

    prop = set(re.findall(r"[a-zA-Z]{4,}", proposition.lower()))
    hold = set(re.findall(r"[a-zA-Z]{4,}", holding.lower()))
    if not prop or not hold:
        return 0.0
    return len(prop & hold) / max(len(prop), len(hold))


def semantic_cascade_status() -> dict[str, Any]:
    """Report whether the model-backed cascade is configured/enabled.

    No network calls — inspects the cascade config the same way the
    semantic path does, so an operator can see why a run fell back to
    lexical scoring before they spend time on a report.
    """
    try:
        from OutClaw.outclaw_model_cascade import get_cascade  # type: ignore

        cascade = get_cascade()
        return {
            **_ADVISORY,
            "backend": "cascade",
            "enabled": bool(cascade.enabled),
        }
    except Exception:
        return {**_ADVISORY, "backend": "cascade", "enabled": False}


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

    Extends the extraction layer's bag-of-words matching with a model-backed semantic
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
                if isinstance(confidence, bool):
                    confidence = None
                elif type(confidence) is int or isinstance(confidence, float):
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


# ---------------------------------------------------------------------------
# Deep factual-contradiction scan (WRAP AND EXTEND, round 3)
# ---------------------------------------------------------------------------

# Content-word filters used to anchor the same "event" across documents.
_DEEP_STOP = frozenset(
    """the a an at on in of to and or for with was were had has have he she it
    they his her their that this from by as be been is are did do does not no
    there about around approximately roughly said stated according per then
    when where what who whom which""".split()
)
_APPROX_WORDS = {"about", "around", "approximately", "roughly", "approx", "circa"}

# Word-boundary negation patterns (never "never" inside "nevertheless").
_NEGATION_PATTERNS = (
    r"\bdid not\b", r"\bdidn't\b", r"\bwas not\b", r"\bwasn't\b",
    r"\bwere not\b", r"\bweren't\b", r"\bnever\b", r"\bno evidence\b",
    r"\bunable to\b", r"\brefused to\b", r"\bdenied that\b",
)
_NEGATION_RE = re.compile("|".join(_NEGATION_PATTERNS), re.IGNORECASE)

_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+\d{4}\b|"
    r"\b\d{1,2}/\d{1,2}/\d{4}\b"
)
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)?\b")
_AMOUNT_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s*"
    r"(?:years?|months?|weeks?|days?|hours?|miles?|feet?|pounds?|"
    r"dollars?|percent|%)\b"
)
_ENTITY_RE = re.compile(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")

# Capitalized words that are never entities (sentence starters, months,
# generic nouns) — keeps shared-entity anchoring honest.
_ENTITY_JUNK = frozenset(
    """The On At In A An It He She They We This That Court However But
    January February March April May June July August September October
    November December Incident Report Officer Detective State""".split()
)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}
_AMOUNT_UNITS = {
    "year": "years", "years": "years", "month": "months", "months": "months",
    "week": "weeks", "weeks": "weeks", "day": "days", "days": "days",
    "hour": "hours", "hours": "hours", "mile": "miles", "miles": "miles",
    "foot": "feet", "feet": "feet", "pound": "pounds", "pounds": "pounds",
    "dollar": "dollars", "dollars": "dollars", "percent": "percent", "%": "percent",
}

# Amount-context nouns: when two sentences name the same monetary subject
# ("the settlement", "the payment", "the award"), the amounts are comparable
# even without a capitalized proper-noun entity.
_AMOUNT_CONTEXT_WORDS = frozenset(
    """settlement payment award damages fee fine bail salary wage cost price
    bond judgment restitution compensation penalty expense amount total sum
    """.split()
)

# Common deposition/record action verbs (base + inflected). Time/amount/date
# conflicts must share one of these so "arrived at 8" vs "left at 9" (same
# person, different events) are not reported as a contradiction.
_VERB_WORDS = frozenset(
    """arrive arrived arrives leave left leaves depart departed departs
    return returned returns attend attended attends testify testified
    testifies state stated states admit admitted admits receive received
    receives pay paid pays send sent sends call called calls file filed
    files enter entered enters exit exited exits start started starts end
    ended ends begin began begun occur occurred occurs happen happened
    happens see saw seen hear heard hears sign signed signs visit visited
    visits purchase purchased purchases sell sold sells meet met meets
    appear appeared appears remain remained remains stay stayed stays
    walk walked walks run ran runs drive drove drives show showed shows
    bring brought brings take took takes give gave gives make made makes
    """.split()
)


def _deep_sentences(text: str) -> list[str]:
    """Split text into sentences on sentence boundaries."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 15]


def _normalize_date(raw: str) -> Optional[str]:
    """Canonicalize a date to YYYY-MM-DD so equivalent formats compare equal."""
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        raw,
        re.IGNORECASE,
    )
    if m:
        month_name, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        return f"{year:04d}-{_MONTHS[month_name]:02d}-{day:02d}"
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    return raw


def _normalize_time(raw: str) -> Optional[str]:
    """Canonicalize a clock time to HH:MM (24h) so 8:00 a.m. == 8:00 am."""
    m = re.search(r"(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)?", raw, re.IGNORECASE)
    if not m:
        return raw
    hour, minute = int(m.group(1)), int(m.group(2))
    meridiem = (m.group(3) or "").lower().replace(".", "")
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _normalize_amount(raw: str) -> Optional[str]:
    """Canonicalize an amount to 'VALUE|UNIT' so $5,000 == $5000.00."""
    m = re.search(r"\$\s?([\d,]+(?:\.\d+)?)", raw)
    if m:
        value = m.group(1).replace(",", "")
        return f"{float(value):.2f}|currency"
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(\w+|%)", raw)
    if m:
        value = m.group(1).replace(",", "")
        unit = _AMOUNT_UNITS.get(m.group(2).lower(), m.group(2).lower())
        return f"{float(value):.2f}|{unit}"
    return raw


def _deep_fact_vector(sentence: str) -> dict[str, Any]:
    """Extract an event-anchor vector from one sentence (deterministic).

    Returns entities (capitalized runs, junk filtered), canonicalized
    date/time/amount, the negation flag, and the content-word set used to
    anchor "same event" comparisons across documents.
    """
    raw_entities = re.findall(_ENTITY_RE, sentence)
    entities = sorted({
        e for e in raw_entities
        if e.split()[0] not in _ENTITY_JUNK and e.lower() not in _DEEP_STOP
    })
    date_m = re.search(_DATE_RE, sentence)
    time_m = re.search(_TIME_RE, sentence)
    amount_m = re.search(_AMOUNT_RE, sentence)
    lowered = sentence.lower()
    approx = any(w in lowered for w in _APPROX_WORDS)
    content = {
        w for w in re.findall(r"[a-z]{4,}", lowered) if w not in _DEEP_STOP
    }
    return {
        "sentence": sentence,
        "entities": entities,
        "date": _normalize_date(date_m.group(0)) if date_m else None,
        "time": _normalize_time(time_m.group(0)) if time_m else None,
        "amount": _normalize_amount(amount_m.group(0)) if amount_m else None,
        "approximate": approx,
        "negated": bool(_NEGATION_RE.search(lowered)),
        "content": content,
        "action": content & _VERB_WORDS,
        "amount_context": content & _AMOUNT_CONTEXT_WORDS,
    }


def _same_event(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Anchor two facts to the same event: shared entity AND either a shared
    date or >=2 shared content words (excluding the shared entity names)."""
    shared_ents = set(a["entities"]) & set(b["entities"])
    if not shared_ents:
        # Amount-bearing sentences may name the same monetary subject with
        # no proper noun ("the settlement was $5,000") — a shared
        # amount-context noun is a valid anchor on its own.
        if a["amount"] and b["amount"]:
            return bool(a["amount_context"] & b["amount_context"])
        return False
    shared_content = a["content"] & b["content"]
    if a["date"] and b["date"]:
        return a["date"] == b["date"] or bool(shared_content)
    # Amount-bearing sentences often share only a context noun ("settlement",
    # "payment") — one shared word plus a shared entity is enough to anchor.
    if a["amount"] and b["amount"] and shared_content:
        return True
    return len(shared_content) >= 2


def _shared_action(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Require a shared action verb so 'arrived at 8' vs 'left at 9'
    (same person, different events) are not reported as a contradiction."""
    return bool(a["action"] & b["action"])


def _shared_word(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Looser anchor for amount conflicts: any shared content word (the
    context noun like "settlement"/"payment") is sufficient."""
    return bool(a["content"] & b["content"])


def deep_contradiction_scan(documents: Mapping[str, str]) -> dict[str, Any]:
    """Deterministic deep factual-contradiction scan (WRAP AND EXTEND).

    Complements the vendored did/did-not scan with concrete, reviewable
    conflict leads:
      * date conflicts  — same anchored event, different dates
      * time conflicts  — same anchored event, different times
      * amount conflicts — same anchored event, different amounts
      * negation conflicts — same anchored event, one side negated

    Values are canonicalized before comparison (8:00 a.m. == 8:00 am,
    $5,000 == $5,000.00, January 15, 2024 == 1/15/2024), negation is
    word-boundary matched ("never" does not match "nevertheless"), and
    time/amount/date leads require a shared action word so unrelated
    events involving the same person are not conflated. Approximate values
    ("around 8:00 a.m.") never conflict with exact ones. Output is
    strictly advisory; every lead is a pointer for a human to check, never
    proof of contradiction.
    """
    docs = dict(documents)
    names = list(docs.keys())
    leads: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for i, name_a in enumerate(names):
        facts_a = [_deep_fact_vector(s) for s in _deep_sentences(docs[name_a])]
        for name_b in names[i + 1:]:
            facts_b = [_deep_fact_vector(s) for s in _deep_sentences(docs[name_b])]
            for fa in facts_a:
                for fb in facts_b:
                    if not _same_event(fa, fb):
                        continue
                    shared_ents = sorted(set(fa["entities"]) & set(fb["entities"]))
                    # Negation conflict: same event, opposite polarity.
                    if fa["negated"] != fb["negated"]:
                        key = ("negation", fa["sentence"], fb["sentence"])
                        if key not in seen:
                            seen.add(key)
                            leads.append({
                                "type": "negation_conflict",
                                "shared_entities": shared_ents[:5],
                                "source_a": name_a,
                                "fact_a": fa["sentence"][:300],
                                "source_b": name_b,
                                "fact_b": fb["sentence"][:300],
                                "note": "one document asserts the fact, the other negates it",
                            })
                    # Date conflict: same event, different dates.
                    if (
                        fa["date"] and fb["date"] and fa["date"] != fb["date"]
                        and _shared_action(fa, fb)
                    ):
                        key = ("date", fa["date"], fb["date"])
                        if key not in seen:
                            seen.add(key)
                            leads.append({
                                "type": "date_conflict",
                                "shared_entities": shared_ents[:5],
                                "source_a": name_a,
                                "fact_a": fa["sentence"][:300],
                                "source_b": name_b,
                                "fact_b": fb["sentence"][:300],
                                "date_a": fa["date"],
                                "date_b": fb["date"],
                                "note": "the same anchored event is dated differently",
                            })
                    # Time conflict: same event, different exact times.
                    if (
                        fa["time"] and fb["time"] and fa["time"] != fb["time"]
                        and not fa["approximate"] and not fb["approximate"]
                        and _shared_action(fa, fb)
                    ):
                        key = ("time", fa["time"], fb["time"])
                        if key not in seen:
                            seen.add(key)
                            leads.append({
                                "type": "time_conflict",
                                "shared_entities": shared_ents[:5],
                                "source_a": name_a,
                                "fact_a": fa["sentence"][:300],
                                "source_b": name_b,
                                "fact_b": fb["sentence"][:300],
                                "time_a": fa["time"],
                                "time_b": fb["time"],
                                "note": "the same anchored event is timed differently",
                            })
                    # Amount conflict: same event, different amounts. Uses
                    # the looser shared-word anchor (context nouns like
                    # "settlement" carry no verb, so verb-anchoring would
                    # miss them).
                    if (
                        fa["amount"] and fb["amount"] and fa["amount"] != fb["amount"]
                        and not fa["approximate"] and not fb["approximate"]
                        and _shared_word(fa, fb)
                    ):
                        key = ("amount", fa["amount"], fb["amount"])
                        if key not in seen:
                            seen.add(key)
                            leads.append({
                                "type": "amount_conflict",
                                "shared_entities": shared_ents[:5],
                                "source_a": name_a,
                                "fact_a": fa["sentence"][:300],
                                "source_b": name_b,
                                "fact_b": fb["sentence"][:300],
                                "amount_a": fa["amount"],
                                "amount_b": fb["amount"],
                                "note": "the same anchored event reports different amounts",
                            })

    order = {"negation_conflict": 0, "date_conflict": 1, "time_conflict": 2, "amount_conflict": 3}
    leads.sort(key=lambda lead: (order.get(lead["type"], 9), lead["source_a"], lead["source_b"]))
    return {
        **_ADVISORY,
        "scan": "outclaw-deep-factual-v1",
        "documents_analyzed": names,
        "total_leads": len(leads),
        "leads": leads[:50],
    }


def detect_contradictions(documents: Mapping[str, str]) -> dict[str, Any]:
    """Cross-document factual contradiction scan.

    Composes the vendored shallow scan (omission + did/did-not) with the
    round-3 deep scan (date/time/amount/negation leads). Every hit is a
    lead for human review, never proof of contradiction.
    """
    shallow = detect_factual_contradictions(dict(documents))
    deep = deep_contradiction_scan(documents)
    shallow["deep_scan"] = deep
    return shallow


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
    """Run the extraction/ingestion layer over a case record.

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
        "engine": "the vendored extraction layer (vendored) + outclaw_extraction",
        "documents_processed": list(docs.keys()),
        "per_document_extraction": {
            name: extract_citation_metadata(text) for name, text in docs.items()
        },
        "cross_reference": cross_reference_documents(docs),
        "chronology": build_timeline(docs),
        "contradiction_leads": detect_contradictions(docs),
        "statement_of_facts_validation": None,
        "semantic_checks": {
            "use_llm": use_llm,
            "cascade_status": semantic_cascade_status(),
        },
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
