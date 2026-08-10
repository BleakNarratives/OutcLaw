# Copy-Pasta Blocks — Yarder Prompts

Two versions of each block: **CLI** (plain text, no markdown symbols, safe for
terminal tools like Vibe/Gemini CLI/Grok Coder) and **APP** (markdown-friendly,
for chat interfaces like the Claude/Gemini/DeepSeek apps).

Fill in [BRACKETS] before sending. Everything else is copy-exact.

---

## ROUND 1 — Independent Facet Assignment

### CLI version
```
TASK: [FACET NAME]

You are one of several independent reviewers looking at the same spec from
different angles. Answer only your assigned facet. Do not try to cover the
whole spec.

SPEC CONTEXT:
[paste relevant section of outclaw_manifesto.md here]

YOUR FACET: [FACET NAME]
[one-line description of what this facet is asking]

Give a direct, concrete answer. If proposing code, give complete runnable
code, not a fragment. If you're missing information you'd need to be sure,
say exactly what's missing instead of guessing.
```

### APP version
```
**Task: [FACET NAME]**

You're one of several independent reviewers looking at the same spec from
different angles. Please answer only your assigned facet — don't try to
cover the whole spec.

**Spec context:**
[paste relevant section of outclaw_manifesto.md here]

**Your facet:** [FACET NAME]
[one-line description of what this facet is asking]

Give a direct, concrete answer. If proposing code, give complete runnable
code, not a fragment. If you're missing information you'd need to be sure,
say exactly what's missing instead of guessing.
```

---

## ROUND 2 — Cross-Haul (send the compiled landing back out)

### CLI version
```
CROSS-REVIEW

Below are independent answers from other reviewers on related facets of the
same spec. React to them: what do you disagree with, what would you change
about your own earlier answer given what they found, what's missing that
nobody covered.

COMPILED ANSWERS:
[paste the Yarder's "copy" output from Round 1 here]

Be specific. Point to which facet/model you're responding to when you
disagree.
```

### APP version
```
**Cross-review**

Below are independent answers from other reviewers on related facets of the
same spec. Please react to them: what do you disagree with, what would you
change about your own earlier answer given what they found, and what's
missing that nobody covered.

**Compiled answers:**
[paste the Yarder's "copy" output from Round 1 here]

Be specific — point to which facet/model you're responding to when you
disagree.
```

---

## ROUND 3 — Synthesis Handoff (if asking a model to help synthesize)

### CLI version
```
SYNTHESIS PASS

Below is a full haul: independent answers plus cross-reactions from several
reviewers on one spec. Your job is not to pick a favorite. Merge what
actually holds up, flag what conflicts and needs a human call, and drop
anything that got contradicted without a real defense.

FULL HAUL:
[paste the Yarder's Round 3 "full haul" output here]

Output format: one section per decision (keep / cut / needs a human call),
plain text, no ritual framing.
```

### APP version
```
**Synthesis pass**

Below is a full haul — independent answers plus cross-reactions from several
reviewers on one spec. Your job isn't to pick a favorite. Merge what
actually holds up, flag what conflicts and needs a human call, and drop
anything that got contradicted without a real defense.

**Full haul:**
[paste the Yarder's Round 3 "full haul" output here]

Format: one section per decision (**keep** / **cut** / **needs a human
call**), plain language, no ritual framing.
```

---

## Quick device/tool notes
- **CLI tools (Vibe on Moto, Gemini CLI on A9, Grok Coder on Chromebook):**
  use the CLI blocks — no markdown bold/headers, since terminal output won't
  render them and some CLIs choke on stray `#`/`**` characters in piped input.
- **App interfaces (Claude, Gemini, DeepSeek apps):** use the APP blocks —
  markdown renders and makes the reviewer's job clearer.
- Whichever block you use, the bracketed paste-ins are the only thing that
  changes call to call. Keep the surrounding instruction text identical
  across models — that's what makes the comparison fair.
