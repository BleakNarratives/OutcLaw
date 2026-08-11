# OutClaw: Simple Legal Verification

OutClaw is a tool for auditing legal documents for citation fraud and procedural inconsistencies. It is designed to be neutral, factual, and accessible.

## Getting Started (Three-Click Install)

1.  **Install Docker**: If you don't have it, [get Docker here](https://docs.docker.com/get-docker/).
2.  **Build OutClaw**: Run this command in the project folder:
    `docker build -t outclaw .`
3.  **Run It**: Run this command in the project folder:
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

Outputs are **human-review evidence, not filed pleadings**. An evidence match is not legal validation or authorization to file. Missing evidence and validation errors produce a nonzero CLI status and no partial batch is published. The compiler stages a batch in the output directory, publishes `compile_manifest.json` last, and uses a process lock plus recovery journal for interrupted replacements. Readers should treat the manifest as the publication marker. The lock uses POSIX `fcntl` semantics; this compiler is currently intended for Linux/macOS-style environments. Staging and rollback directories can temporarily contain duplicate packet text, and a failed rollback intentionally preserves them with `.compile_recovery.json` until recovery succeeds; protect the output directory and remove retained recovery material after confirming restoration. Unjournaled staging/backup directories are never deleted automatically. The canonical tree currently has no `outclaw_builder.py`; the permanent DRAFT safety block remains active.

## Round 3 extraction layer

`outclaw_record_review.py` adds a native, standard-library-only extraction
layer for broad citation/statute/date metadata, multi-document chronology,
potential contradiction leads, citation overlap, and an explicit process-local
deposition search store. Unified audit JSON exposes this as advisory
`extraction_metadata`; it never changes OutClaw's semantic fraud findings or
DRAFT gate. Source material is not persisted by this layer, and deposition
content should be cleared after review. All leads require human verification
against the official record.

Run focused checks with:

```bash
python3 -m unittest discover -s outclaw_tests -p 'test_record_review.py' -v
python3 -m unittest discover -s outclaw_tests -p 'test_compile_case_docs.py' -v
```
