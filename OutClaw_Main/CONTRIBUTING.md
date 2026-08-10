# Contributing to OutClaw

Thank you for helping improve OutClaw. Keep changes small, reviewable, and
focused on reliable local-first tooling.

## Before you start

- Read [README.md](README.md), [runbook.txt](runbook.txt), and [SECURITY.md](SECURITY.md).
- Work in `OutClaw_Main/`, the canonical implementation directory.
- Open an issue first for architectural changes, new external integrations, or
  changes to safety-gate behavior.

## Development setup

```bash
cd OutClaw_Main
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Optional dashboard profiles are documented in `runbook.txt`. Core tests should
not depend on optional services.

## Required checks

Before opening a pull request, run:

```bash
python3 -m py_compile outclaw_cli.py outclaw_regression.py outclaw_safety.py
python3 -m unittest discover -s outclaw_tests -t . -v
python3 outclaw_regression.py
# Optional web-profile regression (requires requirements-web.txt):
.venv/bin/python -m unittest outclaw_tests.test_dashboard_web_app -v
```

The regression runner must report `11/11 cases matched expected severity`.
Add or update tests for behavior changes. Keep tests deterministic and offline.

## Pull requests

A pull request should explain:

- what changed and why;
- which commands were run and their results;
- whether the CLI, safety gate, dashboard, or data boundary changed;
- any compatibility or migration concern.

Do not combine unrelated cleanup with changes to audit or safety semantics.
Update `README.md`, `runbook.txt`, or module documentation when commands or
operator behavior change.

## Privacy and security

Never commit raw case evidence, images, personally identifying information,
credentials, `.env` files, tokens, generated local databases, or private logs.
Do not use real case material in tests. Use synthetic fixtures or the controlled
redacted workflow after a human privacy review.

If a change touches `outclaw_safety.py`, acknowledgment-token handling, external
network calls, or evidence boundaries, call it out prominently in the pull request.
See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Style

Follow the surrounding Python style, preserve the standard-library-first offline
path, and prefer explicit error handling over silent fallback. Avoid claiming
that generated legal text is correct, admissible, timely, or filing-ready.
