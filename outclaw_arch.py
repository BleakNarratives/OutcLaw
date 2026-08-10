#!/usr/bin/env python3
"""
OutClaw Architecture Pipeline - Complete Runnable Prototype
Facet: Architecture (independent reviewer)
Assumes Python 3.8+ with no external dependencies.
"""

import re
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple

# ---------- STAGE 0: Ingest & Normalize ----------
def normalize_text(raw: str) -> Tuple[str, List[int]]:
    """Return (clean_text, offset_map) where offset_map[i] = original index."""
    subs = {
        '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"',
        '\u2013': '-', '\u2014': '-', '\u2026': '...'
    }
    for old, new in subs.items():
        raw = raw.replace(old, new)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw, list(range(len(raw)))

# ---------- STAGE 1: Tokenize & Chunk ----------
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[Dict[str, Any]]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        chunks.append({'id': len(chunks), 'text': chunk, 'start': start, 'end': end})
        if end == len(text):
            break
        start = max(0, end - overlap)
        if start >= len(text):
            break
    return chunks

# ---------- STAGE 2: Candidate Extraction ----------
PATTERNS = {
    'USC': re.compile(r'\b(\d{1,3})\s*U\.?S\.?C\.?\s*§\s*(\d+[a-z]?)\b', re.IGNORECASE),
    'CFR': re.compile(r'\b(\d{1,3})\s*C\.?F\.?R\.?\s*§\s*(\d+\.\d+)\b', re.IGNORECASE),
    'F3D': re.compile(r'\b(\d{1,4})\s*F\.?\s*3d\s*(\d+)\b', re.IGNORECASE),
    'STATE_STATUTE': re.compile(r'\b([A-Z][a-z]+\.?\s*[A-Z][a-z]+)?\s*(?:Penal|Civil|Criminal)\s+Code\s*§\s*(\d+)\b', re.IGNORECASE),
    'CASE_NAME': re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+v\.\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', re.IGNORECASE)
}

def extract_candidates(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = []
    text = chunk['text']
    for label, pat in PATTERNS.items():
        for match in pat.finditer(text):
            candidates.append({
                'type': label, 'raw_text': match.group(0),
                'start': chunk['start'] + match.start(), 'end': chunk['start'] + match.end(),
                'chunk_id': chunk['id'], 'groups': match.groups()
            })
    return candidates

# ---------- STAGE 3: Contextual Disambiguation ----------
def compute_confidence(candidate: Dict[str, Any], full_text: str) -> Tuple[float, str]:
    start = max(0, candidate['start'] - 100)
    end = min(len(full_text), candidate['end'] + 100)
    context = full_text[start:end].lower()
    weight = 1.0
    reasons = []
    if re.search(r'\b(see also|but see|cf\.|contra|accord)\b', context):
        weight *= 0.6
        reasons.append('preceded by non-authoritative signal')
    if re.search(r'\b(quoted in|cited in|discussed in)\b', context):
        weight *= 0.5
        reasons.append('secondary reference')
    if context.count('\n') > 3:
        weight *= 0.7
        reasons.append('within block quote')
    if re.search(r'\b(held|ruled|pursuant to|under|as provided in)\b', context):
        weight *= 1.2
        reasons.append('direct authoritative context')
    weight = min(1.0, max(0.0, weight))
    reason = '; '.join(reasons) if reasons else 'neutral'
    return weight, reason

# ---------- STAGE 4: Cross-Reference Validation (Stub) ----------
STUB_DB = {
    'USC': {('42', '1983'): True, ('18', '1341'): True, ('26', '1'): True},
    'CFR': {('26', '1.1'): True, ('14', '121.1'): True},
    'F3D': {}, 'STATE_STATUTE': {}, 'CASE_NAME': {}
}

def validate_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    ctype = candidate['type']
    groups = candidate['groups']
    validated = False
    note = "not in stub DB"
    if ctype in ('USC', 'CFR'):
        key = tuple(groups[:2])
        if key in STUB_DB.get(ctype, {}):
            validated = True
            note = "matches stub DB"
        else:
            note = f"no match for {key}"
    elif ctype == 'F3D':
        note = "F.3d validation not implemented in stub"
    elif ctype == 'STATE_STATUTE':
        note = "state statute validation not implemented in stub"
    elif ctype == 'CASE_NAME':
        if re.search(r'\d{4}\s+WL\s+\d+', candidate['raw_text']):
            validated = True
            note = "vendor-neutral WL cite"
        else:
            note = "case name only, no reporter"
    candidate['validated'] = validated
    candidate['validation_note'] = note
    return candidate

# ---------- STAGE 5: Deduplication & Aggregation ----------
def deduplicate_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique = {}
    for c in candidates:
        key = c['type'] + ':' + re.sub(r'\s+', '', c['raw_text'].lower())
        if key not in unique or c.get('confidence', 0) > unique[key].get('confidence', 0):
            unique[key] = c
    return list(unique.values())

# ---------- STAGE 6: Output Formatter ----------
def generate_report(unique_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(unique_candidates)
    flagged = sum(1 for c in unique_candidates if not c.get('validated', False))
    by_type = {}
    for c in unique_candidates:
        t = c['type']
        by_type[t] = by_type.get(t, 0) + 1
    return {
        "summary": {
            "total_citations": total, "flagged_count": flagged,
            "flagged_percent": round(flagged/total*100, 1) if total else 0,
            "by_type": by_type
        },
        "citations": unique_candidates
    }

# ---------- PIPELINE ORCHESTRATOR ----------
def run_pipeline(raw_text: str) -> Dict[str, Any]:
    clean_text, _ = normalize_text(raw_text)
    chunks = chunk_text(clean_text)
    all_candidates = []
    for chunk in chunks:
        all_candidates.extend(extract_candidates(chunk))
    for c in all_candidates:
        conf, reason = compute_confidence(c, clean_text)
        c['confidence'] = conf
        c['confidence_reason'] = reason
    for c in all_candidates:
        validate_candidate(c)
    unique = deduplicate_candidates(all_candidates)
    report = generate_report(unique)
    return report

# ---------- EXAMPLE USAGE ----------
if __name__ == "__main__":
    sample = """
    The defendant argues that under 42 U.S.C. § 1983, there is no claim.
    However, pursuant to 26 C.F.R. § 1.1, the IRS has jurisdiction.
    See also Roe v. Wade, 410 U.S. 113 (1973) but cf. 123 F.3d 456.
    The state penal code § 187 is also cited. A fabricated cite: 99 U.S.C. § 9999.
    """
    print("=== OutClaw Architecture Pipeline Report ===")
    report = run_pipeline(sample)
    print(json.dumps(report, indent=2))
    print("\n=== Flagged Citations ===")
    for cit in report['citations']:
        if not cit.get('validated'):
            print(f"  [FLAG] {cit['type']}: {cit['raw_text']} (reason: {cit['validation_note']})")
