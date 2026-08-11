# Vendored into OutClaw from the vendored extraction layer 1.0.0 (MIT License)
# Source: https://github.com/daltonjsawyer-png/extraction
# Copied verbatim into the OutClaw tree (2026-08-11) so the
# extraction/ingestion layer is self-contained and portable.
# See extraction/README.md for provenance and OutClaw wrap points.

"""
Citation Extractor - Text-Based Core
=====================================
Refactored to accept TEXT INPUT instead of file paths.
This makes it universally useful for Claude Desktop - works with uploaded files,
web content, or any text Claude can access.
"""

import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Set

# ============================================================================
# COMPILED REGEX PATTERNS (same as before)
# ============================================================================

_CITATION_PATTERNS = [
    # Federal reporters
    r'\d{1,3}\s+U\.?\s?S\.?\s+\d+',
    r'\d{1,3}\s+S\.?\s?Ct\.?\s+\d+',
    r'\d{1,3}\s+F\.?\s?(?:2d|3d|4th)?\s+\d+',
    r'\d{1,3}\s+F\.?\s?Supp\.?\s?(?:2d|3d)?\s+\d+',
    r'\d{1,3}\s+F\.?\s?App\'?x\.?\s+\d+',

    # State reporters
    r'\d{1,3}\s+Mass\.?\s?App\.?\s?Ct\.?\s+\d+',
    r'\d{1,3}\s+Cal\.?\s?(?:App\.?\s?)?(?:2d|3d|4th|5th)?\s+\d+',
    r'\d{1,3}\s+N\.?Y\.?\s?(?:2d|3d)?\s+\d+',
    r'\d{1,3}\s+Tex\.?\s?(?:2d|3d)?\s+\d+',
    r'\d{1,3}\s+Ill\.?\s?(?:App\.?\s?)?(?:2d|3d)?\s+\d+',
    r'\d{1,3}\s+Pa\.?\s?(?:Super\.|Commw\.)?\s?(?:2d|3d)?\s+\d+',
    r'\d{1,3}\s+Mich\.?\s?(?:App\.?\s?)?(?:2d)?\s+\d+',
    r'\d{1,3}\s+Ohio\s+(?:App\.?\s?)?(?:2d|3d)?\s+\d+',

    # Regional reporters
    r'\d{1,3}\s+N\.?E\.?\s?(?:2d|3d)?\s+\d+',
    r'\d{1,3}\s+S\.?E\.?\s?(?:2d)?\s+\d+',
    r'\d{1,3}\s+S\.?W\.?\s?(?:2d|3d)?\s+\d+',
    r'\d{1,3}\s+P\.?\s?(?:2d|3d)?\s+\d+',
    r'\d{1,3}\s+A\.?\s?(?:2d|3d)?\s+\d+',
    r'\d{1,3}\s+N\.?W\.?\s?(?:2d)?\s+\d+',
    r'\d{1,3}\s+So\.?\s?(?:2d|3d)?\s+\d+',

    # Generic pattern (last to avoid over-matching)
    r'\d{1,3}\s+[A-Z][a-z]{2,8}\.?\s+(?:2d|3d|4th)?\s+\d+',
]

CITATION_PATTERN = re.compile('|'.join(_CITATION_PATTERNS))
ID_PATTERN = re.compile(r'\b[Ii]d\.\s*(?:at\s+\d+)?')
PINPOINT_PATTERN = re.compile(r'(?:,\s+|at\s+)(\d{1,4})(?:\s*-\s*\d{1,4})?(?=\s*[\(,]|$)')
STAR_PAGE_PATTERN = re.compile(r'\*(\d{2,4})\b')

# Statute patterns
_STATUTE_PATTERNS = [
    r'\d+\s+U\.?S\.?C\.?\s+§?\s*\d+[\w\-\(\)]*',
    r'\d+\s+C\.?F\.?R\.?\s+§?\s*\d+[\.\d]*',
    r'Fed\.?\s*R\.?\s*(?:Civ|Crim)\.?\s*P\.?\s*\d+[\w\-\(\)]*',
    r'Mass\.?\s*Gen\.?\s*Laws\.?\s*(?:ch\.?|c\.?)?\s*\d+[A-Z]?,?\s*§?\s*\d+[\w\-]*',
]

STATUTE_PATTERN = re.compile('|'.join(_STATUTE_PATTERNS), re.IGNORECASE)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def normalize_citation(citation: str) -> str:
    """Normalize citation by removing extra whitespace."""
    citation = re.sub(r'\s+', ' ', citation)
    citation = citation.strip()
    return citation

def is_valid_citation(citation: str) -> bool:
    """
    Validate if text is a proper legal citation.

    Args:
        citation: Citation text to validate

    Returns:
        True if valid citation, False otherwise
    """
    invalid_words = {'Statutes', 'Rules', 'Section', 'Page', 'Argument',
                     'Brief', 'Footnotes', 'Table', 'Index'}
    if any(word in citation for word in invalid_words):
        return False

    parts = citation.split()
    if len(parts) < 3:
        return False

    if not parts[0] or not parts[0][0].isdigit():
        return False

    return True

# ============================================================================
# TEXT-BASED EXTRACTION FUNCTIONS
# ============================================================================

def extract_citations_from_text(text: str) -> Dict[str, Dict]:
    """
    Extract legal citations from text.

    Args:
        text: Document text to analyze

    Returns:
        Dictionary mapping citation -> {pinpoint_cites: List[str]}
    """
    citations = defaultdict(lambda: {'pinpoint_cites': []})
    last_citation = None

    # Clean up text
    text = text.replace('\n', ' ')

    # Find all citations
    for match in CITATION_PATTERN.finditer(text):
        citation = match.group()
        citation_clean = normalize_citation(citation)

        if not is_valid_citation(citation_clean):
            continue

        # Track this citation
        if citation_clean not in citations:
            citations[citation_clean] = {'pinpoint_cites': []}

        # Look for pinpoint citations after this match
        end_pos = match.end()
        context = text[end_pos:end_pos+100]

        for pm in PINPOINT_PATTERN.finditer(context):
            pinpoint = pm.group(1).strip()

            try:
                page_num_int = int(pinpoint)
                # Exclude single digit numbers unless preceded by "at"
                context_before = context[max(0, pm.start()-5):pm.start()]
                if page_num_int < 10 and 'at' not in context_before:
                    continue

                if pinpoint not in citations[citation_clean]['pinpoint_cites']:
                    citations[citation_clean]['pinpoint_cites'].append(pinpoint)
            except ValueError:
                continue

        last_citation = citation_clean

    # Handle "Id." citations
    if last_citation:
        for id_match in ID_PATTERN.finditer(text):
            # Extract pinpoint from "Id. at 123"
            id_text = id_match.group()
            if 'at' in id_text:
                pinpoint_match = re.search(r'at\s+(\d+)', id_text)
                if pinpoint_match:
                    pinpoint_page = pinpoint_match.group(1)
                    if pinpoint_page not in citations[last_citation]['pinpoint_cites']:
                        citations[last_citation]['pinpoint_cites'].append(pinpoint_page)

    return dict(citations)


def extract_statutes_from_text(text: str) -> Dict[str, int]:
    """
    Extract statute and rule references from text.

    Args:
        text: Document text to analyze

    Returns:
        Dictionary mapping statute -> occurrence count
    """
    statutes = defaultdict(int)
    text = text.replace('\n', ' ')

    patterns = {
        'USC': r'\d{1,2}\s+U\.?S\.?C\.?(?:A\.?)?\s+(?:§+|[Ss]ec(?:tion)?\.?)\s*\d+[\w\-\.]*(?:\([a-z]\)(?:\(\d+\))?)?',
        'CFR': r'\d{1,2}\s+C\.?F\.?R\.?\s+(?:§+|[Ss]ec(?:tion)?\.?)?\s*[\d\.]+',
        'Fed_Rules_Civ': r'(?:Fed\.?\s*R\.?\s*Civ\.?\s*P\.?|FRCP|F\.?R\.?C\.?P\.?)\s*\d+(?:\([a-z]\d*\))*',
        'Fed_Rules_Evid': r'(?:Fed\.?\s*R\.?\s*Evid\.?|FRE|F\.?R\.?E\.?)\s*\d+(?:\([a-z]\))?',
        'Fed_Rules_Crim': r'(?:Fed\.?\s*R\.?\s*Crim\.?\s*P\.?|FRCrP|F\.?R\.?Cr\.?P\.?)\s*\d+',
        'Fed_Rules_App': r'(?:Fed\.?\s*R\.?\s*App\.?\s*P\.?|FRAP|F\.?R\.?A\.?P\.?)\s*\d+',
        # Textbook-style rule format: "Rule 103", "RULE 401", "rule 611" etc.
        'FRE_Textbook': r'\bRule\s+\d{2,4}\b',
        'California_Codes': r'Cal\.?\s+(?:Civ\.|Penal|Bus\.\s*&\s*Prof\.|Corp\.|Fam\.)\s+Code\s+(?:§+|[Ss]ec(?:tion)?\.?)\s*[\d\-\.]+',
        'Generic_State_Statute': r'[A-Z][a-z]+\.?\s+(?:Rev\.?\s*)?(?:Stat\.?|Code)\s+(?:Ann\.?\s*)?(?:§+|[Ss]ec(?:tion)?\.?)\s*[\d\-\.]+',
        'Restatement': r'Restatement\s+(?:\((?:Second|Third)\)\s+)?(?:of\s+)?(?:Contracts|Torts|Property)\s+(?:§+|[Ss]ec(?:tion)?\.?)\s*\d+',
    }

    for statute_type, pattern in patterns.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            clean_match = normalize_citation(match)
            statutes[clean_match] += 1

    return dict(statutes)


def search_keywords_in_text(text: str, keywords: List[str], case_sensitive: bool = False) -> Dict[str, int]:
    """
    Search for keywords in text and count occurrences.

    Args:
        text: Document text to search
        keywords: List of keywords to find
        case_sensitive: Whether to match case exactly

    Returns:
        Dictionary mapping keyword -> count
    """
    results = {}

    for keyword in keywords:
        search_term = keyword if case_sensitive else keyword.lower()
        search_text = text if case_sensitive else text.lower()

        count = search_text.count(search_term)
        if count > 0:
            results[keyword] = count

    return results


def format_citations_output(citations: Dict[str, Dict]) -> str:
    """Format citations for human-readable output."""
    if not citations:
        return "No citations found."

    output = []
    output.append("CITATIONS FOUND")
    output.append("=" * 70)
    output.append(f"\nTotal unique citations: {len(citations)}\n")

    for citation in sorted(citations.keys()):
        data = citations[citation]
        output.append(f"\n• {citation}")

        if data.get('pinpoint_cites'):
            pinpoint_pages = sorted(set(data['pinpoint_cites']),
                                   key=lambda x: int(x.split('-')[0]) if '-' not in x else int(x.split('-')[0]))
            pinpoint_str = ', '.join(pinpoint_pages)
            output.append(f"   Citing to pages: {pinpoint_str}")

    return '\n'.join(output)


def format_statutes_output(statutes: Dict[str, int]) -> str:
    """Format statutes for human-readable output."""
    if not statutes:
        return "No statutes or rules found."

    output = []
    output.append("STATUTES & RULES FOUND")
    output.append("=" * 70)
    output.append(f"\nTotal unique statutes/rules: {len(statutes)}\n")

    for statute, count in sorted(statutes.items()):
        output.append(f"\n• {statute}")
        output.append(f"   Occurrences: {count}")

    return '\n'.join(output)


def format_keywords_output(results: Dict[str, int]) -> str:
    """Format keyword search results."""
    if not results:
        return "No keyword matches found."

    output = []
    output.append("KEYWORD SEARCH RESULTS")
    output.append("=" * 70)
    output.append(f"\nKeywords found: {len(results)}\n")

    total_count = sum(results.values())
    output.append(f"Total occurrences: {total_count}\n")

    for keyword, count in sorted(results.items(), key=lambda x: x[1], reverse=True):
        output.append(f"\n• \"{keyword}\"")
        output.append(f"   Count: {count}")

    return '\n'.join(output)


def analyze_text_comprehensive(text: str) -> Dict:
    """
    Perform comprehensive analysis on text.

    Args:
        text: Document text to analyze

    Returns:
        Dictionary containing all analysis results
    """
    return {
        'citations': extract_citations_from_text(text),
        'statutes': extract_statutes_from_text(text),
        'total_citations': len(extract_citations_from_text(text)),
        'total_statutes': len(extract_statutes_from_text(text)),
        'text_length': len(text),
        'word_count': len(text.split())
    }


# ============================================================================
# BACKWARDS COMPATIBILITY - File-based wrapper
# ============================================================================

def extract_citations_from_file(file_path: str) -> Dict[str, Dict]:
    """
    Wrapper that accepts file path and reads text, then extracts citations.
    Provides backwards compatibility with existing code.
    """
    # Import here to avoid circular dependency.
    # NOTE: the companion file-based module (extract_citations.py) is not
    # part of the vendored extraction package; OutClaw consumes the text-based
    # API only. Guard the import so the module imports cleanly standalone.
    try:
        from .extract_citations import extract_text_from_pdf  # type: ignore
    except ImportError:
        raise ImportError(
            "extract_citations_from_file requires the un-vendored "
            "extract_citations module; use extract_citations_from_text instead."
        ) from None

    pages_text = extract_text_from_pdf(file_path)
    full_text = '\n'.join(pages_text)

    return extract_citations_from_text(full_text)
