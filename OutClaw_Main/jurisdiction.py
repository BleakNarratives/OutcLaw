"""
jurisdiction.py — first-class jurisdiction detection for OutClaw.

Jurisdiction is a FACT of the case, not a preference: the area where the
alleged offense occurred governs which statutes, courts, and authorities
apply. These helpers extract it from case text (arrest reports, issue
strings, court names, statute citations, agency names, ORI numbers) so
every scout and CLI command can enforce it automatically.

Usage:
    from jurisdiction import detect_jurisdiction, normalize_jurisdiction
    state = detect_jurisdiction(issue, court, report_text)   # -> 'kansas' | None
"""

import re

# State key -> conservative regex patterns found in real case text.
# Full state names and statute/ORI/agency markers carry the most signal;
# bare two-letter abbreviations are risky ("ne" inside "Northeast"), so
# only unambiguous ones are included and most are boundary-anchored.
JURISDICTION_ALIASES = {
    "kansas": [
        r"kansas",
        r"kan\.",
        r"\bks\b",
        r"k\.s\.a\.",
        r"\bksa\b",
        r"wellington\s+(?:pd|police|kansas|ks)?",
        r"sumner county",
        r"\bks\d{5,}\b",  # Kansas ORI numbers, e.g. KS0960100
    ],
    "oklahoma": [
        r"oklahoma",
        r"okla\.",
        r"oklahoma statutes",
        r"oscn",
    ],
    "missouri": [
        r"missouri",
        r"mo\.",
        r"r\.s\.mo\.",
    ],
    "colorado": [
        r"colorado",
        r"colo\.",
        r"c\.r\.s\.",
    ],
    "nebraska": [
        r"nebraska",
        r"neb\.",
        r"r\.r\.s\.",
    ],
    "texas": [
        r"texas",
        r"tex\.",
        r"tex\. penal",
    ],
    "california": [
        r"california",
        r"cal\.",
        r"cal\. penal",
    ],
    "illinois": [
        r"illinois",
        r"ill\.",
        r"720 ilcs",
    ],
    "new york": [
        r"new york",
        r"n\.y\.",
        r"nys",
    ],
    "florida": [
        r"florida",
        r"fla\.",
        r"f\.s\.a\.",
    ],
    "federal": [
        r"u\.s\.c\.",
        r"united states code",
        r"federal rule",
        r"f\.r\.c\.p\.",
        r"f\.r\.e\.",
    ],
}


def normalize_jurisdiction(jurisdiction):
    """Normalize a jurisdiction string to a known key, or None."""
    if not jurisdiction:
        return None
    j = str(jurisdiction).strip().lower()
    if j in ("ks", "kansas"):
        return "kansas"
    if j in ("ok", "oklahoma"):
        return "oklahoma"
    return j


def detect_jurisdiction(*texts):
    """Detect the governing state from case facts.

    The state with the most pattern hits wins; ties resolve to the first
    state in declaration order. Returns a normalized key ('kansas',
    'oklahoma', ...) or None when no jurisdiction can be determined.
    """
    haystack = " ".join(str(t or "") for t in texts).lower()
    if not haystack.strip():
        return None

    order = list(JURISDICTION_ALIASES.keys())
    hits = []
    for state, patterns in JURISDICTION_ALIASES.items():
        count = 0
        for pat in patterns:
            count += len(re.findall(pat, haystack))
        if count:
            hits.append((count, state))

    if not hits:
        return None
    hits.sort(key=lambda h: (-h[0], order.index(h[1])))
    # Ambiguous tie: don't guess. Return None so the caller prints the
    # "jurisdiction not detected" warning instead of a wrong pin.
    if len(hits) > 1 and hits[0][0] == hits[1][0]:
        return None
    return hits[0][1]


def find_workspace_profile(boundary_dir, name="case_context.json", max_up=8):
    """Locate a case workspace profile by walking up from the cwd.

    Only searches when the cwd is inside the OutClaw tree (at or below
    ``boundary_dir``, the scripts' home) and never walks above it — so a
    stray case_context.json in an unrelated parent directory can never
    silently pin a run. Returns the absolute profile path or None.

    Callers print their own "auto-loaded" notice to stderr.
    """
    from pathlib import Path

    boundary = Path(boundary_dir).resolve()
    cwd = Path.cwd().resolve()
    if cwd != boundary and boundary not in cwd.parents:
        return None
    cur = cwd
    for _ in range(max_up):
        cand = cur / name
        if cand.is_file():
            return str(cand)
        if cur == boundary:  # never search above the scripts' home
            break
        cur = cur.parent
    return None
