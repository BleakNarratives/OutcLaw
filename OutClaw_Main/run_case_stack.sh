#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# run_case_stack.sh — one-case research stack (works for ANY case profile)
#
# The OutClaw scripts themselves are GENERAL-PURPOSE and unpinned. This
# wrapper is the "this use case" button: it scopes ONE run to ONE case
# profile (default case_context.json) so results center on that case
# and jurisdiction — and nothing else. Out-of-state results are filtered
# at the source. Point it at any other profile to scope it to a different
# case (e.g. ./run_case_stack.sh demo_oklahoma/case_context.json).
#
# Usage:
#   ./run_case_stack.sh                       # full stack, default profile
#   ./run_case_stack.sh <profile.json>        # different case profile
#   ./run_case_stack.sh <profile.json> scout-only   # case law only (no names needed)
#
# Outputs land in <profile-dir>/OutClaw_Research and OutClaw_Intelligence.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")"

PROFILE="${1:-case_context.json}"
MODE="${2:-full}"

if [ ! -f "$PROFILE" ]; then
  echo "[!] Case profile not found: $PROFILE" >&2
  exit 1
fi

# Everything else derives from the profile — the wrapper is case-agnostic.
CASE_DIR="$(cd "$(dirname "$PROFILE")" && pwd)"
OUT_BASE="$CASE_DIR/OutClaw_Research"
INTEL_BASE="$CASE_DIR/OutClaw_Intelligence"
REQUESTER="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['case'].get('defendant','Pro Se Litigant'))" "$PROFILE" 2>/dev/null || echo 'Pro Se Litigant')"
CASE_NO="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['case'].get('case_number','case'))" "$PROFILE" 2>/dev/null || echo 'case')"
JURIS="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['research'].get('jurisdiction','generic'))" "$PROFILE" 2>/dev/null || echo 'generic')"

echo "═══════════════════════════════════════════════════════════"
echo "  OUTCLAW — CASE-PINNED STACK"
echo "  Profile:    $PROFILE"
echo "  Jurisdiction: $JURIS"
echo "  Requester:  $REQUESTER"
echo "  Case No.:   $CASE_NO"
echo "═══════════════════════════════════════════════════════════"

# ── 1. Case law research (jurisdiction-pinned; out-of-state filtered) ──
echo
echo "▶ [1/3] Case law scout (CourtListener + Google Scholar, ${JURIS}-pinned)"
mkdir -p "$OUT_BASE"
python3 scouts/case_law_scout.py \
  --profile "$PROFILE" \
  --out "$OUT_BASE" \
  --brief || echo "  [!] case_law_scout finished with warnings"

if [ "$MODE" = "scout-only" ]; then
  echo
  echo "✓ Scout-only mode. Docket/FOIA skipped (names still PLACEHOLDER)."
  echo "  Fill in $PROFILE, then run ./run_case_stack.sh $PROFILE"
  exit 0
fi

# ── 2. Attorney / judge intelligence (jurisdiction-scoped dorks) ──
echo
if grep -q PLACEHOLDER "$PROFILE"; then
  echo "▶ [2/3] SKIPPED — fill the judge/prosecutor names in $PROFILE first (PLACEHOLDER)"
else
  echo "▶ [2/3] Legal docket scout (attorney + judge intel, ${JURIS}-scoped)"
  python3 scouts/legal_docket_scout.py \
    --profile "$PROFILE" \
    --out "$INTEL_BASE" || echo "  [!] docket scout finished with warnings"
fi

# ── 3. Open Records (FOIA) request pre-drafted for this jurisdiction ──
echo
echo "▶ [3/3] Open Records request (${JURIS})"
mkdir -p "$OUT_BASE"
python3 outclaw_cli.py foia --profile "$PROFILE" \
  --name "$REQUESTER" \
  > "$OUT_BASE/foia_${CASE_NO}.txt" || echo "  [!] FOIA generation finished with warnings"

echo
echo "═══════════════════════════════════════════════════════════"
echo "  RESULTS"
echo "    Case law:  $OUT_BASE/case_law_*.{json,txt}"
echo "    Docket:    $INTEL_BASE/legal_docket_*.json"
echo "    FOIA:      $OUT_BASE/foia_${CASE_NO}.txt"
echo "═══════════════════════════════════════════════════════════"
echo
if grep -q PLACEHOLDER "$PROFILE"; then
  echo "  NOTE: PLACEHOLDER names remain in $PROFILE — fill judge,"
  echo "  prosecutor, and defense counsel to target them by name."
else
  echo "  NOTE: All case names wired. Re-run on a networked machine for live intel."
fi
