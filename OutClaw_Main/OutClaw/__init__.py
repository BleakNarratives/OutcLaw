"""Compatibility namespace for the canonical OutClaw_Main implementation.

The source modules remain flat under ``OutClaw_Main``. This package keeps the
historical ``OutClaw.<module>`` imports working without importing the stale
root-level ``OutClaw`` placeholder tree.
"""

import sys
from pathlib import Path

# Let Python resolve OutClaw.<module> against the canonical flat source tree
# and make its flat sibling imports available to those modules.
_CANONICAL = Path(__file__).resolve().parent.parent
_CANONICAL_STR = str(_CANONICAL)
if _CANONICAL_STR not in sys.path:
    sys.path.insert(0, _CANONICAL_STR)
__path__ = [_CANONICAL_STR]
