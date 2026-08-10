"""
OutClaw Web Dashboard — Flask Application

One-click, plain-English web interface for OutClaw citation audits.
Reworked 2026-08-03 for the least-technical-possible user:

  * `/` is now the SIMPLE plain-English page (one big button).
  * Multi-file uploads are aggregated into ONE verdict (green/yellow/red)
    with plain-language explanations — not a pile of legal jargon.
  * The HANDOFF SecurityViolation blocker is fixed: uploaded temp files use
    sanitized names and pass the widened path validator.
  * Status no longer pokes at Ollama (cloud-only cascade now).
"""

import json
import os
import re
import tempfile
import webbrowser
from pathlib import Path
from threading import Timer
from typing import Optional

from flask import Flask, jsonify, render_template, request

from .orchestrator import DashboardOrchestrator
from .security import SecureInput, SecurityViolation


# Initialize Flask app
app = Flask(__name__,
            template_folder=str(Path(__file__).parent / 'templates'),
            static_folder=str(Path(__file__).parent / 'static'))
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Initialize orchestrator
orchestrator = DashboardOrchestrator()

# Plain-English rule -> explanation mapping. The user-facing UI speaks
# these sentences, never the internal rule codes.
PLAIN_RULES = {
    "EXISTENCE": "This citation may not exist. It needs to be checked against the real court record.",
    "NEGATIVE TREATMENT": "This case has been overruled or reversed — it may no longer stand as law.",
    "OPPOSITE HOLDING": "This case is being used to say the OPPOSITE of what it actually decided.",
    "MISQUOTE / OPPOSITE": "This law is being used to say the OPPOSITE of what it actually says.",
    "NO SUPPORT": "This citation does not appear to support the sentence it is attached to.",
    "SUPPORTED": "This citation appears to support the sentence.",
}
SEVERITY_LABEL = {"HIGH": "Serious problem", "MEDIUM": "Possible problem", "LOW": "Minor", "OK": "Looks fine"}
SEVERITY_PLAIN = {
    "HIGH": "red",
    "MEDIUM": "yellow",
    "LOW": "green",
    "OK": "green",
}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _sanitize_filename(filename: str) -> str:
    """Make an uploaded filename safe for the temp dir while keeping it
    readable. Fixes the HANDOFF SecurityViolation on multi-file uploads."""
    name = os.path.basename(str(filename))
    name = re.sub(r"[^A-Za-z0-9._ ()'§#+-]", "_", name)
    name = re.sub(r"\s+", " ", name).strip() or "document"
    if len(name) > 120:
        stem, dot, ext = name.rpartition(".")
        name = stem[:100] + dot + ext
    return name


def _save_upload(file) -> Path:
    """Save an uploaded file to an exclusive, safe temp path and return it."""
    safe = _sanitize_filename(file.filename or "document")
    upload_dir = Path(app.config['UPLOAD_FOLDER'])
    upload_dir.mkdir(parents=True, exist_ok=True)
    stem, dot, suffix = safe.rpartition(".")
    prefix = f"outclaw_{stem if dot else safe}_"
    extension = f".{suffix}" if dot else ""
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=prefix,
        suffix=extension,
        dir=upload_dir,
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        file.save(handle)
    except Exception:
        handle.close()
        temp_path.unlink(missing_ok=True)
        raise
    handle.close()
    return temp_path


# ---------------------------------------------------------------------------
# Verdict aggregation — one plain answer for many files
# ---------------------------------------------------------------------------

def _aggregate(file_results: list[dict]) -> dict:
    """
    Combine per-file audit results into a single plain-English verdict.
    Rules:
      - Any HIGH finding anywhere          -> RED  (do not file)
      - Any MEDIUM finding anywhere        -> YELLOW (fix before filing)
      - Any file that failed to be read    -> YELLOW (it was NOT checked)
      - Otherwise                          -> GREEN (looks fine)

    A file that could not be read (corrupt PDF, scanned image, wrong
    extension) must NEVER produce a green "no problems found". We cannot
    claim a document is clean when we could not look inside it.
    """
    findings_all = []
    failed_files = []
    for fr in file_results:
        if fr.get("ok"):
            findings_all.extend(fr.get("findings", []))
        else:
            failed_files.append(fr)

    high = [f for f in findings_all if f.get("severity") == "HIGH"]
    medium = [f for f in findings_all if f.get("severity") == "MEDIUM"]

    if high:
        verdict = {
            "level": "red",
            "title": "Stop — do not file this yet",
            "message": ("OutClaw found serious problems. Filing these papers "
                        "as they are could hurt your case. Each problem below "
                        "should be fixed or checked by a real attorney or "
                        "legal-aid clinic first."),
        }
    elif medium:
        verdict = {
            "level": "yellow",
            "title": "Review these before filing",
            "message": ("OutClaw found possible problems. They may be fixable, "
                        "but a judge could see them as mistakes. Have someone "
                        "qualified look at the items below before you file."),
        }
    elif failed_files:
        if len(failed_files) == len(file_results):
            verdict = {
                "level": "red",
                "title": "Your papers could not be checked",
                "message": ("OutClaw could not read your files, so it could "
                            "not check them. Please open each file and save it "
                            "again (as a PDF or plain text), then try again. "
                            "Do not file anything that has not been checked."),
            }
        else:
            verdict = {
                "level": "yellow",
                "title": "Some papers could not be read",
                "message": ("OutClaw could not read one or more of your files, so "
                            "it could not check them. Please open those files and "
                            "save them again (as a PDF or plain text), then try "
                            "again. A real attorney should review anything you "
                            "cannot get checked."),
            }
    else:
        verdict = {
            "level": "green",
            "title": "No problems found",
            "message": ("OutClaw did not find citation problems in these papers. "
                        "That is not a guarantee — a real attorney should still "
                        "review anything this important before you file it."),
        }

    plain_findings = []
    for f in findings_all:
        rule = f.get("rule", "")
        plain_findings.append({
            "citation": f.get("citation", ""),
            "sentence": (f.get("sentence") or "")[:160],
            "severity": f.get("severity", "MEDIUM"),
            "severity_label": SEVERITY_LABEL.get(f.get("severity"), "Possible problem"),
            "color": SEVERITY_PLAIN.get(f.get("severity"), "yellow"),
            "what": PLAIN_RULES.get(rule, f.get("detail", "") or rule),
            "detail": f.get("detail", ""),
            "file": f.get("_file", ""),
        })
    # Surface unreadable files as plain-language findings too, so they
    # always appear in the list, never just in the verdict.
    for fr in failed_files:
        plain_findings.append({
            "citation": "",
            "sentence": "",
            "severity": "MEDIUM",
            "severity_label": "Not checked",
            "color": "yellow",
            "what": ("OutClaw could not read this file. It may be a scanned "
                     "or damaged PDF. Open it, save it again, and re-check."),
            "detail": fr.get("error", ""),
            "file": fr.get("file", ""),
        })

    return {
        "verdict": verdict,
        "file_count": len(file_results),
        "files_checked": len([fr for fr in file_results if fr.get("ok")]),
        "files_failed": len(failed_files),
        "plain_findings": plain_findings,
        "counts": {
            "high": len(high),
            "medium": len(medium),
            "ok": sum(1 for f in findings_all if f.get("severity") == "OK"),
        },
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """The one-click, plain-English page (default landing)."""
    return render_template('index.html')


@app.route('/guide')
def guide():
    """One-page, no-jargon guide for least-technical users."""
    return render_template('guide.html')


@app.route('/boardroom')
def boardroom():
    """Power-user boardroom view kept for the advanced crowd."""
    return render_template('boardroom.html')


@app.route('/api/status')
def get_status():
    """System status — no Ollama probe; reports cascade readiness instead."""
    try:
        # Cascade readiness is computed once by the orchestrator (enabled +
        # which free providers have keys). No local-model probing anywhere.
        status = orchestrator.get_system_status()
        cascade = status.get("cascade") or {
            "enabled": False, "providers_ready": [], "providers_total": 0,
        }
        status["cascade"] = cascade
        status["llm_available"] = bool(status.get("llm_available"))
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/audit-case', methods=['POST'])
def audit_case():
    """
    Audit one or many uploaded files and return ONE aggregated verdict.
    This is the endpoint the plain-English page calls. Sanitized temp
    filenames + widened validator fix the HANDOFF SecurityViolation.
    """
    try:
        files = request.files.getlist('files')
        files = [f for f in files if f and f.filename]
        if not files:
            return jsonify({'success': False, 'error': 'No files uploaded'}), 400

        use_llm = request.form.get('use_llm', 'false').lower() == 'true'

        file_results = []
        for file in files:
            temp_path = _save_upload(file)
            try:
                result = orchestrator.audit_file(str(temp_path), use_llm=use_llm)
                if result.success:
                    data = result.data
                    for f in data.get('findings', []):
                        f['_file'] = _sanitize_filename(file.filename)
                    file_results.append({
                        'ok': True,
                        'file': _sanitize_filename(file.filename),
                        'findings': data.get('findings', []),
                        'summary': data.get('summary', {}),
                        'risk': data.get('risk', {}),
                    })
                else:
                    file_results.append({
                        'ok': False,
                        'file': _sanitize_filename(file.filename),
                        'error': result.error,
                    })
            finally:
                temp_path.unlink(missing_ok=True)

        aggregated = _aggregate(file_results)
        return jsonify({
            'success': True,
            'data': aggregated,
            'elapsed_ms': 0,
        })

    except SecurityViolation as e:
        return jsonify({'success': False, 'error': f'Security: {e}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/full-audit', methods=['POST'])
def full_audit():
    """Full pipeline audit (citation + aura + risk) for a single file."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        file = request.files['file']
        if not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        use_llm = request.form.get('use_llm', 'false').lower() == 'true'
        enable_aura = request.form.get('enable_aura', 'true').lower() == 'true'

        temp_path = _save_upload(file)
        try:
            result = orchestrator.full_audit(
                str(temp_path), use_llm=use_llm, enable_aura=enable_aura,
            )
            if not result.success:
                return jsonify({'success': False, 'error': result.error}), 500
            return jsonify({
                'success': True,
                'data': result.data,
                'elapsed_ms': result.elapsed_ms,
            })
        finally:
            temp_path.unlink(missing_ok=True)

    except SecurityViolation as e:
        return jsonify({'success': False, 'error': f'Security: {e}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/lookup', methods=['POST'])
def lookup_citation():
    """Lookup a citation (CourtListener)."""
    try:
        data = request.get_json() or {}
        citation = str(data.get('citation', '')).strip()
        if not citation:
            return jsonify({'success': False, 'error': 'No citation provided'}), 400
        validated = SecureInput.validate_citation(citation)
        result = orchestrator.lookup_citation(validated)
        if result.success:
            return jsonify({'success': True, 'data': result.data,
                            'elapsed_ms': result.elapsed_ms})
        return jsonify({'success': False, 'error': result.error}), 404
    except SecurityViolation as e:
        return jsonify({'success': False, 'error': f'Invalid citation: {e}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def open_browser(port: int = 8765):
    webbrowser.open(f'http://localhost:{port}/')


def run_web_dashboard(port: int = 8765, debug: bool = False,
                      open_browser_on_start: bool = True):
    """Run the web dashboard (browser opens automatically)."""
    # LAUNCH_ME.py handles its own browser open and sets this flag so the
    # module does not also pop a tab (double-open).
    if open_browser_on_start and os.environ.get('OUTCLAW_NO_AUTOOPEN') != '1':
        Timer(1.5, open_browser, args=[port]).start()
    print(f"""
  OutClaw is starting…
  Open your browser to:  http://localhost:{port}/
  (It should open by itself in a moment.)
  Press Ctrl+C to stop.
""")
    app.run(host='127.0.0.1', port=port, debug=debug, use_reloader=False)


if __name__ == '__main__':
    run_web_dashboard()
