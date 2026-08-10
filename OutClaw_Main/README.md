# OutClaw: Simple Legal Verification

OutClaw is a tool for auditing legal documents for citation fraud and procedural inconsistencies. It is designed to be neutral, factual, and accessible.

## Getting Started (Three-Click Install)

1.  **Install Docker**: If you don't have it, [get Docker here](https://docs.docker.com/get-docker/).
2.  **Build OutClaw**: Run this command in the project folder:
    `docker build -t outclaw .`
3.  **Run It**: Run this command:
    `docker run -p 5000:5000 outclaw`
4.  **Open in Browser**: Visit `http://localhost:5000`

---

## How to use
- **Drag and Drop**: Place your documents (PDFs, TXT) into the browser window.
- **Analyze**: Click "Full Analysis" to scan all uploaded documents for inconsistencies.
- **Review**: The dashboard will highlight potential issues based on factual record, not legal opinion.

## Purpose
This tool is for factual verification and transparency in legal documents. It is not a lawyer. Always verify findings against the official court record.

## Batch review compiler

`compile_case_docs.py` audits UTF-8 `.txt` and `.md` case materials through the canonical legacy evidence-consistency validator and writes provenance-rich review packets, JSON audit sidecars, and `compile_manifest.json`.

```bash
python3 compile_case_docs.py \
  --input /path/to/case.txt \
  --output-dir ~/akasha/court_filings/
```

Outputs are **human-review evidence, not filed pleadings**. An evidence match is not legal validation or authorization to file. Missing evidence and per-file errors produce a nonzero CLI status. The canonical tree currently has no `outclaw_builder.py`; the permanent DRAFT safety block remains active.

Run focused checks with:

```bash
python3 -m unittest discover -s outclaw_tests -p 'test_compile_case_docs.py' -v
```
