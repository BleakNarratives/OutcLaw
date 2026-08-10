#!/usr/bin/env python3
"""
outclaw_unified.py -- OutClaw Unified Audit Orchestrator (orchestrator-as-source-of-truth rewrite).

Background
----------
Earlier revisions called ``outclaw_depth_detector.SemanticValidator.validate_text``
to produce findings. Probe basher diagnostics revealed that depth_mod
unreliably returns EMPTY findings for cases where the regex clearly matches
(e.g. "42 U.S.C. § 1983" inside a single-sentence statute path), and stores
a TRUNCATED ``sentence`` field on findings (e.g. "Jones, 123 F.3d 456."
instead of the full "Smith v. Jones, 123 F.3d 456.").

Per the design intent, the orchestrator is the source of truth on audit
findings. We now:
  1. Use orchestrator-owned CITATION_RE (verbatim copy of depth_mod's regex
     so behaviour stays compatible) and walk the text directly.
  2. For each citation found, look up the case / statute registry from the
     injected seed (case_db, statute_db).
  3. Compute the support score using a PRIOR-SENTENCE WINDOW so cross-sentence
     citations (e.g. case [6]) are scored honestly from the start -- no
     post-hoc rescore pass required for that recovery.
  4. Apply the negation-flip detector (now expanded with modal-verb pairs)
     for OPPOSITE HOLDING / MISQUOTE / OPPOSITE escalation.
  5. depth_mod is retained ONLY for the lightweight RegexBaseline.find()
     hit-count and unchanged.
  6. (BUFF-FIX 2026-07-26) Optional LLM fallback via outclaw_llm.py for
     genuinely ambiguous classifications where regex heuristics cannot
     distinguish between OPPOSITE HOLDING and NO SUPPORT.

Severity mapping (single source of truth shared with regression runner):
  - EXISTENCE, NEGATIVE TREATMENT, OPPOSITE HOLDING, MISQUOTE / OPPOSITE  -> HIGH
  - NO SUPPORT                                                            -> MEDIUM
  - SUPPORTED                                                              -> OK
  - unknown failure                                                        -> MEDIUM (don't silently downgrade)

LLM fallback (opt-in, off by default for regression reproducibility):
  - Consulted ONLY when heuristic score is in the ambiguous range (0.0-0.25)
    and the citation EXISTS in the registry (not fabricated).
  - Purpose: regex cannot detect OPPOSITE HOLDING without surface negators
    (e.g., "The court held X" when holding is "did not hold X").
  - Never overrides EXISTENCE, NEGATIVE TREATMENT, or clear SUPPORTED findings.
  - Controlled by ``use_llm`` kwarg on ``audit_text()``. Default: False.

Window-overlap-based override:
  - If depth_mod would label OPPOSITE HOLDING but the prior+current-window
    fan-out gives a substantive overlap score against the holding, allow
    the orchestrator to recover the finding to OK. This is what makes
    case [6] return OK even though depth_mod (and our orchestrator's raw
    score on the citation-only sentence) would mark it OPPOSITE HOLDING.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_SEED_PATH = _HERE / "outclaw_seed.json"

sys.path.insert(0, str(_HERE))
import outclaw_depth_detector as depth_mod  # type: ignore

try:
    import outclaw_arch as arch_mod  # type: ignore
except ModuleNotFoundError:
    # ``outclaw_arch.py`` predates the canonical OutClaw_Main boundary and
    # remains at the repository root. Load that read-only helper explicitly
    # when this project is executed from its own directory.
    import importlib.util

    _ARCH_PATH = _HERE.parent / "outclaw_arch.py"
    _ARCH_SPEC = importlib.util.spec_from_file_location("outclaw_arch", _ARCH_PATH)
    if _ARCH_SPEC is None or _ARCH_SPEC.loader is None:
        raise
    arch_mod = importlib.util.module_from_spec(_ARCH_SPEC)
    _ARCH_SPEC.loader.exec_module(arch_mod)

# LLM layer -- optional, lazy-loaded, never imported at module level
# to keep the regression suite deterministic when use_llm=False.
_llm_log = logging.getLogger("outclaw.llm")


CITATION_RE = depth_mod.SemanticValidator.CITATION_RE


# ---------------------------------------------------------------------------
# Severity taxonomy
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"OK": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
OK = "OK"

_HIGH_RULES = frozenset(
    {
        "EXISTENCE",
        "NEGATIVE TREATMENT",
        "OPPOSITE HOLDING",
        "MISQUOTE / OPPOSITE",
    }
)
_MEDIUM_RULES = frozenset(
    {
        "NO SUPPORT",
    }
)


def severity_from_rule(rule: str, ok: bool) -> str:
    if ok:
        return OK
    if rule in _HIGH_RULES:
        return HIGH
    if rule in _MEDIUM_RULES:
        return MEDIUM
    return MEDIUM


# ---------------------------------------------------------------------------
# Negation flip + window-overlap score
# ---------------------------------------------------------------------------

_NEGATION_TOKENS = ("not ", "no,", "no ", "cannot", "must not", "does not", "never")
# Polarity pairs (post code review): kept narrow to avoid false positives on
# neutral legal prose (e.g. "the motion was denied, but contempt was granted"
# -- those are NOT a flip of each other).
_POLARITY_PAIRS = (
    ("cannot", "must"),
    ("cannot", "shall"),
    ("may not", "shall"),
    ("never", "always"),
    ("no ", "every "),
    ("prohibited", "required"),
    ("void", "valid"),
    ("reject", "approve"),
)
_WITHOUT_NOUN_RE = re.compile(r"\bwithout\s+(?:a\s+|the\s+|an\s+)?([a-zA-Z]{3,})")
# Nouns that commonly appear after "without" in legal English but should NOT
# trigger a polarity flip (they are neutral procedural phrases, not a denial
# of substance). Keeps the without-X heuristic from false-firing on phrases
# like "without prejudice", "without notice", "without limitation".
_WITHOUT_NOUN_SKIPLIST = frozenset(
    {
        "prejudice",
        "limitation",
        "notice",
        "hearing",
        "leave",
        "objection",
        "intervention",
        "delay",
        "warrant_of",
        "exception",
        "precedent",
        "recourse",
    }
)


# ═══════════════════════════════════════════════════════
#  TEXT HELPERS — pushed down
# ═══════════════════════════════════════════════════════════════

def _negates_holding(proposition: str, holding_lower: str) -> bool:
    """Detect a polarity flip between proposition and holding."""
    if any(tok in proposition.lower() for tok in _NEGATION_TOKENS):
        if not any(tok in holding_lower for tok in _NEGATION_TOKENS):
            return True
    prop_lower = proposition.lower()
    for neg_verb, pos_verb in _POLARITY_PAIRS:
        in_prop = neg_verb in prop_lower
        in_hold = pos_verb in holding_lower
        if in_prop and in_hold and neg_verb not in holding_lower:
            return True
        in_prop_pos = pos_verb in prop_lower
        in_hold_neg = neg_verb in holding_lower
        if in_prop_pos and in_hold_neg and pos_verb not in holding_lower:
            return True
    # Special: "without [noun]" affirmatively negates a required-[noun]
    # holding. Captures case 1 ("without a warrant" vs holding that
    # requires warrant). Skip the curated skiplist of neutral procedural
    # "without X" phrases.
    m = _WITHOUT_NOUN_RE.search(prop_lower)
    if m:
        noun = m.group(1).rstrip(".,;:!?")
        if (
            noun
            and noun not in _WITHOUT_NOUN_SKIPLIST
            and noun in holding_lower
            and f"without {noun}" not in holding_lower
        ):
            return True
    return False


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_ABBREVIATION_MARKERS = {
    "U.S.C.": "U§S§C§",
    "U.S.": "U§S§",
    "v.": "v§",
}


def _split_sentences(text: str) -> list[str]:
    """Split prose without treating common legal abbreviations as endings."""
    protected = text
    for abbreviation, marker in _ABBREVIATION_MARKERS.items():
        protected = protected.replace(abbreviation, marker)
    sentences = _SENTENCE_SPLIT.split(protected)
    for index, sentence in enumerate(sentences):
        for abbreviation, marker in _ABBREVIATION_MARKERS.items():
            sentences[index] = sentences[index].replace(marker, abbreviation)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _proposition(prior_window: str, citation: str) -> str:
    prop = prior_window.replace(citation, " ")
    return " ".join(prop.split())


def _lexical_score(proposition: str, target: str) -> float:
    """
    Jaccard-like score over alpha-only tokens of length >= 3 (case-insensitive).
    Mirrors the spirit of depth_mod._supports without inverting on negation
    (negation is handled separately by _negates_holding).
    """
    prop_words = set(re.findall(r"[a-zA-Z]{3,}", proposition.lower()))
    hold_words = set(re.findall(r"[a-zA-Z]{3,}", target.lower()))
    if not prop_words or not hold_words:
        return 0.0
    shared = prop_words & hold_words
    score = len(shared) / max(len(prop_words), len(hold_words))
    return min(1.0, score)


# ---------------------------------------------------------------------------
# Seed loader
# ---------------------------------------------------------------------------


# ═══════════════════════════════════════════════════════
#  SEED LOADER — pushed down
# ═══════════════════════════════════════════════════════════════

def load_seed(path: Path | None = None) -> dict[str, Any]:
    p = path or _SEED_PATH
    if not p.exists():
        raise FileNotFoundError(f"OutClaw seed not found at {p}.")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "_about" not in data or "cases" not in data or "statutes" not in data:
        raise ValueError(f"OutClaw seed {p} is missing required keys.")
    return data


def _norm_key(s: str) -> str:
    """Canonicalise a citation key by collapsing whitespace."""
    return " ".join(s.split())


def _dict_to_case_entry(d: dict[str, Any]) -> depth_mod.CaseEntry:
    return depth_mod.CaseEntry(
        name=d.get("name", ""),
        holding=d.get("holding", ""),
        overruled=bool(d.get("overruled", False)),
        distinguished_by=tuple(d.get("distinguished_by", ())),
        area=d.get("area", "general"),
    )


def inject_seed_into_seed(dataclass_instance: Any, seed: dict[str, Any]) -> None:
    """Inject seed registries into a depth_mod.SemanticValidator post-construction."""
    dataclass_instance.case_db = {
        _norm_key(k): _dict_to_case_entry(v) for k, v in seed["cases"].items()
    }
    dataclass_instance.statute_db = {
        _norm_key(k): v for k, v in seed["statutes"].items()
    }


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    citation: str
    rule: str
    severity: str
    sentence: str
    detail: str
    score: float = 0.0
    recovered_by_window: bool = False
    llm_assisted: bool = False  # BUFF-FIX: track LLM involvement


# ---------------------------------------------------------------------------
# Per-citation classifier (orchestrator's source of truth on findings)
# ---------------------------------------------------------------------------


# ═══════════════════════════════════════════════════════
#  CLASSIFIERS — pushed down
# ═══════════════════════════════════════════════════════════════

def _classify_citation(
    citation_norm: str,
    kind: str | None,
    proposition: str,
    case_db: dict[str, Any],
    statute_db: dict[str, str],
    use_llm: bool = False,
) -> tuple[str, str, float, bool, bool]:
    """
    Returns (rule, severity, score, recovered_via_window, llm_assisted).

    Recovery is allowed ONLY when the prior-window context substantively
    supports the citation. Window-overlap threshold: >= 0.5 with at least
    5 shared words and no negative-rule trigger.

    LLM assistance is tracked in the 5th return value for observability.
    """
    if kind == "statute":
        return _classify_statute(
            citation_norm, proposition, statute_db, use_llm=use_llm
        )
    if kind == "case":
        return _classify_case(citation_norm, proposition, case_db, use_llm=use_llm)
    if kind == "cfr":
        if citation_norm not in statute_db:
            return ("EXISTENCE", HIGH, 0.0, False, False)
        return ("SUPPORTED", OK, 1.0, False, False)
    return ("EXISTENCE", HIGH, 0.0, False, False)


def _classify_statute(
    citation_norm: str,
    proposition: str,
    statute_db: dict[str, str],
    use_llm: bool = False,
) -> tuple[str, str, float, bool, bool]:
    if citation_norm not in statute_db:
        return ("EXISTENCE", HIGH, 0.0, False, False)
    target = statute_db[citation_norm]
    if _negates_holding(proposition, target.lower()):
        return ("MISQUOTE / OPPOSITE", HIGH, 0.0, False, False)
    score = _lexical_score(proposition, target)
    if score >= 0.3:
        return ("SUPPORTED", OK, score, score > 0.5, False)
    if score >= 0.15:
        return ("NO SUPPORT", MEDIUM, score, False, False)
    # score < 0.15: ambiguous. Consult LLM if enabled, then fall back.
    if use_llm and score < 0.15:
        llm_result = _consult_llm_opposite_holding(proposition, target)
        if llm_result is not None and llm_result.get("is_opposite"):
            if llm_result.get("confidence", 0.0) >= 0.70:
                return ("MISQUOTE / OPPOSITE", HIGH, 0.0, False, True)
    if _negates_holding(proposition, target.lower()):
        return ("MISQUOTE / OPPOSITE", HIGH, 0.0, False, False)
    return ("NO SUPPORT", MEDIUM, score, False, False)


def _classify_case(
    citation_norm: str,
    proposition: str,
    case_db: dict[str, Any],
    use_llm: bool = False,
) -> tuple[str, str, float, bool, bool]:
    """
    Returns (rule, severity, score, recovered_via_window, llm_assisted).

    LLM fallback (when use_llm=True): consulted only in the ambiguous
    score range (0.0-0.25) where regex cannot distinguish OPPOSITE HOLDING
    from NO SUPPORT. The LLM is asked directly: "Does this proposition
    assert the opposite of what this case holds?"
    """
    if citation_norm not in case_db:
        return ("EXISTENCE", HIGH, 0.0, False, False)
    entry = case_db[citation_norm]
    target = entry.holding if hasattr(entry, "holding") else entry["holding"]
    if hasattr(entry, "overruled") and entry.overruled:
        return ("NEGATIVE TREATMENT", HIGH, 0.0, False, False)
    flip = _negates_holding(proposition, target.lower())
    score = _lexical_score(proposition, target)
    shared = _shared_word_count(proposition, target)
    # Same threshold for both SUPPORTED paths (rediscovery via prior-
    # sentence window OR scored via immediate sentence). shared >= 4 keeps
    # this conservative (\u2265 4 substantive legal-vocabulary words).
    if score >= 0.5 and not flip and shared >= 4:
        return ("SUPPORTED", OK, score, True, False)
    # Substantive vocabulary overlap with a polarity flip -> OPPOSITE HOLDING.
    if flip and shared >= 3:
        return ("OPPOSITE HOLDING", HIGH, score, False, False)
    # ---- LLM FALLBACK: ambiguous range ----
    if use_llm and score < 0.25 and not flip:
        llm_result = _consult_llm_opposite_holding(proposition, target)
        if llm_result is not None and llm_result.get("is_opposite"):
            llm_conf = llm_result.get("confidence", 0.0)
            if llm_conf >= 0.70:
                return ("OPPOSITE HOLDING", HIGH, score, False, True)
    # ----------------------------------------
    if score >= 0.15:
        return ("NO SUPPORT", MEDIUM, score, False, False)
    return ("NO SUPPORT", MEDIUM, score, False, False)


def _shared_word_count(proposition: str, target: str) -> int:
    prop_words = set(re.findall(r"[a-zA-Z]{3,}", proposition.lower()))
    hold_words = set(re.findall(r"[a-zA-Z]{3,}", target.lower()))
    return len(prop_words & hold_words)


# ---------------------------------------------------------------------------
# Compatibility helpers
# ---------------------------------------------------------------------------


def _disambiguate_rule(
    finding: dict[str, Any],
    case_db: dict[str, Any],
    statute_db: dict[str, str],
) -> tuple[str, float]:
    """Preserve the former rule-disambiguation contract for older callers."""
    if finding.get("rule") != "OPPOSITE HOLDING":
        return finding.get("rule", "NO SUPPORT"), 0.0
    citation = _norm_key(str(finding.get("citation", "")))
    proposition = _proposition(str(finding.get("sentence", "")), citation)
    entry = case_db.get(citation)
    target = (
        (entry.holding if hasattr(entry, "holding") else entry.get("holding", ""))
        if entry is not None
        else statute_db.get(citation, "")
    )
    if not target:
        return "NO SUPPORT", 0.0
    target_lower = target.lower()
    # Preserve the legacy compatibility contract: "may not" versus
    # "must not" is a polarity mismatch even though both contain "not".
    modal_flip = "may not" in proposition.lower() and "must not" in target_lower
    if _negates_holding(proposition, target_lower) or modal_flip:
        return "OPPOSITE HOLDING", 1.0
    return "NO SUPPORT", 0.0


class _FindingDict(dict[str, Any]):
    """Dict result with the attribute access used by legacy callers."""

    def __getattr__(self, name: str) -> Any:
        if name == "recovered_by_window":
            return False
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class SentenceWindowAdapter:
    """Compatibility facade for the former post-hoc sentence-window pass."""

    @staticmethod
    def rescore(
        findings: list[dict[str, Any]],
        text: str,
        case_db: dict[str, Any],
        statute_db: dict[str, str],
    ) -> list[dict[str, Any]]:
        output = [_FindingDict(finding) for finding in findings]
        for finding in output:
            if finding.get("severity") in (HIGH, OK):
                continue
            sentence = str(finding.get("sentence", ""))
            if not sentence or sentence not in text:
                continue
            citation = _norm_key(str(finding.get("citation", "")))
            kind = "statute" if "U.S.C." in citation else "case"
            rule, severity, score, _recovered, _llm = _classify_citation(
                citation,
                kind,
                _proposition(sentence, citation),
                case_db,
                statute_db,
            )
            if rule == "SUPPORTED":
                finding.update(
                    rule=rule,
                    severity=severity,
                    score=score,
                    recovered_by_window=True,
                )
        return output


# ---------------------------------------------------------------------------
# Unified report
# ---------------------------------------------------------------------------


@dataclass
class UnifiedReport:
    text: str
    findings: list[Finding] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "findings": [
                {
                    "citation": f.citation,
                    "rule": f.rule,
                    "severity": f.severity,
                    "sentence": f.sentence,
                    "detail": f.detail,
                    "score": round(f.score, 3),
                    "recovered_by_window": f.recovered_by_window,
                }
                for f in self.findings
            ],
            "candidates": self.candidates,
            "summary": self.summary,
        }

    def safe_to_draft(self) -> bool:
        # Round 24: align with outclaw_safety.py's default -- MEDIUM
        # findings STILL block the draft (federal judges sanction for
        # tangential citations, so the audit cannot let a fabricated /
        # unrelated cite slip through just because the orchestrator
        # couldn't promote it to HIGH).
        # Tighten only if downstream callers explicitly require HIGH-only
        # blocking (none in this repo).
        return all(f.severity not in (HIGH, MEDIUM) for f in self.findings)

    def risk_score(self) -> int:
        """
        Compute the Audit Risk Score (0-100) for this report.
        Delegates to outclaw_scorer.AuditRiskScorer (Predicase gem).
        Lazy-loaded so scorer import only fires when called.
        """
        try:
            from OutClaw.outclaw_scorer import AuditRiskScorer  # type: ignore

            scorer = AuditRiskScorer()
            risk = scorer.score_report(self)
            return risk.score
        except Exception:
            # Fallback: quick score from severity counts
            sc = self.summary.get("severity_counts", {})
            return min(100, sc.get("HIGH", 0) * 25 + sc.get("MEDIUM", 0) * 10)


def _consult_llm_opposite_holding(
    proposition: str, holding: str
) -> dict[str, Any] | None:
    """
    Consult the LLM for OPPOSITE HOLDING detection.
    Lazy-loaded so the import only fires when use_llm=True.
    Returns None if the LLM is unavailable.

    Cascade-only (2026-08-03): the stair-stepped model cascade is the only
    LLM path. OPPOSITE HOLDING is adjudicated on the classification tier
    (tier 2, free cloud) with escalation to the adjudication tier (tier 3)
    on low confidence. There is deliberately NO local model fallback —
    end users will not have models installed.
    """
    try:
        from OutClaw.outclaw_model_cascade import get_cascade  # type: ignore

        cascade = get_cascade()
        if cascade.enabled:
            from OutClaw.outclaw_llm import OPPOSITE_HOLDING_PROMPT  # type: ignore

            prompt = OPPOSITE_HOLDING_PROMPT.format(
                proposition=proposition[:1500],
                holding=holding[:1500],
            )
            result = cascade.complete(
                prompt,
                task="opposite_holding",
                min_confidence=0.70,
                max_tokens=800,
            )
            if result.ok and result.data is not None:
                return result.data
            return None
    except Exception:
        pass  # cascade import failure is non-fatal

    # Fall back through outclaw_llm's validator, which is ALSO cascade-only
    # (no local inference). If the cascade is off/unconfigured it returns
    # None and the deterministic pipeline stands.
    try:
        from OutClaw.outclaw_llm import get_llm  # type: ignore

        llm = get_llm()
        if not llm.is_available():
            return None
        return llm.check_opposite_holding(proposition, holding)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════
#  MAIN API
# ═══════════════════════════════════════════════════════════════

def full_audit_text(
    text: str,
    seed: dict[str, Any] | None = None,
    use_llm: bool = False,
    enable_aura: bool = True,
    enable_benford: bool = False,
    numeric_data: list[float] | None = None,
) -> dict[str, Any]:
    """
    FULL AUDIT PIPELINE: citation audit + aura pattern detection + benford
    (if numeric data) + risk scoring. The complete LWM-integrated pipeline.

    Args:
        text: The draft legal text to audit.
        seed: Optional seed dict.
        use_llm: Enable LLM-assisted classification.
        enable_aura: Run Aura Scout pattern detection (default: True).
        enable_benford: Run Benford's Law analysis on numeric_data.
        numeric_data: Optional list of numbers for Benford analysis.

    Returns:
        Dict with 'citation_audit', 'aura', 'benford', 'risk', 'verdict'.
    """
    result: dict[str, Any] = {}

    # Stage 1: Citation audit
    report = audit_text(text, seed=seed, use_llm=use_llm)
    result["citation_audit"] = report.to_dict()

    # Stage 2: Aura pattern detection
    if enable_aura:
        try:
            from OutClaw.outclaw_aura import AuraBridge  # type: ignore

            bridge = AuraBridge()
            aura_findings = bridge.scan_text(text)
            result["aura"] = {
                "findings": aura_findings,
                "summary": bridge.summary(),
            }
        except Exception as e:
            result["aura"] = {"error": str(e), "findings": [], "summary": {}}
    else:
        result["aura"] = {"skipped": True}

    # Stage 3: Benford's Law
    if enable_benford:
        try:
            from OutClaw.outclaw_benford import BenfordAnalyzer  # type: ignore

            analyzer = BenfordAnalyzer()
            result["benford"] = analyzer.analyze(numeric_data or [])
        except Exception as e:
            result["benford"] = {"error": str(e)}
    else:
        result["benford"] = {"skipped": True}

    # Stage 4: Risk score
    try:
        from OutClaw.outclaw_scorer import AuditRiskScorer  # type: ignore

        scorer = AuditRiskScorer()
        risk = scorer.score_report(report)
        result["risk"] = {
            "score": risk.score,
            "tier": risk.tier,
            "safe_to_file": risk.safe_to_file,
            "recommendation": risk.recommendation,
            "fix_actions": risk.fix_actions,
        }
    except Exception as e:
        result["risk"] = {"error": str(e), "score": 50, "tier": "UNKNOWN"}

    # Verdict
    citation_safe = result["citation_audit"]["summary"]["safe_to_draft"]
    aura_high = 0
    if isinstance(result.get("aura"), dict) and "summary" in result["aura"]:
        aura_high = result["aura"]["summary"].get("high_count", 0)
    risk_score = result.get("risk", {}).get("score", 50)

    if citation_safe and aura_high == 0 and risk_score < 25:
        result["verdict"] = (
            "✅ SAFE TO FILE — no citation fraud, no misconduct patterns, low risk"
        )
    elif citation_safe and aura_high == 0:
        result["verdict"] = (
            "⚠️  CONDITIONAL — citations clean but risk score elevated; review before filing"
        )
    elif not citation_safe and aura_high > 0:
        result["verdict"] = (
            "🚫 DO NOT FILE — citation fraud AND misconduct patterns detected"
        )
    elif not citation_safe:
        result["verdict"] = (
            "🚫 DO NOT FILE — citation fraud detected; fix before filing"
        )
    else:
        result["verdict"] = (
            "⚠️  REVIEW — misconduct patterns detected; verify before filing"
        )

    return result


def audit_text(
    text: str,
    seed: dict[str, Any] | None = None,
    use_llm: bool = False,
    auto_escalate: bool = False,
) -> UnifiedReport:
    """
    Run the unified pipeline (orchestrator as source of truth).

    Args:
        text: The draft legal text to audit.
        seed: Optional seed dict (loaded from outclaw_seed.json if None).
        use_llm: If True, consult the CLOUD-ONLY model cascade during
            classification for ambiguous cases where regex heuristics
            cannot distinguish OPPOSITE HOLDING from NO SUPPORT.
            Default: False.
        auto_escalate: If True, after the deterministic pipeline completes,
            automatically re-examine all MEDIUM-severity findings with the
            cloud cascade.  Uses multi-task escalation:
            opposite-holding → support-scoring.
            Findings are reclassified only when the cascade returns high
            confidence (>= 0.65).  Requires free cloud API keys.  With no
            keys, findings pass through unchanged.  Default: False.
    """
    seed = seed or load_seed()
    text_norm = unicodedata.normalize("NFKC", text)

    case_db = {_norm_key(k): _dict_to_case_entry(v) for k, v in seed["cases"].items()}
    statute_db = dict(seed["statutes"])

    # Stage 1: regex baseline (lightweight hit-count only; depth_mod unreliable).
    regex_hits = depth_mod.RegexBaseline().find(text_norm)

    # Stage 2: orchestrator-owned CITATION_RE walker with prior-window context.
    sentences = _split_sentences(text_norm)
    findings: list[Finding] = []
    for idx, sentence in enumerate(sentences):
        prior_window = " ".join(sentences[max(0, idx - 1) : idx + 1])
        proposition_window = prior_window
        for m in CITATION_RE.finditer(sentence):
            citation_norm = _norm_key(m.group(0))
            # Build proposition WITHOUT the citation (and without the trailing
            # case-name token that depth_mod sometimes drops) from the WINDOW.
            proposition = _proposition(proposition_window, citation_norm)
            rule, severity, score, recovered, llm_assisted = _classify_citation(
                citation_norm,
                m.lastgroup,
                proposition,
                case_db,
                statute_db,
                use_llm=use_llm,
            )
            detail = _detail_for(rule, case_db, statute_db, citation_norm)
            if llm_assisted:
                detail += " [LLM-assisted classification]"
            findings.append(
                Finding(
                    citation=citation_norm,
                    rule=rule,
                    severity=severity,
                    sentence=sentence,
                    detail=detail,
                    score=score,
                    recovered_by_window=recovered,
                    llm_assisted=llm_assisted,
                )
            )

    # Stage 3: arch pipeline (structural validation).
    arch_report = arch_mod.run_pipeline(text_norm)

    # Stage 3.5: LLM auto-escalation (post-processing pass).
    escalation_stats: dict[str, int] = {}
    if auto_escalate:
        try:
            from OutClaw.outclaw_llm_fallback import LLMEscalationLayer  # type: ignore

            escalator = LLMEscalationLayer()
            findings, escalation_stats = escalator.escalate_findings(
                findings, case_db, statute_db  # type: ignore[arg-type]
            )
        except Exception as exc:
            _llm_log.warning("LLM auto-escalation failed: %s", exc)
            escalation_stats = {"error": str(exc)}

    # Stage 4: aggregate.
    severity_counts = {OK: 0, LOW: 0, MEDIUM: 0, HIGH: 0}
    for f in findings:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
    summary = {
        "regex_hits": len(regex_hits),
        "arch_total_citations": arch_report["summary"]["total_citations"],
        "arch_flagged_count": arch_report["summary"]["flagged_count"],
        "severity_counts": severity_counts,
        "recovered_by_window_count": sum(1 for f in findings if f.recovered_by_window),
        "llm_assisted_count": sum(1 for f in findings if f.llm_assisted),
        "llm_escalation": escalation_stats if auto_escalate else {"disabled": True},
        "llm_escalated_count": sum(1 for f in findings if getattr(f, "llm_escalated", False)),
        "safe_to_draft": all(f.severity not in (HIGH, MEDIUM) for f in findings),
    }
    return UnifiedReport(
        text=text_norm,
        findings=findings,
        candidates=arch_report.get("citations", []),
        summary=summary,
    )


def _detail_for(
    rule: str,
    case_db: dict[str, Any],
    statute_db: dict[str, str],
    citation_norm: str,
) -> str:
    if rule == "EXISTENCE":
        return f"Citation '{citation_norm}' not in registry."
    if rule == "NEGATIVE TREATMENT":
        entry = case_db.get(citation_norm)
        name = entry.name if entry and hasattr(entry, "name") else citation_norm
        return f"{name} has been overruled."
    if rule == "OPPOSITE HOLDING":
        entry = case_db.get(citation_norm)
        name = entry.name if entry and hasattr(entry, "name") else citation_norm
        return f"{name} is cited for the opposite of what it holds."
    if rule == "MISQUOTE / OPPOSITE":
        return (
            "Statute text does not support the proposition; possibly inverted meaning."
        )
    if rule == "NO SUPPORT":
        return "Citation exists but does not support this sentence."
    if rule == "SUPPORTED":
        return "Citation supports the proposition."
    return ""


# ---------------------------------------------------------------------------
# OutclawOrchestrator class
# ---------------------------------------------------------------------------
# Round-9 polish: this facade was previously defined IN outclaw_bridge_bootstrap
# and self-imported through the fully-qualified path. It is now defined
# HERE alongside outclaw_unified.audit_text -- where it logically belongs --
# so ``from OutClaw.outclaw_unified import OutclawOrchestrator`` is a clean
# one-liner.


class OutclawOrchestrator:
    """
    Stable instance API wrapping ``audit_text`` so callers
    (``bundle.orchestrator.audit_text(text)``) always get a callable.
    Delegates to the module-level ``audit_text`` function. Catches
    ImportError / ModuleNotFoundError / AttributeError + TypeError (the
    latter for drift guards on ``audit_text`` becoming non-callable).
    """

    def __init__(self, seed_path: Path | None = None):
        self._seed_path = seed_path
        self._seed: dict[str, Any] | None = None
        self._init_error: str | None = None
        # Try to import the audit_text function eagerly so __init__ surfaces
        # real import drift instead of burying it on first .audit_text call.
        try:
            audit_fn = audit_text
            if not callable(audit_fn):
                raise TypeError(
                    f"audit_text is not callable "
                    f"(got {type(audit_fn).__name__}) -- possible programmer drift."
                )
            self._audit_text = audit_fn
        except TypeError as exc:
            self._init_error = repr(exc)
            self._audit_text = None
            sys.stderr.write(
                f"[outclaw_unified] WARN: orchestrator init failed: {exc!r}\n"
            )
            sys.stderr.flush()

    @property
    def has_audit_pipeline(self) -> bool:
        return self._audit_text is not None

    def audit_text(self, text: str) -> Any:
        if self._audit_text is None:
            raise RuntimeError(
                f"audit_text unavailable (init_error={self._init_error!r})"
            )
        return self._audit_text(text, seed=self._get_seed())

    def diagnostics(self) -> dict[str, Any]:
        return {
            "has_audit_pipeline": self.has_audit_pipeline,
            "seed_loaded": self._seed is not None,
            "init_error": self._init_error,
        }

    def _get_seed(self) -> dict[str, Any] | None:
        if self._seed is None and self._seed_path is not None:
            try:
                self._seed = load_seed(self._seed_path)
            except Exception as exc:
                self._init_error = repr(exc)
        return self._seed


# ---------------------------------------------------------------------------
# Pretty-print
# ---------------------------------------------------------------------------


def _print_summary(report: UnifiedReport) -> None:
    s = report.summary
    print("=" * 70)
    print("OutClaw Unified Audit Summary")
    print("=" * 70)
    print(f"  Regex hits:                   {s['regex_hits']}")
    print(f"  Arch unique citations:        {s['arch_total_citations']}")
    print(f"  Arch flagged (not in stub DB): {s['arch_flagged_count']}")
    print(f"  Severity counts:              {s['severity_counts']}")
    print(f"  Recovered by sentence-window: {s['recovered_by_window_count']}")
    print(f"  Safe to draft:                {s['safe_to_draft']}")
    print()
    if report.findings:
        for f in report.findings:
            tag = "!!" if f.severity == HIGH else "??" if f.severity == MEDIUM else "ok"
            print(f"  [{tag}] {f.citation}  {f.rule}  ({f.severity})")
            print(f"      {f.detail[:120]}")


if __name__ == "__main__":
    sample = (
        "A plaintiff may recover punitive damages under \u00a7 1983 only on "
        "proof of malice. Miller v. Acme Corp., 555 F.3d 789."
    )
    rep = audit_text(sample)
    _print_summary(rep)
    if "--json" in sys.argv[1:]:
        print()
        print(json.dumps(rep.to_dict(), indent=2))
