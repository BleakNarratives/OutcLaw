#!/usr/bin/env python3
"""
OutClaw/outclaw_discover.py — Autonomous Citation Pattern Discovery Loop.

PREDICASE GEM (2026-07-26): Adapted from Predicase's ``discover_hot_leads.py``
which autonomously scans public index networks for class-action boilerplate,
isolates target defendants, and injects them into the pipeline for processing.

OutClaw's equivalent: an autonomous discovery engine that:
  1. Scans legal text corpora for novel citation patterns
  2. Extracts citation→proposition pairs using regex + LLM fallback
  3. Classifies discoveries (case, statute, CFR, state)
  4. Feeds verified discoveries into the seed registry auto-expander
  5. Logs everything for operator review (never auto-modifies seed)

Design principles (from Predicase):
  - Autonomous but safe: discoveries are logged, NOT auto-injected
  - Multi-signal: uses regex baseline + optional LLM verification
  - Decoupled: runs independently, feeds into seed via expander
  - Observable: every discovery is logged with source, confidence, timestamp

Usage:
    from OutClaw.outclaw_discover import DiscoveryEngine

    engine = DiscoveryEngine()
    discoveries = engine.scan_text(legal_document_text)
    for d in discoveries:
        print(f"Found: {d['citation']} ({d['type']}, confidence={d['confidence']:.2f})")

    # Review and manually approve before injecting into seed:
    engine.approve_and_inject("42 U.S.C. § 1985", seed_path="OutClaw/outclaw_seed.json")
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

_DISCOVERY_LOG = Path.home() / ".outclaw" / "discoveries.jsonl"


# ---------------------------------------------------------------------------
# Citation extraction patterns (broader than CITATION_RE — designed for discovery)
# ---------------------------------------------------------------------------

DISCOVERY_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Federal statutes
    (
        "statute",
        re.compile(
            r"\b(\d{1,3})\s*U\.?S\.?C\.?\s*§\s*(\d{1,6}[a-z]?)\b",
            re.IGNORECASE,
        ),
    ),
    # Federal regulations
    (
        "cfr",
        re.compile(
            r"\b(\d{1,3})\s*C\.?F\.?R\.?\s*§?\s*(\d+\.\d+)\b",
            re.IGNORECASE,
        ),
    ),
    # Federal Reporter citations
    (
        "case",
        re.compile(
            r"\b(\d{1,4})\s*F\.?\s*(?:3d|4th|Supp\.?)\s*(\d+)\b",
            re.IGNORECASE,
        ),
    ),
    # Supreme Court citations
    (
        "case",
        re.compile(
            r"\b(\d{1,3})\s*U\.?S\.?\s*(\d{1,4})\b",
            re.IGNORECASE,
        ),
    ),
    # Supreme Court Reporter
    (
        "case",
        re.compile(
            r"\b(\d{1,3})\s*S\.?\s*Ct\.?\s*(\d{1,4})\b",
            re.IGNORECASE,
        ),
    ),
    # State reporter patterns
    (
        "state_case",
        re.compile(
            r"\b(\d{1,4})\s*([A-Z][a-z]+\.)\s*(?:2d|3d)?\s*(\d{1,4})\b",
        ),
    ),
    # Case name with v.
    (
        "case_name",
        re.compile(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+v\.\s+"
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
        ),
    ),
    # State code citations (e.g., "Cal. Penal Code § 187")
    (
        "state_statute",
        re.compile(
            r"\b([A-Z][a-z]+\.)\s*([A-Z][a-z]+)\s+Code\s*§\s*(\d+[a-z]?)\b",
        ),
    ),
    # Vendor-neutral / WL citations
    (
        "wl_cite",
        re.compile(
            r"\b(\d{4})\s+WL\s+(\d+)\b",
        ),
    ),
]

# Legal context verbs that indicate a citation is being used meaningfully
CONTEXT_VERBS = re.compile(
    r"\b(held|ruled|found|stated|decided|established|concluded|reasoned|"
    r"determined|ordered|granted|denied|reversed|affirmed|remanded|cited|"
    r"quoted|referenced|pursuant to|under|according to|per)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Discovery record
# ---------------------------------------------------------------------------


@dataclass
# ═══════════════════════════════════════════════════════
#  OUTCLAW_DISCOVER
# ═══════════════════════════════════════════════════════════════

class Discovery:
    citation: str
    citation_type: str
    proposition: str
    sentence: str
    confidence: float
    source: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Discovery Engine
# ---------------------------------------------------------------------------


class DiscoveryEngine:
    """
    Autonomous citation pattern discovery engine.

    Scans legal text for novel citations (not in existing seed registry),
    extracts surrounding propositions, classifies type, and logs discoveries
    for operator review.

    Mirrors Predicase's ``discover_hot_leads.py`` pattern:
    scan → extract → classify → log (operator approves → inject).
    """

    def __init__(self, seed_path: Path | None = None):
        self._seed_path = Path(seed_path or (_HERE / "outclaw_seed.json"))
        self._known_citations: set = self._load_known_citations()
        self._discoveries: list[Discovery] = []
        self._log_path = _DISCOVERY_LOG
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_text(self, text: str, source: str = "unknown") -> list[dict[str, Any]]:
        """
        Scan a block of legal text for undiscovered citations.

        Returns list of discovery dicts: citation, type, proposition,
        sentence, confidence, source.
        """
        discoveries: list[dict[str, Any]] = []

        # Step 1: Extract candidate citations
        candidates = self._extract_candidates(text)

        # Step 2: For each candidate, extract surrounding proposition
        for candidate in candidates:
            citation = self._normalize(candidate["text"])

            # Skip if already in seed registry
            if citation in self._known_citations:
                continue

            # Skip if already discovered this session
            if any(d.citation == citation for d in self._discoveries):
                continue

            # Extract proposition from surrounding context
            proposition = self._extract_proposition(
                text, candidate["start"], candidate["end"]
            )

            # Classify
            ctype = candidate["type"]
            confidence = self._compute_confidence(citation, proposition, ctype)

            disc = Discovery(
                citation=citation,
                citation_type=ctype,
                proposition=proposition,
                sentence=self._get_sentence(text, candidate["start"]),
                confidence=confidence,
                source=source,
            )
            self._discoveries.append(disc)
            discoveries.append(
                {
                    "citation": disc.citation,
                    "type": disc.citation_type,
                    "proposition": disc.proposition,
                    "sentence": disc.sentence,
                    "confidence": disc.confidence,
                    "source": disc.source,
                    "timestamp": disc.timestamp,
                    "status": "pending_review",
                }
            )

        # Step 3: Log discoveries
        self._log_discoveries()

        return discoveries

    def scan_file(self, path: str) -> list[dict[str, Any]]:
        """Scan a file on disk for undiscovered citations."""
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        return self.scan_text(text, source=path)

    def scan_corpus(
        self, directory: str, glob_pattern: str = "*.txt"
    ) -> dict[str, Any]:
        """
        Scan all text files in a directory. Returns aggregate summary.
        """
        d = Path(directory)
        if not d.is_dir():
            return {"error": f"{directory} is not a directory"}

        all_discoveries: list[dict[str, Any]] = []
        for fp in d.glob(glob_pattern):
            try:
                results = self.scan_file(str(fp))
                all_discoveries.extend(results)
            except Exception:
                continue

        return {
            "directory": directory,
            "files_scanned": len(list(d.glob(glob_pattern))),
            "total_discoveries": len(all_discoveries),
            "discoveries": all_discoveries,
        }

    def approve_and_inject(
        self,
        citation: str,
        holding: str = "",
        area: str = "general",
        overruled: bool = False,
        seed_path: Path | None = None,
    ) -> bool:
        """
        Approve a discovery and inject it into the seed registry.

        The operator should review the discovery log before calling this.
        Never auto-injected — always requires explicit operator approval.
        """
        sp = Path(seed_path or self._seed_path)
        if not sp.exists():
            return False

        with open(sp, "r", encoding="utf-8") as f:
            seed = json.load(f)

        # Determine if case or statute
        disc = next((d for d in self._discoveries if d.citation == citation), None)
        ctype = disc.citation_type if disc else "case"

        if ctype in ("case", "case_name", "wl_cite", "state_case"):
            if citation not in seed.get("cases", {}):
                seed["cases"][citation] = {
                    "name": citation,
                    "holding": holding or "Discovered by OutClaw pattern scanner.",
                    "overruled": overruled,
                    "area": area,
                }
        elif ctype in ("statute", "state_statute"):
            if citation not in seed.get("statutes", {}):
                seed["statutes"][citation] = holding or "Statute text not yet indexed."

        with open(sp, "w", encoding="utf-8") as f:
            json.dump(seed, f, indent=2)

        self._known_citations.add(citation)
        return True

    def verify_discovery(
        self,
        discovery: dict[str, Any],
        min_confidence: float = 0.60,
    ) -> dict[str, Any] | None:
        """
        RAG VERIFICATION STEP (2026-08-03): confirm a pattern-scanned discovery
        is a REAL citation used meaningfully, before an operator invests review
        time in it. The discovery engine's regex is broad by design; the
        cascade adds a semantic second opinion on the classification tier.

        Returns {"verified": bool, "confidence": float, "reasoning": str,
                 "tier": int, "provider": str, "model": str}
        or None when cascade disabled / unavailable (engine stays deterministic).
        """
        try:
            from OutClaw.outclaw_model_cascade import get_cascade  # type: ignore

            cascade = get_cascade()
            if not cascade.enabled:
                return None

            prompt = (
                "You are a legal citation auditor. A pattern scanner found "
                "the following potential citation. Determine whether it is a "
                "genuine legal citation being used meaningfully (not a false "
                "positive like an address, year, or random number).\n\n"
                f"CANDIDATE CITATION: {discovery.get('citation', '')}\n"
                f"TYPE: {discovery.get('type', '')}\n"
                f"CONTEXT SENTENCE: {discovery.get('sentence', '')[:600]}\n\n"
                "Respond with ONLY this JSON (no other text): "
                '{"verified": true_or_false, "confidence": 0.0_to_1.0, '
                '"reasoning": "one sentence"}'
            )
            result = cascade.complete(
                prompt,
                task="discovery_verification",
                min_confidence=min_confidence,
                max_tokens=500,
            )
            if not result.ok or result.data is None:
                return None
            return {
                **result.data,
                "tier": result.tier,
                "provider": result.provider,
                "model": result.model,
            }
        except Exception:
            return None

    def pending_review(self) -> list[dict[str, Any]]:
        """List all discoveries awaiting operator review."""
        return [
            {
                "citation": d.citation,
                "type": d.citation_type,
                "proposition": d.proposition,
                "confidence": d.confidence,
                "source": d.source,
                "timestamp": d.timestamp,
            }
            for d in self._discoveries
        ]

    def diagnostics(self) -> dict[str, Any]:
        """Operational diagnostics."""
        return {
            "known_citations": len(self._known_citations),
            "pending_discoveries": len(self._discoveries),
            "log_path": str(self._log_path),
            "seed_path": str(self._seed_path),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_known_citations(self) -> set:
        """Load all citation keys from the seed registry."""
        known: set = set()
        if self._seed_path.exists():
            try:
                with open(self._seed_path, "r") as f:
                    seed = json.load(f)
                known.update(seed.get("cases", {}).keys())
                known.update(seed.get("statutes", {}).keys())
            except (json.JSONDecodeError, KeyError):
                pass
        return known

    def _extract_candidates(self, text: str) -> list[dict[str, Any]]:
        """Extract all potential citations from text using discovery patterns."""
        candidates: list[dict[str, Any]] = []
        for ctype, pattern in DISCOVERY_PATTERNS:
            for match in pattern.finditer(text):
                candidates.append(
                    {
                        "type": ctype,
                        "text": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                    }
                )
        # Deduplicate by span
        seen: set = set()
        unique: list[dict[str, Any]] = []
        for c in candidates:
            span = (c["start"], c["end"])
            if span not in seen:
                seen.add(span)
                unique.append(c)
        return unique

    def _extract_proposition(self, text: str, start: int, end: int) -> str:
        """Extract the proposition around a citation (200-char window)."""
        ctx_start = max(0, start - 100)
        ctx_end = min(len(text), end + 100)
        context = text[ctx_start:ctx_end]
        # Remove the citation itself
        citation_text = text[start:end]
        prop = context.replace(citation_text, " ", 1)
        return " ".join(prop.split())[:200]

    @staticmethod
    def _normalize(citation: str) -> str:
        """Normalize a citation string."""
        return " ".join(citation.split())

    @staticmethod
    def _get_sentence(text: str, pos: int) -> str:
        """Get the sentence containing a given position."""
        # Find sentence boundaries
        before = text[:pos]
        after = text[pos:]
        sent_start = max(before.rfind("."), before.rfind("!"), before.rfind("?"))
        sent_end = min(
            (after.find(".") if after.find(".") >= 0 else len(after)),
            (after.find("!") if after.find("!") >= 0 else len(after)),
            (after.find("?") if after.find("?") >= 0 else len(after)),
        )
        if sent_start < 0:
            sent_start = 0
        else:
            sent_start += 1
        sent_end += pos
        return text[sent_start:sent_end].strip()

    def reload_known_citations(self) -> int:
        """Reload known citations from the seed registry. Call after seed expansions."""
        previous = len(self._known_citations)
        self._known_citations = self._load_known_citations()
        return len(self._known_citations) - previous

    @staticmethod
    def _compute_confidence(citation: str, proposition: str, ctype: str) -> float:
        """
        Compute a confidence score for a discovered citation.
        Mirrors Predicase's weighted signal approach.
        """
        score = 0.0

        # Base confidence by type
        type_weights = {
            "statute": 0.7,
            "cfr": 0.6,
            "case": 0.8,
            "state_case": 0.5,
            "case_name": 0.4,
            "state_statute": 0.6,
            "wl_cite": 0.3,
        }
        score = type_weights.get(ctype, 0.3)

        # Boost: citation has standard legal format (reporter abbreviation pattern)
        if re.search(r"\d+\s+[A-Z][a-z]*\.", citation) or re.search(
            r"\d+\s+[A-Z]\.\s*[A-Z]\.", citation
        ):
            score += 0.1

        # Boost: proposition contains legal context verbs
        if CONTEXT_VERBS.search(proposition):
            score += 0.1

        # Penalty: citation is purely numeric (no reporter/legal indicators at all)
        if not re.search(r"[A-Z][a-zA-Z]{1,}", citation) and not re.search(
            r"[A-Z]\.[A-Z]\.", citation
        ):
            score -= 0.2

        return max(0.0, min(1.0, score))

    def _log_discoveries(self) -> None:
        """Append ALL new discoveries to the JSONL log."""
        # Track what we've already persisted
        logged = getattr(self, "_logged_count", 0)
        with open(self._log_path, "a") as f:
            for d in self._discoveries[logged:]:
                f.write(
                    json.dumps(
                        {
                            "citation": d.citation,
                            "type": d.citation_type,
                            "proposition": d.proposition,
                            "confidence": d.confidence,
                            "source": d.source,
                            "timestamp": d.timestamp,
                        }
                    )
                    + "\n"
                )
        self._logged_count = len(self._discoveries)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_engine: DiscoveryEngine | None = None


def get_engine() -> DiscoveryEngine:
    """Get or create the default discovery engine."""
    global _default_engine
    if _default_engine is None:
        _default_engine = DiscoveryEngine()
    return _default_engine


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample = """
    The plaintiff brings this action under 42 U.S.C. § 1983 for violations
    of the Fourth Amendment. The court held in Smith v. Jones, 123 F.3d 456
    that a warrant is required. However, 99 U.S.C. § 9999 provides an
    alternative cause of action. The defendant relies on Miranda v. Arizona,
    384 U.S. 436, which established the right to remain silent. But see
    18 U.S.C. § 242 for criminal liability of state actors.
    """
    engine = DiscoveryEngine()
    discoveries = engine.scan_text(sample, source="smoke-test")

    print(f"Found {len(discoveries)} undiscovered citations:")
    for d in discoveries:
        tag = (
            "HIGH"
            if d["confidence"] >= 0.7
            else "MEDIUM"
            if d["confidence"] >= 0.4
            else "LOW"
        )
        print(f"  [{tag}] {d['citation']} ({d['type']})")
        print(f'        "{d["proposition"][:80]}..."')
        print(f"        confidence={d['confidence']:.2f}, status={d['status']}")

    print(f"\nDiagnostics: {engine.diagnostics()}")
