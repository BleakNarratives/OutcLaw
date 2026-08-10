#!/usr/bin/env python3
"""
OutClaw Failure Modes Pipeline - Runnable Prototype
Facet: Failure Modes (independent reviewer, via Gemini CLI/Moto)
"""

import re

class OutClawValidator:
    def __init__(self, authoritative_index):
        self.index = authoritative_index

    def scan(self, text):
        # High-recall pattern: captures everything that structurally
        # looks like a citation
        pattern = r'(\d+\s+U\.S\.C\.\s+§\s+\d+|\d+\s+F\.3d\s+\d+)'
        return re.findall(pattern, text)

    def validate(self, candidates):
        results = {}
        for cand in candidates:
            # Stage 2: Verification against authoritative source
            results[cand] = "VALID" if cand in self.index else "FLAGGED: FABRICATION"
        return results


# Authoritative mock index
authoritative_db = {"42 U.S.C. § 1983", "500 F.3d 100"}

# Hypothetical seven-case regression suite
# NOTE: this is Gemini's constructed suite, NOT your real one.
# Flagged as such in the original answer.
regression_suite = [
    ("Case 1 (Valid)", "See 42 U.S.C. § 1983."),
    ("Case 2 (Fab)", "See 99 U.S.C. § 9999."),
    ("Case 3 (Valid)", "Cited in 500 F.3d 100."),
    ("Case 4 (Fab)", "Cited in 999 F.3d 999."),
    ("Case 5 (Noise)", "My zip code is 12345."),
    ("Case 6 (Complex)", "Valid: 42 U.S.C. § 1983, Fab: 1 U.S.C. § 1."),
    ("Case 7 (Edge)", "No citation here."),
]

def run_suite():
    validator = OutClawValidator(authoritative_db)
    print("Running Regression Suite:\n")
    for name, text in regression_suite:
        candidates = validator.scan(text)
        report = validator.validate(candidates)
        print(f"{name}: {report}")

if __name__ == "__main__":
    run_suite()
