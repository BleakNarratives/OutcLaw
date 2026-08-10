#!/usr/bin/env python3
"""
Test script for outclaw_semantic.py - runs non-interactively
"""
import sys
sys.path.insert(0, '/home/bleaknarratives')

from outclaw_semantic import VibeCLI, SeedRegistry

def main():
    print("="*70)
    print("OUTCLAW SEMANTIC ENHANCEMENT - AUTOMATED TEST")
    print("="*70)
    
    # Initialize CLI
    cli = VibeCLI()
    
    # Run regression test
    print("\n[TEST] Running regression test suite...")
    suite = cli.load_test_suite()
    results = cli.run_regression_test(suite)
    
    # Print results
    print("\n" + "="*70)
    print("REGRESSION TEST RESULTS")
    print("="*70)
    print(f"Total citations analyzed: {results['summary']['total_citations']}")
    print(f"Signal distribution:")
    for signal, count in results['summary']['signal_distribution'].items():
        print(f"  {signal}: {count}")
    print(f"Support percentage: {results['summary']['support_percentage']}%")
    
    # Detailed analysis
    print("\n" + "="*70)
    print("DETAILED ANALYSIS")
    print("="*70)
    
    for case in results['test_results']:
        print(f"\nCase {case['case_id']}:")
        print(f"  Text: {case['analyses'][0]['analysis']['context_snippet']}...")
        for analysis in case['analyses']:
            a = analysis['analysis']
            print(f"  Citation: '{analysis['citation']}'")
            print(f"    Dominant signal: {a['dominant_signal']}")
            print(f"    Signal strength: {a['signal_strength']:.2f}")
            print(f"    Scores: {a['scores']}")
            if a['matches']['SUPPORT']:
                print(f"    Support matches: {[m['text'] for m in a['matches']['SUPPORT']]}")
            if a['matches']['OPPOSE']:
                print(f"    Oppose matches: {[m['text'] for m in a['matches']['OPPOSE']]}")
            if a['boosts']:
                print(f"    Boosts: {a['boosts']}")
    
    # Test seed registry
    print("\n" + "="*70)
    print("SEED REGISTRY SUMMARY")
    print("="*70)
    print(f"SUPPORT patterns: {len(cli.seed.signals['SUPPORT']['patterns'])}")
    print(f"OPPOSE patterns: {len(cli.seed.signals['OPPOSE']['patterns'])}")
    print(f"NEUTRAL patterns: {len(cli.seed.signals['NEUTRAL']['patterns'])}")
    print(f"Boost patterns: {len(cli.seed.boost_patterns)}")
    
    # Sync to moto4 and a9
    print("\n" + "="*70)
    print("SYNC TO DEVICES")
    print("="*70)
    cli.sync_to_moto4(results)
    cli.sync_to_a9(results)
    
    print("\n" + "="*70)
    print("Files created in ~/.outclaw/outgoing/:")
    print("="*70)
    import os
    for f in os.listdir(os.path.expanduser('~/.outclaw/outgoing/')):
        print(f"  - {f}")
    
    print("\n[TEST] Complete!")
    print("The sky is calling!")

if __name__ == "__main__":
    main()
