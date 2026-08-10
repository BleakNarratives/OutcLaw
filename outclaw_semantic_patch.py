#!/usr/bin/env python3
"""
outclaw_semantic_patch.py - Patch for OutClaw that enhances Stage 3

This module patches outclaw_arch.py's compute_confidence function with
enhanced semantic analysis that better detects support/opposite signals.

Usage:
    import outclaw_semantic_patch as patch
    # The patch auto-applies when imported
    
    # Then use the normal OutClaw pipeline
    import outclaw_arch as arch_mod
    report = arch_mod.run_pipeline(your_text)
    
The patch adds a 'semantic' field to each candidate with:
    - dominant_signal: SUPPORT, OPPOSE, or NEUTRAL
    - signal_strength: 0.0-1.0 confidence
    - scores: dict of normalized scores for each signal type
    - matches: list of matched patterns
    - boosts: list of context boost patterns detected
"""

import re
import sys
from typing import Dict, List, Any, Tuple
from pathlib import Path

# Add OutClaw to path
_HERE = Path(__file__).resolve().parent
_OUTCLAW = _HERE / "OutClaw"
if str(_OUTCLAW) not in sys.path:
    sys.path.insert(0, str(_OUTCLAW))

import outclaw_arch as arch_mod


# ============================================
# ENHANCED SEED REGISTRY
# ============================================
class SemanticRegistry:
    """
    Rich semantic registry for citation signals.
    Designed to replace/augment the simple compute_confidence in Stage 3.
    """
    
    def __init__(self):
        # Primary signal categories with legal-specific patterns
        self.signals = {
            'SUPPORT': {
                'patterns': [
                    # Direct authority
                    r'\bheld\b',
                    r'\bruled\b',
                    r'\bestablished\b',
                    r'\bdecided\b',
                    r'\baffirmed\b',
                    r'\buphold(?:ing)?\b',
                    # Authority language
                    r'\bpursuant to\b',
                    r'\bunder\b',
                    r'\bas provided in\b',
                    r'\bunder authority of\b',
                    r'\bas authorized by\b',
                    r'\bin accordance with\b',
                    r'\bconsistent with\b',
                    # Citation signals
                    r'\brelies on\b',
                    r'\bcites\b',
                    r'\bsee\b(?! also| generally)',
                    r'\baccord\b',
                    r'\bsupports\b',
                    r'\bconfirms\b',
                    # Direct quotes
                    r'\bquoted in\b',
                    r'\bquoting\b',
                ],
                'weight': 1.3,
                'color': 'green'
            },
            'OPPOSE': {
                'patterns': [
                    # Contradiction signals
                    r'\bsee also\b',
                    r'\bbut see\b',
                    r'\bcf\.\b',
                    r'\bcontra\b',
                    r'\bhowever\b',
                    r'\bnevertheless\b',
                    r'\bon the other hand\b',
                    # Negative treatment
                    r'\bdistinguish(?:ing)?\b',
                    r'\breject(?:ing)?\b',
                    r'\boverrule(?:d|ing)?\b',
                    r'\bdisagree(?:ing)? with\b',
                    r'\bcriticizing\b',
                    r'\bquestion(?:ing)?\b',
                    r'\bchalleng(?:ing)?\b',
                    r'\bwithdrawn\b',
                    r'\bvacated\b',
                    r'\binvalid(?:ated)?\b',
                    r'\bnot follow(?:ing)?\b',
                    r'\bcontrary to\b',
                    # Misquote signals
                    r'\bmisquot(?:ing|ed)?\b',
                    r'\btaken out of context\b',
                ],
                'weight': 0.4,
                'color': 'red'
            },
            'NEUTRAL': {
                'patterns': [
                    r'\bsee generally\b',
                    r'\bcompare\b',
                    r'\bcontrast\b',
                    r'\bmentioned in\b',
                    r'\breferenced in\b',
                    r'\bnoted in\b',
                    r'\bdiscussed in\b',
                    r'\bsee also\b',  # Can be neutral depending on context
                ],
                'weight': 0.8,
                'color': 'yellow'
            }
        }
        
        # Context-aware boost patterns (increase confidence when found)
        self.boost_patterns = {
            'direct_authority': r'\b(as|the)\s+court\s+(held|ruled|found|decided)\b',
            'statutory': r'\bstatute\s+provides\b',
            'regulatory': r'\bregulation\s+requires\b',
            'mandatory': r'\bshall\b|\bmust\b|\brequired\b|\bmandatory\b',
            'permissive': r'\bmay\b|\bmight\b|\bpermitted\b|\ballowed\b',
            'prohibited': r'\bprohibited\b|\bforbidden\b|\bcannot\b',
        }
        
        # Special negation patterns that flip meaning
        self.negation_flip = {
            'not_held': r'\bnot\s+(held|ruled|established)\b',
            'cannot': r'\bcannot\b',
            'does_not': r'\bdoes not\b',
            'never': r'\bnever\b',
            'no_': r'\bno\s+',
        }
        
        # Compile all patterns for performance
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for efficiency"""
        self.compiled = {}
        for category, data in self.signals.items():
            self.compiled[category] = [
                (re.compile(p, re.IGNORECASE), data['weight'], data['color'])
                for p in data['patterns']
            ]
        
        self.boost_compiled = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.boost_patterns.items()
        }
        
        self.negation_compiled = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.negation_flip.items()
        }
    
    def analyze_context(self, text: str, citation_span: Tuple[int, int]) -> Dict[str, Any]:
        """
        Analyze context around a citation span.
        Returns rich semantic analysis with signal detection.
        """
        # Extract expanded context window (200 chars each side)
        start = max(0, citation_span[0] - 200)
        end = min(len(text), citation_span[1] + 200)
        context = text[start:end]
        
        # Initialize scores
        scores = {'SUPPORT': 0.0, 'OPPOSE': 0.0, 'NEUTRAL': 0.0}
        matches = {'SUPPORT': [], 'OPPOSE': [], 'NEUTRAL': []}
        boosts = []
        negations = []
        
        # Check each signal category
        for category, patterns in self.compiled.items():
            for pattern, weight, color in patterns:
                for match in pattern.finditer(context):
                    scores[category] += weight
                    matches[category].append({
                        'text': match.group(0),
                        'pos': start + match.start(),  # Absolute position in full text
                        'weight': weight,
                        'color': color
                    })
        
        # Check for boost patterns
        for name, pattern in self.boost_compiled.items():
            if pattern.search(context):
                boosts.append(name)
        
        # Check for negation patterns
        for name, pattern in self.negation_compiled.items():
            if pattern.search(context):
                negations.append(name)
        
        # Apply boosts: increase confidence for support signals
        if boosts:
            scores['SUPPORT'] *= 1.2 if scores['SUPPORT'] > 0 else 1.0
            scores['NEUTRAL'] *= 1.1 if scores['NEUTRAL'] > 0 else 1.0
        
        # Apply negations: reduce support, increase oppose
        if negations:
            scores['SUPPORT'] *= 0.6
            scores['OPPOSE'] *= 1.3
        
        # Normalize scores to 0-1 range
        total = sum(scores.values()) or 1.0
        normalized = {k: v/total for k, v in scores.items()}
        
        # Determine dominant signal
        dominant = max(scores.items(), key=lambda x: x[1])
        
        # Extract citation text
        citation_text = text[citation_span[0]:citation_span[1]]
        
        return {
            'dominant_signal': dominant[0],
            'signal_strength': min(1.0, max(0.0, dominant[1])),
            'raw_scores': scores,
            'scores': normalized,
            'matches': matches,
            'boosts': boosts,
            'negations': negations,
            'context_snippet': context[:150] + '...' if len(context) > 150 else context,
            'citation': citation_text,
            'span': citation_span
        }


# ============================================
# ENHANCED COMPUTE_CONFIDENCE
# ============================================
def enhanced_compute_confidence(candidate: Dict[str, Any], full_text: str, registry: SemanticRegistry = None) -> Tuple[float, str]:
    """
    Enhanced replacement for outclaw_arch.compute_confidence.
    
    Adds semantic signal detection while maintaining backward compatibility.
    """
    if registry is None:
        # Lazy init
        if not hasattr(enhanced_compute_confidence, '_registry'):
            enhanced_compute_confidence._registry = SemanticRegistry()
        registry = enhanced_compute_confidence._registry
    
    # Perform enhanced analysis
    span = (candidate['start'], candidate['end'])
    analysis = registry.analyze_context(full_text, span)
    
    # Store analysis in candidate for later use
    candidate['semantic_analysis'] = analysis
    
    # Map semantic signal to confidence score
    signal = analysis['dominant_signal']
    strength = analysis['signal_strength']
    
    # Base confidence from original implementation
    # (We'll use the semantic strength as a multiplier)
    base_confidence = 1.0
    
    # Adjust based on signal type
    if signal == 'OPPOSE':
        # Opposing signals reduce confidence significantly
        confidence = min(0.5, strength * 0.5)
        reason_parts = [f"opposing signal detected ({signal})"]
    elif signal == 'SUPPORT':
        # Supporting signals increase confidence
        confidence = min(1.0, 0.5 + (strength * 0.5))
        reason_parts = [f"support signal detected ({signal})"]
    else:  # NEUTRAL
        # Neutral signals keep moderate confidence
        confidence = 0.7
        reason_parts = [f"neutral context"]
    
    # Add context from matches
    if analysis['boosts']:
        reason_parts.append(f"context boosts: {', '.join(analysis['boosts'])}")
    
    if analysis['negations']:
        reason_parts.append(f"negation patterns: {', '.join(analysis['negations'])}")
    
    # Build reason string
    reason = '; '.join(reason_parts)
    
    return confidence, reason


# ============================================
# MONKEY PATCH
# ============================================
def apply_patch():
    """
    Apply the enhanced semantic analysis as a monkey patch to outclaw_arch.
    
    After calling this, the standard OutClaw pipeline will use enhanced
    semantic analysis automatically.
    """
    global enhanced_compute_confidence
    
    # Store original for reference
    original = arch_mod.compute_confidence
    
    # Create registry
    registry = SemanticRegistry()
    
    # Define wrapper that maintains original signature
    def patched_compute_confidence(candidate, full_text):
        # Call enhanced version
        conf, reason = enhanced_compute_confidence(candidate, full_text, registry)
        
        # Also store semantic analysis
        if 'semantic_analysis' in candidate:
            # Already has it
            pass
        
        return conf, reason
    
    # Apply patch
    arch_mod.compute_confidence = patched_compute_confidence
    
    # Store reference to original
    arch_mod.compute_confidence_original = original
    
    print("[PATCH] Enhanced semantic analysis applied to outclaw_arch.compute_confidence")
    print(f"[PATCH] Registry initialized with:")
    print(f"        SUPPORT patterns: {len(registry.signals['SUPPORT']['patterns'])}")
    print(f"        OPPOSE patterns: {len(registry.signals['OPPOSE']['patterns'])}")
    print(f"        NEUTRAL patterns: {len(registry.signals['NEUTRAL']['patterns'])}")
    print(f"        Boost patterns: {len(registry.boost_patterns)}")

def revert_patch():
    """Revert the monkey patch"""
    if hasattr(arch_mod, 'compute_confidence_original'):
        arch_mod.compute_confidence = arch_mod.compute_confidence_original
        print("[PATCH] Reverted to original compute_confidence")


# Auto-apply patch on import
apply_patch()


# ============================================
# UTILITY: EXPORT SEMANTIC DATA
# ============================================
def export_semantic_analysis(text: str) -> Dict[str, Any]:
    """
    Run full OutClaw pipeline with enhanced semantics and export the semantic data.
    
    Returns a dict with both standard OutClaw results and enhanced semantic analysis.
    """
    # Run standard pipeline
    report = arch_mod.run_pipeline(text)
    
    # Extract candidates and add semantic analysis
    candidates = report.get('citations', [])
    enhanced_candidates = []
    
    for c in candidates:
        if 'semantic_analysis' in c:
            # Already has semantic data from patched pipeline
            enhanced_candidates.append(c)
        else:
            # Manually add it
            span = (c['start'], c['end'])
            registry = SemanticRegistry()
            analysis = registry.analyze_context(text, span)
            c['semantic_analysis'] = analysis
            enhanced_candidates.append(c)
    
    return {
        'original_report': report,
        'enhanced_candidates': enhanced_candidates,
        'summary': {
            'total_candidates': len(enhanced_candidates),
            'with_semantic': sum(1 for c in enhanced_candidates if 'semantic_analysis' in c)
        }
    }


# ============================================
# CLI TOOL
# ============================================
def main():
    """CLI for testing the semantic patch"""
    import argparse
    
    parser = argparse.ArgumentParser(description='OutClaw Semantic Enhancement Patch')
    parser.add_argument('--test', action='store_true', help='Run self-test')
    parser.add_argument('--revert', action='store_true', help='Revert the patch')
    parser.add_argument('file', nargs='?', help='Text file to analyze')
    
    args = parser.parse_args()
    
    if args.revert:
        revert_patch()
        return
    
    if args.test:
        # Run self-test
        print("Running semantic patch self-test...")
        
        test_text = """
        The court held that 42 U.S.C. § 1983 applies. 
        However, see also Smith v. Jones, 123 F.3d 456 for contrary authority.
        Pursuant to 26 C.F.R. § 1.1, the IRS has jurisdiction.
        But cf. Doe v. State, 999 F.3d 111.
        """
        
        result = export_semantic_analysis(test_text)
        
        print(f"\nAnalyzed {result['summary']['total_candidates']} candidates")
        print(f"With semantic data: {result['summary']['with_semantic']}")
        
        print("\nEnhanced candidates:")
        for c in result['enhanced_candidates']:
            sa = c.get('semantic_analysis', {})
            print(f"\n  Citation: {c.get('raw_text', '?')}")
            print(f"    Type: {c.get('type', '?')}")
            print(f"    Confidence: {c.get('confidence', 0):.2f}")
            print(f"    Signal: {sa.get('dominant_signal', 'N/A')}")
            print(f"    Strength: {sa.get('signal_strength', 0):.2f}")
            print(f"    Context: {sa.get('context_snippet', 'N/A')[:80]}...")
        
        return
    
    if args.file:
        with open(args.file, 'r') as f:
            text = f.read()
        
        result = export_semantic_analysis(text)
        
        import json
        print(json.dumps(result, indent=2))
        return
    
    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
