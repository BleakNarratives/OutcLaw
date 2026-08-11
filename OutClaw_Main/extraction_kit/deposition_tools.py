# Vendored into OutClaw from the vendored extraction layer (MIT License)
# Copied verbatim into the OutClaw tree (2026-08-11) so the
# extraction/ingestion layer is self-contained and portable.
# See extraction_kit/README.md for provenance and OutClaw wrap points.

"""
Deposition Processing Tools - Parse, search, and validate deposition transcripts.

This module provides functionality to:
1. Ingest deposition transcripts and extract Q/A pairs with page:line citations
2. Search ingested depositions by keyword, witness, citation range, or topic
3. Validate Statement of Facts against the deposition record
"""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

# Import ExtractionMeta from extraction_validation (vendored sibling)
try:
    from .extraction_validation import ExtractionMeta, build_extraction_meta
except ImportError:
    # Fallback for standalone testing
    @dataclass
    class ExtractionMeta:
        extraction_complete: bool
        targets_found: List[str]
        targets_missing: List[str]
        confidence_scores: Dict[str, float]
        suggestions: List[str]

        def to_dict(self) -> Dict[str, Any]:
            return {
                "extraction_complete": self.extraction_complete,
                "targets_found": self.targets_found,
                "targets_missing": self.targets_missing,
                "confidence_scores": self.confidence_scores,
                "suggestions": self.suggestions
            }

    def build_extraction_meta(found, missing, confidence, suggestions=None):
        return ExtractionMeta(
            extraction_complete=len(missing) == 0,
            targets_found=found,
            targets_missing=missing,
            confidence_scores=confidence,
            suggestions=suggestions or []
        )


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class DepositionEntry:
    """A single Q/A exchange in a deposition."""
    id: int
    question: str
    answer: str
    cite_start: str      # "45:10" (page:line)
    cite_end: str        # "45:15"
    full_cite: str       # "Smith Dep. 45:10-15"
    examiner: Optional[str] = None
    topics: List[str] = field(default_factory=list)
    objections: List[str] = field(default_factory=list)


@dataclass
class DepositionData:
    """Full deposition data with searchable index."""
    witness: str
    deposition_date: Optional[str] = None
    case_name: Optional[str] = None
    total_pages: int = 0
    testimony: List[DepositionEntry] = field(default_factory=list)
    topics_index: Dict[str, List[int]] = field(default_factory=dict)
    ingested_at: str = ""


# In-memory storage for ingested depositions
_DEPOSITION_STORE: Dict[str, DepositionData] = {}


# ============================================================================
# TOPIC KEYWORDS
# ============================================================================

TOPIC_KEYWORDS = {
    "timeline": [
        "when", "what time", "what date", "before", "after", "during",
        "how long", "minutes", "hours", "days", "weeks", "months", "years",
        "morning", "afternoon", "evening", "night", "o'clock", "a.m.", "p.m."
    ],
    "knowledge": [
        "know", "aware", "understand", "realize", "learn", "discover",
        "told", "informed", "heard", "saw", "notice", "recognize", "familiar"
    ],
    "actions": [
        "did", "do", "done", "took", "went", "came", "made", "gave",
        "said", "told", "called", "sent", "received", "signed", "wrote"
    ],
    "documents": [
        "document", "email", "letter", "memo", "report", "record",
        "exhibit", "contract", "agreement", "policy", "form", "file"
    ],
    "communications": [
        "conversation", "discuss", "meeting", "call", "phone", "email",
        "text", "message", "spoke", "talked", "communicated", "contact"
    ],
    "injuries": [
        "injury", "injured", "hurt", "pain", "damage", "harm", "suffer",
        "medical", "doctor", "hospital", "treatment", "diagnosis", "surgery"
    ],
    "employment": [
        "job", "work", "employ", "position", "title", "duty", "duties",
        "supervisor", "manager", "colleague", "coworker", "company", "hired", "fired"
    ],
    "training": [
        "train", "training", "taught", "learn", "instruction", "certif",
        "course", "class", "education", "experience", "qualified"
    ]
}


# ============================================================================
# CORE FUNCTIONS
# ============================================================================

def ingest_deposition(
    transcript_text: str,
    witness_name: str,
    deposition_date: Optional[str] = None,
    case_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Parse deposition transcript and extract Q/A pairs with page:line citations.

    Args:
        transcript_text: Full text of deposition transcript
        witness_name: Name of the deponent
        deposition_date: Date of deposition (optional)
        case_name: Case name for citation formatting (optional)

    Returns:
        Dict with _meta and ingestion results
    """
    targets_found = []
    targets_missing = []
    confidence_scores = {}
    suggestions = []

    # Initialize deposition data
    depo = DepositionData(
        witness=witness_name,
        deposition_date=deposition_date,
        case_name=case_name,
        ingested_at=datetime.now().isoformat(),
        topics_index={topic: [] for topic in TOPIC_KEYWORDS.keys()}
    )

    # Parse transcript
    entries, parse_stats = _parse_transcript(transcript_text, witness_name)
    depo.testimony = entries
    depo.total_pages = parse_stats.get("max_page", 0)

    # Build topic index
    for entry in entries:
        detected_topics = _detect_topics(entry.question + " " + entry.answer)
        entry.topics = detected_topics
        for topic in detected_topics:
            if topic in depo.topics_index:
                depo.topics_index[topic].append(entry.id)

    # Store in memory
    store_key = _normalize_witness_name(witness_name)
    _DEPOSITION_STORE[store_key] = depo

    # Build meta
    if entries:
        targets_found.append(f"Q/A pairs: {len(entries)}")
        targets_found.append(f"Pages: {depo.total_pages}")
        confidence_scores["parsing"] = min(1.0, len(entries) / 50)  # Higher confidence with more entries
    else:
        targets_missing.append("Q/A pairs")
        suggestions.append("Check transcript format - expected Q. and A. markers")
        confidence_scores["parsing"] = 0.0

    if parse_stats.get("objections_found", 0) > 0:
        targets_found.append(f"Objections: {parse_stats['objections_found']}")

    # Topic coverage
    topics_with_content = [t for t, ids in depo.topics_index.items() if ids]
    if topics_with_content:
        targets_found.append(f"Topics indexed: {', '.join(topics_with_content[:5])}")
        confidence_scores["topics"] = len(topics_with_content) / len(TOPIC_KEYWORDS)

    meta = build_extraction_meta(
        found=targets_found,
        missing=targets_missing,
        confidence=confidence_scores,
        suggestions=suggestions
    )

    return {
        "_meta": meta.to_dict(),
        "result": {
            "witness": witness_name,
            "store_key": store_key,
            "total_entries": len(entries),
            "total_pages": depo.total_pages,
            "topics_indexed": {t: len(ids) for t, ids in depo.topics_index.items() if ids},
            "sample_entries": [asdict(e) for e in entries[:3]] if entries else [],
            "parse_stats": parse_stats
        }
    }


def _parse_transcript(text: str, witness_name: str) -> Tuple[List[DepositionEntry], Dict]:
    """Parse transcript text into Q/A entries with citations."""
    entries = []
    stats = {
        "lines_processed": 0,
        "qa_pairs_found": 0,
        "objections_found": 0,
        "max_page": 0
    }

    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')
    stats["lines_processed"] = len(lines)

    current_page = 1
    current_line = 1
    current_question = None
    question_start = None
    current_answer = None
    answer_start = None
    current_objections = []
    entry_id = 0

    # Page detection patterns
    page_patterns = [
        r'^(?:Page\s+)?(\d+)\s*$',           # "Page 45" or just "45" on its own line
        r'^\s*(\d+)\s*$',                     # Just a number (common page marker)
        r'\[Page\s*(\d+)\]',                  # [Page 45]
        r'^\s*-\s*(\d+)\s*-\s*$',            # - 45 -
    ]

    # Line number pattern (often at start of line)
    line_num_pattern = r'^\s*(\d{1,2})\s+'

    for raw_line in lines:
        line = raw_line.strip()

        # Check for page markers
        for pattern in page_patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                page_num = int(match.group(1))
                if 1 <= page_num <= 9999:  # Sanity check
                    current_page = page_num
                    current_line = 1
                    stats["max_page"] = max(stats["max_page"], current_page)
                break

        # Check for line numbers at start
        line_match = re.match(line_num_pattern, line)
        if line_match:
            try:
                current_line = int(line_match.group(1))
                line = line[line_match.end():].strip()
            except ValueError:
                pass

        # Check for objections
        if re.search(r'\b(OBJECTION|Object|MR\.|MS\.|MRS\.)\b.*:', line, re.IGNORECASE):
            obj_match = re.search(r'(OBJECTION[^.]*\.)', line, re.IGNORECASE)
            if obj_match:
                current_objections.append(obj_match.group(1))
                stats["objections_found"] += 1

        # Check for Q/A markers
        q_match = re.match(r'^Q[\.\:]?\s*(.*)$', line, re.IGNORECASE)
        a_match = re.match(r'^A[\.\:]?\s*(.*)$', line, re.IGNORECASE)

        if q_match:
            # Save previous Q/A pair if exists
            if current_question and current_answer:
                entry = _create_entry(
                    entry_id, current_question, current_answer,
                    question_start, (current_page, current_line),
                    witness_name, current_objections
                )
                entries.append(entry)
                entry_id += 1
                stats["qa_pairs_found"] += 1
                current_objections = []

            current_question = q_match.group(1).strip()
            question_start = (current_page, current_line)
            current_answer = None
            answer_start = None

        elif a_match:
            if current_question:  # Only capture answer if we have a question
                current_answer = a_match.group(1).strip()
                answer_start = (current_page, current_line)

        else:
            # Continuation of previous Q or A
            if current_answer is not None:
                current_answer += " " + line
            elif current_question is not None:
                current_question += " " + line

        current_line += 1

    # Don't forget last Q/A pair
    if current_question and current_answer:
        entry = _create_entry(
            entry_id, current_question, current_answer,
            question_start, (current_page, current_line),
            witness_name, current_objections
        )
        entries.append(entry)
        stats["qa_pairs_found"] += 1

    return entries, stats


def _create_entry(
    entry_id: int,
    question: str,
    answer: str,
    q_start: Tuple[int, int],
    a_end: Tuple[int, int],
    witness_name: str,
    objections: List[str]
) -> DepositionEntry:
    """Create a DepositionEntry with proper citation formatting."""
    cite_start = f"{q_start[0]}:{q_start[1]}"
    cite_end = f"{a_end[0]}:{a_end[1]}"

    # Format full citation
    short_name = _get_short_witness_name(witness_name)
    if q_start[0] == a_end[0]:
        full_cite = f"{short_name} Dep. {q_start[0]}:{q_start[1]}-{a_end[1]}"
    else:
        full_cite = f"{short_name} Dep. {cite_start}-{cite_end}"

    return DepositionEntry(
        id=entry_id,
        question=question.strip(),
        answer=answer.strip(),
        cite_start=cite_start,
        cite_end=cite_end,
        full_cite=full_cite,
        objections=objections
    )


def _get_short_witness_name(name: str) -> str:
    """Get short form of witness name for citations."""
    parts = name.split()
    if len(parts) >= 2:
        return parts[-1]  # Last name
    return name


def _normalize_witness_name(name: str) -> str:
    """Normalize witness name for storage key."""
    return name.lower().replace(" ", "_").replace(".", "")


def _detect_topics(text: str) -> List[str]:
    """Detect topics present in text."""
    text_lower = text.lower()
    detected = []

    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                detected.append(topic)
                break

    return detected


# ============================================================================
# SEARCH FUNCTION
# ============================================================================

def search_deposition(
    query: str,
    witness: Optional[str] = None,
    cite_range_start: Optional[str] = None,
    cite_range_end: Optional[str] = None,
    topics: Optional[List[str]] = None,
    include_context: bool = True
) -> Dict[str, Any]:
    """
    Search ingested depositions for matching testimony.

    Args:
        query: Search text (required)
        witness: Filter by witness name (searches all if not specified)
        cite_range_start: Start of citation range (e.g., "45:1")
        cite_range_end: End of citation range (e.g., "50:25")
        topics: Filter by detected topics
        include_context: Include surrounding Q/A pairs

    Returns:
        Dict with _meta and search results
    """
    targets_found = []
    targets_missing = []
    confidence_scores = {}
    suggestions = []

    if not _DEPOSITION_STORE:
        return {
            "_meta": build_extraction_meta(
                found=[],
                missing=["depositions"],
                confidence={"search": 0.0},
                suggestions=["No depositions ingested. Use ingest_deposition first."]
            ).to_dict(),
            "results": []
        }

    # Determine which depositions to search
    depos_to_search = {}
    if witness:
        key = _normalize_witness_name(witness)
        if key in _DEPOSITION_STORE:
            depos_to_search[key] = _DEPOSITION_STORE[key]
        else:
            suggestions.append(f"Witness '{witness}' not found. Available: {list(_DEPOSITION_STORE.keys())}")
    else:
        depos_to_search = _DEPOSITION_STORE

    # Parse citation range
    range_start_parsed = _parse_cite(cite_range_start) if cite_range_start else None
    range_end_parsed = _parse_cite(cite_range_end) if cite_range_end else None

    # Search
    results = []
    query_lower = query.lower()
    query_terms = query_lower.split()

    for witness_key, depo in depos_to_search.items():
        for entry in depo.testimony:
            # Check citation range
            if range_start_parsed or range_end_parsed:
                entry_start = _parse_cite(entry.cite_start)
                if range_start_parsed and entry_start < range_start_parsed:
                    continue
                if range_end_parsed and entry_start > range_end_parsed:
                    continue

            # Check topics filter
            if topics:
                if not any(t in entry.topics for t in topics):
                    continue

            # Check query match
            combined_text = (entry.question + " " + entry.answer).lower()

            # Score based on term matches
            match_count = sum(1 for term in query_terms if term in combined_text)
            if match_count == 0:
                continue

            relevance = match_count / len(query_terms)

            result_entry = {
                "witness": depo.witness,
                "entry_id": entry.id,
                "question": entry.question,
                "answer": entry.answer,
                "citation": entry.full_cite,
                "topics": entry.topics,
                "relevance": round(relevance, 2),
                "objections": entry.objections
            }

            # Add context if requested
            if include_context:
                context = _get_context(depo.testimony, entry.id)
                if context:
                    result_entry["context"] = context

            results.append(result_entry)

    # Sort by relevance
    results.sort(key=lambda x: x["relevance"], reverse=True)

    # Build meta
    if results:
        targets_found.append(f"Matches: {len(results)}")
        confidence_scores["search"] = min(1.0, results[0]["relevance"] if results else 0.0)
    else:
        targets_missing.append("matching testimony")
        suggestions.append("Try broader search terms or different topics")
        confidence_scores["search"] = 0.0

    meta = build_extraction_meta(
        found=targets_found,
        missing=targets_missing,
        confidence=confidence_scores,
        suggestions=suggestions
    )

    return {
        "_meta": meta.to_dict(),
        "results": results[:50]  # Limit results
    }


def _parse_cite(cite: str) -> Tuple[int, int]:
    """Parse citation string like '45:10' into (page, line) tuple."""
    if not cite:
        return (0, 0)
    parts = cite.split(":")
    try:
        page = int(parts[0])
        line = int(parts[1]) if len(parts) > 1 else 0
        return (page, line)
    except (ValueError, IndexError):
        return (0, 0)


def _get_context(testimony: List[DepositionEntry], entry_id: int, context_size: int = 1) -> List[Dict]:
    """Get surrounding Q/A pairs for context."""
    context = []
    for entry in testimony:
        if abs(entry.id - entry_id) <= context_size and entry.id != entry_id:
            context.append({
                "id": entry.id,
                "question": entry.question[:100] + "..." if len(entry.question) > 100 else entry.question,
                "answer": entry.answer[:100] + "..." if len(entry.answer) > 100 else entry.answer,
                "citation": entry.full_cite,
                "position": "before" if entry.id < entry_id else "after"
            })
    return context


# ============================================================================
# VALIDATION FUNCTION
# ============================================================================

def validate_facts_against_record(
    statement_of_facts: str,
    record_sources: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Check Statement of Facts against ingested deposition database.

    Args:
        statement_of_facts: Text of Statement of Facts section
        record_sources: Optional list of witness names to check against

    Returns:
        Dict with _meta and validation results
    """
    targets_found = []
    targets_missing = []
    confidence_scores = {}
    suggestions = []

    if not _DEPOSITION_STORE:
        return {
            "_meta": build_extraction_meta(
                found=[],
                missing=["record"],
                confidence={"validation": 0.0},
                suggestions=["No depositions ingested. Use ingest_deposition first."]
            ).to_dict(),
            "validation": {
                "supported": [],
                "unsupported": [],
                "contradicted": [],
                "coverage": 0.0
            }
        }

    # Determine which depositions to check
    if record_sources:
        depos = {_normalize_witness_name(w): _DEPOSITION_STORE.get(_normalize_witness_name(w))
                 for w in record_sources if _normalize_witness_name(w) in _DEPOSITION_STORE}
    else:
        depos = _DEPOSITION_STORE

    # Extract factual assertions from SOF
    assertions = _extract_assertions(statement_of_facts)

    if not assertions:
        targets_missing.append("factual assertions")
        suggestions.append("Statement of Facts appears empty or couldn't be parsed")
        return {
            "_meta": build_extraction_meta(
                found=[],
                missing=targets_missing,
                confidence={"validation": 0.0},
                suggestions=suggestions
            ).to_dict(),
            "validation": {
                "supported": [],
                "unsupported": [],
                "contradicted": [],
                "coverage": 0.0
            }
        }

    # Validate each assertion
    supported = []
    unsupported = []
    contradicted = []

    for assertion in assertions:
        validation = _validate_assertion(assertion, depos)

        if validation["status"] == "SUPPORTED":
            supported.append(validation)
        elif validation["status"] == "CONTRADICTED":
            contradicted.append(validation)
        else:
            unsupported.append(validation)

    # Calculate coverage
    total = len(assertions)
    coverage = len(supported) / total if total > 0 else 0.0

    # Build meta
    targets_found.append(f"Assertions analyzed: {total}")
    targets_found.append(f"Supported: {len(supported)}")
    if unsupported:
        targets_missing.append(f"Citations needed: {len(unsupported)}")
    if contradicted:
        targets_missing.append(f"Contradictions: {len(contradicted)}")
        suggestions.append("Review contradicted facts - testimony conflicts with assertions")

    confidence_scores["validation"] = coverage
    confidence_scores["coverage"] = coverage

    meta = build_extraction_meta(
        found=targets_found,
        missing=targets_missing,
        confidence=confidence_scores,
        suggestions=suggestions
    )

    return {
        "_meta": meta.to_dict(),
        "validation": {
            "total_assertions": total,
            "supported": supported,
            "unsupported": unsupported,
            "contradicted": contradicted,
            "coverage": round(coverage, 2),
            "witnesses_checked": list(depos.keys())
        }
    }


def _extract_assertions(text: str) -> List[Dict[str, str]]:
    """Extract factual assertions from Statement of Facts."""
    assertions = []

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence or len(sentence) < 10:
            continue

        # Skip citation-only sentences
        if re.match(r'^\s*\([^)]+\)\s*$', sentence):
            continue

        # Extract existing citation if present
        existing_cite = None
        cite_match = re.search(r'\(([^)]+(?:Dep\.|Ex\.|Aff\.)[^)]*)\)', sentence)
        if cite_match:
            existing_cite = cite_match.group(1)

        # Clean sentence for matching
        clean = re.sub(r'\([^)]+\)', '', sentence).strip()

        if clean and len(clean) > 10:
            assertions.append({
                "id": i,
                "text": clean,
                "original": sentence,
                "existing_cite": existing_cite
            })

    return assertions


def _validate_assertion(assertion: Dict, depos: Dict[str, DepositionData]) -> Dict[str, Any]:
    """Validate a single assertion against deposition testimony."""
    assertion_text = assertion["text"].lower()

    # Extract key terms for matching
    key_terms = _extract_key_terms(assertion_text)

    best_match = None
    best_score = 0.0
    contradicting_testimony = None

    for witness_key, depo in depos.items():
        for entry in depo.testimony:
            combined = (entry.question + " " + entry.answer).lower()

            # Score based on term overlap
            matches = sum(1 for term in key_terms if term in combined)
            score = matches / len(key_terms) if key_terms else 0.0

            if score > best_score:
                best_score = score
                best_match = {
                    "witness": depo.witness,
                    "citation": entry.full_cite,
                    "question": entry.question[:150],
                    "answer": entry.answer[:200],
                    "match_score": round(score, 2)
                }

            # Check for contradiction
            if score > 0.3:  # Related testimony
                if _check_contradiction(assertion_text, combined):
                    contradicting_testimony = {
                        "witness": depo.witness,
                        "citation": entry.full_cite,
                        "testimony": entry.answer[:200],
                        "conflict_type": "potential_contradiction"
                    }

    # Determine status
    if contradicting_testimony:
        return {
            "status": "CONTRADICTED",
            "assertion": assertion["text"],
            "original": assertion["original"],
            "contradiction": contradicting_testimony,
            "existing_cite": assertion.get("existing_cite")
        }
    elif best_match and best_score >= 0.4:
        return {
            "status": "SUPPORTED",
            "assertion": assertion["text"],
            "original": assertion["original"],
            "support": best_match,
            "existing_cite": assertion.get("existing_cite")
        }
    else:
        return {
            "status": "UNSUPPORTED",
            "assertion": assertion["text"],
            "original": assertion["original"],
            "best_match": best_match if best_match and best_score > 0.2 else None,
            "existing_cite": assertion.get("existing_cite"),
            "suggestion": "NEED CITE" if not assertion.get("existing_cite") else "Verify citation"
        }


def _extract_key_terms(text: str) -> List[str]:
    """Extract key terms for matching, excluding common words."""
    stop_words = {
        "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "must", "shall",
        "this", "that", "these", "those", "i", "you", "he", "she", "it",
        "we", "they", "what", "which", "who", "whom", "when", "where",
        "why", "how", "all", "each", "every", "both", "few", "more", "most",
        "other", "some", "such", "no", "not", "only", "own", "same", "than",
        "too", "very", "just", "also", "now", "then", "so", "if", "as", "at",
        "by", "for", "from", "in", "into", "of", "on", "to", "with"
    }

    # Extract words
    words = re.findall(r'\b[a-z]+\b', text.lower())

    # Filter
    key_terms = [w for w in words if w not in stop_words and len(w) > 2]

    return key_terms[:15]  # Limit to top terms


def _check_contradiction(assertion: str, testimony: str) -> bool:
    """Check if testimony contradicts assertion."""
    # Look for negation patterns
    negation_patterns = [
        (r'\bdid not\b', r'\bdid\b'),
        (r'\bnever\b', r'\balways\b'),
        (r'\bno\b', r'\byes\b'),
        (r'\bwas not\b', r'\bwas\b'),
        (r'\bnot present\b', r'\bpresent\b'),
        (r'\bdenied\b', r'\badmitted\b'),
    ]

    for neg, pos in negation_patterns:
        if re.search(neg, testimony) and re.search(pos, assertion):
            return True
        if re.search(pos, testimony) and re.search(neg, assertion):
            return True

    return False


# ============================================================================
# MCP WRAPPER FUNCTIONS
# ============================================================================

def ingest_deposition_mcp(
    transcript_text: str,
    witness_name: str,
    deposition_date: Optional[str] = None,
    case_name: Optional[str] = None
) -> str:
    """MCP wrapper for ingest_deposition with formatted output."""
    result = ingest_deposition(transcript_text, witness_name, deposition_date, case_name)

    output = []
    output.append("=" * 70)
    output.append("DEPOSITION INGESTION COMPLETE")
    output.append("=" * 70)

    # Extraction report
    meta = result.get("_meta", {})
    output.append("\nEXTRACTION REPORT")
    output.append("-" * 40)

    for item in meta.get("targets_found", []):
        output.append(f"  [OK] {item}")
    for item in meta.get("targets_missing", []):
        output.append(f"  [X] {item}")

    for suggestion in meta.get("suggestions", []):
        output.append(f"  >> {suggestion}")

    # Result summary
    data = result.get("result", {})
    output.append(f"\nWitness: {data.get('witness', 'Unknown')}")
    output.append(f"Store Key: {data.get('store_key', 'N/A')}")
    output.append(f"Q/A Pairs: {data.get('total_entries', 0)}")
    output.append(f"Pages: {data.get('total_pages', 0)}")

    # Topics indexed
    topics = data.get("topics_indexed", {})
    if topics:
        output.append("\nTopics Indexed:")
        for topic, count in sorted(topics.items(), key=lambda x: x[1], reverse=True):
            output.append(f"  - {topic}: {count} entries")

    # Sample entries
    samples = data.get("sample_entries", [])
    if samples:
        output.append("\nSample Entries:")
        for entry in samples[:2]:
            output.append(f"\n  [{entry.get('full_cite', 'N/A')}]")
            output.append(f"  Q: {entry.get('question', '')[:80]}...")
            output.append(f"  A: {entry.get('answer', '')[:80]}...")

    # JSON
    output.append("\n" + "=" * 70)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2, default=str))

    return "\n".join(output)


def search_deposition_mcp(
    query: str,
    witness: Optional[str] = None,
    cite_range_start: Optional[str] = None,
    cite_range_end: Optional[str] = None,
    topics: Optional[List[str]] = None,
    include_context: bool = True
) -> str:
    """MCP wrapper for search_deposition with formatted output."""
    result = search_deposition(query, witness, cite_range_start, cite_range_end, topics, include_context)

    output = []
    output.append("=" * 70)
    output.append("DEPOSITION SEARCH RESULTS")
    output.append("=" * 70)

    # Search parameters
    output.append(f"\nQuery: \"{query}\"")
    if witness:
        output.append(f"Witness: {witness}")
    if cite_range_start or cite_range_end:
        output.append(f"Citation Range: {cite_range_start or 'start'} to {cite_range_end or 'end'}")
    if topics:
        output.append(f"Topics: {', '.join(topics)}")

    # Extraction report
    meta = result.get("_meta", {})
    output.append("\n" + "-" * 40)
    for item in meta.get("targets_found", []):
        output.append(f"  [OK] {item}")
    for item in meta.get("targets_missing", []):
        output.append(f"  [X] {item}")
    for suggestion in meta.get("suggestions", []):
        output.append(f"  >> {suggestion}")

    # Results
    results = result.get("results", [])
    if results:
        output.append(f"\n--- TOP MATCHES ({len(results)} total) ---")
        for i, r in enumerate(results[:10], 1):
            output.append(f"\n{i}. [{r.get('citation', 'N/A')}] (relevance: {r.get('relevance', 0)})")
            output.append(f"   Q: {r.get('question', '')[:100]}")
            output.append(f"   A: {r.get('answer', '')[:150]}")
            if r.get("topics"):
                output.append(f"   Topics: {', '.join(r.get('topics', []))}")
    else:
        output.append("\nNo matching testimony found.")

    # JSON
    output.append("\n" + "=" * 70)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2, default=str))

    return "\n".join(output)


def validate_facts_against_record_mcp(
    statement_of_facts: str,
    record_sources: Optional[List[str]] = None
) -> str:
    """MCP wrapper for validate_facts_against_record with formatted output."""
    result = validate_facts_against_record(statement_of_facts, record_sources)

    output = []
    output.append("=" * 70)
    output.append("RECORD VALIDATION REPORT")
    output.append("=" * 70)

    validation = result.get("validation", {})

    # Summary
    total = validation.get("total_assertions", 0)
    supported = validation.get("supported", [])
    unsupported = validation.get("unsupported", [])
    contradicted = validation.get("contradicted", [])
    coverage = validation.get("coverage", 0)

    output.append(f"\nTotal Assertions: {total}")
    output.append(f"Coverage: {coverage * 100:.0f}%")
    output.append(f"Witnesses Checked: {', '.join(validation.get('witnesses_checked', []))}")

    # Status breakdown
    output.append(f"\n  [OK] SUPPORTED: {len(supported)}")
    output.append(f"  [?]  UNSUPPORTED: {len(unsupported)}")
    output.append(f"  [!]  CONTRADICTED: {len(contradicted)}")

    # Supported facts
    if supported:
        output.append("\n--- SUPPORTED ---")
        for item in supported[:10]:
            assertion = item.get("assertion", "")[:80]
            support = item.get("support", {})
            cite = support.get("citation", "N/A")
            output.append(f'  "{assertion}" -> {cite}')

    # Unsupported facts
    if unsupported:
        output.append("\n--- UNSUPPORTED (NEED CITE) ---")
        for item in unsupported[:10]:
            assertion = item.get("assertion", "")[:80]
            suggestion = item.get("suggestion", "NEED CITE")
            output.append(f'  "{assertion}" -> [{suggestion}]')

    # Contradicted facts
    if contradicted:
        output.append("\n--- CONTRADICTED (CHECK!) ---")
        for item in contradicted:
            assertion = item.get("assertion", "")[:60]
            contradiction = item.get("contradiction", {})
            cite = contradiction.get("citation", "N/A")
            output.append(f'  "{assertion}"')
            output.append(f'    CONFLICTS WITH: {cite}')
            output.append(f'    Testimony: "{contradiction.get("testimony", "")[:80]}..."')

    # Extraction report
    meta = result.get("_meta", {})
    output.append("\n" + "-" * 40)
    for item in meta.get("targets_found", []):
        output.append(f"  [OK] {item}")
    for item in meta.get("targets_missing", []):
        output.append(f"  [X] {item}")
    for suggestion in meta.get("suggestions", []):
        output.append(f"  >> {suggestion}")

    # JSON
    output.append("\n" + "=" * 70)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2, default=str))

    return "\n".join(output)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def list_ingested_depositions() -> Dict[str, Any]:
    """List all currently ingested depositions."""
    return {
        "depositions": [
            {
                "key": key,
                "witness": depo.witness,
                "entries": len(depo.testimony),
                "pages": depo.total_pages,
                "ingested_at": depo.ingested_at
            }
            for key, depo in _DEPOSITION_STORE.items()
        ],
        "total": len(_DEPOSITION_STORE)
    }


def clear_deposition_store():
    """Clear all ingested depositions."""
    global _DEPOSITION_STORE
    _DEPOSITION_STORE = {}
    return {"status": "cleared", "message": "All depositions removed from memory"}


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    # Test with sample transcript
    sample_transcript = """
    Page 1

    1  Q. Please state your name for the record.
    2  A. My name is John Smith.
    3  Q. And where do you work, Mr. Smith?
    4  A. I work at ABC Corporation as a manager.
    5  Q. How long have you been employed there?
    6  A. About five years now.

    Page 2

    1  Q. Do you recall the events of January 15, 2024?
    2  A. Yes, I remember that day clearly.
    3  Q. What happened that morning?
    4  A. I arrived at work around 8:00 a.m. and went
    5  straight to my office. Around 9:30, I heard a
    6  loud noise from the warehouse.
    7  Q. What did you do then?
    8  A. I immediately went to investigate.
    """

    print("Testing ingest_deposition...")
    result = ingest_deposition_mcp(sample_transcript, "John Smith", "2024-03-15", "Doe v. ABC Corp")
    print(result[:1000])

    print("\n\nTesting search_deposition...")
    search_result = search_deposition_mcp("warehouse noise", witness="John Smith")
    print(search_result[:1000])

    print("\n\nTesting validate_facts...")
    sof = """
    On January 15, 2024, John Smith arrived at work at approximately 8:00 a.m.
    He went directly to his office. At approximately 9:30 a.m., Smith heard a
    loud noise coming from the warehouse area. Smith has been employed at ABC
    Corporation for approximately five years.
    """
    validation = validate_facts_against_record_mcp(sof)
    print(validation[:1500])
