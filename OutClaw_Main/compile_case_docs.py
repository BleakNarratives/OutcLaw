#!/usr/bin/env python3
"""Batch case compiler for the canonical OutClaw tree.

The canonical tree currently has no ``outclaw_builder.py``.  Its
``outclaw_validator.py`` is a legacy evidence-consistency validator exposing
``extract_metadata`` and ``validate_document`` rather than a text-audit API.
This script reports that integration honestly and writes provenance-rich,
human-review packets. It never invents pleadings, invokes document generation,
or labels output as a filed legal document.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from functools import lru_cache
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path.home() / "akasha" / "court_filings"
VALID_TEXT_SUFFIXES = frozenset({".txt", ".md"})


def _builder_status() -> str:
    path = HERE / "outclaw_builder.py"
    return "present" if path.exists() else "absent (hard generation block remains)"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return value[:80] or "case"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@lru_cache(maxsize=1)
def _load_validator() -> ModuleType:
    """Load the canonical validator by path, not ambient import precedence."""
    path = HERE / "outclaw_validator.py"
    spec = importlib.util.spec_from_file_location("outclaw_canonical_validator", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load canonical validator at {path}")
    core_dir = Path.home() / "ModMind" / "core"
    for directory in (core_dir, HERE):
        if directory.exists() and str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "validate_document"):
        raise AttributeError("canonical validator lacks validate_document")
    return module


def discover_inputs(paths: Iterable[Path], input_dir: Path | None = None) -> list[Path]:
    """Collect unique UTF-8 text files in stable lexical order."""
    found: set[Path] = set()
    for raw in paths:
        path = raw.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {raw}")
        if path.suffix.lower() not in VALID_TEXT_SUFFIXES:
            raise ValueError(f"Unsupported input type (expected .txt/.md): {raw}")
        found.add(path)
    if input_dir is not None:
        root = input_dir.expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"Input directory not found: {input_dir}")
        found.update(
            path.resolve()
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in VALID_TEXT_SUFFIXES
        )
    return sorted(found, key=lambda path: str(path).lower())


def _targets(output_dir: Path, source: Path) -> tuple[Path, Path]:
    # Include a source-path digest so two directories may safely contain
    # same-named briefs without silently colliding in one filing directory.
    identity = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:10]
    stem = f"{_slug(source.stem)}-{identity}"
    return output_dir / f"{stem}.review.txt", output_dir / f"{stem}.audit.json"


def _preflight(output_dir: Path, sources: list[Path], force: bool) -> None:
    """Reject conflicts before any packet is written."""
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = [target for source in sources for target in _targets(output_dir, source)]
    if not force:
        conflicts = [str(target) for target in targets if target.exists()]
        manifest = output_dir / "compile_manifest.json"
        if manifest.exists():
            conflicts.append(str(manifest))
        if conflicts:
            raise FileExistsError(
                "Refusing to overwrite existing output(s); pass --force: "
                + ", ".join(conflicts)
            )


def _validate(source: Path, text: str) -> dict[str, Any]:
    """Use the actual validator's read-only evidence-consistency API."""
    validator = _load_validator()
    metadata = _json_safe(validator.extract_metadata(text))
    evidence_match = bool(validator.validate_document(source))
    return {
        "validator": "outclaw_validator.validate_document",
        "metadata": metadata,
        "evidence_match": evidence_match,
        # The legacy check is not the safety gate for generating pleadings.
        "safe_to_generate": False,
        "note": "Evidence match is not authorization to file or generate a pleading.",
    }


def _packet(source: Path, text: str, audit: dict[str, Any], status: str, now: str) -> str:
    return "\n".join(
        [
            "OUTCLAW CASE REVIEW PACKET",
            "===========================",
            f"STATUS: {status}",
            "DOCUMENT CLASS: HUMAN-REVIEW EVIDENCE (NOT A FILED PLEADING)",
            f"SOURCE: {source}",
            f"SOURCE SHA256: {_sha256(text)}",
            f"GENERATED UTC: {now}",
            "",
            "INTEGRATION STATUS",
            f"  outclaw_builder.py: {_builder_status()}",
            "  outclaw_validator.py: present; legacy evidence-consistency API",
            "  Generation: intentionally disabled by the OutClaw DRAFT block",
            "",
            "VALIDATION RESULT",
            json.dumps(_json_safe(audit), indent=2, sort_keys=True),
            "",
            "SOURCE TEXT",
            "-----------",
            text.rstrip(),
            "",
            "END REVIEW PACKET",
            "",
        ]
    )


def _temporary_path(target: Path) -> tuple[int, Path]:
    """Create a unique same-directory temporary file for concurrent runs."""
    fd, name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    return fd, Path(name)


def _write_temporary(path: Path, content: str) -> None:
    fd, temporary = _temporary_path(path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_atomic(path: Path, content: str) -> None:
    _write_temporary(path, content)


def _write_pair_atomic(
    first: Path, first_content: str, second: Path, second_content: str
) -> None:
    """Commit packet and sidecar together, restoring old files on failure."""
    first_fd = second_fd = -1
    first_tmp = second_tmp = None
    old_first = first.read_bytes() if first.exists() else None
    old_second = second.read_bytes() if second.exists() else None
    try:
        first_fd, first_tmp = _temporary_path(first)
        second_fd, second_tmp = _temporary_path(second)
        first_stream = os.fdopen(first_fd, "w", encoding="utf-8")
        first_fd = -1
        with first_stream:
            first_stream.write(first_content)
        second_stream = os.fdopen(second_fd, "w", encoding="utf-8")
        second_fd = -1
        with second_stream:
            second_stream.write(second_content)
        first_tmp.replace(first)
        second_tmp.replace(second)
    except Exception:
        for path, old in ((first, old_first), (second, old_second)):
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise
    finally:
        for fd in (first_fd, second_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if first_tmp is not None:
            first_tmp.unlink(missing_ok=True)
        if second_tmp is not None:
            second_tmp.unlink(missing_ok=True)


def compile_cases(
    inputs: Iterable[Path],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    input_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Process all inputs and write review packets plus one manifest."""
    sources = discover_inputs(inputs, input_dir)
    if not sources:
        raise ValueError("No .txt/.md input files were supplied.")
    output_dir = output_dir.expanduser().resolve()
    _preflight(output_dir, sources, force)
    results: list[dict[str, Any]] = []
    for source in sources:
        text = source.read_text(encoding="utf-8")
        packet_path, audit_path = _targets(output_dir, source)
        try:
            audit = _validate(source, text)
            matched = bool(audit["evidence_match"])
            status = "EVIDENCE MATCH — HUMAN REVIEW REQUIRED" if matched else "BLOCKED — EVIDENCE REVIEW REQUIRED"
            now = datetime.now(timezone.utc).isoformat()
            manifest_entry = {
                "source": str(source),
                "status": status,
                "evidence_match": matched,
                "packet": str(packet_path),
                "audit": str(audit_path),
            }
            _write_pair_atomic(
                packet_path,
                _packet(source, text, audit, status, now),
                audit_path,
                json.dumps(
                    {
                        **manifest_entry,
                        "source_sha256": _sha256(text),
                        "generated_utc": now,
                        "builder_status": _builder_status(),
                        "audit": audit,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            results.append(manifest_entry)
        except Exception as exc:  # preserve per-file diagnostics and continue batch
            results.append({"source": str(source), "status": "ERROR", "error": str(exc)})

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "builder_status": _builder_status(),
        "validator_status": "present; legacy evidence-consistency API",
        "generation_status": "disabled by hard DRAFT block",
        "results": results,
        "counts": {
            "total": len(results),
            "evidence_matches": sum(r.get("status") == "EVIDENCE MATCH — HUMAN REVIEW REQUIRED" for r in results),
            "blocked": sum(r.get("status", "").startswith("BLOCKED") for r in results),
            "errors": sum(r.get("status") == "ERROR" for r in results),
        },
    }
    manifest_path = output_dir / "compile_manifest.json"
    _write_atomic(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest["manifest"] = str(manifest_path)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit case text into fail-closed OutClaw review packets.")
    parser.add_argument("--input", action="append", type=Path, default=[], help="Input .txt/.md file; repeatable")
    parser.add_argument("--input-dir", type=Path, help="Recursively collect .txt/.md files")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Default: ~/akasha/court_filings")
    parser.add_argument("--force", action="store_true", help="Replace outputs with matching names")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = compile_cases(args.input, args.output_dir, args.input_dir, args.force)
    except (FileNotFoundError, NotADirectoryError, ValueError, FileExistsError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if not any(
        manifest["counts"][key] for key in ("blocked", "errors")
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
