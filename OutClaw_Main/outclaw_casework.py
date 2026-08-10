#!/usr/bin/env python3
"""
outclaw_casework.py — hands-on case-work tools for self-rep litigants.

The gap between "research output" and "what do I DO with this" is where
pro se litigants lose. This module closes it with deterministic, stdlib-only
tools that never fabricate and always tag verified vs unverified:

  fetch_statute()       current Kansas statute text (kslegislature.org)
  build_evidence_chart() statement-by-statement evidentiary chart
  search_transcript()   find good cause / confront / cross-examine etc.
  scan_case_dir()       ingest documents -> case_record.json (facts, OCR)
  extract_facts()       dates / case numbers / statute cites / jurisdiction
  briefify()            plain-English briefing with verified tags

All outputs are research assistance, not legal advice. Verify against the
record and current law before filing.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Kansas statute retrieval (kslegislature.org)
# ---------------------------------------------------------------------------

# Kansas Legislature "li" session — bump when the legislature rolls over.
# Old sessions stay live at li/bYYYY_YY/, so this only affects freshness.
KSA_SESSION = "2025_26"

KSA_URL_CANDIDATES = [
    # Current-session statute page (the "_k" leaf resolves today)
    "https://www.kslegislature.org/li/b{session}/statute/"
    "{chapter:03d}_000_0000_chapter/{chapter:03d}_{article:03d}_0000_article/"
    "{chapter:03d}_{article:03d}_{section:04d}_section/"
    "{chapter:03d}_{article:03d}_{section:04d}_k/",
    # Fallback: no leaf suffix
    "https://www.kslegislature.org/li/b{session}/statute/"
    "{chapter:03d}_000_0000_chapter/{chapter:03d}_{article:03d}_0000_article/"
    "{chapter:03d}_{article:03d}_{section:04d}_section/",
]

KSA_CITE_RE = re.compile(
    r"(?:K\.?S\.?A\.?\s*)?(\d{1,3})-(\d{1,4})", re.IGNORECASE
)


def parse_ksa_cite(cite: str) -> dict | None:
    """Parse 'K.S.A. 21-5413(b)(1)(A)(2)' -> {chapter, article, section}.

    Handles 3-digit sections (45-215), commas (8-2,144), and trailing
    parentheticals/letters."""
    m = KSA_CITE_RE.search((cite or "").replace(",", ""))
    if not m:
        return None
    chapter, tail = int(m.group(1)), m.group(2).zfill(4)
    return {
        "cite": f"{chapter}-{int(tail)}",
        "chapter": chapter,
        "article": int(tail[:2]),
        "section": int(tail[2:]),
    }


def _strip_html(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def _slice_statute_text(plain: str, parsed: dict) -> str:
    """Extract the statute body from a stripped legislature page."""
    # The page may render the number naturally (45-215) or padded (45-0215).
    natural = rf"{parsed['chapter']}-{parsed['article']}{parsed['section']}\."
    padded = rf"{parsed['chapter']:02d}-{parsed['article']:02d}{parsed['section']:02d}\."
    heading = re.compile(natural)
    m = heading.search(plain)
    if not m:
        m = re.compile(padded).search(plain)
    if not m:
        # fall back to the bare K.S.A. number
        m = re.search(natural.rstrip(r"\\."), plain) or re.search(
            rf"{parsed['chapter']:02d}-{parsed['article']:02d}{parsed['section']:02d}\b", plain
        )
    if not m:
        return plain[:3000]
    start = m.start()
    # Kansas sections end with a "History:" line; stop there.
    end_m = re.search(r"History:", plain[start:])
    end = start + end_m.start() if end_m else min(start + 8000, len(plain))
    return plain[start:end].strip()


def fetch_statute(cite: str, session: str = KSA_SESSION, timeout: int = 20) -> dict:
    """Fetch current Kansas statute text from kslegislature.org.

    Returns {cite, url, text, retrieved}. Raises ValueError with a clear
    message when the cite is unparseable or the page is unreachable.
    """
    parsed = parse_ksa_cite(cite)
    if not parsed:
        raise ValueError(
            f"Could not parse statute cite: {cite!r} — expected e.g. 'K.S.A. 21-5413'"
        )
    headers = {"User-Agent": "OutClaw-Casework/1.0 research@outclaw.legal"}
    last_err = None
    for template in KSA_URL_CANDIDATES:
        url = template.format(session=session, **parsed)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                html = r.read().decode("utf-8", errors="ignore")
            text = _slice_statute_text(_strip_html(html), parsed)
            return {
                "cite": parsed["cite"],
                "url": url,
                "text": text,
                "retrieved": date.today().isoformat(),
            }
        except Exception as e:  # noqa: BLE001 - report and try next candidate
            last_err = e
    raise ValueError(f"Could not fetch K.S.A. {parsed['cite']} from kslegislature.org: {last_err}")


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

# Speaker-turn detection: "THE COURT:", "MR. SMITH:", "OFFICER TRENT:",
# "Q:" / "A:", and optional leading line numbers. Labels that merely look
# like speakers ("TYPE OF ARREST:", "MIRANDA:", "RELEASED TO:") are
# rejected so form text does not masquerade as testimony.
_TURN_RE = re.compile(
    r"^\s*(?:\[?\s*\d{1,5}\s*\]?\s*)?"
    r"(?P<speaker>[A-Z][A-Z0-9 .'\-&]{1,40}):\s*(?P<text>.+?)\s*$"
)

_ROLE_SPEAKERS = {
    "q", "a", "the court", "court", "the witness", "witness",
    "the defendant", "defendant", "the prosecutor", "prosecutor",
    "the judge", "judge", "defense", "the defense", "the state",
    "state", "counsel", "clerk", "the bailiff", "bailiff",
}
_HONORIFIC_RE = re.compile(
    r"^(mr|mrs|ms|dr|sgt|cpl|lt|capt|chief|off|officer|det)\.?\s+[a-z]", re.I
)
_PERSON_NAME_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$")


def _is_plausible_speaker(name: str) -> bool:
    """True when the candidate looks like a court role or a person, not a
    form-field label (e.g. all-caps "TYPE OF ARREST")."""
    clean = name.strip()
    low = clean.lower()
    if low in _ROLE_SPEAKERS:
        return True
    if _HONORIFIC_RE.match(clean):
        return True
    if _PERSON_NAME_RE.match(clean):
        return True
    return False


def parse_transcript(text: str) -> list[dict]:
    """Split transcript text into speaker turns: {line, speaker, text}."""
    turns = []
    for i, raw in enumerate((text or "").splitlines(), 1):
        m = _TURN_RE.match(raw)
        if m and _is_plausible_speaker(m.group("speaker")):
            turns.append({
                "line": i,
                "speaker": m.group("speaker").strip(),
                "text": m.group("text").strip(),
            })
    return turns


# ---------------------------------------------------------------------------
# Evidence chart
# ---------------------------------------------------------------------------

_HEARSAY_TERMS = [
    "he said", "she said", "told me", "told the officer", "stated that",
    "reported that", "according to", "i heard", "somebody said", "out of court",
]
_OBJECTION_MAP = [
    (r"heard|said|told|stated|reported", "HEARSAY"),
    (r"i think|i believe|in my opinion|probably|maybe|must have", "SPECULATION / LACK OF PERSONAL KNOWLEDGE"),
    (r"everyone knows|common knowledge|obviously", "RELEVANCE / IMPROPER"),
]
_ATTORNEY_ROLES = {"prosecutor", "attorney", "counsel", "defense"}


def _objection_hint(text: str) -> str:
    low = text.lower()
    for pat, label in _OBJECTION_MAP:
        if re.search(pat, low):
            return label
    return ""


def build_evidence_chart(text: str) -> list[dict]:
    """Build a statement-by-statement chart from transcript/narrative text.

    Each row: {n, speaker, quote, hearsay_flag, foundation_flag,
    objection_hint, page_line}. Nothing is asserted as fact — flags are
    prompts for the user to verify against the actual record.
    """
    turns = parse_transcript(text)
    if not turns:
        # narrative-style text: treat non-empty lines as statements, but skip
        # markdown/comment headers and other non-statement lines.
        turns = [
            {"line": i, "speaker": "", "text": ln.strip()}
            for i, ln in enumerate((text or "").splitlines(), 1)
            if ln.strip()
            and len(ln.strip()) >= 4
            and not ln.lstrip().startswith(("#", "//", ">"))
        ]
    rows = []
    for i, t in enumerate(turns, 1):
        low = t["text"].lower()
        hearsay = any(term in low for term in _HEARSAY_TERMS)
        role_hint = (
            "counsel/officer assertion — verify personal knowledge & foundation"
            if t["speaker"].lower() in _ATTORNEY_ROLES or "prosecutor" in t["speaker"].lower()
            else ""
        )
        rows.append({
            "n": i,
            "speaker": t["speaker"],
            "quote": t["text"][:220],
            "offered_for": "",  # user fills: truth / impeachment / notice / effect
            "hearsay_flag": "⚠ possible hearsay — verify declarant, purpose, and exception"
            if hearsay else "",
            "foundation_flag": role_hint,
            "objection_hint": _objection_hint(t["text"]),
            "page_line": f"line {t['line']}",
        })
    return rows


def render_chart_markdown(rows: list[dict]) -> str:
    out = ["# STATEMENT-BY-STATEMENT EVIDENCE CHART", "",
           "> Each flag is a prompt to VERIFY against the actual record, "
           "transcript, and applicable hearsay exceptions before filing.",
           "",
           "| # | Speaker | Statement (quote) | Offered for | Hearsay? | Foundation | Objection | Loc |",
           "|---|---------|-------------------|-------------|----------|-----------|-----------|-----|"]
    for r in rows:
        quote = r["quote"].replace("|", "/")[:120]
        out.append(
            f"| {r['n']} | {r['speaker'] or '—'} | {quote} | {r['offered_for'] or '—'} "
            f"| {r['hearsay_flag'] or '—'} | {r['foundation_flag'] or '—'} "
            f"| {r['objection_hint'] or '—'} | {r['page_line']} |"
        )
    return "\n".join(out)


def render_chart_csv(rows: list[dict]) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[
        "n", "speaker", "quote", "offered_for", "hearsay_flag",
        "foundation_flag", "objection_hint", "page_line",
    ])
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Transcript search
# ---------------------------------------------------------------------------

DEFAULT_SEARCH_TERMS = [
    "good cause", "unavailable", "confront", "cross-examine", "hearsay",
    "objection", "sustained", "overruled", "unsworn", "foundation",
]


def search_transcript(text: str, terms: list[str] | None = None) -> dict:
    """Find key terms in a transcript with context.

    Returns {term: [hits]} where each hit is {line, speaker, text, context}.
    """
    terms = [t.strip() for t in (terms or DEFAULT_SEARCH_TERMS) if t.strip()]
    lines = (text or "").splitlines()
    report: dict[str, list[dict]] = {t: [] for t in terms}
    for i, raw in enumerate(lines, 1):
        low = raw.lower()
        for term in terms:
            if term in low:
                ctx_lines = lines[max(0, i - 2):i + 2]
                report[term].append({
                    "line": i,
                    "speaker": "",
                    "text": raw.strip()[:250],
                    "context": " | ".join(l.strip()[:80] for l in ctx_lines),
                })
    return report


def render_search_report(report: dict) -> str:
    out = ["# TRANSCRIPT SEARCH REPORT", "",
           "> Locate the exact pages/lines and read them in full before relying "
           "on anything. A keyword hit is a lead, not a finding.",
           ""]
    total = 0
    for term, hits in report.items():
        out.append(f"## “{term}” — {len(hits)} hit(s)")
        out.append("")
        if not hits:
            out.append("_No matches in this transcript._")
            out.append("")
            continue
        for h in hits[:15]:
            out.append(f"- **line {h['line']}**: {h['text']}")
            if h["context"]:
                out.append(f"  _context:_ {h['context']}")
        if len(hits) > 15:
            out.append(f"- … and {len(hits) - 15} more")
        out.append("")
        total += len(hits)
    out.append(f"---\n\n**Total hits: {total}**")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Ingest: documents -> case record
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(
    r"\b(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/(?:20)?\d{2}\b"
)
# Classic Kansas case-number shape (24-001). Statute cites (NN-NNNN) are
# handled separately and excluded below.
_CASE_NO_RE = re.compile(r"\b\d{2}-\d{3}\b")
# Case/docket numbers that appear next to an explicit label.
_LABELED_CASE_RE = re.compile(
    r"\b(?:case|docket)\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9.\-]{2,25})",
    re.IGNORECASE,
)
_STATUTE_RE = re.compile(
    r"(?:K\.?S\.?A\.?\s*)?\d{2}-\d{4}(?:\([^)]*\))*", re.IGNORECASE
)
_BARE_STATUTE_CORE_RE = re.compile(r"\d{2}-\d{4}")
_ORI_RE = re.compile(r"\b(?:KS|OK|MO)\d{6,}\b", re.IGNORECASE)


def extract_facts(text: str) -> dict:
    """Extract basic facts from case text: dates, case numbers, statute
    cites, ORI numbers, and jurisdiction. Never guesses beyond patterns."""
    low = text or ""
    def _is_statute_core(token: str, bare_statutes: set) -> bool:
        """True when a case-number candidate is really a statute cite."""
        core = _BARE_STATUTE_CORE_RE.search(token)
        return bool(core and core.group(0) in bare_statutes)

    statute_matches = list(_STATUTE_RE.finditer(low))
    statute_cites = sorted(set(m.group(0) for m in statute_matches))
    bare_statutes = set()
    for m in statute_matches:
        core = _BARE_STATUTE_CORE_RE.search(m.group(0))
        if core:
            bare_statutes.add(core.group(0))

    case_numbers = set(m.group(0) for m in _CASE_NO_RE.finditer(low))
    for m in _LABELED_CASE_RE.finditer(low):
        cand = m.group(1).strip(" .:-_")
        if (
            cand
            and any(ch.isdigit() for ch in cand)  # real numbers only, not labels
            and not _is_statute_core(cand, bare_statutes)
        ):
            case_numbers.add(cand)
    case_numbers = sorted(
        c for c in case_numbers if not _is_statute_core(c, bare_statutes)
    )

    facts: dict = {
        "dates": sorted(set(_DATE_RE.findall(low))),
        "case_numbers": case_numbers,
        "statute_cites": statute_cites,
        "ori_numbers": sorted(set(m.group(0).upper() for m in _ORI_RE.finditer(low))),
    }
    try:
        from jurisdiction import detect_jurisdiction
        facts["jurisdiction"] = detect_jurisdiction(low)
    except ImportError:
        facts["jurisdiction"] = None
    return facts


def _read_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(str(path))
        return "\n".join(
            (p.extract_text() or "") for p in reader.pages
        )
    except Exception:  # noqa: BLE001
        return ""


def _ocr_image(path: Path) -> tuple[str, str]:
    """OCR an image; returns (text, status). Graceful when OCR is absent."""
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return "", "OCR engine unavailable (pip install pytesseract + system tesseract)"
    try:
        img = Image.open(str(path))
        return (pytesseract.image_to_string(img) or ""), "ocr"
    except Exception as e:  # noqa: BLE001
        return "", f"ocr failed: {e}"


# PDFs larger than this are catalogued + hashed but not text-extracted.
# Parsing a 150 MB scan with pypdf can hang for minutes and is rarely useful.
PDF_TEXT_MAX_BYTES = 25 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    """Stream a file in 1 MB chunks to hash it (memory-friendly for big PDFs)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_case_dir(
    directory: str | Path,
    out_path: str | Path | None = None,
    ocr: bool = True,
) -> dict:
    """Ingest a case folder into a case_record.json.

    - Catalog every file (name, size, sha256).
    - Extract text from .txt/.md, PDFs (pypdf), images (tesseract when
      available).
    - Pull facts (dates, case numbers, statute cites, ORI, jurisdiction).
    - NEVER modifies or moves originals.

    Returns the record dict (also written to --out when provided).
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    import hashlib

    sources = []
    all_text: list[str] = []
    ocr_status = "ocr-skipped" if not ocr else "ok"
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        entry = {
            "name": path.name,
            "path": str(path.relative_to(directory)),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
            "text": "",
        }
        suffix = path.suffix.lower()
        if suffix in (".txt", ".md", ".csv"):
            entry["text"] = path.read_text(encoding="utf-8", errors="ignore")
        elif suffix == ".pdf":
            if path.stat().st_size > PDF_TEXT_MAX_BYTES:
                entry["text"] = ""
                entry["ocr"] = "pdf-too-large-skipped"
            else:
                entry["text"] = _read_pdf_text(path)
                entry["ocr"] = "pdf-text" if entry["text"] else "pdf-no-text"
        elif suffix in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"):
            if ocr:
                entry["text"], entry["ocr"] = _ocr_image(path)
                if entry["ocr"] != "ocr" and ocr_status == "ok":
                    ocr_status = entry["ocr"]
            else:
                entry["text"] = ""
                entry["ocr"] = "ocr-skipped"
        if entry["text"]:
            all_text.append(entry["text"])
        sources.append(entry)

    corpus = "\n".join(all_text)
    facts = extract_facts(corpus)
    record = {
        "record_created": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(directory),
        "file_count": len(sources),
        "ocr_status": ocr_status,
        "facts": facts,
        "sources": [{k: v for k, v in s.items() if k != "text"} for s in sources],
        "notes": (
            "Auto-extracted patterns only — verify every fact against the "
            "original record before relying on it."
        ),
    }
    if out_path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=2, default=str))
        record["record_file"] = str(out)
    return record


# ---------------------------------------------------------------------------
# Briefify: plain-English briefing with verified/unverified tags
# ---------------------------------------------------------------------------

def briefify(
    dossier: dict | None = None,
    record: dict | None = None,
    issues: list[str] | None = None,
    profile: dict | None = None,
) -> str:
    """Plain-English briefing from a research dossier + case record.

    Deterministic and honest: everything is tagged VERIFIED (returned by a
    named source) or UNVERIFIED (must be confirmed before citing). Nothing
    is generated or embellished — this summarizes what the tools actually
    found.
    """
    lines: list[str] = []
    lines.append("# OUTCLAW CASE BRIEFING — plain English")
    lines.append("")

    case = (profile or {}).get("case", {}) or {}
    header_bits = []
    if case.get("defendant"):
        header_bits.append(f"Defendant: **{case['defendant']}**")
    if case.get("case_number"):
        header_bits.append(f"Case: **{case['case_number']}**")
    if case.get("court"):
        header_bits.append(f"Court: {case['court']}")
    if case.get("state"):
        header_bits.append(f"State: {case['state']}")
    if header_bits:
        lines.append(" | ".join(header_bits))
        lines.append("")

    if record and record.get("facts"):
        f = record["facts"]
        lines.append("## Facts found in the record")
        lines.append("")
        lines.append(f"- **Jurisdiction detected:** {f.get('jurisdiction') or '—'}")
        lines.append(f"- **Dates:** {', '.join(f.get('dates', [])) or '—'}")
        lines.append(f"- **Case numbers:** {', '.join(f.get('case_numbers', [])) or '—'}")
        lines.append(f"- **Statute cites:** {', '.join(f.get('statute_cites', [])) or '—'}")
        lines.append(f"- **Agency/ORI:** {', '.join(f.get('ori_numbers', [])) or '—'}")
        lines.append("")

    cases = []
    if dossier:
        cases = dossier.get("cases_found", []) or []
    if cases:
        lines.append(f"## Research findings — {len(cases)} case(s) returned")
        lines.append("")
        for c in cases[:20]:
            source = c.get("source", "Unknown")
            if source == "CourtListener":
                tag = ("VERIFIED to EXIST via CourtListener — read the opinion "
                       "itself before citing it for a proposition")
            else:
                tag = "UNVERIFIED — confirm citation before citing"
            lines.append(f"- **{c.get('case_name', 'Unknown')}** — {c.get('court', 'court?')} "
                         f"({c.get('date_filed', 'date?')})  _[{tag}]_")
            snippet = (c.get("snippet") or "").strip()
            if snippet:
                lines.append(f"  > {snippet[:220]}")
            lines.append("")
        if len(cases) > 20:
            lines.append(f"_… and {len(cases) - 20} more. Review the full dossier._")
            lines.append("")
    else:
        lines.append("## Research findings")
        lines.append("")
        lines.append("_No cases were returned by the research run — check the "
                     "dossier for source errors (network/API) before concluding "
                     "nothing exists._")
        lines.append("")

    if dossier and dossier.get("filtered_out_by_jurisdiction"):
        tot = sum(x.get("dropped_count", 0) for x in dossier["filtered_out_by_jurisdiction"])
        lines.append(f"## Jurisdiction filtering")
        lines.append("")
        lines.append(f"- **{tot} out-of-state result(s) were dropped** so this "
                     "briefing stays in-state.")
        lines.append("")

    statutes = []
    if case.get("statutes"):
        statutes = case["statutes"]
    elif record and record.get("facts", {}).get("statute_cites"):
        statutes = record["facts"]["statute_cites"]
    if statutes:
        lines.append("## Statutes involved")
        lines.append("")
        for s in statutes:
            lines.append(f"- **{s}** — run `outclaw statute \"{s}\"` to fetch the "
                         "current text from kslegislature.org. _[VERIFY current "
                         "text before filing — statutes change]_")
        lines.append("")

    if issues:
        lines.append("## What this means for YOU")
        lines.append("")
        for i, issue in enumerate(issues[:8], 1):
            lines.append(f"{i}. **{issue}**")
            if cases:
                lines.append(f"   → {len(cases)} case(s) returned above to support "
                             "or distinguish this point. Tag each one VERIFIED/"
                             "UNVERIFIED before citing.")
            lines.append("")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> **Honest limits:** this briefing only restates what the tools "
                 "found. It is NOT legal advice. Verify every citation, statute, "
                 "deadline, and fact against the record and current Kansas law — "
                 "and consider a qualified lawyer or legal-aid provider before "
                 "filing anything.")
    return "\n".join(lines)
