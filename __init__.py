"""Compatibility namespace for the canonical :mod:`OutClaw_Main` project.

The repository root contains this historical shell for compatibility. The
implementation lives in ``OutClaw_Main``; exposing that directory as this
package's search path prevents imports from accidentally selecting an older
or empty root implementation.
"""

import sys
from pathlib import Path

_CANONICAL = Path(__file__).resolve().parent / "OutClaw_Main"
_CANONICAL_STR = str(_CANONICAL)
if _CANONICAL_STR not in sys.path:
    sys.path.insert(0, _CANONICAL_STR)
__path__ = [_CANONICAL_STR]
