# OutClaw Pro Se Tool Box — Template Catalog

Extracted from the Legal War Machine (LWM) sessions and curated for self-represented
litigants. These are real legal templates that have been battle-tested in pro se
filings. Each template is cataloged here with its purpose and usage notes.

> **⚠️ DISCLAIMER**: These templates are provided for informational and educational
> purposes only. They are not legal advice. Laws vary by jurisdiction. Consult with
> a licensed attorney before filing. OutClaw's audit pipeline can check citations
> but cannot replace competent legal counsel.

---

## Template Inventory

### Step 01 — Six Elements to a Contract
- **File**: `Step 01_Six Elements to a Contract.docx`
- **Type**: Educational / Reference
- **Purpose**: Breaks down the six essential elements of a valid contract: offer,
  acceptance, consideration, mutual assent, capacity, and legality.
- **Use When**: Building or challenging any contractual claim. Fundamental to breach
  of contract analysis.
- **OutClaw Integration**: Use with `outclaw analyze` for contract law questions.

### Step 02 — Schedule A
- **File**: `Step 02_Schedule A.pdf`
- **Type**: Procedural Attachment
- **Purpose**: Standard Schedule A attachment form — used to itemize exhibits,
  property lists, or document inventories attached to a filing.
- **Use When**: Filing complaints, motions, or discovery responses that reference
  exhibits.
- **OutClaw Integration**: Attach after running `outclaw enhance` on your main filing.

### Step 03 — Basic Flow Chart
- **File**: `Step 03_Basic Flow Chart.pdf`
- **Type**: Procedural Reference
- **Purpose**: Visual decision tree for navigating the litigation process — complaint
  → service → response → discovery → motions → trial.
- **Use When**: Planning your litigation strategy; understanding procedural posture.
- **OutClaw Integration**: Reference before running `outclaw enhance` to understand
  where your filing fits in the litigation timeline.

### Step 04 — Code Section 6068
- **File**: `Step 04_Code Section 6068.pdf`
- **Type**: Statutory Authority
- **Purpose**: Text of the relevant code section (likely state professional conduct
  or procedural code). Verify jurisdiction before citing.
- **Use When**: Asserting statutory rights, challenging professional conduct, or
  citing procedural authority.
- **OutClaw Integration**: Run `outclaw audit` on the section text before citing.

### Step 05 — Circuit Court Listing
- **File**: `Step 05_Circuit Court Listing.jpg`
- **Type**: Reference
- **Purpose**: Listing of circuit courts — useful for determining proper venue and
  appellate path.
- **Use When**: Determining where to file or which appellate court has jurisdiction.
- **OutClaw Integration**: Reference when setting jurisdiction in `outclaw analyze`
  or `outclaw foia`.

### Step 06 — Constitutional Criminal Complaint
- **File**: `Step 06_Constitutional Criminal Complaint.pdf`
- **Type**: Pleading Template
- **Purpose**: Template for filing a criminal complaint asserting constitutional
  violations. Includes required elements: jurisdiction, factual allegations,
  constitutional provisions violated, prayer for relief.
- **Use When**: Filing a criminal complaint based on constitutional violations.
- **OutClaw Integration**: Run `outclaw full-audit` on your completed complaint
  before filing. Use `outclaw enhance` to catch citation fraud.

### Step 07 — Commercial Liens
- **File**: `Step 07_Commercial Liens.pdf`
- **Type**: Filing Template / Reference
- **Purpose**: Information and templates related to commercial liens — UCC filings,
  mechanic's liens, judgment liens.
- **Use When**: Perfecting or challenging a commercial lien.
- **OutClaw Integration**: Run `outclaw audit` on lien documents; use
  `outclaw benford` if lien amounts are in dispute.

### Step 08 — Disappearance Affidavit
- **File**: `Step 08_Disappearance Affidavit.docx`
- **Type**: Affidavit Template
- **Purpose**: Template for swearing to the disappearance of a person, document,
  or evidence. Used in missing person cases, spoliation claims, or evidence
  chain-of-custody challenges.
- **Use When**: Documenting the disappearance of evidence or a person.
- **OutClaw Integration**: Run `outclaw audit` on the affidavit before notarization.
  Aura Scout (`outclaw full-audit`) can detect concealment patterns.

### Step 09 — Oath of Office Laws
- **File**: `Step 09_Oath of Office Laws..docx`
- **Type**: Statutory Reference
- **Purpose**: Compilation of oath of office statutes and requirements. Useful for
  challenging actions taken by officials who failed to properly take or maintain
  their oath.
- **Use When**: Challenging official actions on oath-of-office grounds.
- **OutClaw Integration**: Run `outclaw analyze` with jurisdiction set to the
  relevant state. Cross-reference with Aura Scout's abuse-of-power patterns.

### Step 10 — Uniform Bonding Code
- **File**: `Step 10_Uniform Bonding Code.docx`
- **Type**: Statutory Reference / Filing Template
- **Purpose**: Information on surety bonds, bonding requirements, and the Uniform
  Bonding Code. Used in bail proceedings, contractor disputes, and fiduciary bonds.
- **Use When**: Challenging bond amounts, bonding procedures, or surety requirements.
- **OutClaw Integration**: Use `outclaw benford` if analyzing bond-related financial
  data for irregularities.

---

## How to Use These with OutClaw

### Recommended Workflow

```
1. SELECT the template(s) relevant to your situation
2. DRAFT your document using the template as a guide
3. AUDIT your draft with OutClaw:
   $ outclaw full-audit my_complaint.txt
4. FIX any HIGH or MEDIUM severity findings
5. RE-AUDIT until SAFE TO FILE
6. FILE with confidence
```

### Chain Commands for Maximum Coverage

```bash
# Full pipeline: audit + aura + benford + score + discover
outclaw full-audit complaint.txt --llm --jurisdiction oklahoma

# Generate FOIA request from audit findings
outclaw audit complaint.txt --json | outclaw foia --agency "County Sheriff" --jurisdiction oklahoma

# IRAC legal analysis on a specific question
outclaw analyze "Was probable cause established?" --jurisdiction federal --facts facts.txt
```

---

## Template Status

| # | Template | Format | Pages | Last Verified |
|---|----------|--------|-------|---------------|
| 01 | Six Elements to a Contract | DOCX | — | 2026-07-26 |
| 02 | Schedule A | PDF | — | 2026-07-26 |
| 03 | Basic Flow Chart | PDF | — | 2026-07-26 |
| 04 | Code Section 6068 | PDF | — | 2026-07-26 |
| 05 | Circuit Court Listing | JPG | — | 2026-07-26 |
| 06 | Constitutional Criminal Complaint | PDF | — | 2026-07-26 |
| 07 | Commercial Liens | PDF | — | 2026-07-26 |
| 08 | Disappearance Affidavit | DOCX | — | 2026-07-26 |
| 09 | Oath of Office Laws | DOCX | — | 2026-07-26 |
| 10 | Uniform Bonding Code | DOCX | — | 2026-07-26 |

---

*Catalog compiled by Buffy (Freebuff/DeepSeek V4 Pro), LWM Integration Session, 2026-07-26.*
