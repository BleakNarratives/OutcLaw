"""Local record-review helpers for OutClaw.

This module is intentionally extraction-only. It produces citation/statute
metadata and multi-document review leads; the semantic citation classifier and
DRAFT safety gate remain in ``outclaw_unified`` and are not replaced here.

The implementation is standard-library-only and does not persist source text,
call a network service, or generate legal prose.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any, Mapping


_CITATION_PATTERNS = (
    r"\b\d{1,3}\s+U\.?\s*S\.?\s+\d{1,4}\b",
    r"\b\d{1,3}\s+S\.?\s*Ct\.?\s+\d{1,4}\b",
    r"\b\d{1,3}\s+F\.?\s*(?:2d|3d|4th|Supp\.?\s*2d|App'?x)\s+\d{1,4}\b",
    r"\b\d{1,3}\s+[A-Z][A-Za-z.]{1,8}\s+(?:2d|3d|4th)?\s*\d{1,4}\b",
)
_STATUTE_PATTERNS = (
    r"\b\d+\s+U\.?\s*S\.?\s*C\.?\s*(?:§|Sec(?:tion)?\.?)\s*[\w.-]+(?:\([\w-]+\))*",
    r"\b\d+\s+C\.?\s*F\.?\s*R\.?\s*(?:§|Sec(?:tion)?\.?)\s*[\w.-]+(?:\([\w-]+\))*",
)
_CITATION_RE = re.compile("|".join(_CITATION_PATTERNS))
_STATUTE_RE = re.compile("|".join(_STATUTE_PATTERNS), re.IGNORECASE)
_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b"
    r"|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"\b[a-z][a-z'-]{2,}\b", re.IGNORECASE)
_NEGATION_RE = re.compile(r"\b(?:not|never|no|denied|didn't|wasn't|weren't)\b", re.IGNORECASE)
_COMMON_FACT_WORDS = {
    "about", "after", "before", "being", "does", "from", "have", "into",
    "more", "only", "other", "record", "same", "some", "statement", "that",
    "the", "their", "then", "there", "these", "they", "this", "were", "with",
}


def _normalize(value: str) -> str:
    return " ".join(value.split()).strip(" ,.;:")


def extract_text_metadata(text: str) -> dict[str, Any]:
    """Return broad citation/statute/date metadata without judging validity."""
    citations = [_normalize(match.group(0)) for match in _CITATION_RE.finditer(text)]
    statutes = [_normalize(match.group(0)) for match in _STATUTE_RE.finditer(text)]
    dates = [_normalize(match.group(0)) for match in _DATE_RE.finditer(text)]
    return {
        "status": "ok",
        "citation_count": len(citations),
        "statute_count": len(statutes),
        "date_count": len(dates),
        "citations": dict(Counter(citations)),
        "statutes": dict(Counter(statutes)),
        "dates": dates,
    }


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _entities(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if len(token) > 3 and token.lower() not in _COMMON_FACT_WORDS
    }


def review_records(documents: Mapping[str, str]) -> dict[str, Any]:
    """Return chronology, citation overlap, and conservative contradiction leads."""
    normalized = {str(name): str(text) for name, text in documents.items()}
    chronology: list[dict[str, str]] = []
    fact_rows: list[tuple[str, str, set[str], bool]] = []
    for source, text in normalized.items():
        for sentence in _sentences(text):
            dates = _DATE_RE.findall(sentence)
            if dates:
                chronology.append(
                    {"date": _normalize(dates[0]), "source": source, "event": sentence}
                )
            fact_rows.append((source, sentence, _entities(sentence), bool(_NEGATION_RE.search(sentence))))

    contradictions: list[dict[str, str]] = []
    for index, (source_a, sentence_a, entities_a, negated_a) in enumerate(fact_rows):
        for source_b, sentence_b, entities_b, negated_b in fact_rows[index + 1 :]:
            shared_entities = entities_a & entities_b
            if source_a == source_b or len(shared_entities) < 2:
                continue
            if negated_a == negated_b:
                continue
            contradictions.append(
                {
                    "source_a": source_a,
                    "fact_a": sentence_a,
                    "source_b": source_b,
                    "fact_b": sentence_b,
                    "status": "potential_contradiction",
                }
            )

    per_document = {
        source: extract_text_metadata(text) for source, text in normalized.items()
    }
    shared_citations: dict[str, list[str]] = {}
    citation_sources: dict[str, set[str]] = {}
    for source, metadata in per_document.items():
        for citation in metadata["citations"]:
            citation_sources.setdefault(citation, set()).add(source)
    for citation, sources in citation_sources.items():
        if len(sources) > 1:
            shared_citations[citation] = sorted(sources)

    return {
        "status": "ok",
        "documents_analyzed": list(normalized),
        "chronology": sorted(chronology, key=lambda row: _date_sort_key(row["date"])),
        "potential_contradictions": contradictions,
        "shared_citations": shared_citations,
        "per_document": per_document,
        "disclaimer": "Review leads require human verification against the official record.",
    }


def _date_sort_key(value: str) -> tuple[int, str]:
    for fmt in ("%B %d, %Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return (int(datetime.strptime(value, fmt).timestamp()), value)
        except ValueError:
            pass
    return (0, value)


class DepositionStore:
    """Explicit process-local deposition store with a clear lifecycle."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    def ingest(
        self,
        transcript_text: str,
        witness_name: str,
        deposition_date: str | None = None,
        case_name: str | None = None,
    ) -> dict[str, Any]:
        entries = []
        page = 1
        line_number = 0
        current_question: str | None = None
        current_answer: str | None = None
        question_start: int | None = None
        answer_end: int | None = None
        for raw_line in transcript_text.replace("\r", "").split("\n"):
            line_number += 1
            line = raw_line.strip()
            page_match = re.fullmatch(r"(?:Page\s+)?(\d+)", line, re.IGNORECASE)
            if page_match:
                page = int(page_match.group(1))
                line_number = 0
                continue

            # Court transcripts commonly prefix Q/A markers with a printed
            # line number (for example, ``12 Q.``). Prefer that number for
            # citations while retaining a sensible fallback for plain text.
            numbered = re.match(r"^(\d{1,4})\s+(.+)$", line)
            printed_line = int(numbered.group(1)) if numbered else line_number
            content = numbered.group(2) if numbered else line
            question = re.match(r"Q[.:]?\s*(.*)", content, re.IGNORECASE)
            answer = re.match(r"A[.:]?\s*(.*)", content, re.IGNORECASE)
            if question:
                if current_question is not None and current_answer is not None:
                    entries.append((current_question, current_answer, page, question_start or printed_line, answer_end or printed_line))
                current_question, current_answer = question.group(1).strip(), None
                question_start, answer_end = printed_line, None
            elif answer and current_question is not None:
                current_answer = answer.group(1).strip()
                answer_end = printed_line
            elif current_answer is not None and content:
                current_answer += " " + content
                answer_end = printed_line
            elif current_question is not None and content:
                current_question += " " + content
                question_start = question_start or printed_line
        if current_question is not None and current_answer is not None:
            entries.append((current_question, current_answer, page, question_start or line_number, answer_end or line_number))

        key = " ".join(witness_name.lower().split())
        self._entries[key] = {
            "witness": witness_name,
            "deposition_date": deposition_date,
            "case_name": case_name,
            "entries": [
                {
                    "id": index,
                    "question": question,
                    "answer": answer,
                    "citation": f"{witness_name.split()[-1]} Dep. {entry_page}:{question_line}-{answer_line}",
                }
                for index, (question, answer, entry_page, question_line, answer_line) in enumerate(entries)
            ],
        }
        return {
            "status": "ok",
            "witness": witness_name,
            "entries": len(entries),
            "store_key": key,
            "disclaimer": "Transcript remains process-local until clear() is called.",
        }

    def search(self, query: str, witness_name: str | None = None) -> list[dict[str, Any]]:
        query_terms = [term.lower() for term in query.split() if term.strip()]
        stores = self._entries
        if witness_name is not None:
            key = " ".join(witness_name.lower().split())
            stores = {key: self._entries[key]} if key in self._entries else {}
        matches = []
        for record in stores.values():
            for entry in record["entries"]:
                haystack = f"{entry['question']} {entry['answer']}".lower()
                score = sum(term in haystack for term in query_terms)
                if score:
                    matches.append({**entry, "witness": record["witness"], "relevance": score / len(query_terms)})
        return sorted(matches, key=lambda item: item["relevance"], reverse=True)

    def clear(self) -> None:
        self._entries.clear()


__all__ = ["DepositionStore", "extract_text_metadata", "review_records"]
