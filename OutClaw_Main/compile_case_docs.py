#!/usr/bin/env python3
"""Batch case compiler for the canonical OutClaw tree.

The canonical tree currently has no ``outclaw_builder.py``.  Its
``outclaw_validator.py`` is a legacy evidence-consistency validator exposing
``extract_metadata`` and ``validate_document`` rather than a text-audit API.
This script reports that integration honestly and writes provenance-rich,
human-review packets. It never invents pleadings, invokes document generation,
or labels output as a filed legal document.

Publication is transactional at the batch level: artifacts are built in a
same-directory staging directory, published with the manifest last, and
protected by a process lock. A small recovery journal lets the next run undo
an interrupted replacement before doing more work.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from contextlib import contextmanager
from functools import lru_cache
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - OutClaw's supported hosts are POSIX
    fcntl = None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path.home() / "akasha" / "court_filings"
VALID_TEXT_SUFFIXES = frozenset({".txt", ".md"})
_LOCK_NAME = ".compile.lock"
_RECOVERY_NAME = ".compile_recovery.json"
_STAGE_PREFIX = ".compile-stage-"
_BACKUP_PREFIX = ".compile-backup-"


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
    """Reject conflicts before any staged artifact is built."""
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


def _extraction_section(text: str) -> dict[str, Any]:
    """Advisory extraction citation/statute extraction for the audit sidecar.

    Best-effort and fail-closed in the right direction: any import or
    runtime failure degrades to ``{"status": "unavailable"}`` and can never
    block or alter a batch publication. Output is extraction evidence for
    human review, not a legal validation.
    """
    try:
        try:
            from OutClaw.outclaw_extraction import extract_citation_metadata  # type: ignore
        except ModuleNotFoundError:
            from outclaw_extraction import extract_citation_metadata  # type: ignore
    except Exception:
        # Any import failure (ModuleNotFoundError, ImportError, name drift)
        # degrades to unavailable — this section must never block a batch.
        return {"status": "unavailable", "error": "extraction layer not importable"}
    try:
        return extract_citation_metadata(text)
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


def _validate(source: Path, text: str) -> dict[str, Any]:
    """Use the actual validator's read-only evidence-consistency API."""
    validator = _load_validator()
    metadata = _json_safe(validator.extract_metadata(text))
    evidence_match = bool(validator.validate_document(source))
    return {
        "validator": "outclaw_validator.validate_document",
        "metadata": metadata,
        "evidence_match": evidence_match,
        # Advisory extraction metadata (vendored extraction layer); never gates.
        "extraction": _extraction_section(text),
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
    """Write a packet/sidecar pair inside staging with paired rollback."""
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


def _safe_journal_name(value: str) -> str:
    """Accept only simple generated filenames from the local recovery journal."""
    path = Path(value)
    if not value or path.name != value or path.is_absolute():
        raise ValueError(f"Invalid recovery artifact name: {value!r}")
    return value


def _journal_path(output_dir: Path) -> Path:
    return output_dir / _RECOVERY_NAME


def _write_recovery_journal(
    output_dir: Path,
    staging_dir: Path,
    backup_dir: Path,
    target_names: list[str],
    existing_names: list[str],
) -> None:
    journal = {
        "version": 1,
        "staging_dir": staging_dir.name,
        "backup_dir": backup_dir.name,
        "targets": target_names,
        "existing": existing_names,
        "manifest_last": "compile_manifest.json",
    }
    _write_atomic(_journal_path(output_dir), json.dumps(journal, indent=2) + "\n")


def _remove_file(path: Path) -> None:
    if path.exists():
        if not path.is_file():
            raise OSError(f"Recovery target is not a file: {path}")
        path.unlink()


def _recover_interrupted_commit(output_dir: Path) -> None:
    """Restore the pre-commit batch described by a leftover recovery journal."""
    journal_path = _journal_path(output_dir)
    if not journal_path.exists():
        return
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if journal.get("version") != 1:
            raise ValueError("unsupported recovery journal version")
        target_names = [_safe_journal_name(name) for name in journal["targets"]]
        existing_names = {
            _safe_journal_name(name) for name in journal.get("existing", [])
        }
        if not existing_names.issubset(target_names):
            raise ValueError("recovery journal has an invalid existing target")
        staging_name = _safe_journal_name(journal["staging_dir"])
        backup_name = _safe_journal_name(journal["backup_dir"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot safely recover interrupted batch: {exc}") from exc

    backup_dir = output_dir / backup_name
    for name in target_names:
        target = output_dir / name
        backup = backup_dir / name
        if backup.exists():
            _remove_file(target)
            # Copy rather than move so a later recovery failure still has the
            # original backup available for the next recovery attempt.
            shutil.copy2(backup, target)
        elif name not in existing_names:
            # The target was new in this transaction; remove any partial
            # replacement so the next run starts from a clean publication.
            _remove_file(target)

    # Keep the journal and backup if any restoration above raises: they are
    # the only durable recovery evidence left for an operator or next run.
    shutil.rmtree(output_dir / staging_name, ignore_errors=True)
    shutil.rmtree(backup_dir, ignore_errors=True)
    journal_path.unlink(missing_ok=True)


@contextmanager
def _output_lock(output_dir: Path) -> Iterator[None]:
    """Serialize publication and recovery for one output directory."""
    if fcntl is None:
        raise RuntimeError("Transactional publication requires POSIX file locking")
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / _LOCK_NAME
    with lock_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            _recover_interrupted_commit(output_dir)
            # Never delete unjournaled directories: they may belong to an
            # operator or a different tool and require manual inspection.
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _publish_batch(
    output_dir: Path,
    staging_dir: Path,
    target_names: list[str],
    force: bool,
) -> None:
    """Publish staged artifacts together, with the manifest replaced last."""
    if "compile_manifest.json" not in target_names:
        raise ValueError("staged batch is missing compile_manifest.json")
    if len(target_names) != len(set(target_names)):
        raise ValueError("staged batch contains duplicate target names")
    target_names = [_safe_journal_name(name) for name in target_names]
    backup_dir = Path(tempfile.mkdtemp(prefix=_BACKUP_PREFIX, dir=output_dir))
    existing_names = [name for name in target_names if (output_dir / name).exists()]
    _write_recovery_journal(
        output_dir, staging_dir, backup_dir, target_names, existing_names
    )
    try:
        for name in target_names:
            target = output_dir / name
            if target.exists():
                if not force:
                    raise FileExistsError(f"Output appeared during compilation: {target}")
                target.replace(backup_dir / name)
        for name in target_names:
            if name == "compile_manifest.json":
                continue
            (staging_dir / name).replace(output_dir / name)
        # The manifest is the publication marker and is intentionally last.
        (staging_dir / "compile_manifest.json").replace(output_dir / "compile_manifest.json")
        _journal_path(output_dir).unlink(missing_ok=True)
    except Exception:
        _recover_interrupted_commit(output_dir)
        raise
    finally:
        # If recovery itself failed, its journal and backup must remain for
        # the next run/operator. Successful recovery removes them already.
        if not _journal_path(output_dir).exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(backup_dir, ignore_errors=True)


def _compile_cases_locked(
    sources: list[Path], output_dir: Path, force: bool
) -> dict[str, Any]:
    _preflight(output_dir, sources, force)
    staging_dir = Path(tempfile.mkdtemp(prefix=_STAGE_PREFIX, dir=output_dir))
    results: list[dict[str, Any]] = []
    target_names: list[str] = []
    try:
        for source in sources:
            text = source.read_text(encoding="utf-8")
            # Use output-relative names so staging and published destinations
            # have identical filenames.
            packet_name, audit_name = _targets(output_dir, source)
            try:
                audit = _validate(source, text)
                matched = bool(audit["evidence_match"])
                status = "EVIDENCE MATCH — HUMAN REVIEW REQUIRED" if matched else "BLOCKED — EVIDENCE REVIEW REQUIRED"
                now = datetime.now(timezone.utc).isoformat()
                manifest_entry = {
                    "source": str(source),
                    "status": status,
                    "evidence_match": matched,
                    "packet": str(output_dir / packet_name.name),
                    "audit": str(output_dir / audit_name.name),
                }
                _write_pair_atomic(
                    staging_dir / packet_name.name,
                    _packet(source, text, audit, status, now),
                    staging_dir / audit_name.name,
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
                target_names.extend([packet_name.name, audit_name.name])
                results.append(manifest_entry)
            except Exception as exc:
                # A transactional batch must not publish a partial set. Keep
                # the error in the manifest-shaped exception for the CLI, but
                # leave the previous published batch untouched.
                raise RuntimeError(
                    f"Batch aborted while processing {source}: {exc}"
                ) from exc

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
        manifest["manifest"] = str(manifest_path)
        manifest_name = manifest_path.name
        _write_atomic(staging_dir / manifest_name, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        target_names.append(manifest_name)
        _publish_batch(output_dir, staging_dir, target_names, force)
        return manifest
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def compile_cases(
    inputs: Iterable[Path],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    input_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Process all inputs and publish review packets plus one manifest."""
    sources = discover_inputs(inputs, input_dir)
    if not sources:
        raise ValueError("No .txt/.md input files were supplied.")
    output_dir = output_dir.expanduser().resolve()
    with _output_lock(output_dir):
        return _compile_cases_locked(sources, output_dir, force)


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
    except (FileNotFoundError, NotADirectoryError, ValueError, FileExistsError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if not any(
        manifest["counts"][key] for key in ("blocked", "errors")
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
