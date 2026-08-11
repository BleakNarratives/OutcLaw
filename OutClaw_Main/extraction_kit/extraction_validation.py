# Vendored into OutClaw from the vendored extraction layer 1.0.0 (MIT License)
# Source: https://github.com/daltonjsawyer-png/extraction
# Copied verbatim into the OutClaw tree (2026-08-11) so the
# extraction/ingestion layer is self-contained and portable.
# See extraction/README.md for provenance and OutClaw wrap points.

"""
Extraction and Validation Tools for extraction MCP Server.

Tools that extract structured data from legal documents for Claude Desktop
to use when writing briefs and legal analysis.

All tools return JSON for Claude Desktop to process into legal prose.
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class ReasoningType(Enum):
    ANALOGICAL = "analogical"
    POLICY = "policy_based"
    TEXTUAL = "textual_interpretation"
    PURPOSIVE = "purposive_interpretation"
    STRUCTURAL = "structural_interpretation"
    CONSTITUTIONAL_TIER = "constitutional_tier"
    HISTORICAL = "historical"
    PRECEDENTIAL = "precedential"
    PRAGMATIC = "pragmatic"


class ProceduralPosture(Enum):
    MOTION_TO_DISMISS = "motion_to_dismiss"
    SUMMARY_JUDGMENT = "summary_judgment"
    TRIAL = "trial"
    APPEAL = "appeal"
    PRELIMINARY_INJUNCTION = "preliminary_injunction"
    CLASS_CERTIFICATION = "class_certification"
    POST_TRIAL = "post_trial"
    HABEAS = "habeas"
    INTERLOCUTORY = "interlocutory"


class ContradictionType(Enum):
    DIRECT_CONFLICT = "direct_conflict"
    OMISSION = "omission"
    INCONSISTENCY = "inconsistency"
    TIMELINE_CONFLICT = "timeline_conflict"


@dataclass
class ExtractionMeta:
    """
    Metadata about extraction quality for improved fallback behavior.

    All extraction functions should return this alongside their results
    to provide transparency about what was found vs. missing.
    """
    extraction_complete: bool  # True if primary targets were found
    targets_found: List[str]   # What was successfully extracted
    targets_missing: List[str]  # What could not be extracted
    confidence_scores: Dict[str, float]  # Confidence per target (0.0-1.0)
    suggestions: List[str]     # Actionable suggestions for missing items

    def to_dict(self) -> Dict[str, Any]:
        return {
            "extraction_complete": self.extraction_complete,
            "targets_found": self.targets_found,
            "targets_missing": self.targets_missing,
            "confidence_scores": self.confidence_scores,
            "suggestions": self.suggestions
        }


def build_extraction_meta(
    found: List[str],
    missing: List[str],
    confidence: Dict[str, float],
    suggestions: Optional[List[str]] = None
) -> ExtractionMeta:
    """Helper to build ExtractionMeta with sensible defaults."""
    return ExtractionMeta(
        extraction_complete=len(missing) == 0,
        targets_found=found,
        targets_missing=missing,
        confidence_scores=confidence,
        suggestions=suggestions or []
    )


def format_extraction_meta(meta: ExtractionMeta) -> str:
    """Format ExtractionMeta for user-facing output."""
    lines = []
    lines.append("EXTRACTION REPORT")
    lines.append("=" * 40)

    for target in meta.targets_found:
        conf = meta.confidence_scores.get(target, 0.0)
        conf_label = "high" if conf >= 0.8 else "moderate" if conf >= 0.5 else "low"
        lines.append(f"  [OK] {target} ({conf_label} confidence: {conf:.0%})")

    for target in meta.targets_missing:
        lines.append(f"  [X] {target} - not detected")

    if meta.suggestions:
        lines.append("")
        lines.append("SUGGESTIONS:")
        for sug in meta.suggestions:
            lines.append(f"  - {sug}")

    return "\n".join(lines)


# ============================================================================
# SENTENCE ROLE CLASSIFICATION (LUIMA-inspired)
# ============================================================================

class SentenceRole(Enum):
    """Classification of sentence's argumentative function in legal text."""
    LEGAL_RULE = "legal_rule"                    # Abstract statement of law
    LEGAL_HOLDING = "legal_holding"              # Court's legal conclusion
    EVIDENCE_BASED_FINDING = "evidence_based_finding"  # Factual conclusion from evidence
    EVIDENCE_SUMMARY = "evidence_summary"        # Recounting testimony/documents
    CITATION = "citation"                        # Reference to authority
    PROCEDURAL_FACT = "procedural_fact"          # Case history/procedure
    POLICY_REASONING = "policy_reasoning"        # Purpose/policy arguments
    PARTY_ARGUMENT = "party_argument"            # What a party contends
    DICTA = "dicta"                              # Non-binding commentary
    UNKNOWN = "unknown"


@dataclass
class SentenceClassification:
    """Result of classifying a sentence's role."""
    text: str
    role: SentenceRole
    confidence: float
    signals: Dict[str, bool]
    formulation_type: Optional[str] = None  # If a legal formulation was detected


@dataclass
class LegalFormulation:
    """A detected legal formulation pattern."""
    text: str
    formulation_type: str  # standard, burden, test, exception, element
    extracted_components: Dict[str, str]  # party, action, elements, etc.
    confidence: float


# Legal formulation patterns - high-confidence rule indicators
LEGAL_FORMULATION_PATTERNS = {
    "standard": [
        # "[Party] must prove/show/establish/plead [elements]"
        r'(?:plaintiff|petitioner|claimant|party|defendant|respondent|private plaintiff)s?\s+(?:must|shall|has to|is required to)\s+(?:prove|show|establish|demonstrate|plead|allege|set forth)\s+(.+?)(?:\.|;|$)',
        # "To prevail/state a claim, [party] must [action]"
        r'[Tt]o\s+(?:prevail|succeed|recover|establish|prove|state a claim|survive)\s*,?\s+(?:a\s+)?(?:plaintiff|petitioner|claimant|party|defendant)\s+must\s+(.+?)(?:\.|;|$)',
        # "[Claim] requires [elements]"
        r'(?:A\s+)?(?:claim|cause of action|action)\s+(?:for|of)\s+\w+\s+requires?\s+(.+?)(?:\.|;|$)',
        # "plaintiff must plead" (common securities law)
        r'(?:plaintiff|petitioner|claimant)s?\s+must\s+(?:plead|allege)\s+(.+?)(?:\.|;|$)',
    ],
    "court_duty": [
        # "court must [action]" - CRITICAL for procedural rules
        r'(?:the\s+)?(?:court|Court|courts)\s+must\s+(.+?)(?:\.|;|$)',
        # "court shall [action]"
        r'(?:the\s+)?(?:court|Court|courts)\s+shall\s+(.+?)(?:\.|;|$)',
        # "a court governed by X must [action]"
        r'(?:a\s+)?court\s+(?:governed\s+by|applying|under)\s+.+?\s+must\s+(.+?)(?:\.|;|$)',
        # "reviewing court must [action]"
        r'(?:the\s+)?(?:reviewing|appellate|district|trial)\s+court\s+must\s+(.+?)(?:\.|;|$)',
        # "court is required to [action]"
        r'(?:the\s+)?(?:court|Court)\s+is\s+required\s+to\s+(.+?)(?:\.|;|$)',
    ],
    "burden": [
        # "[Party] bears the burden of [action]"
        r'(?:plaintiff|petitioner|claimant|party|defendant|respondent)s?\s+bears?\s+(?:the\s+)?burden\s+of\s+(.+?)(?:\.|;|$)',
        # "The burden [of proof] is on [party]"
        r'[Tt]he\s+burden\s+(?:of\s+(?:proof|persuasion|production|pleading))?\s+(?:is|rests|falls|remains)\s+(?:on|upon|with)\s+(?:the\s+)?(?:plaintiff|petitioner|claimant|party|defendant)',
        # "burden shifts to [party]"
        r'burden\s+(?:then\s+)?shifts?\s+to\s+(?:the\s+)?(?:plaintiff|petitioner|defendant|respondent)',
        # "[party] has the burden"
        r'(?:plaintiff|petitioner|defendant|respondent)s?\s+(?:has|have|had)\s+(?:the\s+)?burden\s+(?:of|to)\s+(.+?)(?:\.|;|$)',
    ],
    "test": [
        # "court applies [test name] which requires"
        r'(?:court|we)\s+appl(?:y|ies)\s+(?:the\s+)?(.+?)\s+(?:test|standard|analysis|framework)',
        # "Under [test], court must [action]"
        r'[Uu]nder\s+(?:the\s+)?(.+?)\s+(?:test|standard|framework)\s*,?\s+(?:a\s+)?(?:court|we)\s+must\s+(.+?)(?:\.|;|$)',
        # "[Test] requires court to [action]"
        r'(?:The\s+)?(.+?)\s+(?:test|standard|analysis)\s+requires?\s+(?:the\s+)?(?:court|courts|we)\s+to\s+(.+?)(?:\.|;|$)',
        # "the standard is [X]"
        r'(?:the\s+)?(?:applicable\s+)?standard\s+(?:is|requires)\s+(.+?)(?:\.|;|$)',
        # "inquiry is whether [X]"
        r'(?:the\s+)?(?:relevant|applicable|proper|central)\s+inquiry\s+is\s+(?:whether\s+)?(.+?)(?:\.|;|$)',
    ],
    "exception": [
        # "unless [condition], [rule] applies"
        r'[Uu]nless\s+(.+?),\s+(.+?)(?:\.|;|$)',
        # "[Rule] does not apply when/where [condition]"
        r'(?:This\s+)?(?:rule|standard|requirement)\s+(?:does\s+not|doesn\'t)\s+apply\s+(?:when|where|if)\s+(.+?)(?:\.|;|$)',
        # "except when/where [condition]"
        r'except\s+(?:when|where|if)\s+(.+?)(?:\.|;|$)',
        # "X is not required when/if [condition]"
        r'.+?\s+is\s+not\s+required\s+(?:when|where|if)\s+(.+?)(?:\.|;|$)',
    ],
    "element": [
        # "elements of [claim] are: (1)...(2)..."
        r'(?:The\s+)?elements?\s+of\s+(?:a\s+)?(.+?)\s+(?:are|include|consist of)\s*:?\s*(?:\(?\d\)?|\(?[ai]\)?)?',
        # "To establish [claim], plaintiff must show: (1)...(2)..."
        r'[Tt]o\s+(?:establish|prove|make out)\s+(?:a\s+)?(?:claim|cause of action)\s+(?:for|of)\s+(.+?),?\s+(?:plaintiff|claimant)\s+must\s+(?:show|prove|establish)\s*:?',
        # "[Claim] has [N] elements"
        r'(?:A\s+)?(?:claim|cause of action)\s+(?:for|of)\s+(.+?)\s+has\s+(\d+|two|three|four|five|six)\s+elements?',
        # "factors include/are"
        r'(?:The\s+)?(?:relevant\s+)?factors?\s+(?:are|include|to consider)\s*:?',
        # "X requires showing [N] things"
        r'.+?\s+requires?\s+(?:a\s+)?(?:plaintiff|party)\s+to\s+(?:show|prove|establish)\s*:?',
    ],
    "holding": [
        # "We hold/conclude/find that [conclusion]"
        r'[Ww]e\s+(?:hold|conclude|find|determine|decide)\s+that\s+(.+?)(?:\.|;|$)',
        # "The court holds/held that"
        r'(?:The\s+)?(?:court|Court)\s+(?:holds?|held|concludes?|concluded|finds?|found)\s+that\s+(.+?)(?:\.|;|$)',
        # "It is [adjective] that"
        r'[Ii]t\s+is\s+(?:clear|evident|well-?established|settled|axiomatic)\s+(?:law\s+)?that\s+(.+?)(?:\.|;|$)',
        # "[We/Court] therefore hold"
        r'(?:We|The court)\s+therefore\s+(?:hold|conclude|find)\s+(?:that\s+)?(.+?)(?:\.|;|$)',
        # "This Court has held"
        r'[Tt]his\s+(?:Court|court)\s+has\s+(?:held|concluded|found|recognized)\s+that\s+(.+?)(?:\.|;|$)',
        # "We now hold" / "Today we hold"
        r'(?:We\s+now|Today\s+we|Accordingly,?\s+we)\s+(?:hold|conclude|find)\s+(?:that\s+)?(.+?)(?:\.|;|$)',
        # "[formulation], we conclude"
        r'(.+?),\s+we\s+(?:hold|conclude|find)(?:\.|;|$)',
    ],
    "comparative": [
        # "court must consider/weigh/compare [X]"
        r'(?:the\s+)?(?:court|Court)\s+must\s+(?:consider|weigh|compare|evaluate|assess)\s+(.+?)(?:\.|;|$)',
        # "in determining X, court must consider Y"
        r'[Ii]n\s+(?:determining|assessing|evaluating)\s+.+?,\s+(?:the\s+)?(?:court|Court)\s+must\s+(?:consider|weigh|assess)\s+(.+?)(?:\.|;|$)',
        # "court engages in comparative evaluation"
        r'(?:court|Court)\s+(?:must\s+)?engage[s]?\s+in\s+(?:a\s+)?(?:comparative\s+)?(?:evaluation|analysis|assessment)',
    ],
}

# Negative patterns - indicate sentence is NOT a rule/holding
NEGATIVE_EXTRACTION_PATTERNS = {
    "party_argument": [
        r'(?:Plaintiff|Defendant|Petitioner|Respondent|Appellant|Appellee)s?\s+(?:argues?|contends?|asserts?|claims?|maintains?|submits?)\s+that',
        r'(?:Plaintiff|Defendant|Petitioner|Respondent)\'s\s+(?:argument|position|contention)\s+(?:is|was)\s+that',
        r'(?:According to|Per)\s+(?:plaintiff|defendant|petitioner|respondent)',
    ],
    "testimony": [
        r'(?:Dr\.|Mr\.|Ms\.|Mrs\.)\s+\w+\s+(?:testified|stated|opined|concluded)\s+that',
        r'(?:The\s+)?(?:witness|expert|doctor|physician)\s+(?:testified|stated|opined)\s+that',
        r'(?:At\s+)?(?:trial|deposition|hearing)\s*,?\s+\w+\s+(?:testified|stated)',
    ],
    "conditional": [
        r'[Ii]f\s+(?:plaintiff|defendant|petitioner|respondent)\s+(?:were|had|could|should)',
        r'[Aa]ssuming\s+arguendo',
        r'[Ee]ven\s+if\s+(?:plaintiff|defendant|petitioner|respondent)',
        r'[Ww]ere\s+(?:we|the court)\s+to\s+(?:find|hold|conclude)',
    ],
    "procedural": [
        r'(?:Plaintiff|Defendant|Petitioner|Respondent)\s+(?:moved|filed|appealed|petitioned)\s+(?:for|to)',
        r'(?:The\s+)?(?:court|Court)\s+(?:granted|denied|dismissed)\s+(?:the\s+)?(?:motion|petition|appeal)',
        r'(?:On|In)\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+',
    ],
    "question": [
        r'^(?:Whether|The question (?:is|before us)|At issue is)',
        r'\?$',
    ],
}

# Sentence role signal patterns
ROLE_SIGNAL_PATTERNS = {
    SentenceRole.LEGAL_RULE: [
        r'\b(?:must|shall|is required to|has a duty to)\b',
        r'\b(?:standard|test|elements?|factors?|requirements?)\b',
        r'\b(?:in order to|to establish|to prove|to prevail)\b',
    ],
    SentenceRole.LEGAL_HOLDING: [
        r'\b[Ww]e\s+(?:hold|conclude|affirm|reverse|find)\b',
        r'\b(?:court|Court)\s+(?:holds?|held|concludes?|concluded)\b',
        r'\b(?:judgment|decision)\s+(?:is|was)\s+(?:affirmed|reversed|vacated)\b',
    ],
    SentenceRole.EVIDENCE_BASED_FINDING: [
        r'\b(?:evidence|record|testimony)\s+(?:shows?|establishes?|demonstrates?|supports?)\b',
        r'\b(?:jury|factfinder|trier of fact)\s+(?:found|determined|concluded)\b',
        r'\b(?:finding|fact)\s+that\b',
    ],
    SentenceRole.EVIDENCE_SUMMARY: [
        r'\b(?:testified|stated|opined)\s+that\b',
        r'\b(?:exhibit|document|record)\s+(?:shows?|indicates?)\b',
        r'\b(?:according to|per)\s+(?:the\s+)?(?:testimony|evidence|record)\b',
    ],
    SentenceRole.CITATION: [
        r'\d+\s+(?:U\.S\.|S\.\s*Ct\.|F\.\s*(?:2d|3d|4th)|F\.\s*Supp)',
        r'\bSee\s+[A-Z]',
        r'\bciting\s+[A-Z]',
    ],
    SentenceRole.PROCEDURAL_FACT: [
        r'\b(?:filed|appealed|moved|petitioned|granted|denied|dismissed)\b',
        r'\b(?:district court|circuit court|trial court|appellate court)\b',
        r'\b(?:on appeal|below|remanded)\b',
    ],
    SentenceRole.POLICY_REASONING: [
        r'\b(?:purpose|policy|legislative intent|Congress intended)\b',
        r'\b(?:would undermine|would promote|serves to|designed to)\b',
        r'\b(?:efficiency|fairness|justice|equity)\b',
    ],
    SentenceRole.PARTY_ARGUMENT: [
        r'\b(?:argues?|contends?|asserts?|maintains?|submits?)\s+that\b',
        r'\b(?:Plaintiff|Defendant|Petitioner|Respondent)\'s\s+(?:argument|position)\b',
    ],
}


def detect_legal_formulations(text: str) -> List[LegalFormulation]:
    """
    Detect legal formulation patterns in text.

    These are high-confidence indicators of legal rules.
    Returns list of detected formulations with their types.
    """
    formulations = []

    for formulation_type, patterns in LEGAL_FORMULATION_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                # Extract the full matched text
                full_match = match.group(0)

                # Extract components from capture groups
                components = {}
                for i, group in enumerate(match.groups(), 1):
                    if group:
                        components[f"component_{i}"] = group.strip()

                formulations.append(LegalFormulation(
                    text=full_match,
                    formulation_type=formulation_type,
                    extracted_components=components,
                    confidence=0.85  # Formulations are high confidence
                ))

    return formulations


def is_negative_extraction(sentence: str) -> Tuple[bool, str]:
    """
    Check if sentence should be excluded from rule/holding extraction.

    Returns:
        (is_negative, reason) - True if sentence is NOT a rule/holding
    """
    for neg_type, patterns in NEGATIVE_EXTRACTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                return True, neg_type
    return False, ""


def classify_sentence_role(sentence: str) -> SentenceClassification:
    """
    Classify a single sentence's argumentative role.

    Uses pattern matching and signal detection to determine
    the most likely role of the sentence in legal text.
    """
    sentence = sentence.strip()
    signals = {}
    role_scores = {role: 0.0 for role in SentenceRole}

    # Check for negative extraction first
    is_negative, neg_type = is_negative_extraction(sentence)
    if is_negative:
        if neg_type == "party_argument":
            return SentenceClassification(
                text=sentence,
                role=SentenceRole.PARTY_ARGUMENT,
                confidence=0.8,
                signals={"negative_pattern": True, "neg_type": neg_type}
            )
        elif neg_type == "testimony":
            return SentenceClassification(
                text=sentence,
                role=SentenceRole.EVIDENCE_SUMMARY,
                confidence=0.8,
                signals={"negative_pattern": True, "neg_type": neg_type}
            )
        elif neg_type == "procedural":
            return SentenceClassification(
                text=sentence,
                role=SentenceRole.PROCEDURAL_FACT,
                confidence=0.75,
                signals={"negative_pattern": True, "neg_type": neg_type}
            )

    # Check for legal formulations (high confidence rule indicators)
    formulations = detect_legal_formulations(sentence)
    if formulations:
        formulation = formulations[0]
        if formulation.formulation_type == "holding":
            return SentenceClassification(
                text=sentence,
                role=SentenceRole.LEGAL_HOLDING,
                confidence=0.9,
                signals={"has_formulation": True},
                formulation_type=formulation.formulation_type
            )
        else:
            return SentenceClassification(
                text=sentence,
                role=SentenceRole.LEGAL_RULE,
                confidence=0.85,
                signals={"has_formulation": True},
                formulation_type=formulation.formulation_type
            )

    # Score each role based on signal patterns
    for role, patterns in ROLE_SIGNAL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                role_scores[role] += 1.0
                signals[f"{role.value}_signal"] = True

    # Determine best role
    best_role = max(role_scores, key=role_scores.get)
    best_score = role_scores[best_role]

    if best_score == 0:
        return SentenceClassification(
            text=sentence,
            role=SentenceRole.UNKNOWN,
            confidence=0.3,
            signals=signals
        )

    # Calculate confidence based on score and exclusivity
    total_score = sum(role_scores.values())
    confidence = (best_score / total_score) * 0.7 + 0.3 if total_score > 0 else 0.3

    return SentenceClassification(
        text=sentence,
        role=best_role,
        confidence=min(confidence, 0.8),  # Cap at 0.8 without formulation
        signals=signals
    )


def classify_sentence_roles(
    text: str,
    include_unknown: bool = True
) -> Dict[str, Any]:
    """
    Classify all sentences in text by their argumentative role.

    This is the main MCP-callable function for sentence classification.

    Args:
        text: Full text to analyze
        include_unknown: Whether to include sentences with unknown roles

    Returns:
        Dictionary with classified sentences grouped by role,
        formulations detected, and extraction metadata
    """
    # Split into sentences (simple approach - can be enhanced)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    # Classify each sentence
    classifications = []
    for sentence in sentences:
        classification = classify_sentence_role(sentence)
        if include_unknown or classification.role != SentenceRole.UNKNOWN:
            classifications.append(classification)

    # Detect all formulations in full text
    all_formulations = detect_legal_formulations(text)

    # Group by role
    by_role = {}
    for role in SentenceRole:
        role_sentences = [c for c in classifications if c.role == role]
        if role_sentences:
            by_role[role.value] = [
                {
                    "text": c.text,  # Full text - truncation happens in formatting
                    "confidence": c.confidence,
                    "formulation_type": c.formulation_type
                }
                for c in role_sentences
            ]

    # Build metadata
    total = len(classifications)
    role_counts = {role.value: len([c for c in classifications if c.role == role])
                   for role in SentenceRole}

    high_confidence = [c for c in classifications if c.confidence >= 0.8]

    return {
        "_meta": {
            "total_sentences": total,
            "role_distribution": role_counts,
            "high_confidence_count": len(high_confidence),
            "formulations_detected": len(all_formulations)
        },
        "sentences_by_role": by_role,
        "legal_formulations": [
            {
                "text": f.text,  # Full text - important for legal rules
                "type": f.formulation_type,
                "components": f.extracted_components,
                "confidence": f.confidence
            }
            for f in all_formulations[:20]  # Limit to top 20
        ],
        "legal_rules": [
            {"text": c.text, "confidence": c.confidence}
            for c in classifications
            if c.role == SentenceRole.LEGAL_RULE and c.confidence >= 0.7
        ][:15],
        "legal_holdings": [
            {"text": c.text, "confidence": c.confidence}
            for c in classifications
            if c.role == SentenceRole.LEGAL_HOLDING and c.confidence >= 0.7
        ][:10]
    }


def _smart_truncate(text: str, max_len: int = 500) -> str:
    """Truncate text at sentence boundary if possible."""
    if len(text) <= max_len:
        return text
    # Try to truncate at sentence boundary
    truncated = text[:max_len]
    # Look for last sentence ending
    for end in ['. ', '.) ', '." ', '; ']:
        last_end = truncated.rfind(end)
        if last_end > max_len // 2:  # Don't truncate too early
            return truncated[:last_end + 1]
    # No good sentence boundary, truncate at word
    last_space = truncated.rfind(' ')
    if last_space > max_len // 2:
        return truncated[:last_space] + "..."
    return truncated + "..."


def format_sentence_classification(result: Dict[str, Any]) -> str:
    """Format sentence classification results for display."""
    output = []
    output.append("=" * 70)
    output.append("SENTENCE ROLE CLASSIFICATION")
    output.append("=" * 70)

    meta = result.get("_meta", {})
    output.append(f"\nTotal sentences analyzed: {meta.get('total_sentences', 0)}")
    output.append(f"High-confidence classifications: {meta.get('high_confidence_count', 0)}")
    output.append(f"Legal formulations detected: {meta.get('formulations_detected', 0)}")

    # Role distribution
    output.append("\n--- ROLE DISTRIBUTION ---")
    for role, count in meta.get("role_distribution", {}).items():
        if count > 0:
            output.append(f"  {role}: {count}")

    # Legal formulations (high value) - show FULL text
    formulations = result.get("legal_formulations", [])
    if formulations:
        output.append("\n--- LEGAL FORMULATIONS (High Confidence Rules) ---")
        for f in formulations[:10]:
            output.append(f"\n  [{f['type'].upper()}] ({f['confidence']:.0%})")
            output.append(f"  {f['text']}")

    # Legal rules - show full text with smart truncation for very long ones
    rules = result.get("legal_rules", [])
    if rules:
        output.append("\n--- EXTRACTED LEGAL RULES ---")
        for r in rules[:10]:
            output.append(f"\n  ({r['confidence']:.0%}) {_smart_truncate(r['text'], 500)}")

    # Legal holdings - show full text
    holdings = result.get("legal_holdings", [])
    if holdings:
        output.append("\n--- LEGAL HOLDINGS ---")
        for h in holdings[:5]:
            output.append(f"\n  ({h['confidence']:.0%}) {_smart_truncate(h['text'], 500)}")

    return "\n".join(output)


# ============================================================================
# 1. VALIDATE CITATION ACCURACY
# ============================================================================

def validate_citation_accuracy(
    brief_text: str,
    case_texts: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Validate that citations in a brief actually support claimed propositions.

    Args:
        brief_text: The brief text containing citations and claims
        case_texts: Optional dict mapping case names to their full text

    Returns:
        JSON with validation results for each citation
    """
    results = {
        "total_citations_found": 0,
        "validated": 0,
        "flagged": 0,
        "citations": []
    }

    # Pattern to find citations with surrounding context
    # Matches: "proposition text. Case Name, Volume Reporter Page (Year)."
    # OUTCLAW FIX (2026-08-11): reporter class was [A-Za-z\.\s] which cannot
    # match digit-bearing reporters (F.3d, F.2d, F. Supp. 2d) -- widened to
    # [A-Za-z0-9\.\s]. See extraction/README.md.
    citation_patterns = [
        # Standard citation with proposition before
        r'([^.]+\.)\s*([A-Z][A-Za-z\'\-\s]+(?:v\.|vs\.)\s+[A-Z][A-Za-z\'\-\s,]+),?\s*(\d+)\s+([A-Za-z0-9\.\s]+)\s+(\d+)(?:,\s*(\d+))?\s*\(([^)]+)\)',
        # Citation with "See" signal
        r'(?:See|see|Cf\.|cf\.)\s+([A-Z][A-Za-z\'\-\s]+(?:v\.|vs\.)\s+[A-Z][A-Za-z\'\-\s,]+),?\s*(\d+)\s+([A-Za-z0-9\.\s]+)\s+(\d+)',
        # Parenthetical citation
        r'([A-Z][A-Za-z\'\-\s]+(?:v\.|vs\.)\s+[A-Z][A-Za-z\'\-\s,]+),?\s*(\d+)\s+([A-Za-z0-9\.\s]+)\s+(\d+)[^)]*\(([^)]+)\)',
    ]

    # Find all citations
    found_citations = []
    for pattern in citation_patterns:
        matches = re.finditer(pattern, brief_text)
        for match in matches:
            groups = match.groups()
            citation_info = {
                "full_match": match.group(0),
                "start": match.start(),
                "end": match.end()
            }
            found_citations.append(citation_info)

    # Extract context around each citation
    for cite in found_citations:
        # Get text BEFORE the citation (the proposition being supported)
        text_before = brief_text[max(0, cite["start"] - 300):cite["start"]]

        # Find the last complete sentence before the citation
        # Split on sentence endings but avoid splitting on common abbreviations
        text_before_clean = re.sub(r'(\bv\.|vs\.|U\.S\.|F\.\d+d|S\.\s*Ct\.|L\.\s*Ed)', lambda m: m.group().replace('.', '@'), text_before)
        sentences = re.split(r'(?<=[.!?])\s+', text_before_clean)

        # Get the last sentence and restore periods
        if sentences:
            claimed_prop = sentences[-1].replace('@', '.').strip()
            # If the last "sentence" is very short, include the one before
            if len(claimed_prop) < 30 and len(sentences) > 1:
                claimed_prop = (sentences[-2] + " " + sentences[-1]).replace('@', '.').strip()
        else:
            claimed_prop = text_before.strip()[-200:]

        # Parse the case name from citation
        case_match = re.search(r'([A-Z][A-Za-z\'\-\s]+(?:v\.|vs\.)\s+[A-Z][A-Za-z\'\-\s,]+)', cite["full_match"])
        case_name = case_match.group(1).strip() if case_match else "Unknown"

        citation_result = {
            "citation": cite["full_match"][:100],
            "case_name": case_name,
            "claimed_proposition": claimed_prop.strip()[:200],
            "actual_holding": "[Requires case text to verify]",
            "matches": None,
            "confidence": 0,
            "flags": []
        }

        # If we have the case text, attempt to verify
        if case_texts and case_name in case_texts:
            case_text = case_texts[case_name]
            # Check if key terms from proposition appear in case
            prop_terms = set(re.findall(r'\b[a-z]{4,}\b', claimed_prop.lower()))
            case_terms = set(re.findall(r'\b[a-z]{4,}\b', case_text.lower()))
            overlap = prop_terms & case_terms

            citation_result["confidence"] = min(100, int(len(overlap) / max(len(prop_terms), 1) * 100))
            citation_result["matches"] = citation_result["confidence"] > 50

            if citation_result["confidence"] < 30:
                citation_result["flags"].append("LOW_CONFIDENCE: Key terms not found in case")
        else:
            citation_result["flags"].append("UNVERIFIED: Case text not provided")

        # Check for common citation errors
        if "holding" in claimed_prop.lower() and "dicta" not in claimed_prop.lower():
            # Claiming something is a holding - verify it's not dicta
            citation_result["flags"].append("CHECK: Verify this is holding, not dicta")

        if re.search(r'\b(all|every|always|never|must)\b', claimed_prop.lower()):
            citation_result["flags"].append("CHECK: Absolute language - verify case supports this breadth")

        results["citations"].append(citation_result)

    results["total_citations_found"] = len(found_citations)
    results["validated"] = sum(1 for c in results["citations"] if c["matches"] == True)
    results["flagged"] = sum(1 for c in results["citations"] if c["flags"])

    return results


def validate_citation_accuracy_mcp(brief_text: str) -> str:
    """MCP wrapper for validate_citation_accuracy."""
    result = validate_citation_accuracy(brief_text)

    output = []
    output.append("CITATION ACCURACY VALIDATION")
    output.append("=" * 60)
    output.append(f"Total citations found: {result['total_citations_found']}")
    output.append(f"Validated: {result['validated']}")
    output.append(f"Flagged for review: {result['flagged']}")
    output.append("")

    for i, cite in enumerate(result["citations"], 1):
        output.append(f"[{i}] {cite['case_name']}")
        output.append(f"    Claimed: {cite['claimed_proposition'][:100]}...")
        output.append(f"    Confidence: {cite['confidence']}%")
        if cite["flags"]:
            for flag in cite["flags"]:
                output.append(f"    [!] {flag}")
        output.append("")

    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 2. EXTRACT RECORD FACTS
# ============================================================================

def extract_record_facts(record_text: str, document_name: str = "Record") -> Dict[str, Any]:
    """
    Extract legally significant facts from record documents.

    Args:
        record_text: Text from deposition, exhibit, discovery, etc.
        document_name: Name/identifier of the source document

    Returns:
        JSON with extracted facts and citations
    """
    results = {
        "document": document_name,
        "facts": [],
        "dates_found": [],
        "witnesses_mentioned": [],
        "exhibits_referenced": []
    }

    # Split into paragraphs/sections
    paragraphs = re.split(r'\n\s*\n', record_text)

    # Patterns for legally significant content
    fact_indicators = [
        r'\b(stated|testified|admitted|acknowledged|confirmed|denied|claimed|alleged)\b',
        r'\b(on or about|approximately|at that time|thereafter|subsequently)\b',
        r'\b(document shows|evidence indicates|record reflects)\b',
        r'\b(plaintiff|defendant|witness|deponent)\s+\w+',
    ]

    # Date patterns
    date_pattern = r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b'

    # Witness/party patterns
    witness_pattern = r'(?:Mr\.|Ms\.|Mrs\.|Dr\.)\s+([A-Z][a-z]+)|([A-Z][a-z]+)\s+(?:testified|stated|admitted)'

    # Page/line reference patterns (for depositions)
    page_line_pattern = r'(?:page|p\.|pg\.)\s*(\d+)(?:\s*,?\s*(?:line|l\.|ln\.)\s*(\d+))?'

    for i, para in enumerate(paragraphs):
        if len(para.strip()) < 20:
            continue

        # Check if paragraph contains fact indicators
        is_significant = any(re.search(p, para, re.IGNORECASE) for p in fact_indicators)

        if is_significant or len(para) > 100:
            # Extract dates
            dates = re.findall(date_pattern, para)

            # Extract any page/line references
            page_refs = re.findall(page_line_pattern, para, re.IGNORECASE)

            # Build record cite
            if page_refs:
                page, line = page_refs[0]
                record_cite = f"{document_name} at {page}" + (f":{line}" if line else "")
            else:
                record_cite = f"{document_name} at [PAGE]"

            # Extract the core fact
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sent in sentences:
                if len(sent) > 30 and any(re.search(p, sent, re.IGNORECASE) for p in fact_indicators):
                    fact_entry = {
                        "fact": sent.strip()[:300],
                        "record_cite": record_cite,
                        "date": dates[0] if dates else None,
                        "source": document_name,
                        "significance": "potential",
                        "supporting_evidence": []
                    }

                    # Classify significance
                    if re.search(r'\b(admitted|acknowledged|conceded)\b', sent, re.IGNORECASE):
                        fact_entry["significance"] = "admission"
                    elif re.search(r'\b(denied|disputed|contested)\b', sent, re.IGNORECASE):
                        fact_entry["significance"] = "disputed"
                    elif re.search(r'\b(document|exhibit|evidence)\s+shows\b', sent, re.IGNORECASE):
                        fact_entry["significance"] = "documentary"

                    results["facts"].append(fact_entry)

            results["dates_found"].extend(dates)

    # Extract witnesses
    witnesses = re.findall(witness_pattern, record_text)
    results["witnesses_mentioned"] = list(set(w[0] or w[1] for w in witnesses if w[0] or w[1]))

    # Extract exhibit references
    exhibit_pattern = r'(?:Exhibit|Ex\.|Exh\.)\s*([A-Z0-9\-]+)'
    results["exhibits_referenced"] = list(set(re.findall(exhibit_pattern, record_text)))

    # Deduplicate dates
    results["dates_found"] = list(set(results["dates_found"]))

    return results


def extract_record_facts_mcp(record_text: str, document_name: str = "Record") -> str:
    """MCP wrapper for extract_record_facts."""
    result = extract_record_facts(record_text, document_name)

    output = []
    output.append("RECORD FACTS EXTRACTION")
    output.append("=" * 60)
    output.append(f"Document: {result['document']}")
    output.append(f"Facts extracted: {len(result['facts'])}")
    output.append(f"Dates found: {len(result['dates_found'])}")
    output.append(f"Witnesses: {', '.join(result['witnesses_mentioned']) or 'None identified'}")
    output.append(f"Exhibits: {', '.join(result['exhibits_referenced']) or 'None referenced'}")
    output.append("")

    output.append("EXTRACTED FACTS:")
    output.append("-" * 40)
    for i, fact in enumerate(result["facts"], 1):
        output.append(f"[{i}] [{fact['significance'].upper()}]")
        output.append(f"    {fact['fact'][:150]}...")
        output.append(f"    Cite: {fact['record_cite']}")
        if fact["date"]:
            output.append(f"    Date: {fact['date']}")
        output.append("")

    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 3. MAP FACTS TO ELEMENTS
# ============================================================================

def map_facts_to_elements(
    claim: str,
    elements: List[str],
    facts: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Map extracted facts to legal claim elements.

    Args:
        claim: The legal claim (e.g., "42 U.S.C. 1983 excessive force")
        elements: List of required elements for the claim
        facts: List of fact dicts with 'fact' and 'record_cite' keys

    Returns:
        JSON with element-by-element mapping and gap analysis
    """
    results = {
        "claim": claim,
        "total_elements": len(elements),
        "elements_satisfied": 0,
        "elements_weak": 0,
        "elements_missing": 0,
        "element_analysis": [],
        "overall_sufficiency": 0
    }

    for element in elements:
        element_result = {
            "element": element,
            "supporting_facts": [],
            "record_cites": [],
            "sufficiency_score": 0,
            "gaps": [],
            "strength": "missing"
        }

        # Extract key terms from element
        element_terms = set(re.findall(r'\b[a-z]{3,}\b', element.lower()))
        # Remove common legal filler words
        filler = {'the', 'and', 'that', 'was', 'were', 'has', 'had', 'been', 'will', 'would', 'could', 'should', 'must', 'may', 'can'}
        element_terms -= filler

        # Score each fact against this element
        matching_facts = []
        for fact_dict in facts:
            fact_text = fact_dict.get("fact", "")
            fact_terms = set(re.findall(r'\b[a-z]{3,}\b', fact_text.lower()))

            overlap = element_terms & fact_terms
            if overlap:
                score = len(overlap) / max(len(element_terms), 1)
                matching_facts.append({
                    "fact": fact_text,
                    "cite": fact_dict.get("record_cite", ""),
                    "score": score,
                    "matching_terms": list(overlap)
                })

        # Sort by relevance and take top matches
        matching_facts.sort(key=lambda x: x["score"], reverse=True)
        top_facts = matching_facts[:3]

        if top_facts:
            element_result["supporting_facts"] = [f["fact"] for f in top_facts]
            element_result["record_cites"] = [f["cite"] for f in top_facts if f["cite"]]
            avg_score = sum(f["score"] for f in top_facts) / len(top_facts)
            element_result["sufficiency_score"] = min(100, int(avg_score * 100))

            if element_result["sufficiency_score"] >= 70:
                element_result["strength"] = "strong"
                results["elements_satisfied"] += 1
            elif element_result["sufficiency_score"] >= 40:
                element_result["strength"] = "weak"
                results["elements_weak"] += 1
                element_result["gaps"].append("Supporting facts partially address element - strengthen with additional evidence")
            else:
                element_result["strength"] = "insufficient"
                results["elements_missing"] += 1
                element_result["gaps"].append("Facts do not adequately address this element")
        else:
            results["elements_missing"] += 1
            element_result["gaps"].append("No facts found addressing this element")

        results["element_analysis"].append(element_result)

    # Calculate overall sufficiency
    if results["total_elements"] > 0:
        satisfied_weight = results["elements_satisfied"] * 1.0
        weak_weight = results["elements_weak"] * 0.5
        results["overall_sufficiency"] = int((satisfied_weight + weak_weight) / results["total_elements"] * 100)

    return results


def map_facts_to_elements_mcp(
    claim: str,
    elements: List[str],
    facts: List[Dict[str, str]]
) -> str:
    """MCP wrapper for map_facts_to_elements."""
    result = map_facts_to_elements(claim, elements, facts)

    output = []
    output.append("FACTS-TO-ELEMENTS MAPPING")
    output.append("=" * 60)
    output.append(f"Claim: {result['claim']}")
    output.append(f"Overall Sufficiency: {result['overall_sufficiency']}%")
    output.append("")
    output.append(f"  Strong elements:  {result['elements_satisfied']}/{result['total_elements']}")
    output.append(f"  Weak elements:    {result['elements_weak']}/{result['total_elements']}")
    output.append(f"  Missing proof:    {result['elements_missing']}/{result['total_elements']}")
    output.append("")

    for i, elem in enumerate(result["element_analysis"], 1):
        strength_marker = {"strong": "[+]", "weak": "[~]", "insufficient": "[-]", "missing": "[X]"}
        marker = strength_marker.get(elem["strength"], "[?]")

        output.append(f"{marker} Element {i}: {elem['element']}")
        output.append(f"    Sufficiency: {elem['sufficiency_score']}%")

        if elem["supporting_facts"]:
            output.append("    Supporting facts:")
            for j, fact in enumerate(elem["supporting_facts"][:2], 1):
                output.append(f"      {j}. {fact[:80]}...")
            if elem["record_cites"]:
                output.append(f"    Cites: {', '.join(elem['record_cites'][:3])}")

        if elem["gaps"]:
            for gap in elem["gaps"]:
                output.append(f"    [GAP] {gap}")
        output.append("")

    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 4. DETECT FACTUAL CONTRADICTIONS
# ============================================================================

def detect_factual_contradictions(
    documents: Dict[str, str]
) -> Dict[str, Any]:
    """
    Detect contradictions between multiple documents.

    Args:
        documents: Dict mapping document names to their text

    Returns:
        JSON with detected contradictions
    """
    results = {
        "documents_analyzed": list(documents.keys()),
        "total_contradictions": 0,
        "contradictions": [],
        "potential_omissions": []
    }

    # Extract factual assertions from each document
    doc_facts = {}
    for doc_name, doc_text in documents.items():
        facts = []

        # Look for factual statements
        fact_patterns = [
            r'([A-Z][^.]*(?:stated|testified|occurred|happened|was|were|did|had)[^.]*\.)',
            r'(On [^.]+, [^.]+\.)',
            r'([A-Z][^.]*(?:admitted|acknowledged|denied|claimed)[^.]*\.)',
        ]

        for pattern in fact_patterns:
            matches = re.findall(pattern, doc_text)
            facts.extend(matches)

        # Also extract date-specific facts
        date_facts = re.findall(r'([^.]*\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}[^.]*\.)', doc_text)
        facts.extend(date_facts)

        doc_facts[doc_name] = list(set(facts))

    # Compare facts across documents
    doc_names = list(documents.keys())
    for i, doc_a in enumerate(doc_names):
        for doc_b in doc_names[i+1:]:
            facts_a = doc_facts[doc_a]
            facts_b = doc_facts[doc_b]

            for fact_a in facts_a:
                # Extract key entities and dates from fact_a
                entities_a = set(re.findall(r'\b[A-Z][a-z]+\b', fact_a))
                dates_a = set(re.findall(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}', fact_a))

                for fact_b in facts_b:
                    entities_b = set(re.findall(r'\b[A-Z][a-z]+\b', fact_b))
                    dates_b = set(re.findall(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}', fact_b))

                    # Check if facts discuss same entities/events
                    entity_overlap = entities_a & entities_b
                    date_overlap = dates_a & dates_b

                    if entity_overlap or date_overlap:
                        # Check for contradicting language
                        contradiction_type = None

                        # Direct contradictions
                        if (re.search(r'\bdid\b', fact_a) and re.search(r'\bdid not\b', fact_b)) or \
                           (re.search(r'\bdid not\b', fact_a) and re.search(r'\bdid\b', fact_b)):
                            contradiction_type = ContradictionType.DIRECT_CONFLICT

                        elif (re.search(r'\bwas\b', fact_a) and re.search(r'\bwas not\b', fact_b)) or \
                             (re.search(r'\bwas not\b', fact_a) and re.search(r'\bwas\b', fact_b)):
                            contradiction_type = ContradictionType.DIRECT_CONFLICT

                        # Inconsistent details
                        elif re.search(r'\b(approximately|about|around)\s+(\d+)', fact_a) and \
                             re.search(r'\b(approximately|about|around)\s+(\d+)', fact_b):
                            nums_a = re.findall(r'\b(\d+)\b', fact_a)
                            nums_b = re.findall(r'\b(\d+)\b', fact_b)
                            if nums_a and nums_b and nums_a[0] != nums_b[0]:
                                contradiction_type = ContradictionType.INCONSISTENCY

                        if contradiction_type:
                            results["contradictions"].append({
                                "fact_a": fact_a[:200],
                                "source_a": doc_a,
                                "fact_b": fact_b[:200],
                                "source_b": doc_b,
                                "contradiction_type": contradiction_type.value,
                                "shared_entities": list(entity_overlap)[:5],
                                "shared_dates": list(date_overlap)
                            })
                            results["total_contradictions"] += 1

    # Check for omissions (facts in one doc not addressed in another)
    for i, doc_a in enumerate(doc_names):
        for doc_b in doc_names[i+1:]:
            # Find significant facts in doc_a
            for fact in doc_facts[doc_a][:10]:  # Check first 10 significant facts
                # See if any similar fact exists in doc_b
                fact_terms = set(re.findall(r'\b[a-z]{4,}\b', fact.lower()))

                found_similar = False
                for other_fact in doc_facts[doc_b]:
                    other_terms = set(re.findall(r'\b[a-z]{4,}\b', other_fact.lower()))
                    if len(fact_terms & other_terms) > 3:
                        found_similar = True
                        break

                if not found_similar and len(fact) > 50:
                    results["potential_omissions"].append({
                        "fact": fact[:200],
                        "present_in": doc_a,
                        "missing_from": doc_b,
                        "type": ContradictionType.OMISSION.value
                    })

    # Limit omissions to most significant
    results["potential_omissions"] = results["potential_omissions"][:10]

    return results


def detect_factual_contradictions_mcp(documents: Dict[str, str]) -> str:
    """MCP wrapper for detect_factual_contradictions."""
    result = detect_factual_contradictions(documents)

    output = []
    output.append("FACTUAL CONTRADICTION ANALYSIS")
    output.append("=" * 60)
    output.append(f"Documents analyzed: {', '.join(result['documents_analyzed'])}")
    output.append(f"Contradictions found: {result['total_contradictions']}")
    output.append(f"Potential omissions: {len(result['potential_omissions'])}")
    output.append("")

    if result["contradictions"]:
        output.append("CONTRADICTIONS:")
        output.append("-" * 40)
        for i, contra in enumerate(result["contradictions"], 1):
            output.append(f"[{i}] {contra['contradiction_type'].upper()}")
            output.append(f"    {contra['source_a']}: {contra['fact_a'][:100]}...")
            output.append(f"    vs.")
            output.append(f"    {contra['source_b']}: {contra['fact_b'][:100]}...")
            if contra["shared_entities"]:
                output.append(f"    Re: {', '.join(contra['shared_entities'])}")
            output.append("")

    if result["potential_omissions"]:
        output.append("POTENTIAL OMISSIONS:")
        output.append("-" * 40)
        for i, omit in enumerate(result["potential_omissions"][:5], 1):
            output.append(f"[{i}] Present in {omit['present_in']}, missing from {omit['missing_from']}")
            output.append(f"    {omit['fact'][:100]}...")
            output.append("")

    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 5. EXTRACT PROCEDURAL CONTEXT
# ============================================================================

def extract_procedural_context(text: str) -> Dict[str, Any]:
    """
    Extract procedural posture, standard of review, and burden from case/brief.

    Args:
        text: Case opinion or brief text

    Returns:
        JSON with procedural context
    """
    results = {
        "posture": None,
        "posture_confidence": 0,
        "standard_of_review": None,
        "standard_confidence": 0,
        "burden_of_proof": None,
        "jurisdictional_basis": None,
        "key_procedural_facts": [],
        "procedural_history": []
    }

    text_lower = text.lower()

    # Detect procedural posture
    posture_patterns = {
        ProceduralPosture.MOTION_TO_DISMISS: [
            r'motion to dismiss', r'12\(b\)\(6\)', r'rule 12\(b\)',
            r'failure to state a claim', r'dismissed for failure'
        ],
        ProceduralPosture.SUMMARY_JUDGMENT: [
            r'summary judgment', r'rule 56', r'no genuine issue',
            r'no genuine dispute', r'undisputed facts'
        ],
        ProceduralPosture.TRIAL: [
            r'jury verdict', r'bench trial', r'trial court found',
            r'after trial', r'jury found', r'trial on the merits'
        ],
        ProceduralPosture.APPEAL: [
            r'on appeal', r'appellant', r'appellee', r'we review',
            r'this court reviews', r'appeals from', r'circuit review'
        ],
        ProceduralPosture.PRELIMINARY_INJUNCTION: [
            r'preliminary injunction', r'temporary restraining',
            r'likelihood of success', r'irreparable harm'
        ],
        ProceduralPosture.CLASS_CERTIFICATION: [
            r'class certification', r'rule 23', r'class action',
            r'commonality', r'typicality', r'adequacy'
        ],
        ProceduralPosture.HABEAS: [
            r'habeas corpus', r'2254', r'2255', r'collateral review',
            r'post-conviction'
        ]
    }

    for posture, patterns in posture_patterns.items():
        matches = sum(1 for p in patterns if re.search(p, text_lower))
        if matches > results["posture_confidence"]:
            results["posture"] = posture.value
            results["posture_confidence"] = min(100, matches * 25)

    # Detect standard of review
    standard_patterns = {
        "de_novo": [
            r'de novo', r'review de novo', r'questions of law',
            r'plenary review', r'no deference'
        ],
        "clear_error": [
            r'clear error', r'clearly erroneous', r'factual findings',
            r'findings of fact'
        ],
        "abuse_of_discretion": [
            r'abuse of discretion', r'discretionary', r'abused its discretion',
            r'within.*discretion'
        ],
        "substantial_evidence": [
            r'substantial evidence', r'supported by substantial',
            r'administrative record'
        ],
        "arbitrary_and_capricious": [
            r'arbitrary and capricious', r'arbitrary or capricious',
            r'agency action'
        ],
        "plain_error": [
            r'plain error', r'obvious error', r'manifest injustice'
        ]
    }

    for standard, patterns in standard_patterns.items():
        matches = sum(1 for p in patterns if re.search(p, text_lower))
        if matches > results["standard_confidence"]:
            results["standard_of_review"] = standard
            results["standard_confidence"] = min(100, matches * 30)

    # Detect burden of proof
    burden_patterns = {
        "preponderance": [r'preponderance of the evidence', r'more likely than not'],
        "clear_and_convincing": [r'clear and convincing', r'highly probable'],
        "beyond_reasonable_doubt": [r'beyond a reasonable doubt', r'reasonable doubt'],
        "prima_facie": [r'prima facie', r'makes out a prima facie']
    }

    for burden, patterns in burden_patterns.items():
        if any(re.search(p, text_lower) for p in patterns):
            results["burden_of_proof"] = burden
            break

    # Detect jurisdictional basis
    jurisdiction_patterns = {
        "federal_question": [r'28 u\.?s\.?c\.?\s*1331', r'federal question', r'arising under'],
        "diversity": [r'28 u\.?s\.?c\.?\s*1332', r'diversity jurisdiction', r'citizens of different states'],
        "supplemental": [r'28 u\.?s\.?c\.?\s*1367', r'supplemental jurisdiction', r'pendant'],
        "removal": [r'28 u\.?s\.?c\.?\s*1441', r'removed from state', r'removal jurisdiction'],
        "1983": [r'42 u\.?s\.?c\.?\s*1983', r'section 1983', r'civil rights'],
        "habeas": [r'28 u\.?s\.?c\.?\s*2254', r'28 u\.?s\.?c\.?\s*2255', r'habeas corpus']
    }

    for basis, patterns in jurisdiction_patterns.items():
        if any(re.search(p, text_lower) for p in patterns):
            results["jurisdictional_basis"] = basis
            break

    # Extract procedural history
    history_indicators = [
        r'(The district court [^.]+\.)',
        r'(The [a-z]+ court [^.]+\.)',
        r'([A-Z][^.]*filed [^.]+\.)',
        r'([A-Z][^.]*moved for [^.]+\.)',
        r'([A-Z][^.]*appealed [^.]+\.)',
        r'(This case comes to us [^.]+\.)',
    ]

    for pattern in history_indicators:
        matches = re.findall(pattern, text)
        results["procedural_history"].extend(matches[:3])

    results["procedural_history"] = list(set(results["procedural_history"]))[:5]

    # Extract key procedural facts
    proc_fact_patterns = [
        r'(motion was (?:granted|denied)[^.]*\.)',
        r'(court (?:granted|denied) [^.]+\.)',
        r'(judgment was entered [^.]+\.)',
        r'(case was (?:dismissed|remanded)[^.]+\.)',
    ]

    for pattern in proc_fact_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        results["key_procedural_facts"].extend(matches[:2])

    results["key_procedural_facts"] = list(set(results["key_procedural_facts"]))[:5]

    return results


def extract_procedural_context_mcp(text: str) -> str:
    """MCP wrapper for extract_procedural_context."""
    result = extract_procedural_context(text)

    output = []
    output.append("PROCEDURAL CONTEXT EXTRACTION")
    output.append("=" * 60)

    output.append(f"Posture: {result['posture'] or 'Unknown'} ({result['posture_confidence']}% confidence)")
    output.append(f"Standard of Review: {result['standard_of_review'] or 'Unknown'} ({result['standard_confidence']}% confidence)")
    output.append(f"Burden of Proof: {result['burden_of_proof'] or 'Not specified'}")
    output.append(f"Jurisdictional Basis: {result['jurisdictional_basis'] or 'Not specified'}")
    output.append("")

    if result["procedural_history"]:
        output.append("PROCEDURAL HISTORY:")
        for i, hist in enumerate(result["procedural_history"], 1):
            output.append(f"  {i}. {hist[:100]}...")

    if result["key_procedural_facts"]:
        output.append("")
        output.append("KEY PROCEDURAL FACTS:")
        for i, fact in enumerate(result["key_procedural_facts"], 1):
            output.append(f"  {i}. {fact[:100]}...")

    output.append("")
    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 6. EXTRACT REASONING PATTERNS
# ============================================================================

def extract_reasoning_patterns(case_text: str) -> Dict[str, Any]:
    """
    Extract argument/reasoning types used in a case opinion.

    Args:
        case_text: Full text of case opinion

    Returns:
        JSON with detected reasoning patterns
    """
    results = {
        "patterns_found": [],
        "dominant_reasoning": None,
        "reasoning_summary": {}
    }

    reasoning_indicators = {
        ReasoningType.ANALOGICAL: {
            "patterns": [
                r'(like in [A-Z][^,]+, (?:where|here)[^.]+\.)',
                r'(similar to [A-Z][^,]+[^.]+\.)',
                r'(as in [A-Z][^,]+[^.]+\.)',
                r'(analogous to [^.]+\.)',
                r'(just as [^.]+, so too [^.]+\.)',
                r'(this case is (?:indistinguishable|similar)[^.]+\.)',
            ],
            "keywords": ['analogous', 'similar', 'like in', 'as in', 'indistinguishable', 'on all fours']
        },
        ReasoningType.POLICY: {
            "patterns": [
                r'(policy (?:considerations|concerns|reasons)[^.]+\.)',
                r'(would (?:undermine|promote|serve)[^.]+\.)',
                r'(in the interest of [^.]+\.)',
                r'(public policy [^.]+\.)',
                r'(practical (?:consequences|effects|implications)[^.]+\.)',
            ],
            "keywords": ['policy', 'practical', 'consequences', 'public interest', 'would undermine', 'would promote']
        },
        ReasoningType.TEXTUAL: {
            "patterns": [
                r'(plain (?:language|meaning|text)[^.]+\.)',
                r'(the (?:statute|text) (?:says|states|provides)[^.]+\.)',
                r'(ordinary meaning [^.]+\.)',
                r'(unambiguous [^.]+\.)',
                r'(clear from the text[^.]+\.)',
            ],
            "keywords": ['plain meaning', 'plain language', 'text', 'statutory language', 'unambiguous', 'ordinary meaning']
        },
        ReasoningType.PURPOSIVE: {
            "patterns": [
                r'(Congress intended [^.]+\.)',
                r'(legislative (?:history|intent|purpose)[^.]+\.)',
                r'(purpose of (?:the statute|this provision)[^.]+\.)',
                r'(drafters (?:intended|meant)[^.]+\.)',
                r'(enacted to [^.]+\.)',
            ],
            "keywords": ['legislative history', 'intent', 'purpose', 'Congress intended', 'drafters']
        },
        ReasoningType.STRUCTURAL: {
            "patterns": [
                r'(read (?:together|in context)[^.]+\.)',
                r'(statutory (?:scheme|structure)[^.]+\.)',
                r'(in pari materia[^.]+\.)',
                r'(consistent with [^.]+ provisions[^.]+\.)',
                r'(structure of the (?:statute|Act)[^.]+\.)',
            ],
            "keywords": ['structure', 'scheme', 'in pari materia', 'read together', 'statutory context']
        },
        ReasoningType.CONSTITUTIONAL_TIER: {
            "patterns": [
                r'(strict scrutiny[^.]+\.)',
                r'(intermediate scrutiny[^.]+\.)',
                r'(rational basis[^.]+\.)',
                r'(compelling (?:interest|government interest)[^.]+\.)',
                r'(narrowly tailored[^.]+\.)',
                r'(least restrictive means[^.]+\.)',
            ],
            "keywords": ['strict scrutiny', 'intermediate scrutiny', 'rational basis', 'compelling interest', 'narrowly tailored']
        },
        ReasoningType.HISTORICAL: {
            "patterns": [
                r'(at the (?:time of the )?founding[^.]+\.)',
                r'(historical (?:practice|understanding)[^.]+\.)',
                r'(original (?:meaning|understanding|intent)[^.]+\.)',
                r'((?:18th|19th) century [^.]+\.)',
                r'(framers (?:understood|intended)[^.]+\.)',
            ],
            "keywords": ['founding', 'original', 'historical', 'framers', 'tradition']
        },
        ReasoningType.PRECEDENTIAL: {
            "patterns": [
                r'(we held in [A-Z][^.]+\.)',
                r'(binding precedent[^.]+\.)',
                r'(stare decisis[^.]+\.)',
                r'(this Court has (?:repeatedly|consistently)[^.]+\.)',
                r'(established in [A-Z][^.]+\.)',
            ],
            "keywords": ['we held', 'stare decisis', 'binding', 'precedent', 'controlling']
        }
    }

    text_lower = case_text.lower()

    for reasoning_type, indicators in reasoning_indicators.items():
        type_results = {
            "reasoning_type": reasoning_type.value,
            "instances": [],
            "strength_score": 0,
            "keyword_count": 0
        }

        # Find pattern matches
        for pattern in indicators["patterns"]:
            matches = re.findall(pattern, case_text, re.IGNORECASE)
            for match in matches[:3]:  # Limit to 3 per pattern
                type_results["instances"].append({
                    "text_snippet": match[:200] if isinstance(match, str) else match[0][:200],
                    "pattern_type": "explicit"
                })

        # Count keywords
        for keyword in indicators["keywords"]:
            count = len(re.findall(r'\b' + re.escape(keyword) + r'\b', text_lower))
            type_results["keyword_count"] += count

        # Calculate strength score
        instance_score = min(50, len(type_results["instances"]) * 15)
        keyword_score = min(50, type_results["keyword_count"] * 10)
        type_results["strength_score"] = instance_score + keyword_score

        if type_results["instances"] or type_results["keyword_count"] > 0:
            results["patterns_found"].append(type_results)
            results["reasoning_summary"][reasoning_type.value] = type_results["strength_score"]

    # Sort by strength
    results["patterns_found"].sort(key=lambda x: x["strength_score"], reverse=True)

    # Identify dominant reasoning
    if results["patterns_found"]:
        results["dominant_reasoning"] = results["patterns_found"][0]["reasoning_type"]

    return results


def extract_reasoning_patterns_mcp(case_text: str) -> str:
    """MCP wrapper for extract_reasoning_patterns."""
    result = extract_reasoning_patterns(case_text)

    output = []
    output.append("REASONING PATTERN ANALYSIS")
    output.append("=" * 60)
    output.append(f"Dominant Reasoning: {result['dominant_reasoning'] or 'None detected'}")
    output.append("")

    output.append("PATTERNS FOUND (by strength):")
    output.append("-" * 40)

    for pattern in result["patterns_found"]:
        if pattern["strength_score"] > 0:
            output.append(f"[{pattern['strength_score']}] {pattern['reasoning_type'].upper()}")
            output.append(f"    Keywords found: {pattern['keyword_count']}")
            if pattern["instances"]:
                output.append("    Examples:")
                for inst in pattern["instances"][:2]:
                    output.append(f"      \"{inst['text_snippet'][:80]}...\"")
            output.append("")

    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 7. EXTRACT JUDGE PATTERNS
# ============================================================================

def extract_judge_patterns(
    opinions: List[Dict[str, str]],
    judge_name: str
) -> Dict[str, Any]:
    """
    Extract patterns from a judge's prior opinions.

    Args:
        opinions: List of dicts with 'text' and 'case_name' keys
        judge_name: Name of the judge

    Returns:
        JSON with judge's patterns
    """
    results = {
        "judge_name": judge_name,
        "opinions_analyzed": len(opinions),
        "reasoning_tendencies": [],
        "favored_authorities": [],
        "procedural_notes": [],
        "language_patterns": [],
        "reversal_indicators": []
    }

    # Aggregate reasoning patterns across all opinions
    all_reasoning = {}
    all_citations = []

    for opinion_dict in opinions:
        text = opinion_dict.get("text", "")

        # Extract reasoning patterns
        reasoning = extract_reasoning_patterns(text)
        for pattern in reasoning["patterns_found"]:
            rtype = pattern["reasoning_type"]
            if rtype not in all_reasoning:
                all_reasoning[rtype] = 0
            all_reasoning[rtype] += pattern["strength_score"]

        # Extract frequently cited cases
        case_citations = re.findall(r'([A-Z][A-Za-z\'\-\s]+(?:v\.|vs\.)\s+[A-Z][A-Za-z\'\-\s,]+),?\s*\d+\s+[A-Za-z0-9\.\s]+\s+\d+', text)
        all_citations.extend(case_citations)

        # Look for reversal/affirmance language
        if re.search(r'\b(reversed?|vacated?|remanded?)\b', text.lower()):
            results["reversal_indicators"].append(opinion_dict.get("case_name", "Unknown"))

    # Identify top reasoning tendencies
    sorted_reasoning = sorted(all_reasoning.items(), key=lambda x: x[1], reverse=True)
    results["reasoning_tendencies"] = [
        {"type": r[0], "aggregate_score": r[1]}
        for r in sorted_reasoning[:5]
    ]

    # Identify most frequently cited authorities
    citation_counts = {}
    for cite in all_citations:
        cite_clean = cite.strip()[:50]
        citation_counts[cite_clean] = citation_counts.get(cite_clean, 0) + 1

    sorted_citations = sorted(citation_counts.items(), key=lambda x: x[1], reverse=True)
    results["favored_authorities"] = [
        {"case": c[0], "frequency": c[1]}
        for c in sorted_citations[:10]
    ]

    # Extract procedural preferences
    for opinion_dict in opinions:
        text = opinion_dict.get("text", "").lower()

        if re.search(r'at this early stage', text):
            results["procedural_notes"].append("Cautious at motion to dismiss stage")
        if re.search(r'genuine (issue|dispute) of material fact', text):
            results["procedural_notes"].append("Careful fact analysis at summary judgment")
        if re.search(r'abuse of discretion', text):
            results["procedural_notes"].append("Emphasizes discretionary review standards")

    results["procedural_notes"] = list(set(results["procedural_notes"]))

    return results


def extract_judge_patterns_mcp(
    opinions: List[Dict[str, str]],
    judge_name: str
) -> str:
    """MCP wrapper for extract_judge_patterns."""
    result = extract_judge_patterns(opinions, judge_name)

    output = []
    output.append(f"JUDGE PATTERN ANALYSIS: {result['judge_name']}")
    output.append("=" * 60)
    output.append(f"Opinions analyzed: {result['opinions_analyzed']}")
    output.append("")

    if result["reasoning_tendencies"]:
        output.append("REASONING TENDENCIES:")
        for tend in result["reasoning_tendencies"]:
            output.append(f"  - {tend['type']}: {tend['aggregate_score']} (aggregate score)")

    output.append("")
    if result["favored_authorities"]:
        output.append("FREQUENTLY CITED AUTHORITIES:")
        for auth in result["favored_authorities"][:5]:
            output.append(f"  - {auth['case']} (cited {auth['frequency']}x)")

    output.append("")
    if result["procedural_notes"]:
        output.append("PROCEDURAL NOTES:")
        for note in result["procedural_notes"]:
            output.append(f"  - {note}")

    output.append("")
    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 8. EXTRACT CIRCUIT LAW
# ============================================================================

def extract_circuit_law(
    cases: List[Dict[str, str]],
    circuit: str
) -> Dict[str, Any]:
    """
    Extract circuit-specific rules and splits.

    Args:
        cases: List of dicts with 'text' and 'case_name' keys
        circuit: Circuit identifier (e.g., "9th Circuit", "5th Cir.")

    Returns:
        JSON with circuit law analysis
    """
    results = {
        "circuit": circuit,
        "cases_analyzed": len(cases),
        "binding_rules": [],
        "circuit_splits": [],
        "controlling_cases": [],
        "key_standards": []
    }

    all_rules = []
    split_indicators = []

    for case_dict in cases:
        text = case_dict.get("text", "")
        case_name = case_dict.get("case_name", "Unknown")

        # Extract rules/holdings
        rule_patterns = [
            r'(we (?:hold|held) that [^.]+\.)',
            r'(the rule (?:is|in this circuit is) [^.]+\.)',
            r'(this circuit (?:has held|requires|recognizes) [^.]+\.)',
            r'(under our precedent[^.]+\.)',
        ]

        for pattern in rule_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                all_rules.append({
                    "rule": match[:200],
                    "source": case_name
                })

        # Look for circuit split language
        split_patterns = [
            r'(other circuits (?:have held|disagree|take a different)[^.]+\.)',
            r'(circuit split[^.]+\.)',
            r'((?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|d\.?c\.?) circuit (?:holds|has held|disagrees)[^.]+\.)',
            r'(we (?:join|depart from|agree with|disagree with) (?:our sister|other) circuits[^.]+\.)',
        ]

        for pattern in split_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                split_indicators.append({
                    "text": match[:200],
                    "source": case_name
                })

        # Identify controlling case language
        if re.search(r'\b(en banc|supreme court|controlling)\b', text.lower()):
            results["controlling_cases"].append(case_name)

    # Deduplicate rules
    seen_rules = set()
    for rule in all_rules:
        rule_text = rule["rule"][:100]
        if rule_text not in seen_rules:
            seen_rules.add(rule_text)
            results["binding_rules"].append(rule)

    results["binding_rules"] = results["binding_rules"][:10]

    # Process circuit splits
    for split in split_indicators:
        # Try to identify the issue and positions
        results["circuit_splits"].append({
            "issue": split["text"][:100],
            "this_circuit_position": "See source case",
            "other_circuits": "See split language",
            "source": split["source"]
        })

    results["circuit_splits"] = results["circuit_splits"][:5]
    results["controlling_cases"] = list(set(results["controlling_cases"]))[:5]

    return results


def extract_circuit_law_mcp(
    cases: List[Dict[str, str]],
    circuit: str
) -> str:
    """MCP wrapper for extract_circuit_law."""
    result = extract_circuit_law(cases, circuit)

    output = []
    output.append(f"CIRCUIT LAW ANALYSIS: {result['circuit']}")
    output.append("=" * 60)
    output.append(f"Cases analyzed: {result['cases_analyzed']}")
    output.append("")

    if result["binding_rules"]:
        output.append("BINDING RULES:")
        output.append("-" * 40)
        for i, rule in enumerate(result["binding_rules"], 1):
            output.append(f"[{i}] {rule['rule'][:150]}...")
            output.append(f"    Source: {rule['source']}")
            output.append("")

    if result["circuit_splits"]:
        output.append("CIRCUIT SPLITS DETECTED:")
        output.append("-" * 40)
        for split in result["circuit_splits"]:
            output.append(f"  Issue: {split['issue'][:100]}...")
            output.append(f"  Source: {split['source']}")
            output.append("")

    if result["controlling_cases"]:
        output.append("CONTROLLING CASES:")
        for case in result["controlling_cases"]:
            output.append(f"  - {case}")

    output.append("")
    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 9. BUILD CHRONOLOGY
# ============================================================================

def build_chronology(
    documents: Dict[str, str]
) -> Dict[str, Any]:
    """
    Build a timeline from record documents.

    Args:
        documents: Dict mapping document names to text

    Returns:
        JSON with chronological timeline
    """
    results = {
        "documents_processed": list(documents.keys()),
        "timeline": [],
        "gaps": [],
        "date_range": {"earliest": None, "latest": None}
    }

    # Date patterns
    date_patterns = [
        (r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})', 'month_day_year'),
        (r'(\d{1,2})/(\d{1,2})/(\d{2,4})', 'numeric'),
        (r'(\d{4})-(\d{2})-(\d{2})', 'iso'),
    ]

    all_events = []

    for doc_name, doc_text in documents.items():
        # Find all dates with context
        for pattern, date_type in date_patterns:
            for match in re.finditer(pattern, doc_text):
                # Get surrounding context
                start = max(0, match.start() - 10)
                end = min(len(doc_text), match.end() + 150)
                context = doc_text[start:end]

                # Extract the event description
                event_match = re.search(r'[A-Z][^.]*\.', context)
                event_desc = event_match.group(0) if event_match else context[:100]

                # Normalize date
                date_str = match.group(0)

                # Determine significance
                significance = "routine"
                if re.search(r'\b(filed|served|testified|occurred|signed|executed)\b', event_desc.lower()):
                    significance = "key_event"
                elif re.search(r'\b(deadline|due|hearing|trial)\b', event_desc.lower()):
                    significance = "procedural"

                all_events.append({
                    "date": date_str,
                    "event": event_desc[:200],
                    "source": doc_name,
                    "significance": significance,
                    "sort_key": date_str  # Would need proper date parsing for accurate sorting
                })

    # Remove duplicates and sort
    seen = set()
    unique_events = []
    for event in all_events:
        key = (event["date"], event["event"][:50])
        if key not in seen:
            seen.add(key)
            unique_events.append(event)

    # Simple sort (proper implementation would parse dates)
    results["timeline"] = sorted(unique_events, key=lambda x: x["date"])[:50]

    # Identify gaps (simplified - would need date parsing)
    if len(results["timeline"]) >= 2:
        results["gaps"].append("Review timeline for unexplained gaps between events")

    return results


def build_chronology_mcp(documents: Dict[str, str]) -> str:
    """MCP wrapper for build_chronology."""
    result = build_chronology(documents)

    output = []
    output.append("CHRONOLOGY BUILDER")
    output.append("=" * 60)
    output.append(f"Documents processed: {', '.join(result['documents_processed'])}")
    output.append(f"Events found: {len(result['timeline'])}")
    output.append("")

    output.append("TIMELINE:")
    output.append("-" * 40)

    for event in result["timeline"]:
        sig_marker = {"key_event": "[KEY]", "procedural": "[PROC]", "routine": ""}
        marker = sig_marker.get(event["significance"], "")
        output.append(f"{event['date']} {marker}")
        output.append(f"  {event['event'][:100]}...")
        output.append(f"  Source: {event['source']}")
        output.append("")

    if result["gaps"]:
        output.append("GAPS/NOTES:")
        for gap in result["gaps"]:
            output.append(f"  [!] {gap}")

    output.append("")
    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 10. VALIDATE PLEADING ELEMENTS
# ============================================================================

# Common claim elements databases
CLAIM_ELEMENTS = {
    "1983_excessive_force": [
        "Acting under color of state law",
        "Deprivation of constitutional right",
        "Force used was objectively unreasonable",
        "Causation between force and injury"
    ],
    "1983_false_arrest": [
        "Acting under color of state law",
        "Deprivation of Fourth Amendment right",
        "Arrest without probable cause",
        "Causation"
    ],
    "negligence": [
        "Duty of care owed",
        "Breach of duty",
        "Causation (actual and proximate)",
        "Damages"
    ],
    "breach_of_contract": [
        "Valid contract existed",
        "Plaintiff performed or was excused",
        "Defendant breached",
        "Damages resulted"
    ],
    "fraud": [
        "False representation of material fact",
        "Knowledge of falsity (scienter)",
        "Intent to induce reliance",
        "Justifiable reliance",
        "Damages"
    ],
    "defamation": [
        "False statement of fact",
        "Publication to third party",
        "Fault (negligence or actual malice)",
        "Damages (or per se category)"
    ],
    "title_vii_discrimination": [
        "Member of protected class",
        "Qualified for position",
        "Adverse employment action",
        "Circumstances giving rise to inference of discrimination"
    ],
    "ada_discrimination": [
        "Disability within meaning of ADA",
        "Qualified individual",
        "Adverse action because of disability",
        "Failure to provide reasonable accommodation (if applicable)"
    ]
}


def validate_pleading_elements(
    pleading_text: str,
    claim_type: str
) -> Dict[str, Any]:
    """
    Validate that a pleading contains required elements.

    Args:
        pleading_text: Text of complaint or answer
        claim_type: Type of claim (e.g., "1983_excessive_force")

    Returns:
        JSON with element analysis
    """
    results = {
        "claim": claim_type,
        "required_elements": [],
        "pled_elements": [],
        "missing_elements": [],
        "sufficiency_scores": {},
        "overall_sufficiency": 0
    }

    # Get required elements
    if claim_type in CLAIM_ELEMENTS:
        results["required_elements"] = CLAIM_ELEMENTS[claim_type]
    else:
        # Try to match partial
        for key in CLAIM_ELEMENTS:
            if claim_type.lower() in key.lower() or key.lower() in claim_type.lower():
                results["required_elements"] = CLAIM_ELEMENTS[key]
                break

    if not results["required_elements"]:
        return {
            "error": f"Unknown claim type: {claim_type}",
            "available_claims": list(CLAIM_ELEMENTS.keys())
        }

    text_lower = pleading_text.lower()

    for element in results["required_elements"]:
        # Extract key terms from element
        element_terms = set(re.findall(r'\b[a-z]{4,}\b', element.lower()))
        element_terms -= {'that', 'the', 'and', 'was', 'were', 'been'}

        # Search for element in pleading
        found_indicators = []
        score = 0

        for term in element_terms:
            if term in text_lower:
                score += 20
                # Find the sentence containing the term
                pattern = rf'[^.]*\b{term}\b[^.]*\.'
                matches = re.findall(pattern, pleading_text, re.IGNORECASE)
                found_indicators.extend(matches[:2])

        score = min(100, score)
        results["sufficiency_scores"][element] = score

        if score >= 60:
            results["pled_elements"].append({
                "element": element,
                "score": score,
                "supporting_text": found_indicators[:2] if found_indicators else []
            })
        else:
            results["missing_elements"].append({
                "element": element,
                "score": score,
                "suggestion": f"Add specific allegations addressing: {element}"
            })

    # Calculate overall sufficiency
    if results["sufficiency_scores"]:
        results["overall_sufficiency"] = int(
            sum(results["sufficiency_scores"].values()) / len(results["sufficiency_scores"])
        )

    return results


def validate_pleading_elements_mcp(
    pleading_text: str,
    claim_type: str
) -> str:
    """MCP wrapper for validate_pleading_elements."""
    result = validate_pleading_elements(pleading_text, claim_type)

    output = []
    output.append("PLEADING ELEMENT VALIDATION")
    output.append("=" * 60)

    if "error" in result:
        output.append(f"Error: {result['error']}")
        output.append(f"Available claims: {', '.join(result['available_claims'])}")
        return "\n".join(output)

    output.append(f"Claim: {result['claim']}")
    output.append(f"Overall Sufficiency: {result['overall_sufficiency']}%")
    output.append(f"Elements pled: {len(result['pled_elements'])}/{len(result['required_elements'])}")
    output.append("")

    output.append("ELEMENT ANALYSIS:")
    output.append("-" * 40)

    for element in result["required_elements"]:
        score = result["sufficiency_scores"].get(element, 0)
        if score >= 60:
            output.append(f"[+] {element}")
            output.append(f"    Score: {score}%")
        else:
            output.append(f"[-] {element}")
            output.append(f"    Score: {score}%")
            output.append(f"    [!] Add allegations addressing this element")
        output.append("")

    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 11. EXTRACT CANONS AND RULES
# ============================================================================

INTERPRETATION_CANONS = {
    "plain_meaning": {
        "patterns": [
            r'plain meaning', r'ordinary meaning', r'common understanding',
            r'unambiguous', r'clear from the text', r'plain language'
        ],
        "description": "Text should be interpreted according to ordinary meaning"
    },
    "legislative_history": {
        "patterns": [
            r'legislative history', r'committee report', r'floor debate',
            r'sponsor.*statement', r'congressional intent'
        ],
        "description": "Use legislative history to determine intent"
    },
    "rule_of_lenity": {
        "patterns": [
            r'rule of lenity', r'ambiguity.*defendant', r'criminal statute.*narrowly',
            r'resolve.*doubt.*defendant'
        ],
        "description": "Ambiguous criminal statutes construed in favor of defendant"
    },
    "constitutional_avoidance": {
        "patterns": [
            r'constitutional.*avoid', r'avoid.*constitutional.*question',
            r'serious constitutional.*problem', r'construe.*avoid'
        ],
        "description": "Avoid interpretations raising constitutional issues"
    },
    "expressio_unius": {
        "patterns": [
            r'expressio unius', r'inclusion of one.*exclusion',
            r'express mention.*implied exclusion'
        ],
        "description": "Expression of one thing excludes others"
    },
    "ejusdem_generis": {
        "patterns": [
            r'ejusdem generis', r'same kind', r'general words.*specific',
            r'similar nature'
        ],
        "description": "General terms limited by specific ones preceding them"
    },
    "noscitur_a_sociis": {
        "patterns": [
            r'noscitur a sociis', r'known by.*company', r'surrounding words',
            r'context.*surrounding'
        ],
        "description": "Words known by their companions/context"
    },
    "whole_act_rule": {
        "patterns": [
            r'read.*whole', r'statutory scheme', r'in pari materia',
            r'consistent.*provisions', r'harmonize'
        ],
        "description": "Statute should be read as a coherent whole"
    },
    "absurdity": {
        "patterns": [
            r'absurd result', r'absurdity', r'could not have intended',
            r'irrational'
        ],
        "description": "Avoid interpretations leading to absurd results"
    },
    "presumption_against_surplusage": {
        "patterns": [
            r'surplusage', r'no word.*superfluous', r'every word.*meaning',
            r'render.*meaningless'
        ],
        "description": "Every word in statute should have meaning"
    }
}


def extract_canons_and_rules(text: str) -> Dict[str, Any]:
    """
    Extract interpretive canons used in statutory interpretation.

    Args:
        text: Case text discussing statutory interpretation

    Returns:
        JSON with canons detected
    """
    results = {
        "canons_found": [],
        "primary_canon": None,
        "interpretation_approach": None  # textualist, purposivist, etc.
    }

    text_lower = text.lower()

    for canon_name, canon_info in INTERPRETATION_CANONS.items():
        instances = []
        for pattern in canon_info["patterns"]:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                # Get context
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 150)
                context = text[start:end]

                # Find the full sentence
                sent_match = re.search(r'[^.]*' + re.escape(match.group(0)) + r'[^.]*\.', context, re.IGNORECASE)
                if sent_match:
                    instances.append({
                        "text_snippet": sent_match.group(0)[:200],
                        "how_applied": "See context"
                    })

        if instances:
            results["canons_found"].append({
                "canon_type": canon_name,
                "description": canon_info["description"],
                "instances": instances[:3],
                "citation": "[Extract from case]"
            })

    # Determine primary canon
    if results["canons_found"]:
        # Sort by number of instances
        results["canons_found"].sort(key=lambda x: len(x["instances"]), reverse=True)
        results["primary_canon"] = results["canons_found"][0]["canon_type"]

    # Determine interpretation approach
    textualist_indicators = sum(1 for c in results["canons_found"] if c["canon_type"] in
                                ["plain_meaning", "expressio_unius", "ejusdem_generis", "noscitur_a_sociis"])
    purposivist_indicators = sum(1 for c in results["canons_found"] if c["canon_type"] in
                                 ["legislative_history", "absurdity"])

    if textualist_indicators > purposivist_indicators:
        results["interpretation_approach"] = "textualist"
    elif purposivist_indicators > textualist_indicators:
        results["interpretation_approach"] = "purposivist"
    elif results["canons_found"]:
        results["interpretation_approach"] = "mixed"

    return results


def extract_canons_and_rules_mcp(text: str) -> str:
    """MCP wrapper for extract_canons_and_rules."""
    result = extract_canons_and_rules(text)

    output = []
    output.append("INTERPRETIVE CANONS ANALYSIS")
    output.append("=" * 60)
    output.append(f"Primary Canon: {result['primary_canon'] or 'None detected'}")
    output.append(f"Interpretation Approach: {result['interpretation_approach'] or 'Unknown'}")
    output.append("")

    if result["canons_found"]:
        output.append("CANONS DETECTED:")
        output.append("-" * 40)
        for canon in result["canons_found"]:
            output.append(f"[{canon['canon_type'].upper()}]")
            output.append(f"  {canon['description']}")
            output.append(f"  Instances found: {len(canon['instances'])}")
            if canon["instances"]:
                output.append(f"  Example: \"{canon['instances'][0]['text_snippet'][:100]}...\"")
            output.append("")
    else:
        output.append("No interpretive canons detected in text.")

    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# 12. CROSS REFERENCE CITATIONS
# ============================================================================

def cross_reference_citations(
    documents: Dict[str, str]
) -> Dict[str, Any]:
    """
    Cross-reference citations across multiple documents.

    Args:
        documents: Dict mapping document names to text

    Returns:
        JSON with citation analysis
    """
    results = {
        "documents_analyzed": list(documents.keys()),
        "shared_cases": [],
        "unique_to_doc": {},
        "authority_overlap_matrix": {},
        "most_cited": []
    }

    # Extract citations from each document
    doc_citations = {}
    all_citations = {}

    citation_pattern = r'([A-Z][A-Za-z\'\-\s]+(?:v\.|vs\.)\s+[A-Z][A-Za-z\'\-\s,]+),?\s*(\d+)\s+([A-Za-z0-9\.\s]+)\s+(\d+)'

    for doc_name, doc_text in documents.items():
        citations = set()
        matches = re.findall(citation_pattern, doc_text)
        for match in matches:
            case_name = match[0].strip()[:60]
            citations.add(case_name)

            if case_name not in all_citations:
                all_citations[case_name] = {"docs": [], "count": 0}
            all_citations[case_name]["docs"].append(doc_name)
            all_citations[case_name]["count"] += 1

        doc_citations[doc_name] = citations

    # Find shared citations
    for case_name, info in all_citations.items():
        if len(set(info["docs"])) > 1:
            results["shared_cases"].append({
                "case": case_name,
                "docs": list(set(info["docs"])),
                "frequency": info["count"]
            })

    # Sort by frequency
    results["shared_cases"].sort(key=lambda x: x["frequency"], reverse=True)

    # Find unique citations per document
    for doc_name, citations in doc_citations.items():
        unique = []
        for cite in citations:
            if len(set(all_citations[cite]["docs"])) == 1:
                unique.append(cite)
        results["unique_to_doc"][doc_name] = unique[:10]

    # Build overlap matrix
    doc_names = list(documents.keys())
    for i, doc_a in enumerate(doc_names):
        results["authority_overlap_matrix"][doc_a] = {}
        for doc_b in doc_names:
            if doc_a != doc_b:
                overlap = doc_citations[doc_a] & doc_citations[doc_b]
                results["authority_overlap_matrix"][doc_a][doc_b] = len(overlap)

    # Most cited overall
    sorted_citations = sorted(all_citations.items(), key=lambda x: x[1]["count"], reverse=True)
    results["most_cited"] = [
        {"case": c[0], "frequency": c[1]["count"]}
        for c in sorted_citations[:10]
    ]

    return results


def cross_reference_citations_mcp(documents: Dict[str, str]) -> str:
    """MCP wrapper for cross_reference_citations."""
    result = cross_reference_citations(documents)

    output = []
    output.append("CITATION CROSS-REFERENCE ANALYSIS")
    output.append("=" * 60)
    output.append(f"Documents analyzed: {', '.join(result['documents_analyzed'])}")
    output.append("")

    if result["most_cited"]:
        output.append("MOST CITED AUTHORITIES:")
        output.append("-" * 40)
        for cite in result["most_cited"][:5]:
            output.append(f"  [{cite['frequency']}x] {cite['case']}")
        output.append("")

    if result["shared_cases"]:
        output.append("SHARED AUTHORITIES (appear in multiple docs):")
        output.append("-" * 40)
        for shared in result["shared_cases"][:5]:
            output.append(f"  {shared['case']}")
            output.append(f"    In: {', '.join(shared['docs'])} ({shared['frequency']}x)")
        output.append("")

    output.append("UNIQUE AUTHORITIES BY DOCUMENT:")
    output.append("-" * 40)
    for doc, uniques in result["unique_to_doc"].items():
        output.append(f"  {doc}: {len(uniques)} unique citations")
        for u in uniques[:3]:
            output.append(f"    - {u}")
    output.append("")

    output.append("OVERLAP MATRIX:")
    for doc_a, overlaps in result["authority_overlap_matrix"].items():
        overlap_str = ", ".join(f"{doc_b}: {count}" for doc_b, count in overlaps.items())
        output.append(f"  {doc_a}: {overlap_str}")

    output.append("")
    output.append("=" * 60)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2))

    return "\n".join(output)


# ============================================================================
# VERIFY CITATIONS - Check Quoted Language Matches Source
# ============================================================================

class VerificationStatus(Enum):
    VERIFIED = "verified"
    CLOSE_MATCH = "close_match"
    NOT_FOUND = "not_found"
    CASE_MISSING = "case_missing"


def verify_citations(
    brief_text: str,
    case_texts: Dict[str, str]
) -> Dict[str, Any]:
    """
    Verify that quoted language in your brief matches the source cases.

    Searches for exact and close matches, flags discrepancies.

    Args:
        brief_text: Your brief containing citations with quoted language
        case_texts: Dict mapping case names to their full text

    Returns:
        Dict with verification results for each quoted citation
    """
    from difflib import SequenceMatcher

    results = {
        "total_quotes_found": 0,
        "verified": 0,
        "close_matches": 0,
        "not_found": 0,
        "case_missing": 0,
        "quotes": []
    }

    # Pattern to extract quoted text with case attribution
    # Case name must start with capital letter and contain "v." or "vs."
    # Party name allows: letters, numbers, spaces, punctuation, &, Inc., Ltd., etc.
    party_chars = r"[A-Za-z0-9\'\-\.,\s&]"

    # Normalize curly quotes to straight quotes for matching
    normalized_text = brief_text.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")

    quote_patterns = [
        # Quote with citation after (Bluebook format) - most common
        # Case name starts with capital, has v., then volume number
        rf'"([^"]{{10,500}})"[^"]*?([A-Z]{party_chars}*?(?:v\.|vs\.)\s*[A-Z]{party_chars}*?),\s*\d+\s*(?:U\.S\.|F\.\d+d|S\.\s*Ct\.)',
        # Quote followed by case name with volume number
        rf'"([^"]{{10,500}})"[^"]*?([A-Z]{party_chars}*?(?:v\.|vs\.)\s*[A-Z]{party_chars}*?),\s*\d+',
        # Direct quote followed by case name (no intervening text)
        rf'"([^"]{{10,500}})"\s*([A-Z]{party_chars}*?(?:v\.|vs\.)\s*[A-Z]{party_chars}+)',
        rf'"([^"]{{10,500}})\."\s*([A-Z]{party_chars}*?(?:v\.|vs\.)\s*[A-Z]{party_chars}+)',
        # Citing format
        rf'"([^"]{{10,500}})"\s*\(citing\s+([A-Z]{party_chars}*?(?:v\.|vs\.)\s*[A-Z]{party_chars}+)',
    ]

    found_quotes = []
    seen_quotes = set()  # For deduplication

    for pattern in quote_patterns:
        for match in re.finditer(pattern, normalized_text, re.DOTALL):
            groups = match.groups()
            quote_text = groups[0].strip() if groups[0] else ""
            case_name = groups[1].strip() if len(groups) > 1 and groups[1] else None
            if case_name:
                case_name = re.sub(r',\s*$', '', case_name).strip()

            # Deduplicate - same quote + same case = skip
            dedup_key = f"{quote_text[:50]}|{case_name or 'unknown'}"
            if dedup_key in seen_quotes:
                continue
            seen_quotes.add(dedup_key)

            # Get position for context window
            start_pos = match.start()
            end_pos = match.end()

            found_quotes.append({
                "quote": quote_text,
                "case_name": case_name,
                "start_pos": start_pos,
                "end_pos": end_pos
            })

    for quote_info in found_quotes:
        quote = quote_info["quote"]
        case_name = quote_info["case_name"]

        quote_result = {
            "quote_text": quote[:200] + ("..." if len(quote) > 200 else ""),
            "attributed_case": case_name or "Unknown",
            "status": None,
            "found_text": None,
            "context_window": None,  # Surrounding text in source
            "context_warning": None,  # Warning if quote may be out of context
            "difference_summary": None,
            "match_confidence": 0.0
        }

        if not case_name:
            quote_result["status"] = VerificationStatus.CASE_MISSING.value
            results["case_missing"] += 1
        elif case_name not in case_texts:
            matched = _find_matching_case(case_name, case_texts)
            if matched:
                case_name = matched
            else:
                quote_result["status"] = VerificationStatus.CASE_MISSING.value
                results["case_missing"] += 1
                results["quotes"].append(quote_result)
                continue

        if case_name in case_texts:
            case_text = case_texts[case_name]
            norm_quote = _normalize_text(quote)
            norm_case = _normalize_text(case_text)

            if norm_quote in norm_case:
                quote_result["status"] = VerificationStatus.VERIFIED.value
                quote_result["match_confidence"] = 1.0
                results["verified"] += 1

                # Add context window - find where quote appears and get surrounding text
                quote_pos = norm_case.find(norm_quote)
                if quote_pos >= 0:
                    context_start = max(0, quote_pos - 100)
                    context_end = min(len(case_text), quote_pos + len(quote) + 100)
                    context = case_text[context_start:context_end]
                    quote_result["context_window"] = f"...{context}..."

                    # Check for context warnings
                    warning = _check_context_issues(quote, context, case_text)
                    if warning:
                        quote_result["context_warning"] = warning

            else:
                best_match, confidence = _fuzzy_find(quote, case_text)
                if confidence >= 0.85:
                    quote_result["status"] = VerificationStatus.CLOSE_MATCH.value
                    quote_result["found_text"] = best_match[:200] if best_match else None
                    quote_result["match_confidence"] = confidence
                    quote_result["difference_summary"] = _summarize_quote_differences(quote, best_match) if best_match else None
                    results["close_matches"] += 1
                else:
                    quote_result["status"] = VerificationStatus.NOT_FOUND.value
                    quote_result["match_confidence"] = confidence
                    results["not_found"] += 1

        results["quotes"].append(quote_result)

    results["total_quotes_found"] = len(found_quotes)
    return results


def _check_context_issues(quote: str, context: str, full_text: str) -> Optional[str]:
    """Check if quote might be taken out of context."""
    context_lower = context.lower()
    full_lower = full_text.lower()

    warnings = []

    # Check if quote is from a section describing opposing arguments
    opposing_indicators = ['appellant argues', 'plaintiff contends', 'defendant argues',
                          'the argument that', 'rejected the argument', 'we disagree']
    for indicator in opposing_indicators:
        if indicator in context_lower:
            warnings.append(f"Quote appears near '{indicator}' - verify this is the court's view, not a rejected argument")
            break

    # Check if quote is from dissent
    if 'dissent' in context_lower or 'dissenting' in context_lower:
        warnings.append("Quote may be from a dissent, not the majority opinion")

    # Check if there's a "but" or "however" immediately after the quote
    quote_end = context_lower.find(quote.lower()) + len(quote)
    after_quote = context_lower[quote_end:quote_end+50] if quote_end < len(context_lower) else ""
    if re.search(r'^[,\s]*(but|however|although|yet|nevertheless)', after_quote):
        warnings.append("Quote is immediately followed by qualifying language - check full context")

    return warnings[0] if warnings else None


def _summarize_quote_differences(expected: str, found: str) -> str:
    """Summarize differences between expected and found quote."""
    if not found:
        return "Quote not found in source"

    from difflib import SequenceMatcher
    matcher = SequenceMatcher(None, expected.lower(), found.lower())

    changes = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace' and (i2 - i1) < 20:
            changes.append(f"'{expected[i1:i2]}' → '{found[j1:j2]}'")
        elif tag == 'delete' and (i2 - i1) < 15:
            changes.append(f"Missing: '{expected[i1:i2]}'")
        elif tag == 'insert' and (j2 - j1) < 15:
            changes.append(f"Extra: '{found[j1:j2]}'")

    if changes:
        return "; ".join(changes[:3])
    return "Minor differences in punctuation or spacing"


def _find_matching_case(name: str, case_texts: Dict[str, str]) -> Optional[str]:
    """Find a matching case name in case_texts."""
    name_lower = re.sub(r'[^\w\s]', '', name.lower())
    for case_name in case_texts.keys():
        if re.sub(r'[^\w\s]', '', case_name.lower()) == name_lower:
            return case_name
        # Check partial match
        name_words = set(name_lower.split()) - {'v', 'vs', 'the', 'of'}
        case_words = set(re.sub(r'[^\w\s]', '', case_name.lower()).split()) - {'v', 'vs', 'the', 'of'}
        if len(name_words & case_words) >= min(len(name_words), len(case_words)) * 0.6:
            return case_name
    return None


def _normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[""'']', '"', text)
    return text.strip()


def _fuzzy_find(quote: str, case_text: str) -> Tuple[Optional[str], float]:
    """Find best fuzzy match for quote in case text."""
    from difflib import SequenceMatcher

    norm_quote = _normalize_text(quote)
    norm_case = _normalize_text(case_text)
    quote_words = norm_quote.split()[:3]
    first_words = ' '.join(quote_words)

    best_match, best_ratio = None, 0.0

    for i in range(len(norm_case) - len(first_words)):
        if norm_case[i:i+len(first_words)] == first_words:
            candidate = norm_case[i:i+len(norm_quote)+30]
            ratio = SequenceMatcher(None, norm_quote, candidate[:len(norm_quote)]).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = case_text[i:i+len(quote)+30]

    return best_match, best_ratio


def verify_citations_mcp(brief_text: str, case_texts: Dict[str, str]) -> str:
    """MCP wrapper for verify_citations."""
    result = verify_citations(brief_text, case_texts)

    output = []
    output.append("=" * 70)
    output.append("CITATION QUOTE VERIFICATION")
    output.append("=" * 70)
    output.append(f"\nTotal quotes found: {result['total_quotes_found']}")
    output.append(f"  [OK] VERIFIED: {result['verified']} - exact match in source")
    output.append(f"  [~]  CLOSE MATCH: {result['close_matches']} - similar text found")
    output.append(f"  [X]  NOT FOUND: {result['not_found']} - quote not in source")
    output.append(f"  [?]  CASE MISSING: {result['case_missing']} - source not provided")

    for i, q in enumerate(result["quotes"], 1):
        status_icon = {"verified": "[OK]", "close_match": "[~]", "not_found": "[X]", "case_missing": "[?]"}.get(q["status"], "?")
        output.append(f"\n{'='*60}")
        output.append(f"{i}. {status_icon} {q['status'].upper()}")
        output.append(f"{'='*60}")

        output.append(f"\nQUOTE IN YOUR BRIEF:")
        output.append(f"  \"{q['quote_text']}\"")

        output.append(f"\nATTRIBUTED TO:")
        output.append(f"  {q['attributed_case']}")

        output.append(f"\nCONFIDENCE: {q['match_confidence']:.0%}")

        # Context window
        if q.get("context_window"):
            output.append(f"\nCONTEXT IN SOURCE:")
            output.append(f"  {q['context_window'][:300]}")

        # Context warning
        if q.get("context_warning"):
            output.append(f"\n⚠️  CONTEXT WARNING:")
            output.append(f"  {q['context_warning']}")

        # Differences for close matches
        if q["status"] == "close_match" and q.get("found_text"):
            output.append(f"\nFOUND IN SOURCE (slightly different):")
            output.append(f"  \"{q['found_text']}\"")
            if q.get("difference_summary"):
                output.append(f"\nDIFFERENCES:")
                output.append(f"  {q['difference_summary']}")

        # Not found guidance
        if q["status"] == "not_found":
            output.append(f"\n⚠️  ACTION NEEDED:")
            output.append(f"  Quote not found in {q['attributed_case']}. Verify the source or check for typos.")

    output.append("\n" + "=" * 70)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2, default=str))
    return "\n".join(output)


# ============================================================================
# CHECK PARENTHETICAL ACCURACY
# ============================================================================

class AccuracyFlag(Enum):
    ACCURATE = "accurate"
    OVERSTATED = "overstated"
    UNDERSTATED = "understated"
    UNSUPPORTED = "unsupported"


def check_parenthetical_accuracy(
    parentheticals: List[Dict],
    case_texts: Dict[str, str]
) -> Dict[str, Any]:
    """
    Verify that parentheticals accurately represent case holdings.

    Args:
        parentheticals: List of {case_name, parenthetical_text} dicts
        case_texts: Dict mapping case names to their full text

    Returns:
        Dict with accuracy check results including:
        - Side-by-side comparison of parenthetical vs actual holding
        - Clear explanation of any discrepancy
        - Suggested revision if inaccurate
    """
    results = {
        "total_checked": 0,
        "accurate": 0,
        "overstated": 0,
        "understated": 0,
        "unsupported": 0,
        "checks": []
    }

    for paren in parentheticals:
        case_name = paren.get("case_name", "")
        paren_text = paren.get("parenthetical_text", "")

        check_result = {
            "case_name": case_name,
            "parenthetical_text": paren_text,
            "flag": None,
            "explanation": "",
            "suggested_revision": None,
            "actual_holding": None,
            "comparison": None
        }

        # Find matching case
        matched_name = _find_matching_case(case_name, case_texts)
        if not matched_name:
            check_result["flag"] = AccuracyFlag.UNSUPPORTED.value
            check_result["explanation"] = f"Case text for '{case_name}' not provided - cannot verify accuracy"
            results["unsupported"] += 1
            results["checks"].append(check_result)
            continue

        case_text = case_texts[matched_name]

        # Find the most relevant holding/sentence in the case
        holding = _find_relevant_holding(paren_text, case_text)
        check_result["actual_holding"] = holding

        if not holding:
            check_result["flag"] = AccuracyFlag.UNSUPPORTED.value
            check_result["explanation"] = "Could not find a holding in the case that matches your parenthetical's subject matter"
            results["unsupported"] += 1
            results["checks"].append(check_result)
            continue

        # Analyze the parenthetical vs the actual holding
        analysis = _analyze_parenthetical_vs_holding(paren_text, holding)

        check_result["flag"] = analysis["flag"]
        check_result["explanation"] = analysis["explanation"]
        check_result["suggested_revision"] = analysis["suggested_revision"]
        check_result["comparison"] = {
            "your_parenthetical": paren_text,
            "actual_holding": holding,
            "discrepancies": analysis.get("discrepancies", [])
        }

        results[analysis["flag"]] += 1
        results["checks"].append(check_result)

    results["total_checked"] = len(parentheticals)
    return results


def _find_relevant_holding(paren_text: str, case_text: str) -> Optional[str]:
    """Find the sentence in case_text most relevant to the parenthetical."""
    # Extract key content words from parenthetical
    paren_lower = paren_text.lower()
    # Remove common parenthetical starters
    paren_lower = re.sub(r'^(holding|finding|concluding|explaining|noting|recognizing|requiring)\s+that\s+', '', paren_lower)
    key_words = [w for w in re.findall(r'\b\w{4,}\b', paren_lower)
                 if w not in {'that', 'this', 'with', 'from', 'have', 'been', 'were', 'must', 'shall'}]

    if not key_words:
        return None

    # Split case into sentences
    sentences = re.split(r'(?<=[.!?])\s+', case_text)

    # Score each sentence by keyword overlap
    best_sentence = None
    best_score = 0

    for sentence in sentences:
        if len(sentence) < 30:  # Skip short fragments
            continue

        sentence_lower = sentence.lower()
        score = sum(1 for w in key_words if w in sentence_lower)

        # Bonus for holding indicators
        if re.search(r'\b(hold|held|holding|conclude|concluded|find|found|require|required)\b', sentence_lower):
            score += 2

        if score > best_score:
            best_score = score
            best_sentence = sentence

    # Require minimum match
    if best_score < 2:
        return None

    return best_sentence[:400] if best_sentence else None


def _analyze_parenthetical_vs_holding(paren_text: str, holding: str) -> Dict:
    """
    Compare parenthetical against actual holding and identify discrepancies.

    Returns dict with flag, explanation, suggested_revision, and discrepancies.
    """
    paren_lower = paren_text.lower()
    holding_lower = holding.lower()

    discrepancies = []

    # Words indicating absolute/categorical claims
    absolute_words = {
        'always': 'in all cases',
        'never': 'in no case',
        'must': 'is required to',
        'shall': 'is required to',
        'all': 'every',
        'every': 'all',
        'only': 'exclusively',
        'cannot': 'is prohibited from',
        'required': 'mandatory',
        'requires': 'mandates'
    }

    # Words indicating qualified/limited claims
    qualification_words = {
        'generally': 'as a general rule',
        'typically': 'in most cases',
        'usually': 'ordinarily',
        'may': 'has discretion to',
        'might': 'could potentially',
        'unless': 'except when',
        'except': 'other than',
        'if': 'when/provided that',
        'when': 'in circumstances where',
        'where': 'in situations where',
        'sometimes': 'in some cases',
        'often': 'frequently but not always'
    }

    # Check for absolute language in parenthetical not supported by holding
    paren_absolutes = []
    for word, meaning in absolute_words.items():
        if re.search(r'\b' + word + r'\b', paren_lower):
            if not re.search(r'\b' + word + r'\b', holding_lower):
                paren_absolutes.append((word, meaning))

    # Check for qualifications in holding missing from parenthetical
    missing_quals = []
    for word, meaning in qualification_words.items():
        if re.search(r'\b' + word + r'\b', holding_lower):
            if not re.search(r'\b' + word + r'\b', paren_lower):
                # Find context around the qualification
                match = re.search(r'([^.]*\b' + word + r'\b[^.]*)', holding_lower)
                if match:
                    missing_quals.append((word, meaning, match.group(1)[:100]))

    # Determine flag and generate explanation
    if paren_absolutes:
        words_used = [w[0] for w in paren_absolutes]
        flag = AccuracyFlag.OVERSTATED.value

        explanation = f"Your parenthetical uses absolute language ('{', '.join(words_used)}') "
        explanation += "that the court did not use. "
        explanation += f"The actual holding is more limited: \"{holding[:150]}...\""

        # Generate suggested revision - remove absolute words and add qualifier
        revised = paren_text
        for word, meaning in paren_absolutes:
            # Remove absolute words (don't replace with 'generally' each time)
            revised = re.sub(r'\b' + word + r'\b\s*', '', revised, flags=re.IGNORECASE)

        # Clean up extra spaces
        revised = re.sub(r'\s+', ' ', revised).strip()

        # Add "generally" qualifier if it starts with "holding that" or "finding that"
        if revised.lower().startswith("holding that"):
            revised = re.sub(r'(holding that)\s+', r'\1 generally ', revised, flags=re.IGNORECASE)
        elif revised.lower().startswith("finding that"):
            revised = re.sub(r'(finding that)\s+', r'\1 generally ', revised, flags=re.IGNORECASE)
        else:
            revised = "generally, " + revised

        discrepancies = [f"Used '{w}' but holding doesn't support absolute claim" for w, _ in paren_absolutes]

        return {
            "flag": flag,
            "explanation": explanation,
            "suggested_revision": revised,
            "discrepancies": discrepancies
        }

    elif missing_quals:
        flag = AccuracyFlag.UNDERSTATED.value

        qual_words = [q[0] for q in missing_quals]
        qual_context = missing_quals[0][2] if missing_quals else ""

        explanation = f"The case qualifies its holding with '{qual_words[0]}' but your parenthetical omits this. "
        explanation += f"The court actually said: \"...{qual_context}...\" "
        explanation += "Your parenthetical should reflect this limitation."

        # Generate suggested revision - add the qualification
        revised = paren_text
        if revised.lower().startswith("holding that"):
            qual = qual_words[0]
            revised = re.sub(r'(holding that)\s+', f'\\1 {qual} ', revised, flags=re.IGNORECASE)
        elif revised.lower().startswith("finding that"):
            qual = qual_words[0]
            revised = re.sub(r'(finding that)\s+', f'\\1 {qual} ', revised, flags=re.IGNORECASE)
        else:
            revised = f"{qual_words[0]}, {paren_text}"

        discrepancies = [f"Holding includes '{q[0]}' qualification: \"{q[2]}\"" for q in missing_quals[:2]]

        return {
            "flag": flag,
            "explanation": explanation,
            "suggested_revision": revised,
            "discrepancies": discrepancies
        }

    else:
        return {
            "flag": AccuracyFlag.ACCURATE.value,
            "explanation": f"Parenthetical accurately represents the holding. The case states: \"{holding[:150]}...\"",
            "suggested_revision": None,
            "discrepancies": []
        }


def check_parenthetical_accuracy_mcp(parentheticals: List[Dict], case_texts: Dict[str, str]) -> str:
    """MCP wrapper for check_parenthetical_accuracy."""
    result = check_parenthetical_accuracy(parentheticals, case_texts)

    output = []
    output.append("=" * 70)
    output.append("PARENTHETICAL ACCURACY CHECK")
    output.append("=" * 70)
    output.append(f"\nTotal: {result['total_checked']}")
    output.append(f"  ACCURATE: {result['accurate']}")
    output.append(f"  OVERSTATED: {result['overstated']}")
    output.append(f"  UNDERSTATED: {result['understated']}")
    output.append(f"  UNSUPPORTED: {result['unsupported']}")

    for i, c in enumerate(result["checks"], 1):
        icon = {"accurate": "[OK]", "overstated": "[!]", "understated": "[~]", "unsupported": "[X]"}.get(c["flag"], "?")
        output.append(f"\n{'='*60}")
        output.append(f"{i}. {icon} {c['case_name']}: {c['flag'].upper()}")
        output.append(f"{'='*60}")

        # Your parenthetical
        output.append(f"\nYOUR PARENTHETICAL:")
        output.append(f"  ({c['parenthetical_text']})")

        # Actual holding from case
        if c.get("actual_holding"):
            output.append(f"\nACTUAL HOLDING:")
            output.append(f"  \"{c['actual_holding'][:300]}...\"")

        # Explanation
        output.append(f"\nANALYSIS:")
        output.append(f"  {c['explanation']}")

        # Discrepancies
        if c.get("comparison") and c["comparison"].get("discrepancies"):
            output.append(f"\nDISCREPANCIES:")
            for d in c["comparison"]["discrepancies"]:
                output.append(f"  - {d}")

        # Suggested revision
        if c.get("suggested_revision"):
            output.append(f"\nSUGGESTED REVISION:")
            output.append(f"  ({c['suggested_revision']})")

    output.append("\n" + "=" * 70)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2, default=str))
    return "\n".join(output)


# ============================================================================
# FIND ADVERSE AUTHORITY
# ============================================================================

class SeverityLevel(Enum):
    FATAL = "fatal"
    SERIOUS = "serious"
    MINOR = "minor"


def find_adverse_authority(
    your_argument: str,
    case_texts: Dict[str, str]
) -> Dict[str, Any]:
    """
    Identify cases that opposing counsel will cite against your argument.

    Severity levels:
    - FATAL: Case directly holds against your position on the same issue
    - SERIOUS: Case contradicts your argument but may be distinguishable
    - MINOR: Case limits or qualifies a rule you rely on

    Args:
        your_argument: Your legal argument text
        case_texts: Dict mapping case names to their full text

    Returns:
        Dict with adverse holdings, conflict analysis, and distinguishing strategies
    """
    results = {
        "argument_summary": your_argument[:300],
        "total_cases_analyzed": len(case_texts),
        "adverse_holdings_found": 0,
        "fatal": 0,
        "serious": 0,
        "minor": 0,
        "adverse_holdings": []
    }

    # Extract the key claims/propositions from the argument
    claims = _extract_claims(your_argument)
    arg_lower = your_argument.lower()

    # Patterns that indicate adverse holdings
    adverse_indicators = {
        "direct_negation": [
            (r'does\s+not\s+require', "holds that X is NOT required"),
            (r'need\s+not\s+(show|prove|establish|demonstrate)', "holds that plaintiff need not show X"),
            (r'is\s+not\s+(required|necessary|sufficient|fatal|dispositive)', "holds that X is not required/fatal"),
            (r'cannot\s+(show|prove|establish|succeed)', "holds that party cannot establish X"),
            (r'fails?\s+to\s+(establish|show|prove|meet)', "holds that party failed to meet standard"),
            (r'(absence|lack)\s+of\s+\w+\s+(is\s+not|does\s+not)', "absence of X is not fatal"),
            (r'not\s+(alone\s+)?(sufficient|enough|dispositive)', "X alone is not sufficient"),
            (r'insufficient\s+to', "holds that X is insufficient"),
        ],
        "rejection": [
            (r'reject(?:s|ed)?\s+(?:the\s+)?(argument|claim|contention|position)', "explicitly rejects this argument"),
            (r'we\s+disagree', "court disagreed with similar reasoning"),
            (r'(decline|declined|refuses?)\s+to\s+(hold|find|adopt)', "court declined to adopt this position"),
            (r'(unconvinced|unpersuaded)\s+by', "court was unconvinced by argument"),
        ],
        "limitation": [
            (r'only\s+(when|where|if|in)', "limits rule to specific circumstances"),
            (r'unless', "creates exception that may apply"),
            (r'except\s+(when|where|if|in)', "creates exception to the rule"),
            (r'limited\s+to', "narrows scope of the rule"),
            (r'does\s+not\s+extend\s+to', "rule does not apply in certain situations"),
            (r'narrow(ly|er)?', "court adopted narrow interpretation"),
            (r'however', "introduces qualification or limitation"),
            (r'but\s+(this|that|the|we|it)', "introduces contrasting point"),
        ]
    }

    for case_name, case_text in case_texts.items():
        sentences = re.split(r'(?<=[.!?])\s+', case_text)

        # Find citation for this case
        cite_match = re.search(r'\d+\s+(?:U\.S\.|F\.\d+d|S\.\s*Ct\.)\s+\d+', case_text)
        citation = cite_match.group(0) if cite_match else "N/A"

        for claim in claims:
            claim_lower = claim.lower()
            claim_words = set(re.findall(r'\b\w{4,}\b', claim_lower))

            for sentence in sentences:
                if len(sentence) < 40:
                    continue

                sentence_lower = sentence.lower()

                # Check keyword overlap to ensure relevance
                # Lower threshold to 1 since we also check for specific adverse patterns
                sent_words = set(re.findall(r'\b\w{4,}\b', sentence_lower))
                overlap = claim_words & sent_words
                if len(overlap) < 1:
                    continue

                # Check for adverse indicators
                found_adverse = None
                conflict_type = None
                base_severity = SeverityLevel.MINOR

                for category, patterns in adverse_indicators.items():
                    for pattern, description in patterns:
                        if re.search(pattern, sentence_lower):
                            found_adverse = description
                            conflict_type = category
                            if category == "direct_negation":
                                base_severity = SeverityLevel.SERIOUS
                            elif category == "rejection":
                                base_severity = SeverityLevel.SERIOUS
                            break
                    if found_adverse:
                        break

                if not found_adverse:
                    continue

                # Determine final severity
                severity = base_severity

                # Upgrade to FATAL if it's an explicit holding
                if re.search(r'\b(we\s+hold|the\s+court\s+holds?|holding\s+that|held\s+that)\b', sentence_lower):
                    severity = SeverityLevel.FATAL

                # Upgrade if it's from a higher court (look for U.S. citation)
                if 'U.S.' in citation or 'S. Ct.' in citation or 'S.Ct.' in citation:
                    if severity == SeverityLevel.SERIOUS:
                        severity = SeverityLevel.FATAL

                # Generate conflict analysis
                conflict_analysis = _generate_conflict_analysis(claim, sentence, found_adverse, conflict_type)

                # Generate distinguishing language
                distinguishing = _generate_distinguishing_language(
                    case_name, sentence, claim, your_argument, conflict_type
                )

                results["adverse_holdings"].append({
                    "case_name": case_name,
                    "citation": citation,
                    "adverse_holding": sentence[:400],
                    "your_claim": claim[:200],
                    "conflict_type": conflict_type,
                    "severity": severity.value,
                    "severity_reason": _explain_severity(severity, conflict_type, citation),
                    "conflict_analysis": conflict_analysis,
                    "distinguishing_language": distinguishing
                })
                results["adverse_holdings_found"] += 1
                results[severity.value] += 1

    # Sort by severity and deduplicate similar findings
    results["adverse_holdings"].sort(key=lambda x: {"fatal": 0, "serious": 1, "minor": 2}.get(x["severity"], 3))
    results["adverse_holdings"] = _deduplicate_adverse(results["adverse_holdings"])

    return results


def _extract_claims(argument: str) -> List[str]:
    """Extract key legal claims/propositions from argument."""
    claims = []

    # Patterns for explicit claims
    claim_patterns = [
        r'(?:we|plaintiff|defendant)\s+(?:argue|contend|assert|maintain|submit)\s+that\s+([^.]+\.)',
        r'(?:the\s+)?(?:law|rule|standard)\s+(?:requires?|provides?|states?|mandates?)\s+that\s+([^.]+\.)',
        r'(?:courts?\s+)?(?:must|should|shall)\s+([^.]+\.)',
        r'(?:it\s+is\s+)?(?:well[- ])?(?:established|settled)\s+that\s+([^.]+\.)',
        r'(?:under|pursuant\s+to)\s+[^,]+,\s+([^.]+\.)',
        r'(?:to\s+(?:establish|prove|show))[^,]*,\s+(?:a\s+)?(?:plaintiff|party)\s+must\s+([^.]+\.)',
    ]

    for pattern in claim_patterns:
        for match in re.finditer(pattern, argument, re.IGNORECASE):
            claim = match.group(1).strip()
            if len(claim) > 25 and claim not in claims:
                claims.append(claim)

    # If no explicit claims found, use key sentences
    if not claims:
        sentences = re.split(r'(?<=[.!?])\s+', argument)
        for sent in sentences[:7]:
            if len(sent) > 40:
                claims.append(sent.strip())

    return claims[:10]


def _generate_conflict_analysis(claim: str, adverse_holding: str, adverse_type: str, conflict_category: str) -> str:
    """Generate clear explanation of why the holding conflicts with your argument."""

    claim_lower = claim.lower()
    holding_lower = adverse_holding.lower()

    # Identify the specific conflict
    if conflict_category == "direct_negation":
        # Find what's being negated
        if "require" in holding_lower and "require" in claim_lower:
            return f"You argue that something is required, but the court held it is NOT required: \"{adverse_holding[:150]}...\""
        elif "must" in claim_lower and "need not" in holding_lower:
            return f"You argue a mandatory standard, but the court held parties 'need not' meet this standard."
        else:
            return f"The court directly negates your position: \"{adverse_holding[:150]}...\""

    elif conflict_category == "rejection":
        return f"The court explicitly rejected similar reasoning: \"{adverse_holding[:150]}...\""

    elif conflict_category == "limitation":
        # Find the limiting language
        if "only" in holding_lower:
            match = re.search(r'only\s+(when|where|if|in)\s+([^,\.]+)', holding_lower)
            if match:
                condition = match.group(2)
                return f"The rule you rely on applies 'only {match.group(1)} {condition}' - opposing counsel will argue your case doesn't meet this condition."
        elif "unless" in holding_lower:
            match = re.search(r'unless\s+([^,\.]+)', holding_lower)
            if match:
                exception = match.group(1)
                return f"There's an exception: 'unless {exception}' - opposing counsel may argue this exception applies to your case."
        return f"The court limited the rule's scope: \"{adverse_holding[:150]}...\""

    return f"This holding conflicts with your argument: \"{adverse_holding[:150]}...\""


def _generate_distinguishing_language(case_name: str, adverse_holding: str, claim: str, argument: str, conflict_type: str) -> str:
    """Generate actual distinguishing language based on the specific conflict."""

    holding_lower = adverse_holding.lower()
    arg_lower = argument.lower()

    strategies = []

    # Procedural posture distinction
    if any(word in holding_lower for word in ['summary judgment', 'motion to dismiss', '12(b)(6)']):
        strategies.append(
            f"{case_name} arose on [summary judgment/motion to dismiss], where the standard differs. "
            f"Here, [explain different procedural posture or why your case survives that standard]."
        )

    # Factual distinction
    if conflict_type == "limitation":
        # The case creates a limitation - argue your facts meet it
        if "only when" in holding_lower or "only where" in holding_lower:
            strategies.append(
                f"Unlike {case_name}, this case satisfies the required condition because [specific facts showing you meet the 'only when' requirement]."
            )
        elif "unless" in holding_lower:
            strategies.append(
                f"The exception in {case_name} does not apply here because [explain why the 'unless' condition is not present in your case]."
            )

    # Scope distinction
    if any(word in holding_lower for word in ['limited to', 'narrow', 'specific']):
        strategies.append(
            f"{case_name}'s narrow holding was limited to [specific context]. This case involves [different context], so the holding does not control."
        )

    # Different legal issue
    if conflict_type == "direct_negation":
        strategies.append(
            f"While {case_name} held [X was not required], that holding addressed [specific issue/element]. "
            f"The issue here is [different issue], which {case_name} did not decide."
        )

    # Jurisdiction/precedential weight
    strategies.append(
        f"Alternatively, {case_name} is [persuasive only/from a different circuit/pre-dates controlling authority], "
        f"and this Court should follow [better authority] instead."
    )

    if strategies:
        return strategies[0]  # Return the most relevant strategy

    return f"{case_name} is distinguishable on its facts because [identify specific factual differences that make the holding inapplicable]."


def _explain_severity(severity: SeverityLevel, conflict_type: str, citation: str) -> str:
    """Explain why this adverse authority has this severity level."""

    if severity == SeverityLevel.FATAL:
        if 'U.S.' in citation:
            return "FATAL: Supreme Court holding directly on point against your position"
        return "FATAL: Explicit holding ('we hold...') directly contradicting your argument"

    elif severity == SeverityLevel.SERIOUS:
        if conflict_type == "direct_negation":
            return "SERIOUS: Court negated a proposition central to your argument, but may be distinguishable"
        elif conflict_type == "rejection":
            return "SERIOUS: Court rejected similar reasoning, requiring you to explain why your case is different"
        return "SERIOUS: Significant adverse language that opposing counsel will cite"

    else:
        return "MINOR: Case limits or qualifies the rule but doesn't directly contradict your argument"


def _deduplicate_adverse(holdings: List[Dict]) -> List[Dict]:
    """Remove duplicate or near-duplicate adverse holdings."""
    seen_holdings = set()
    deduplicated = []

    for h in holdings:
        # Create a key from case name + first 100 chars of holding
        key = f"{h['case_name']}:{h['adverse_holding'][:100]}"
        if key not in seen_holdings:
            seen_holdings.add(key)
            deduplicated.append(h)

    return deduplicated


def find_adverse_authority_mcp(your_argument: str, case_texts: Dict[str, str]) -> str:
    """MCP wrapper for find_adverse_authority."""
    result = find_adverse_authority(your_argument, case_texts)

    output = []
    output.append("=" * 70)
    output.append("ADVERSE AUTHORITY ANALYSIS")
    output.append("=" * 70)

    output.append(f"\nYOUR ARGUMENT (summary):")
    output.append(f"  {result['argument_summary'][:200]}...")

    output.append(f"\nCases analyzed: {result['total_cases_analyzed']}")
    output.append(f"Adverse holdings found: {result['adverse_holdings_found']}")
    output.append(f"  [!!!] FATAL: {result['fatal']} - directly on point against you")
    output.append(f"  [!!]  SERIOUS: {result['serious']} - contradicts but distinguishable")
    output.append(f"  [!]   MINOR: {result['minor']} - limits rule, doesn't contradict")

    for i, a in enumerate(result["adverse_holdings"][:10], 1):
        icon = {"fatal": "[!!!]", "serious": "[!!]", "minor": "[!]"}.get(a["severity"], "?")
        output.append(f"\n{'='*60}")
        output.append(f"{i}. {icon} {a['severity'].upper()}: {a['case_name']}, {a['citation']}")
        output.append(f"{'='*60}")

        # Severity explanation
        if a.get("severity_reason"):
            output.append(f"\nWHY {a['severity'].upper()}:")
            output.append(f"  {a['severity_reason']}")

        # The adverse holding
        output.append(f"\nADVERSE HOLDING:")
        output.append(f"  \"{a['adverse_holding'][:300]}...\"")

        # Your claim it conflicts with
        output.append(f"\nCONFLICTS WITH YOUR CLAIM:")
        output.append(f"  \"{a['your_claim'][:200]}...\"")

        # Conflict analysis
        if a.get("conflict_analysis"):
            output.append(f"\nCONFLICT ANALYSIS:")
            output.append(f"  {a['conflict_analysis']}")

        # Distinguishing language
        output.append(f"\nHOW TO DISTINGUISH:")
        output.append(f"  {a['distinguishing_language']}")

    if not result["adverse_holdings"]:
        output.append("\n[No adverse authority found in the provided cases]")

    output.append("\n" + "=" * 70)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2, default=str))
    return "\n".join(output)


# ============================================================================
# ADVERSARIAL THINKING TOOLS
# ============================================================================

def steelman_counterargument(
    your_argument: str,
    case_texts: Dict[str, str],
    claim_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate the strongest possible opposing response to your argument.

    This tool forces you to confront weaknesses before opposing counsel does.
    It identifies your argument's dependencies, attacks each one, and
    synthesizes a comprehensive counterargument.

    Args:
        your_argument: Your legal argument text
        case_texts: Dict mapping case names to full text
        claim_type: Optional claim type (e.g., "excessive_force", "negligence")

    Returns:
        Dict with "_meta" and steelman response including attacks and draft language
    """
    targets_found = []
    targets_missing = []
    suggestions = []

    # Step 1: Extract claims from your argument
    claims = _extract_argument_claims(your_argument)
    if claims:
        targets_found.append("claims")
    else:
        targets_missing.append("claims")
        suggestions.append(
            "Could not extract explicit claims from your argument. "
            "Try stating your position more directly (e.g., 'Plaintiff must prove...')."
        )
        # Fallback to sentence-based extraction
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', your_argument)
                     if len(s.strip()) > 30]
        claims = sentences[:5]

    # Step 2: Find adverse authority
    adverse_result = find_adverse_authority(your_argument, case_texts)
    adverse_holdings = adverse_result.get("adverse_holdings", [])

    if adverse_holdings:
        targets_found.append("adverse_authority")
    else:
        targets_missing.append("adverse_authority")

    # Step 3: Identify element weaknesses (if claim type known)
    element_weaknesses = []
    if claim_type:
        elements = _get_elements_for_claim_type(claim_type)
        if elements:
            for element in elements:
                element_lower = element.lower()
                # Check if argument addresses this element
                if not any(word in your_argument.lower() for word in element_lower.split()):
                    element_weaknesses.append({
                        "element": element,
                        "gap": f"Your argument does not appear to address the '{element}' element.",
                        "exploit": f"Defendant will argue Plaintiff fails to establish {element}."
                    })

    if element_weaknesses:
        targets_found.append("element_gaps")

    # Step 4: Generate key attacks
    key_attacks = []

    # Attack 1: Factual challenges from adverse authority
    for adverse in adverse_holdings[:3]:
        key_attacks.append({
            "attack_type": "adverse_authority",
            "target": adverse.get("your_claim", "your position")[:100],
            "attack": f"Under {adverse['case_name']}, {adverse['adverse_holding'][:200]}",
            "supporting_authority": f"{adverse['case_name']}, {adverse['citation']}",
            "strength": 0.9 if adverse.get("severity") == "fatal" else 0.7
        })

    # Attack 2: Element-based challenges
    for weakness in element_weaknesses[:3]:
        key_attacks.append({
            "attack_type": "missing_element",
            "target": weakness["element"],
            "attack": weakness["exploit"],
            "supporting_authority": None,
            "strength": 0.8
        })

    # Attack 3: Logical challenges (look for conclusory language)
    conclusory_patterns = [
        (r'\bclearly\b', "Remove 'clearly' - this is conclusory"),
        (r'\bobviously\b', "Remove 'obviously' - this is conclusory"),
        (r'\bundoubtedly\b', "Unsupported assertion"),
        (r'\bmust\b.*\btherefore\b', "Logical leap without support"),
    ]

    for pattern, critique in conclusory_patterns:
        if re.search(pattern, your_argument, re.IGNORECASE):
            key_attacks.append({
                "attack_type": "logical_weakness",
                "target": "conclusory language",
                "attack": critique,
                "supporting_authority": None,
                "strength": 0.5
            })
            break

    # Step 5: Generate draft opposing response
    draft_response = _generate_steelman_draft(
        claims, key_attacks, adverse_holdings, element_weaknesses
    )

    # Calculate confidence
    if key_attacks:
        avg_strength = sum(a["strength"] for a in key_attacks) / len(key_attacks)
        confidence = round(avg_strength, 2)
    else:
        confidence = 0.30

    return {
        "_meta": {
            "extraction_complete": len(key_attacks) > 0,
            "targets_found": targets_found,
            "targets_missing": targets_missing,
            "confidence_scores": {
                "steelman": confidence,
                "overall": confidence
            },
            "suggestions": suggestions
        },
        "steelman_response": {
            "summary": f"Identified {len(key_attacks)} potential attacks on your argument.",
            "key_attacks": key_attacks,
            "adverse_precedent": [
                {
                    "case": a["case_name"],
                    "citation": a["citation"],
                    "holding": a["adverse_holding"][:200],
                    "severity": a.get("severity", "unknown")
                }
                for a in adverse_holdings[:5]
            ],
            "element_weaknesses": element_weaknesses,
            "draft_response": draft_response
        }
    }


def _extract_argument_claims(text: str) -> List[str]:
    """Extract explicit legal claims from argument text."""
    claims = []

    claim_patterns = [
        r'(?:plaintiff|defendant|we|petitioner|appellant)\s+(?:must|should|will)\s+(?:prove|establish|show|demonstrate)\s+([^.]+\.)',
        r'(?:the|this)\s+(?:court|evidence|record)\s+(?:shows?|demonstrates?|establishes?|proves?)\s+([^.]+\.)',
        r'(?:as|because|since)\s+(?:the|this)\s+([^,]+),\s+(?:plaintiff|defendant|we)',
        r'(?:therefore|thus|accordingly),?\s+([^.]+\.)',
    ]

    for pattern in claim_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            claim = match.group(1).strip() if match.groups() else match.group(0).strip()
            if len(claim) > 20:
                claims.append(claim)

    return claims[:10]


def _get_elements_for_claim_type(claim_type: str) -> List[str]:
    """Get legal elements for common claim types."""
    elements_map = {
        "excessive_force": [
            "seizure occurred",
            "force was objectively unreasonable",
            "causation"
        ],
        "negligence": [
            "duty",
            "breach",
            "causation",
            "damages"
        ],
        "fraud": [
            "false representation",
            "materiality",
            "scienter",
            "reliance",
            "damages"
        ],
        "breach_of_contract": [
            "valid contract",
            "plaintiff's performance",
            "defendant's breach",
            "damages"
        ],
        "securities_fraud": [
            "material misrepresentation or omission",
            "scienter",
            "connection with purchase or sale",
            "reliance",
            "economic loss",
            "loss causation"
        ],
        "discrimination": [
            "protected class membership",
            "adverse action",
            "causation",
            "damages"
        ]
    }

    claim_lower = claim_type.lower().replace(" ", "_").replace("-", "_")
    return elements_map.get(claim_lower, [])


def _generate_steelman_draft(
    claims: List[str],
    attacks: List[Dict],
    adverse_holdings: List[Dict],
    element_weaknesses: List[Dict]
) -> str:
    """Generate a draft opposing response paragraph."""
    parts = []

    # Opening
    if adverse_holdings:
        primary_adverse = adverse_holdings[0]
        parts.append(
            f"Plaintiff's argument fails under {primary_adverse['case_name']}. "
        )
    else:
        parts.append("Plaintiff's argument is fatally flawed for several reasons. ")

    # Element attack
    if element_weaknesses:
        weakness = element_weaknesses[0]
        parts.append(
            f"First, Plaintiff fails to establish {weakness['element']}. "
        )

    # Authority attack
    if adverse_holdings:
        adv = adverse_holdings[0]
        parts.append(
            f"In {adv['case_name']}, the court held that {adv['adverse_holding'][:150]}. "
            f"Here, Plaintiff's position is directly contrary to this binding precedent. "
        )

    # Conclusion
    parts.append(
        "For these reasons, Plaintiff's argument should be rejected."
    )

    return "".join(parts)


def steelman_counterargument_mcp(
    your_argument: str,
    case_texts: Dict[str, str],
    claim_type: Optional[str] = None
) -> str:
    """MCP wrapper for steelman_counterargument."""
    result = steelman_counterargument(your_argument, case_texts, claim_type)

    output = []
    output.append("=" * 70)
    output.append("STEELMAN COUNTERARGUMENT")
    output.append("=" * 70)

    resp = result["steelman_response"]
    output.append(f"\n{resp['summary']}")

    # Key attacks
    output.append("\n" + "-" * 40)
    output.append("KEY ATTACKS ON YOUR POSITION:")
    for i, attack in enumerate(resp["key_attacks"][:5], 1):
        output.append(f"\n[{i}] {attack['attack_type'].upper()} (strength: {attack['strength']:.0%})")
        output.append(f"    Target: {attack['target'][:100]}")
        output.append(f"    Attack: {attack['attack'][:200]}")
        if attack.get("supporting_authority"):
            output.append(f"    Authority: {attack['supporting_authority']}")

    # Adverse precedent
    if resp["adverse_precedent"]:
        output.append("\n" + "-" * 40)
        output.append("ADVERSE PRECEDENT:")
        for adv in resp["adverse_precedent"][:3]:
            severity_icon = "[!!!]" if adv["severity"] == "fatal" else "[!!]" if adv["severity"] == "serious" else "[!]"
            output.append(f"\n{severity_icon} {adv['case']}, {adv['citation']}")
            output.append(f"    {adv['holding'][:200]}...")

    # Element weaknesses
    if resp["element_weaknesses"]:
        output.append("\n" + "-" * 40)
        output.append("ELEMENT GAPS:")
        for weak in resp["element_weaknesses"]:
            output.append(f"\n  [{weak['element'].upper()}]")
            output.append(f"    Gap: {weak['gap']}")
            output.append(f"    Exploit: {weak['exploit']}")

    # Draft response
    output.append("\n" + "-" * 40)
    output.append("DRAFT OPPOSING RESPONSE:")
    output.append(f"\n{resp['draft_response']}")

    # Extraction report
    meta = result["_meta"]
    output.append("\n" + "-" * 40)
    output.append("EXTRACTION REPORT:")
    for target in meta["targets_found"]:
        output.append(f"  [OK] {target}")
    for target in meta["targets_missing"]:
        output.append(f"  [X] {target}")
    if meta["suggestions"]:
        output.append("\nSuggestions:")
        for sug in meta["suggestions"]:
            output.append(f"  - {sug}")

    output.append("\n" + "=" * 70)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2, default=str))

    return "\n".join(output)


def generate_distinction(
    adverse_case_name: str,
    adverse_case_text: str,
    adverse_citation: str,
    your_facts: str,
    your_position: str
) -> Dict[str, Any]:
    """
    Generate paste-ready distinction language for an adverse case.

    This tool analyzes how the adverse case differs from your situation
    and generates multiple distinction strategies.

    Args:
        adverse_case_name: Name of the adverse case
        adverse_case_text: Full text of the adverse case
        adverse_citation: Citation for the adverse case
        your_facts: Your client's facts
        your_position: Your legal argument/position

    Returns:
        Dict with "_meta" and distinction analysis with draft language
    """
    targets_found = []
    targets_missing = []
    suggestions = []

    # Import here to avoid circular imports
    try:
        from enhanced_rules import extract_enhanced_rules
        from brief_synthesis import extract_case_facts
    except ImportError:
        extract_enhanced_rules = None
        extract_case_facts = None

    # Step 1: Extract adverse holding
    adverse_holding = None
    adverse_rules = []

    if extract_enhanced_rules:
        adverse_rules = extract_enhanced_rules(
            adverse_case_text, adverse_case_name, adverse_citation
        )
        # Find the primary holding
        for rule in adverse_rules:
            if hasattr(rule.rule_type, 'value') and rule.rule_type.value == 'holding':
                adverse_holding = rule.text
                break
        if not adverse_holding and adverse_rules:
            adverse_holding = adverse_rules[0].text

    if adverse_holding:
        targets_found.append("adverse_holding")
    else:
        targets_missing.append("adverse_holding")
        # Fallback: search for holding patterns
        holding_match = re.search(
            r'(?:we|the court)\s+(?:hold|held|conclude[sd]?)\s+that\s+([^.]+\.)',
            adverse_case_text, re.IGNORECASE
        )
        if holding_match:
            adverse_holding = holding_match.group(1)
            targets_found.append("adverse_holding")
        else:
            adverse_holding = "holding not extracted"
            suggestions.append(
                "Could not extract adverse holding. Provide case text with explicit 'we hold' language."
            )

    # Step 2: Extract adverse facts
    adverse_facts = []
    if extract_case_facts:
        adverse_facts = extract_case_facts(adverse_case_text)[:5]

    if adverse_facts:
        targets_found.append("adverse_facts")
    else:
        targets_missing.append("adverse_facts")
        suggestions.append(
            "Could not extract facts from adverse case. It may be procedural or lack factual detail."
        )

    # Step 3: Extract your facts (parse sentences)
    your_fact_list = [s.strip() for s in re.split(r'(?<=[.!?])\s+', your_facts)
                      if len(s.strip()) > 20][:5]

    # Step 4: Determine distinction type
    distinction_type = _determine_distinction_type(
        adverse_holding, adverse_facts, your_fact_list, your_position, adverse_case_text
    )

    # Step 5: Calculate distinction strength
    # Higher if facts are clearly different
    fact_overlap = 0
    if adverse_facts and your_fact_list:
        adverse_words = set(' '.join(adverse_facts).lower().split())
        your_words = set(' '.join(your_fact_list).lower().split())
        common = adverse_words & your_words
        fact_overlap = len(common) / max(len(adverse_words), 1)

    distinction_strength = 1.0 - fact_overlap
    distinction_strength = max(0.3, min(0.95, distinction_strength))

    # Step 6: Generate distinction language
    draft_language = _generate_distinction_language(
        adverse_case_name, adverse_citation, adverse_holding,
        adverse_facts, your_fact_list, distinction_type
    )

    return {
        "_meta": {
            "extraction_complete": len(targets_missing) == 0,
            "targets_found": targets_found,
            "targets_missing": targets_missing,
            "confidence_scores": {
                "distinction": round(distinction_strength, 2),
                "overall": round(distinction_strength, 2)
            },
            "suggestions": suggestions
        },
        "distinction": {
            "adverse_holding": adverse_holding[:500] if adverse_holding else None,
            "adverse_facts": adverse_facts,
            "your_facts": your_fact_list,
            "distinction_type": distinction_type,
            "distinction_strength": round(distinction_strength, 2),
            "draft_language": draft_language
        }
    }


def _determine_distinction_type(
    adverse_holding: str,
    adverse_facts: List[str],
    your_facts: List[str],
    your_position: str,
    adverse_text: str
) -> str:
    """Determine the best distinction strategy."""

    adverse_lower = adverse_text.lower()
    position_lower = your_position.lower()

    # Check for procedural distinction
    procedural_terms = ['motion to dismiss', 'summary judgment', 'appeal', 'preliminary injunction']
    for term in procedural_terms:
        if term in adverse_lower and term not in position_lower:
            return "procedural"

    # Check for legal issue distinction
    if re.search(r'different\s+(?:issue|question|claim)', position_lower):
        return "legal_issue"

    # Check for scope/narrow holding
    narrow_indicators = ['limited to', 'only where', 'narrow', 'specific']
    if any(ind in adverse_lower for ind in narrow_indicators):
        return "scope"

    # Default to factual distinction
    return "factual"


def _generate_distinction_language(
    case_name: str,
    citation: str,
    holding: str,
    adverse_facts: List[str],
    your_facts: List[str],
    distinction_type: str
) -> List[str]:
    """Generate multiple distinction language options."""
    drafts = []

    # Primary distinction based on type
    if distinction_type == "factual":
        if adverse_facts and your_facts:
            drafts.append(
                f"{case_name} is distinguishable. There, {adverse_facts[0].lower().rstrip('.')}. "
                f"Here, by contrast, {your_facts[0].lower().rstrip('.')}. "
                f"See {citation}."
            )
        drafts.append(
            f"Unlike in {case_name}, where the facts supported the defendant's position, "
            f"here the facts establish liability. {citation}."
        )

    elif distinction_type == "procedural":
        drafts.append(
            f"{case_name} arose in a different procedural posture and is inapposite. "
            f"See {citation}."
        )
        drafts.append(
            f"The holding in {case_name} does not control here because that case "
            f"involved a different procedural standard. {citation}."
        )

    elif distinction_type == "legal_issue":
        drafts.append(
            f"{case_name} addressed a different legal question than the one before this Court. "
            f"See {citation}."
        )
        drafts.append(
            f"While {case_name} is superficially similar, it did not decide the issue presented here. "
            f"{citation}."
        )

    elif distinction_type == "scope":
        drafts.append(
            f"The holding in {case_name} was expressly limited and does not extend to these facts. "
            f"See {citation}."
        )
        drafts.append(
            f"{case_name} should be read narrowly. Its holding applies only to [specific context], "
            f"not to situations like this one. {citation}."
        )

    # Add generic fallback
    drafts.append(
        f"{case_name} does not compel a different result. "
        f"The facts and circumstances here are materially different. {citation}."
    )

    return drafts


def generate_distinction_mcp(
    adverse_case_name: str,
    adverse_case_text: str,
    adverse_citation: str,
    your_facts: str,
    your_position: str
) -> str:
    """MCP wrapper for generate_distinction."""
    result = generate_distinction(
        adverse_case_name, adverse_case_text, adverse_citation, your_facts, your_position
    )

    output = []
    output.append("=" * 70)
    output.append("DISTINCTION ANALYSIS")
    output.append("=" * 70)

    dist = result["distinction"]

    # Adverse holding
    output.append("\nADVERSE HOLDING:")
    output.append(f"  {dist['adverse_holding'][:400]}...")

    # Distinction type and strength
    output.append(f"\nDISTINCTION TYPE: {dist['distinction_type'].upper()}")
    output.append(f"DISTINCTION STRENGTH: {dist['distinction_strength']:.0%}")

    # Factual comparison
    if dist["adverse_facts"]:
        output.append("\n" + "-" * 40)
        output.append("ADVERSE CASE FACTS:")
        for fact in dist["adverse_facts"][:3]:
            output.append(f"  - {fact[:150]}...")

    if dist["your_facts"]:
        output.append("\nYOUR FACTS:")
        for fact in dist["your_facts"][:3]:
            output.append(f"  - {fact[:150]}...")

    # Draft language
    output.append("\n" + "-" * 40)
    output.append("DRAFT DISTINCTION LANGUAGE (paste-ready):")
    for i, draft in enumerate(dist["draft_language"], 1):
        output.append(f"\n[Option {i}]")
        output.append(f"  \"{draft}\"")

    # Extraction report
    meta = result["_meta"]
    output.append("\n" + "-" * 40)
    output.append("EXTRACTION REPORT:")
    for target in meta["targets_found"]:
        conf = meta["confidence_scores"].get(target, meta["confidence_scores"].get("overall", 0))
        output.append(f"  [OK] {target}")
    for target in meta["targets_missing"]:
        output.append(f"  [X] {target}")

    if meta["suggestions"]:
        output.append("\nSuggestions:")
        for sug in meta["suggestions"]:
            output.append(f"  - {sug}")

    output.append("\n" + "=" * 70)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2, default=str))

    return "\n".join(output)


def identify_fact_gaps(
    legal_standard: str,
    elements: List[str],
    your_facts: str,
    record_available: Optional[str] = None
) -> Dict[str, Any]:
    """
    Identify what facts are missing to satisfy each element of a legal standard.

    This tool maps your facts to legal elements and identifies gaps
    that need to be filled through discovery or additional evidence.

    Args:
        legal_standard: The legal standard/test you must satisfy
        elements: List of elements to prove
        your_facts: Your current facts
        record_available: Optional description of available record sources

    Returns:
        Dict with "_meta" and gap analysis with discovery suggestions
    """
    targets_found = []
    targets_missing = []
    suggestions = []

    # Parse your facts into sentences
    fact_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', your_facts)
                      if len(s.strip()) > 15]

    # Analyze each element
    element_analysis = []
    satisfied_count = 0
    weak_count = 0
    missing_count = 0

    for element in elements:
        element_lower = element.lower()
        element_words = set(re.findall(r'\b\w{4,}\b', element_lower))  # Words 4+ chars

        # Find facts that might support this element
        supporting_facts = []
        for fact in fact_sentences:
            fact_lower = fact.lower()
            fact_words = set(re.findall(r'\b\w{4,}\b', fact_lower))

            # Check word overlap
            overlap = element_words & fact_words
            if len(overlap) >= 1:
                supporting_facts.append(fact)

        # Calculate confidence
        if len(supporting_facts) >= 2:
            status = "satisfied"
            confidence = 0.80
            satisfied_count += 1
        elif len(supporting_facts) == 1:
            status = "weak"
            confidence = 0.50
            weak_count += 1
        else:
            status = "missing"
            confidence = 0.10
            missing_count += 1

        # Identify specific gaps
        gaps = []
        if status in ("weak", "missing"):
            gaps.append(f"No facts directly establish '{element}'")

            # Generate specific gap description
            if 'intent' in element_lower or 'scienter' in element_lower:
                gaps.append("Need evidence of defendant's state of mind")
            if 'causation' in element_lower or 'caused' in element_lower:
                gaps.append("Need evidence linking defendant's action to harm")
            if 'damages' in element_lower:
                gaps.append("Need quantification of harm suffered")
            if 'knowledge' in element_lower or 'knew' in element_lower:
                gaps.append("Need evidence defendant knew of relevant facts")

        # Generate discovery suggestions
        discovery_suggestions = _generate_discovery_suggestions(element, status)

        element_analysis.append({
            "element": element,
            "status": status,
            "supporting_facts": supporting_facts[:3],
            "gaps": gaps,
            "confidence": round(confidence, 2),
            "suggested_discovery": discovery_suggestions
        })

    # Overall sufficiency
    total = len(elements)
    if total > 0:
        overall_sufficiency = (satisfied_count * 1.0 + weak_count * 0.5) / total
    else:
        overall_sufficiency = 0.0

    # Identify critical gaps
    critical_gaps = [
        ea["element"] for ea in element_analysis
        if ea["status"] == "missing"
    ]

    # Build targets
    if satisfied_count > 0:
        targets_found.append("supported_elements")
    if weak_count > 0:
        targets_found.append("weak_elements")
    if missing_count > 0:
        targets_missing.append("missing_elements")
        suggestions.append(
            f"{missing_count} element(s) have no factual support. "
            "Discovery should target these gaps."
        )

    return {
        "_meta": {
            "extraction_complete": missing_count == 0,
            "targets_found": targets_found,
            "targets_missing": targets_missing,
            "confidence_scores": {
                "sufficiency": round(overall_sufficiency, 2),
                "overall": round(overall_sufficiency, 2)
            },
            "suggestions": suggestions
        },
        "gap_analysis": {
            "overall_sufficiency": round(overall_sufficiency, 2),
            "elements": element_analysis,
            "critical_gaps": critical_gaps,
            "elements_satisfied": satisfied_count,
            "elements_weak": weak_count,
            "elements_missing": missing_count
        }
    }


def _generate_discovery_suggestions(element: str, status: str) -> List[str]:
    """Generate discovery suggestions for an element gap."""
    suggestions = []
    element_lower = element.lower()

    if status == "satisfied":
        return []

    # General suggestions
    suggestions.append(f"Deposition question: What facts support {element}?")

    # Element-specific suggestions
    if 'intent' in element_lower or 'scienter' in element_lower:
        suggestions.append("Document request: Communications showing defendant's knowledge")
        suggestions.append("Deposition: Ask about defendant's state of mind")

    if 'causation' in element_lower:
        suggestions.append("Expert discovery: Obtain expert opinion on causation")
        suggestions.append("Document request: Timeline of events")

    if 'damages' in element_lower:
        suggestions.append("Interrogatory: Itemization of all damages claimed")
        suggestions.append("Document request: Financial records, medical bills")

    if 'knowledge' in element_lower or 'knew' in element_lower:
        suggestions.append("Document request: Emails, memos showing knowledge")
        suggestions.append("30(b)(6) deposition: Corporate knowledge")

    if 'reasonable' in element_lower:
        suggestions.append("Expert discovery: Standard of care opinion")

    if 'duty' in element_lower:
        suggestions.append("Document request: Policies, procedures, contracts")

    return suggestions[:4]


def identify_fact_gaps_mcp(
    legal_standard: str,
    elements: List[str],
    your_facts: str,
    record_available: Optional[str] = None
) -> str:
    """MCP wrapper for identify_fact_gaps."""
    result = identify_fact_gaps(legal_standard, elements, your_facts, record_available)

    output = []
    output.append("=" * 70)
    output.append("FACT GAP ANALYSIS")
    output.append("=" * 70)

    gap = result["gap_analysis"]

    output.append(f"\nLEGAL STANDARD: {legal_standard[:200]}")
    output.append(f"\nOVERALL SUFFICIENCY: {gap['overall_sufficiency']:.0%}")
    output.append(f"  Satisfied: {gap['elements_satisfied']}")
    output.append(f"  Weak: {gap['elements_weak']}")
    output.append(f"  Missing: {gap['elements_missing']}")

    # Element-by-element analysis
    output.append("\n" + "-" * 40)
    output.append("ELEMENT-BY-ELEMENT ANALYSIS:")

    for ea in gap["elements"]:
        status_icon = "[OK]" if ea["status"] == "satisfied" else "[~]" if ea["status"] == "weak" else "[X]"
        output.append(f"\n{status_icon} {ea['element'].upper()}")
        output.append(f"    Status: {ea['status']} ({ea['confidence']:.0%} confidence)")

        if ea["supporting_facts"]:
            output.append("    Supporting facts:")
            for fact in ea["supporting_facts"][:2]:
                output.append(f"      - {fact[:100]}...")

        if ea["gaps"]:
            output.append("    Gaps:")
            for g in ea["gaps"][:2]:
                output.append(f"      - {g}")

        if ea["suggested_discovery"] and ea["status"] != "satisfied":
            output.append("    Discovery targets:")
            for disc in ea["suggested_discovery"][:2]:
                output.append(f"      - {disc}")

    # Critical path
    if gap["critical_gaps"]:
        output.append("\n" + "-" * 40)
        output.append("CRITICAL PATH:")
        output.append(f"  To prevail, you must establish: {', '.join(gap['critical_gaps'])}")
        output.append("  Priority: Focus discovery on these elements first.")

    # Extraction report
    meta = result["_meta"]
    if meta["suggestions"]:
        output.append("\n" + "-" * 40)
        output.append("RECOMMENDATIONS:")
        for sug in meta["suggestions"]:
            output.append(f"  - {sug}")

    output.append("\n" + "=" * 70)
    output.append("JSON_DATA:")
    output.append(json.dumps(result, indent=2, default=str))

    return "\n".join(output)
