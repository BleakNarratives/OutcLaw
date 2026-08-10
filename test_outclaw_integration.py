#!/usr/bin/env python3
"""
Integration test: Enhanced semantic layer with real OutClaw data
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, '/home/bleaknarratives')
sys.path.insert(0, '/home/bleaknarratives/OutClaw')

from outclaw_semantic import SeedRegistry, enhanced_semantic_analysis
import outclaw_unified as unified
import outclaw_depth_detector as depth_mod

def test_with_outclaw_seed():
    """Test enhanced semantics with the actual OutClaw seed registry"""
    print("="*70)
    print("INTEGRATION TEST: Enhanced Semantics + OutClaw Seed")
    print("="*70)
    
    # Load the real OutClaw seed
    seed = unified.load_seed()
    print(f"\nLoaded seed version: {seed.get('version', 'unknown')}")
    print(f"  Cases: {len(seed.get('cases', {}))}")
    print(f"  Statutes: {len(seed.get('statutes', {}))}")
    print(f"  Regression cases: {len(seed.get('regression', []))}")
    print(f"  Adversarial cases: {len(seed.get('adversarial', []))}")
    
    # Initialize enhanced seed registry
    enhanced_seed = SeedRegistry()
    
    # Test on actual regression suite cases
    all_cases = seed.get('regression', []) + seed.get('adversarial', [])
    
    print("\n" + "="*70)
    print("Testing Enhanced Semantic Analysis on Real Cases")
    print("="*70)
    
    for case in all_cases[:5]:  # Test first 5 cases
        text = case.get('text', '')
        expected_severity = case.get('expected_severity', 'UNKNOWN')
        case_id = case.get('id', 'unknown')
        label = case.get('label', 'no label')
        
        print(f"\n--- Case {case_id}: {label} ---")
        print(f"Expected: {expected_severity}")
        print(f"Text: {text[:100]}...")
        
        # Run the full OutClaw unified pipeline
        try:
            report = unified.audit_text(text)
            print(f"  Unified findings: {len(report.findings)}")
            for f in report.findings:
                print(f"    - {f.citation}: {f.rule} ({f.severity})")
        except Exception as e:
            print(f"  Unified pipeline error: {e}")
        
        # Now test enhanced semantics on extracted citations
        # Use the regex baseline to find citations
        regex = depth_mod.RegexBaseline()
        regex_hits = regex.find(text)
        
        print(f"  Regex found {len(regex_hits)} citation-like strings")
        for label, citation_text in regex_hits[:2]:
            # Create a mock candidate for enhanced analysis
            # Find approximate position
            start = text.find(citation_text)
            end = start + len(citation_text) if start >= 0 else 0
            
            if start >= 0:
                candidate = {
                    'type': label,
                    'raw_text': citation_text,
                    'start': start,
                    'end': end,
                    'chunk_id': 0
                }
                
                # Apply enhanced semantic analysis
                enhanced_candidate = enhanced_semantic_analysis(
                    candidate, text, enhanced_seed
                )
                
                semantic = enhanced_candidate.get('semantic', {})
                print(f"    Enhanced: '{citation_text}'")
                print(f"      Signal: {semantic.get('dominant_signal', 'N/A')}")
                print(f"      Strength: {semantic.get('signal_strength', 0):.2f}")
                print(f"      Reason: {semantic.get('reason', 'N/A')}")
    
    print("\n" + "="*70)
    print("Enhanced Semantic Layer Integration Test Complete")
    print("="*70)

def test_pattern_coverage():
    """Test which patterns from OutClaw seed trigger our enhanced signals"""
    print("\n" + "="*70)
    print("PATTERN COVERAGE ANALYSIS")
    print("="*70)
    
    seed = unified.load_seed()
    enhanced = SeedRegistry()
    
    # Check case holdings for signal keywords
    print("\nChecking case holdings for enhanced signal patterns:")
    for cite, case_data in seed.get('cases', {}).items():
        holding = case_data.get('holding', '')
        print(f"\n  {cite} ({case_data.get('name', 'unknown')}):")
        print(f"    Holding: {holding[:80]}...")
        
        # Check for support signals
        support_matches = []
        for pattern in enhanced.signals['SUPPORT']['patterns']:
            if re.search(pattern, holding, re.IGNORECASE):
                support_matches.append(pattern)
        
        oppose_matches = []
        for pattern in enhanced.signals['OPPOSE']['patterns']:
            if re.search(pattern, holding, re.IGNORECASE):
                oppose_matches.append(pattern)
        
        if support_matches:
            print(f"    Support signals: {support_matches[:3]}")
        if oppose_matches:
            print(f"    Oppose signals: {oppose_matches[:3]}")

def main():
    test_with_outclaw_seed()
    test_pattern_coverage()
    
    print("\n" + "="*70)
    print("ALL INTEGRATION TESTS COMPLETE")
    print("="*70)
    print("\nNext steps:")
    print("  1. Run: python3 OutClaw/outclaw_cli.py regression")
    print("  2. Run: python3 OutClaw/outclaw_cli.py audit <your_file.txt>")
    print("  3. Use rclone to sync ~/.outclaw/outgoing/ to moto4 and a9")
    print("\nThe sky is calling!")

if __name__ == "__main__":
    import re
    main()
