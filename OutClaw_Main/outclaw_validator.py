#!/usr/bin/env python3
"""outclaw_validator.py - Legal document validation for OutClaw pipeline.

Cross-references drafted documents from outclaw_builder.py against raw evidence logs.
Emits 'legal_doc_verified' event via nexus_transport on passing consistency checks.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "ModMind" / "core"))
from state_manager import get_state
from nexus_transport import emit

DOCS_DIR = Path.home() / "OutClaw" / "generated_docs"
EVIDENCE_DIR = Path.home() / "OutClaw" / "OutClaw_Main"

def extract_metadata(text: str) -> dict:
    """Extract case_number, dates, names from document text."""
    metadata = {}
    for line in text.split('\n'):
        line = line.upper()
        if "CASE" in line and ":" in line:
            metadata["case_number"] = line.split(":")[-1].strip()
        if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', line):
            metadata.setdefault("dates", []).append(line)
        if "NAME" in line and ":" in line:
            metadata["name"] = line.split(":")[-1].strip()
    return metadata

def load_evidence_logs() -> dict:
    """Load raw evidence logs as reference."""
    evidence = {}
    evidence_dir = EVIDENCE_DIR
    if evidence_dir.exists():
        for f in evidence_dir.glob("*.txt"):
            evidence[f.name] = f.read_text()
        for f in evidence_dir.glob("*.json"):
            evidence[f.name] = json.loads(f.read_text())
    return evidence

def validate_document(doc_path: Path) -> bool:
    """Validate a single document against evidence."""
    text = doc_path.read_text()
    doc_meta = extract_metadata(text)

    evidence = load_evidence_logs()

    case_num = doc_meta.get("case_number", "")
    if not case_num:
        return False

    for name, content in evidence.items():
        if isinstance(content, str) and case_num in content:
            return True
        if isinstance(content, dict) and case_num in str(content):
            return True

    return False

def validate_all_documents():
    """Validate all generated documents."""
    if not DOCS_DIR.exists():
        print(f"[VALIDATOR] No documents found at {DOCS_DIR}")
        return

    verified = []
    for doc_path in DOCS_DIR.glob("*.txt"):
        if validate_document(doc_path):
            print(f"[VALIDATOR] VERIFIED: {doc_path.name}")
            emit("legal_doc_verified", {
                "document": doc_path.name,
                "path": str(doc_path),
                "status": "verified"
            })
            verified.append(doc_path.name)
        else:
            print(f"[VALIDATOR] FAILED: {doc_path.name}")

    state = get_state()
    state["outclaw_verified_docs"] = verified
    print(f"[VALIDATOR] {len(verified)}/{len(list(DOCS_DIR.glob('*.txt')))} documents verified")

if __name__ == "__main__":
    validate_all_documents()
