#!/usr/bin/env python3
"""
outclaw_semantic.py
Semantic layer upgrade for OutClaw - adds rich support/opposite detection
Designed for vibe CLI in Crostini with rclone sync to moto4 and a9
"""

import re
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime

# ============================================
# ENHANCED SEED REGISTRY
# ============================================
class SeedRegistry:
    """
    Rich semantic registry for citation signals.
    Tracks support/opposite/neutral patterns with weights.
    """
    
    def __init__(self):
        # Primary signal categories
        self.signals = {
            'SUPPORT': {
                'patterns': [
                    r'\bheld\b',
                    r'\bruled\b',
                    r'\bestablished\b',
                    r'\bpursuant to\b',
                    r'\bunder\b',
                    r'\bas provided in\b',
                    r'\bconsistent with\b',
                    r'\bin accordance with\b',
                    r'\brelies on\b',
                    r'\bcites\b',
                    r'\bsee\b(?! also)',
                    r'\baccord\b',
                ],
                'weight': 1.3,
                'color': 'green'
            },
            'OPPOSE': {
                'patterns': [
                    r'\bsee also\b',
                    r'\bbut see\b',
                    r'\bcf\.\b',
                    r'\bcontra\b',
                    r'\bdistinguish(?:ing)?\b',
                    r'\breject(?:ing)?\b',
                    r'\boverrule(?:ing)?\b',
                    r'\bdisagree(?:ing)? with\b',
                    r'\bcriticizing\b',
                    r'\bquestion(?:ing)?\b',
                    r'\bwithdrawn\b',
                    r'\bvacated\b',
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
                ],
                'weight': 0.8,
                'color': 'yellow'
            }
        }
        
        # Context-aware boost patterns (higher confidence when found with citations)
        self.boost_patterns = {
            'direct_authority': r'\b(as|the)\s+court\s+(held|ruled|found)\b',
            'statutory': r'\bstatute\s+provides\b',
            'regulatory': r'\bregulation\s+requires\b',
            'mandatory': r'\bshall\b|\bmust\b|\brequired\b',
            'permissive': r'\bmay\b|\bmight\b|\bpermitted\b'
        }
        
        # Compile all patterns for performance
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns"""
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
    
    def analyze_context(self, text: str, citation_span: Tuple[int, int]) -> Dict[str, Any]:
        """
        Analyze context around a citation.
        Returns rich semantic analysis.
        """
        # Extract context window (200 chars each side)
        start = max(0, citation_span[0] - 200)
        end = min(len(text), citation_span[1] + 200)
        context = text[start:end]
        
        # Initialize scores
        scores = {'SUPPORT': 0.0, 'OPPOSE': 0.0, 'NEUTRAL': 0.0}
        matches = {'SUPPORT': [], 'OPPOSE': [], 'NEUTRAL': []}
        boosts = []
        
        # Check each category
        for category, patterns in self.compiled.items():
            for pattern, weight, color in patterns:
                for match in pattern.finditer(context):
                    scores[category] += weight
                    matches[category].append({
                        'text': match.group(0),
                        'pos': match.start(),
                        'weight': weight,
                        'color': color
                    })
        
        # Check for boost patterns
        for name, pattern in self.boost_compiled.items():
            if pattern.search(context):
                boosts.append(name)
                # Boost all scores except OPPOSE
                scores['SUPPORT'] *= 1.2 if scores['SUPPORT'] > 0 else 1.0
                scores['NEUTRAL'] *= 1.1 if scores['NEUTRAL'] > 0 else 1.0
        
        # Determine dominant signal
        dominant = max(scores.items(), key=lambda x: x[1])
        
        # Normalize scores to 0-1 range
        total = sum(scores.values()) or 1.0
        normalized = {k: v/total for k, v in scores.items()}
        
        return {
            'dominant_signal': dominant[0],
            'signal_strength': min(1.0, dominant[1]),
            'scores': normalized,
            'matches': matches,
            'boosts': boosts,
            'context_snippet': context[:100] + '...' if len(context) > 100 else context
        }

# ============================================
# ENHANCED PIPELINE STAGE 3 REPLACEMENT
# ============================================
def enhanced_semantic_analysis(candidate: Dict[str, Any], full_text: str, seed_registry: SeedRegistry) -> Dict[str, Any]:
    """
    Replace the old compute_confidence with this richer semantic analysis.
    """
    span = (candidate['start'], candidate['end'])
    analysis = seed_registry.analyze_context(full_text, span)
    
    # Map to old interface for compatibility
    confidence = analysis['signal_strength']
    if analysis['dominant_signal'] == 'OPPOSE':
        confidence *= 0.7  # Opposing citations get lower confidence in validation
    
    # Build rich reason string
    reasons = []
    if analysis['matches']['SUPPORT']:
        reasons.append(f"support signals: {', '.join([m['text'] for m in analysis['matches']['SUPPORT'][:3]])}")
    if analysis['matches']['OPPOSE']:
        reasons.append(f"opposition signals: {', '.join([m['text'] for m in analysis['matches']['OPPOSE'][:3]])}")
    if analysis['boosts']:
        reasons.append(f"context boosts: {', '.join(analysis['boosts'])}")
    
    candidate['semantic'] = {
        'confidence': confidence,
        'dominant_signal': analysis['dominant_signal'],
        'signal_strength': analysis['signal_strength'],
        'scores': analysis['scores'],
        'reason': '; '.join(reasons) if reasons else 'neutral context',
        'context_snippet': analysis['context_snippet']
    }
    
    # Also update old fields for backward compatibility
    candidate['confidence'] = confidence
    candidate['confidence_reason'] = candidate['semantic']['reason']
    
    return candidate

# ============================================
# VIBE CLI WRAPPER
# ============================================
class VibeCLI:
    """
    Interactive CLI for testing semantic enhancements.
    Works with rclone synced directories.
    """
    
    def __init__(self, rclone_path: str = '~/.outclaw'):
        self.rclone_path = Path(rclone_path).expanduser()
        self.seed = SeedRegistry()
        self.results = []
        
        # Create directories if they don't exist
        self.rclone_path.mkdir(parents=True, exist_ok=True)
        (self.rclone_path / 'incoming').mkdir(exist_ok=True)
        (self.rclone_path / 'outgoing').mkdir(exist_ok=True)
        (self.rclone_path / 'logs').mkdir(exist_ok=True)
    
    def test_on_text(self, text: str, citation_spans: List[Tuple[int, int]]) -> List[Dict]:
        """Test semantic analysis on specific citation spans."""
        results = []
        for span in citation_spans:
            analysis = self.seed.analyze_context(text, span)
            
            # Extract the citation text
            cit_text = text[span[0]:span[1]]
            
            results.append({
                'citation': cit_text,
                'span': span,
                'analysis': analysis,
                'timestamp': datetime.now().isoformat()
            })
        
        return results
    
    def load_test_suite(self, suite_path: str = 'regression_suite.json'):
        """Load the 11-case regression suite."""
        try:
            with open(suite_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # Create a default test suite if none exists
            return self._create_default_suite()
    
    def _create_default_suite(self) -> Dict:
        """Create a minimal test suite for demonstration."""
        return {
            'cases': [
                {
                    'id': 'case_001',
                    'text': 'The court held that 42 U.S.C. § 1983 applies, but see 26 C.F.R. § 1.1 for contrary position.',
                    'citations': [(22, 36), (68, 83)]
                },
                {
                    'id': 'case_002',
                    'text': 'Pursuant to 18 U.S.C. § 1341, the defendant is liable. Cf. Roe v. Wade, 410 U.S. 113.',
                    'citations': [(11, 26), (62, 86)]
                },
                {
                    'id': 'case_003',
                    'text': 'See generally 26 C.F.R. § 1.1 and accord 42 U.S.C. § 1983 for the general rule.',
                    'citations': [(14, 29), (37, 51)]
                }
            ]
        }
    
    def run_regression_test(self, suite: Dict) -> Dict:
        """Run the enhanced semantic analysis on the entire regression suite."""
        results = []
        
        for case in suite.get('cases', []):
            text = case.get('text', '')
            citations = case.get('citations', [])
            
            case_result = {
                'case_id': case.get('id', 'unknown'),
                'analyses': self.test_on_text(text, citations),
                'timestamp': datetime.now().isoformat()
            }
            results.append(case_result)
        
        return {
            'test_results': results,
            'summary': self._generate_summary(results),
            'timestamp': datetime.now().isoformat()
        }
    
    def _generate_summary(self, results: List) -> Dict:
        """Generate a summary of test results."""
        total_citations = 0
        signal_counts = {'SUPPORT': 0, 'OPPOSE': 0, 'NEUTRAL': 0}
        
        for case in results:
            for analysis in case['analyses']:
                total_citations += 1
                dominant = analysis['analysis']['dominant_signal']
                signal_counts[dominant] = signal_counts.get(dominant, 0) + 1
        
        return {
            'total_citations': total_citations,
            'signal_distribution': signal_counts,
            'support_percentage': round(signal_counts['SUPPORT'] / total_citations * 100, 1) if total_citations else 0
        }
    
    def sync_to_moto4(self, data: Dict):
        """Write output to rclone sync directory for moto4 (Motorola 4 5G)."""
        output_file = self.rclone_path / 'outgoing' / f'semantic_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"[VIBE] Synced to moto4: {output_file}")
    
    def sync_to_a9(self, data: Dict):
        """Write output to rclone sync directory for a9 (Samsung A9 / Claude)."""
        output_file = self.rclone_path / 'outgoing' / f'claude_feedback_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"[VIBE] Synced to a9: {output_file}")

# ============================================
# INTERACTIVE SESSION
# ============================================
def interactive_vibe_session():
    """Interactive CLI session for testing and exploring."""
    cli = VibeCLI()
    
    print("\n" + "="*60)
    print("OUTCLAW SEMANTIC ENHANCEMENT - VIBE CLI")
    print("Boots on the ground - Crostini Penguin")
    print("="*60)
    
    while True:
        print("\nOptions:")
        print("  1. Run regression test suite")
        print("  2. Analyze custom text")
        print("  3. Show current seed registry")
        print("  4. Sync results to moto4 and a9")
        print("  5. Exit")
        
        choice = input("\nYour choice [1-5]: ").strip()
        
        if choice == '1':
            print("\n[VIBE] Loading regression suite...")
            suite = cli.load_test_suite()
            results = cli.run_regression_test(suite)
            
            print(f"\nResults: {results['summary']['total_citations']} citations analyzed")
            print(f"   SUPPORT: {results['summary']['signal_distribution']['SUPPORT']}")
            print(f"   OPPOSE:  {results['summary']['signal_distribution']['OPPOSE']}")
            print(f"   NEUTRAL: {results['summary']['signal_distribution']['NEUTRAL']}")
            
            # Show detailed examples
            print("\nSample analyses:")
            for case in results['test_results'][:2]:
                print(f"\n  Case {case['case_id']}:")
                for analysis in case['analyses'][:2]:
                    print(f"    * {analysis['citation']}")
                    print(f"      -> {analysis['analysis']['dominant_signal']} (strength: {analysis['analysis']['signal_strength']:.2f})")
            
            # Store for sync
            cli.results = results
        
        elif choice == '2':
            print("\n[VIBE] Enter text to analyze (end with empty line):")
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line == '':
                    break
                lines.append(line)
            text = '\n'.join(lines)
            
            if not text:
                print("  No text entered.")
                continue
            
            print("\n  Enter citation spans (start,end) e.g., 10,25 or 'done':")
            spans = []
            while True:
                span_input = input("  span: ").strip()
                if span_input.lower() == 'done' or span_input == '':
                    break
                try:
                    s, e = map(int, span_input.split(','))
                    spans.append((s, e))
                except ValueError:
                    print("  Invalid format. Use 'start,end'")
            
            if spans:
                results = cli.test_on_text(text, spans)
                print("\n  Analysis:")
                for r in results:
                    print(f"    * '{r['citation']}'")
                    print(f"      -> {r['analysis']['dominant_signal']} (strength: {r['analysis']['signal_strength']:.2f})")
                    print(f"      -> {r['analysis']['matches']}")
                cli.results = results
        
        elif choice == '3':
            print("\n[VIBE] Current Seed Registry:")
            print("  SUPPORT patterns:", len(cli.seed.signals['SUPPORT']['patterns']))
            print("  OPPOSE patterns: ", len(cli.seed.signals['OPPOSE']['patterns']))
            print("  NEUTRAL patterns:", len(cli.seed.signals['NEUTRAL']['patterns']))
            print("  Boost patterns:  ", len(cli.seed.boost_patterns))
            
            # Show some examples
            print("\n  Example patterns:")
            for category in ['SUPPORT', 'OPPOSE', 'NEUTRAL']:
                patterns = cli.seed.signals[category]['patterns']
                print(f"    {category}: {patterns[0]}, {patterns[1]}")
        
        elif choice == '4':
            if cli.results:
                print("\n[VIBE] Syncing to moto4 (Motorola 4 5G)...")
                cli.sync_to_moto4(cli.results)
                print("[VIBE] Syncing to a9 (Samsung A9 / Claude)...")
                cli.sync_to_a9(cli.results)
                print("[VIBE] Sync complete")
            else:
                print("\n  No results to sync. Run a test first.")
        
        elif choice == '5':
            print("\n[VIBE] OutClaw semantic enhancement ready for takeoff!")
            print("   Remember to rclone sync to share with Claude and Gemini")
            print("   The sky is calling!")
            break
        
        else:
            print("  Invalid choice. Try again.")

# ============================================
# ENTRY POINT
# ============================================
if __name__ == "__main__":
    try:
        interactive_vibe_session()
    except KeyboardInterrupt:
        print("\n\n[VIBE] Interrupted. Existing state saved in ~/.outclaw/")
        sys.exit(0)
