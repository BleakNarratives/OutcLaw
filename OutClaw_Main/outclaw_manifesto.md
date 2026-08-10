# OutClaw — Build Spec

## What OutClaw Is
OutClaw is an audit tool for identifying citation fraud and misconduct in legal proceedings. It is **not** a document-filing tool. Its job is to catch bad citations before they reach a judge — fabricated case law, misquoted statutes, pattern-matched nonsense dressed up as legal authority.

## Current State (baseline — don't just re-derive this, improve on it)
- `outclaw_validator.py` exists and is wired into the assessment path.
- Detection is regex-based: U.S.C. references, C.F.R. references, § symbols, case-law name patterns, F.3d reporter citations.
- This replaced a keyword-matching approach that false-positived on things like "zip code" (matched on stray characters, not real citations).
- Validated against a **seven-case regression suite** — any new approach must pass this suite, not just look impressive.
- There is a **hard DRAFT block** on a `generate_document` function, which produces real federal filings (42 U.S.C. § 1983 complaints, motions to dismiss, affidavits, discovery requests). The block exists because the validator's surface-pattern checks aren't reliable enough to trust unsupervised document generation. Do not propose removing this block as part of your answer — treat it as a fixed constraint, not a design flaw to solve.

## The Ask
Give OutClaw a brain. Specifically:

1. **Detection depth** — Where does regex-based citation detection fail? What would a semantic or structural layer catch that pattern matching can't (e.g. a citation that's real but doesn't support the sentence it's attached to; a real case cited for the opposite of what it holds)?
2. **Architecture** — If you were building OutClaw's validation core from scratch today, what would the pipeline look like? Stages, not just a single regex pass.
3. **Failure modes** — What's the most dangerous way this tool could be wrong? (False negative on a fabricated citation is worse than a false positive — say why you agree or disagree, and design around it.)
4. **Runnable output** — Whatever you propose, it needs to come back as actual code (Python preferred, matching the existing `outclaw_validator.py` context) that could be run against the seven-case regression suite, not just a description.

## Constraints
- No filesystem/device access — you're producing a script or module, not executing anything live.
- No ritual language, no framing devices — spec in, code out.
- If you don't have enough information to fully implement something (e.g. you don't know the exact test cases in the regression suite), say what you'd need rather than guessing and presenting it as certain.

## Why Multiple Takes
This spec is going to more than one model/system on purpose. The goal isn't to pick a winner by vibes — it's to diff the outputs against the current validator and the regression suite, and pull whatever's actually better, from wherever it comes from.
