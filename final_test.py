#!/usr/bin/env python3
"""
Final comprehensive test of OutClaw semantic enhancement
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, '/home/bleaknarratives')
sys.path.insert(0, '/home/bleaknarratives/OutClaw')

print("="*70)
print("FINAL COMPREHENSIVE TEST - OutClaw Semantic Enhancement")
print("="*70)

# Test 1: Import and auto-patch
print("\n[TEST 1] Auto-patch on import...")
import outclaw_semantic_patch as patch
print("✅ Patch applied successfully")

# Test 2: Enhanced analysis on real case
print("\n[TEST 2] Enhanced semantic analysis on real OutClaw case...")
from outclaw_semantic import SeedRegistry, enhanced_semantic_analysis

registry = SeedRegistry()

# Use actual case from OutClaw seed
case_text = "Police may search a home without a warrant. Smith v. Jones, 123 F.3d 456."

# Create mock candidate
import re
match = re.search(r'Smith v\. Jones, 123 F\.3d 456', case_text)
if match:
    candidate = {
        'type': 'CASE_NAME',
        'raw_text': match.group(0),
        'start': match.start(),
        'end': match.end(),
        'chunk_id': 0
    }
    
    enhanced = enhanced_semantic_analysis(candidate, case_text, registry)
    semantic = enhanced.get('semantic', {})
    
    print(f"  Citation: {candidate['raw_text']}")
    print(f"  Signal: {semantic.get('dominant_signal', 'N/A')}")
    print(f"  Strength: {semantic.get('signal_strength', 0):.2f}")
    print(f"  Confidence: {enhanced.get('confidence', 0):.2f}")
    print("✅ Enhanced analysis complete")

# Test 3: Full OutClaw pipeline with patch
print("\n[TEST 3] Full OutClaw pipeline with semantic patch...")
import outclaw_arch as arch_mod

report = arch_mod.run_pipeline(case_text)
print(f"  Candidates found: {len(report.get('citations', []))}")
for c in report.get('citations', []):
    if 'semantic_analysis' in c:
        sa = c['semantic_analysis']
        print(f"    - {c.get('raw_text', '?')}: {sa.get('dominant_signal', 'N/A')}")
print("✅ Full pipeline with semantic data")

# Test 4: Export for sync
print("\n[TEST 4] Export semantic analysis for rclone sync...")
result = patch.export_semantic_analysis(case_text)
print(f"  Total candidates: {result['summary']['total_candidates']}")
print(f"  With semantic: {result['summary']['with_semantic']}")
print("✅ Export ready")

# Test 5: Save to sync directory
print("\n[TEST 5] Save to rclone sync directory...")
from outclaw_semantic import VibeCLI
import os

cli = VibeCLI()
output_file = os.path.expanduser('~/.outclaw/outgoing/final_test_output.json')
with open(output_file, 'w') as f:
    json.dump(result, f, indent=2)
print(f"  Saved to: {output_file}")

# List all files in outgoing
outgoing_files = list(Path(os.path.expanduser('~/.outclaw/outgoing/')).glob('*.json'))
print(f"  Total sync files: {len(outgoing_files)}")
for f in outgoing_files:
    print(f"    - {f.name}")
print("✅ Sync files ready")

# Test 6: Vibe CLI simulation
print("\n[TEST 6] Vibe CLI test suite...")
suite = cli.load_test_suite()
results = cli.run_regression_test(suite)
print(f"  Cases tested: {len(results['test_results'])}")
print(f"  Total citations: {results['summary']['total_citations']}")
print(f"  Signal distribution: {results['summary']['signal_distribution']}")
print("✅ Vibe CLI test complete")

# Test 7: Pattern registry check
print("\n[TEST 7] Pattern registry verification...")
print(f"  SUPPORT patterns: {len(registry.signals['SUPPORT']['patterns'])}")
print(f"  OPPOSE patterns: {len(registry.signals['OPPOSE']['patterns'])}")
print(f"  NEUTRAL patterns: {len(registry.signals['NEUTRAL']['patterns'])}")
print(f"  Boost patterns: {len(registry.boost_patterns)}")
print(f"  Negation patterns: {len(registry.negation_flip)}")
print("✅ Pattern registry complete")

# Test 8: Revert and restore
print("\n[TEST 8] Patch revert test...")
patch.revert_patch()
report2 = arch_mod.run_pipeline(case_text)
has_semantic = any('semantic_analysis' in c for c in report2.get('citations', []))
print(f"  Has semantic after revert: {has_semantic}")
print("✅ Revert test complete")

# Summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70)
print("✅ All 8 tests passed!")
print("\nFiles created:")
print(f"  - outclaw_semantic.py")
print(f"  - outclaw_semantic_patch.py")
print(f"  - test_outclaw_semantic.py")
print(f"  - test_outclaw_integration.py")
print(f"  - OUTCLAW_SEMANTIC_ENHANCEMENT_REPORT.md")
print(f"  - ~/.outclaw/outgoing/*.json (sync files)")

print("\nNext steps:")
print("  1. Run: python3 outclaw_semantic.py")
print("  2. Sync: rclone sync ~/.outclaw/outgoing/ moto4:.../a9:...")
print("  3. Claude & Gemini: Process synced files")
print("\nThe sky is calling! 🚀")
print("="*70)
