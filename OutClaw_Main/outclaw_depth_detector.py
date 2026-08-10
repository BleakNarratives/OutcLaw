"""
outclaw_depth_detector.py — Detection depth demonstration for OutClaw Round 1

This module answers the facet:
  "Where does regex-based citation detection fail? What would a semantic or
   structural layer catch that pattern matching can't?"

It ships two validators:
  1. RegexBaseline — pattern-matches U.S.C., C.F.R., §, F.3d, etc.
  2. SemanticValidator — checks existence, negative treatment,
     and whether the cited authority actually supports the sentence.

Design notes
--------------
* Pure stdlib. No network calls, no external models, no paid APIs.
* The legal databases are tiny stubs so the script is self-running.
* The semantic layer uses deterministic claim-vs-holding checks that are
  good enough to flag the dangerous cases regex misses.
* In production these stubs would be replaced by:
      - a citation index / reporter table (for existence),
      - a negative-treatment graph (Shepard's/KeyCite equivalent),
      - statute text and case holding embeddings (for support/opposition).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ═════════════════════════════════════════════════════════════════
# STUB LEGAL DATABASES (production would be real indexes)
# ═════════════════════════════════════════════════════════════════


@dataclass
class CaseEntry:
    name: str
    holding: str
    overruled: bool = False
    distinguished_by: tuple[str, ...] = field(default_factory=tuple)
    # Areas tags help catch contextually wrong citations.
    area: str = "general"


# fmt: off
CASE_DB: dict[str, CaseEntry] = {
    "123 F.3d 456": CaseEntry(
        name="Smith v. Jones",
        holding="The Fourth Amendment requires a warrant for a home search absent exigent circumstances.",
        area="criminal procedure",
    ),
    "999 F.3d 111": CaseEntry(
        name="Doe v. State",
        holding="Contracts procured through duress are voidable, not void.",
        overruled=True,
        area="contracts",
    ),
    "555 F.3d 789": CaseEntry(
        name="Miller v. Acme Corp.",
        holding="A plaintiff may recover punitive damages under § 1983 only on proof of malice or reckless disregard.",
        area="civil rights",
    ),
}

STATUTE_DB: dict[str, str] = {
    "42 U.S.C. § 1983": (
        "Every person who, under color of any statute, ordinance, regulation, "
        "custom, or usage, of any State or Territory or the District of Columbia, "
        "subjects, or causes to be subjected, any citizen of the United States "
        "or other person within the jurisdiction thereof to the deprivation of "
        "any rights, privileges, or immunities secured by the Constitution and "
        "laws, shall be liable to the party injured in an action at law, suit in "
        "equity, or other proper proceeding for redress."
    ),
    "18 U.S.C. § 2511": (
        "It shall be unlawful for any person to intercept any wire, oral, or "
        "electronic communication."
    ),
}
# fmt: on


# ═════════════════════════════════════════════════════════════════
# 1. REGEX BASELINE — only verifies that a citation *looks* legal
# ═════════════════════════════════════════════════════════════════


class RegexBaseline:
    """Pattern-only validator. This is the current OutClaw ceiling."""

    PATTERNS = [
        ("usc", r"\d+\s+U\.S\.C\.\s+§?\s*\d+[a-z]*"),
        ("cfr", r"\d+\s+C\.F\.R\.\s+§?\s*\d+(?:\.\d+)?"),
        ("section_symbol", r"§\s*\d+[a-z]*"),
        ("reporter", r"\d+\s+F\.[2-4]d\s+\d+"),
        ("case_name", r"[A-Z][A-Za-z\s]+\s+v\.\s+[A-Z][A-Za-z\s]+"),
    ]

    def find(self, text: str) -> list[tuple[str, str]]:
        """Return list of (label, match) citation-looking strings."""
        found: list[tuple[str, str]] = []
        for label, pat in self.PATTERNS:
            for m in re.finditer(pat, text):
                found.append((label, m.group(0)))
        return found

    def validate(self, text: str) -> tuple[bool, list[str]]:
        """True if any recognized citation pattern appears."""
        findings = self.find(text)
        reasons = [f"{label}: {match}" for label, match in findings]
        return bool(findings), reasons


# ═════════════════════════════════════════════════════════════════
# 2. SEMANTIC / STRUCTURAL LAYER — verifies *meaning* and *status*
# ═════════════════════════════════════════════════════════════════


@dataclass
class DepthFinding:
    ok: bool
    citation: str
    rule: str
    detail: str


class SemanticValidator:
    """Validate citations beyond syntax: existence, status, and support."""

    # Regex to pull candidate citations from prose.
    CITATION_RE = re.compile(
        r"(?P<statute>\d+\s+U\.S\.C\.\s+§?\s*\d+[a-z]*)|"
        r"(?P<cfr>\d+\s+C\.F\.R\.\s+§?\s*\d+(?:\.\d+)?)|"
        r"(?P<case>\d+\s+F\.[2-4]d\s+\d+)"
    )

    def __init__(self) -> None:
        self.case_db = CASE_DB
        self.statute_db = STATUTE_DB

    def _normalize(self, citation: str) -> str:
        """Collapse whitespace around § and between tokens."""
        return " ".join(citation.split())

    def _negation_flip(self, proposition: str, holding: str) -> bool:
        """
        Detect whether the proposition asserts the opposite of the holding.
        Naive but deterministic: if the holding contains a negated modal
        (cannot, must not, does not) and the proposition drops that negation,
        flag it.
        """
        negators = ("not", "no", "cannot", "must not", "does not", "never")
        holding_has_neg = any(n in holding.lower() for n in negators)
        prop_has_neg = any(n in proposition.lower() for n in negators)
        return holding_has_neg and not prop_has_neg

    def _supports(self, proposition: str, holding: str) -> float:
        """
        Return a support score in [0.0, 1.0].
        0.0 == opposite/inverted, 1.0 == strongly supported.
        """
        # If the proposition negates the holding, it's actively wrong.
        if self._negation_flip(proposition, holding):
            return 0.0

        prop_words = set(re.findall(r"[a-zA-Z]{3,}", proposition.lower()))
        hold_words = set(re.findall(r"[a-zA-Z]{3,}", holding.lower()))
        if not prop_words or not hold_words:
            return 0.0

        shared = prop_words & hold_words
        # Jaccard-ish score that rewards shared legal vocabulary.
        score = len(shared) / max(len(prop_words), len(hold_words))
        if score < 0.15:
            return 0.0
        return min(1.0, score)

    def validate_sentence(self, sentence: str) -> list[DepthFinding]:
        """Run the depth validator against one sentence."""
        findings: list[DepthFinding] = []

        for m in self.CITATION_RE.finditer(sentence):
            citation = self._normalize(m.group(0))

            # --- Statute path ---
            if m.lastgroup == "statute":
                if citation not in self.statute_db:
                    findings.append(
                        DepthFinding(
                            False,
                            citation,
                            "EXISTENCE",
                            "No such statute in the index.",
                        )
                    )
                    continue

                text = self.statute_db[citation]
                support = self._supports(sentence, text)
                if support == 0.0:
                    findings.append(
                        DepthFinding(
                            False,
                            citation,
                            "MISQUOTE / OPPOSITE",
                            "Statute text does not support the sentence; possibly inverted meaning.",
                        )
                    )
                elif support < 0.3:
                    findings.append(
                        DepthFinding(
                            False,
                            citation,
                            "NO SUPPORT",
                            "Sentence uses the real statute but the semantic content is unrelated.",
                        )
                    )
                else:
                    findings.append(
                        DepthFinding(
                            True, citation, "SUPPORTED", f"score={support:.2f}"
                        )
                    )
                continue

            # --- Case-law path ---
            if m.lastgroup == "case":
                if citation not in self.case_db:
                    findings.append(
                        DepthFinding(
                            False,
                            citation,
                            "EXISTENCE",
                            "Citation matches reporter pattern but does not exist in the index.",
                        )
                    )
                    continue

                case = self.case_db[citation]
                if case.overruled:
                    findings.append(
                        DepthFinding(
                            False,
                            citation,
                            "NEGATIVE TREATMENT",
                            f"{case.name} has been overruled.",
                        )
                    )
                    continue

                support = self._supports(sentence, case.holding)
                if support == 0.0:
                    findings.append(
                        DepthFinding(
                            False,
                            citation,
                            "OPPOSITE HOLDING",
                            f"{case.name} is cited for the opposite of what it holds.",
                        )
                    )
                elif support < 0.3:
                    findings.append(
                        DepthFinding(
                            False,
                            citation,
                            "NO SUPPORT",
                            f"{case.name} is real but does not support this sentence.",
                        )
                    )
                else:
                    findings.append(
                        DepthFinding(
                            True, citation, "SUPPORTED", f"score={support:.2f}"
                        )
                    )
                continue

        return findings

    def validate_text(self, text: str) -> dict[str, object]:
        """Validate a block of text, returning structured report."""
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        all_findings: list[dict[str, object]] = []
        for sentence in sentences:
            for finding in self.validate_sentence(sentence):
                all_findings.append(
                    {
                        "sentence": sentence,
                        "citation": finding.citation,
                        "ok": finding.ok,
                        "rule": finding.rule,
                        "detail": finding.detail,
                    }
                )
        return {"text": text, "findings": all_findings}


# ═════════════════════════════════════════════════════════════════
# 3. DEMO / SEVEN-CASE REGRESSION-LIKE TESTS
# ═════════════════════════════════════════════════════════════════

TEST_CASES = [
    # 1. Regex passes; semantic layer fails (opposite holding).
    (
        "Police may search a home without a warrant. Smith v. Jones, 123 F.3d 456.",
        "opposite holding",
    ),
    # 2. Regex passes; semantic layer fails (real case, no support).
    (
        "The defendant breached the contract by failing to deliver widgets. "
        "See Smith v. Jones, 123 F.3d 456.",
        "no support",
    ),
    # 3. Regex passes; semantic layer fails (fabricated case).
    (
        "The court held that widgets are illegal. Fakecase v. Imaginary, 404 F.3d 999.",
        "fabricated case",
    ),
    # 4. Regex passes; semantic layer fails (overruled case).
    (
        "Contracts under duress are void. Doe v. State, 999 F.3d 111.",
        "overruled",
    ),
    # 5. Regex passes; semantic layer fails (misquoted statute).
    (
        "42 U.S.C. § 1983 grants total immunity to all government officials.",
        "misquoted statute",
    ),
    # 6. Regex passes; semantic layer passes (good citation).
    (
        "A plaintiff may recover punitive damages under § 1983 only on proof of malice. "
        "Miller v. Acme Corp., 555 F.3d 789.",
        "valid citation",
    ),
    # 7. Regex passes; semantic layer fails (contextually wrong area).
    (
        "The Fourth Amendment requires a warrant for a home search absent exigent circumstances. "
        "Doe v. State, 999 F.3d 111.",
        "overruled / wrong area",
    ),
]


def main() -> None:
    regex = RegexBaseline()
    depth = SemanticValidator()

    print("=" * 70)
    print("OutClaw Detection Depth Demonstration")
    print("=" * 70)

    for i, (text, label) in enumerate(TEST_CASES, start=1):
        regex_ok, regex_reasons = regex.validate(text)
        report = depth.validate_text(text)

        print(f"\n[{i}] {label!r}")
        print(f"  Text: {text[:80]}{'...' if len(text) > 80 else ''}")
        print(f"  Regex baseline: {'PASS' if regex_ok else 'FAIL'} -> {regex_reasons}")

        failed = [f for f in report["findings"] if not f["ok"]]
        if failed:
            print("  Semantic layer: FAIL")
            for f in failed:
                print(f"    • {f['citation']} | {f['rule']} — {f['detail']}")
        else:
            print("  Semantic layer: PASS")
            for f in report["findings"]:
                print(f"    • {f['citation']} | {f['rule']} — {f['detail']}")


if __name__ == "__main__":
    main()
