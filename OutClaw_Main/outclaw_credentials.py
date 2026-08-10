#!/usr/bin/env python3
"""Local-only credential loading for OutClaw's optional cloud cascade.

This is intentionally separate from the payment-oriented Mrs. Higgins vault
and the legacy concierge JSON vault. It loads only the provider variables
OutClaw understands, keeps process environment variables authoritative, and
never logs credential values.

Default file: ``~/.config/outclaw/credentials.env``
Override with: ``OUTCLAW_CREDENTIALS_PATH``

The file is a deliberately tiny ``KEY=VALUE`` format; no dotenv dependency and
no remote fetch are involved. Only owner-readable 0400/0600 files are accepted.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import MutableMapping
from pathlib import Path
from typing import TypeAlias

CredentialMetadata: TypeAlias = dict[str, bool | str | list[str]]

# A local credentials file must be readable by its owner and inaccessible to
# every other account. 0400 is accepted for deliberately read-only files;
# 0600 is the normal operator-created mode.


SUPPORTED_KEYS = frozenset(
    {
        "OUTCLAW_CASCADE",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "OPENROUTER_API_KEY",
        "CEREBRAS_API_KEY",
        "CF_API_TOKEN",
        "CF_ACCOUNT_ID",
        "HF_TOKEN",
    }
)
DEFAULT_CREDENTIALS_PATH = Path.home() / ".config" / "outclaw" / "credentials.env"
# key -> value for values this module put into os.environ. This lets a later
# file rotation remove/update only values still owned by the loader, without
# clobbering an operator's explicit environment override.
_RUNTIME_LOADED: dict[str, str] = {}


def credentials_path() -> Path:
    """Return the configured local credentials path without reading it."""
    override = os.environ.get("OUTCLAW_CREDENTIALS_PATH", "").strip()
    return Path(override).expanduser() if override else DEFAULT_CREDENTIALS_PATH


def _parse_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "=" not in line:
        raise ValueError("credential file contains a line without '='")
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if key not in SUPPORTED_KEYS:
        raise ValueError(f"unsupported OutClaw credential name: {key}")
    if value[:1] in {"'", '"'} and value[-1:] == value[:1]:
        value = value[1:-1]
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError(f"invalid value for {key}")
    return key, value


def _read_file(path: Path) -> dict[str, str]:
    # Open and validate the same descriptor we read. O_NOFOLLOW prevents a
    # symlink (including a dangling one) and fstat avoids path-check/read races.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise PermissionError("OutClaw credentials path must not be a symlink") from exc
        raise
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        file_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("OutClaw credentials path is not a regular file")
        if file_stat.st_uid != os.getuid():
            raise PermissionError("OutClaw credentials file is not owned by the current user")
        mode = stat.S_IMODE(file_stat.st_mode)
        if mode not in (0o400, 0o600):
            raise PermissionError(
                "OutClaw credentials file must be owner-readable with mode 0400 or 0600"
            )
        values: dict[str, str] = {}
        for line in handle.read().splitlines():
            parsed = _parse_line(line)
            if parsed is not None:
                values[parsed[0]] = parsed[1]
        return values


def load_credentials(
    environ: MutableMapping[str, str] | None = None,
    *,
    path: Path | None = None,
) -> CredentialMetadata:
    """Load local credentials into a mutable environment without overwriting env.

    Immutable mappings are rejected with masked ``TypeError`` metadata. Returns
    masked readiness metadata for diagnostics. The returned ``loaded``
    list contains names only; it never contains credential values.
    """
    target_env: MutableMapping[str, str]
    if environ is None:
        target_env = os.environ
    elif isinstance(environ, MutableMapping):
        target_env = environ
    else:
        return {
            "loaded": [],
            "path": str(path or credentials_path()),
            "error": "TypeError",
        }
    local_path = path or credentials_path()

    # Reconcile values loaded by an earlier call. Only remove/update a value if
    # it still equals the value previously supplied by this loader; explicit
    # operator overrides remain untouched.
    if target_env is os.environ:
        for key, old_value in list(_RUNTIME_LOADED.items()):
            if target_env.get(key) == old_value:
                target_env.pop(key, None)
            _RUNTIME_LOADED.pop(key, None)

    try:
        file_values = _read_file(local_path)
    except FileNotFoundError:
        file_values = {}
    except (OSError, ValueError, PermissionError) as exc:
        return {
            "loaded": [],
            "path": str(local_path),
            "error": type(exc).__name__,
        }

    loaded: list[str] = []
    for key, value in file_values.items():
        # Do not overwrite a value intentionally supplied by the caller.
        if not str(target_env.get(key, "")).strip() and value:
            target_env[key] = value
            loaded.append(key)
            if target_env is os.environ:
                _RUNTIME_LOADED[key] = value
    return {"loaded": sorted(loaded), "path": str(local_path)}


def load_runtime_credentials() -> CredentialMetadata:
    """Convenience entry point used by the cascade before provider discovery."""
    return load_credentials()


if __name__ == "__main__":
    result = load_runtime_credentials()
    print(result)
