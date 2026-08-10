#!/usr/bin/env python3
"""
OutClaw/outclaw_courtlistener.py — CourtListener API Integration Scout.

PREDICASE GEM (2026-07-26): Adapted from Predicase's scout architecture
(``class_signal_scout_v1.py``, ``juris_velocity.py``) and the roadmap in
``scouts/next.txt`` which explicitly calls out CourtListener's free REST
API with 17M+ PACER documents as the path to real citation indexing.

This module is a compliant, privacy-preserving scout that queries the
CourtListener API (Free Law Project) to:
  1. Resolve citation strings to real case metadata (name, holding, court)
  2. Auto-expand OutClaw's seed registry with verified case data
  3. Cross-reference citations against a live legal database
  4. Detect negative treatment (overruled, overturned, superseded)

Design principles (from Predicase):
  - Decoupled: this scout runs independently, feeds into the seed registry
  - Compliant: no PII, no scraping, rate-limited, caches results
  - Gracefully degradable: offline → returns None, seed stays as stubs
  - Single-purpose: one scout = one data source (CourtListener)

CourtListener API details:
  - Base URL: https://www.courtlistener.com/api/rest/v3/
  - No API key required for basic read queries (rate-limited to ~100/hr)
  - Endpoints: /search/, /opinions/, /clusters/, /dockets/
  - Returns JSON with case name, citation, holding text, court, date

Usage:
    from OutClaw.outclaw_courtlistener import CourtListenerScout

    scout = CourtListenerScout()
    case = scout.lookup_citation("410 U.S. 113")
    if case:
        print(f"Found: {case['name']} — {case['holding'][:100]}...")
        scout.expand_seed_registry(case, seed_path="OutClaw/outclaw_seed.json")
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_SEED_PATH = _HERE / "outclaw_seed.json"
_CACHE_DIR = Path.home() / ".outclaw" / "courtlistener_cache"

# CourtListener API base
CL_BASE = "https://www.courtlistener.com/api/rest/v3"
CL_SEARCH = f"{CL_BASE}/search/"
CL_OPINIONS = f"{CL_BASE}/opinions/"

# Rate limiting (be a good API citizen)
MIN_DELAY = 1.0  # seconds between requests
MAX_CACHE_AGE = 86400 * 7  # 7 days


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@dataclass
# ═══════════════════════════════════════════════════════
#  OUTCLAW_COURTLISTENER
# ═══════════════════════════════════════════════════════════════

class CacheEntry:
    citation: str
    data: dict[str, Any]
    fetched_at: float = field(default_factory=time.time)

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.fetched_at) > MAX_CACHE_AGE


# ---------------------------------------------------------------------------
# Scout
# ---------------------------------------------------------------------------


class CourtListenerScout:
    """
    CourtListener API integration scout for OutClaw.

    Mirrors Predicase's scout pattern: one data source, decoupled,
    rate-limited, cache-backed, gracefully degradable.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        rate_limit: float = MIN_DELAY,
    ):
        self._cache_dir = Path(cache_dir or _CACHE_DIR)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit = rate_limit
        self._last_request: float = 0.0
        self._request_count: int = 0
        self._cache: dict[str, CacheEntry] = {}
        self._load_cache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup_citation(self, citation: str) -> dict[str, Any] | None:
        """
        Look up a citation string in CourtListener.

        Args:
            citation: e.g. "410 U.S. 113", "123 F.3d 456"

        Returns:
            Dict with name, holding, court, date, citation, area, overruled,
            or None if not found / offline.
        """
        # Check cache first
        cached = self._cache_get(citation)
        if cached is not None:
            return cached

        # Build query
        result = self._api_search(citation)
        if result is None:
            return None

        # Normalize into OutClaw seed format
        entry = self._normalize_result(citation, result)
        if entry:
            self._cache_put(citation, entry)
        return entry

    def expand_seed_registry(
        self,
        case_entry: dict[str, Any],
        seed_path: Path | None = None,
    ) -> bool:
        """
        Add a CourtListener-resolved case to OutClaw's seed registry.

        Args:
            case_entry: Normalized case dict from lookup_citation()
            seed_path: Path to outclaw_seed.json (default: OutClaw/outclaw_seed.json)

        Returns:
            True if the case was added, False if already present.
        """
        sp = Path(seed_path or _SEED_PATH)
        if not sp.exists():
            return False

        with open(sp, "r", encoding="utf-8") as f:
            seed = json.load(f)

        citation_key = case_entry.get("citation", "")
        if citation_key in seed.get("cases", {}):
            return False  # Already present

        seed["cases"][citation_key] = {
            "name": case_entry.get("name", citation_key),
            "holding": case_entry.get("holding", ""),
            "overruled": case_entry.get("overruled", False),
            "area": case_entry.get("area", "general"),
        }

        with open(sp, "w", encoding="utf-8") as f:
            json.dump(seed, f, indent=2)

        return True

    def diagnostics(self) -> dict[str, Any]:
        """Return operational diagnostics (Predicase telemetry pattern)."""
        return {
            "api_base": CL_BASE,
            "requests_made": self._request_count,
            "cache_size": len(self._cache),
            "cache_dir": str(self._cache_dir),
            "rate_limit": self._rate_limit,
            "last_request_ago": time.time() - self._last_request
            if self._last_request
            else None,
        }

    def verify_holding(
        self,
        case_entry: dict[str, Any],
        proposition: str,
        min_confidence: float = 0.60,
    ) -> dict[str, Any] | None:
        """
        RAG VERIFICATION STEP (2026-08-03): cross-check whether a retrieved
        CourtListener holding actually supports a proposition in the filing.

        This is the semantic bridge between RETRIEVAL and USE: a raw API hit
        is only "ground truth" after the reasoning layer confirms the holding
        text supports (or contradicts) what the filing claims. Uses the
        stair-stepped model cascade when enabled; returns None (no verdict)
        when the cascade is off so retrieval stays pure and deterministic.

        Returns:
            {"verified": bool, "confidence": float, "reasoning": str,
             "tier": int, "provider": str, "model": str}
            or None when cascade disabled / unavailable.
        """
        try:
            from OutClaw.outclaw_model_cascade import get_cascade  # type: ignore

            cascade = get_cascade()
            if not cascade.enabled:
                return None

            holding = str(case_entry.get("holding", ""))[:2500]
            if not holding:
                return None

            prompt = (
                "You are a legal research assistant. Determine whether the "
                "PROPOSITION below is supported by the CITED AUTHORITY's "
                "holding, contradicts it, or is unrelated to it.\n\n"
                f"CITED AUTHORITY (from CourtListener):\n{holding}\n\n"
                f"PROPOSITION IN FILING:\n{proposition[:1500]}\n\n"
                "Respond with ONLY this JSON (no other text): "
                '{"verified": true_or_false, "confidence": 0.0_to_1.0, '
                '"reasoning": "one sentence explaining the relationship"}'
            )
            result = cascade.complete(
                prompt,
                task="citation_verification",
                min_confidence=min_confidence,
                max_tokens=500,
            )
            if not result.ok or result.data is None:
                return None
            return {
                **result.data,
                "tier": result.tier,
                "provider": result.provider,
                "model": result.model,
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal — API calls
    # ------------------------------------------------------------------

    def _api_search(self, citation: str) -> dict[str, Any] | None:
        """Query CourtListener search endpoint for a citation."""
        params = urllib.parse.urlencode(
            {
                "q": citation,
                "type": "o",  # opinions only
            }
        )
        url = f"{CL_SEARCH}?{params}"

        data = self._make_request(url)
        if data is None:
            return None

        results = data.get("results", [])
        if not results:
            return None

        # Take the first result
        first = results[0]
        opinion_id = first.get("id")

        # Fetch full opinion details
        if opinion_id:
            detail = self._make_request(f"{CL_OPINIONS}{opinion_id}/")
            if detail:
                return {**first, **detail}

        return first

    def _make_request(self, url: str) -> dict[str, Any] | None:
        """Make a rate-limited GET request to CourtListener API."""
        # Rate limit
        elapsed = time.time() - self._last_request
        if elapsed < self._rate_limit:
            time.sleep(self._rate_limit - elapsed)

        headers = {
            "User-Agent": "OutClaw-CitationAudit/0.2 (Free Law Project integration; contact via project repo)",
            "Accept": "application/json",
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                self._last_request = time.time()
                self._request_count += 1
                return json.loads(resp.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            # One-shot WARN so operator knows API is unreachable
            if not getattr(self, "_api_failure_warned", False):
                self._api_failure_warned = True
                import sys

                sys.stderr.write(
                    f"[outclaw_courtlistener] WARN: API request failed "
                    f"(CourtListener may be unreachable): {exc!r}\n"
                )
                sys.stderr.flush()
            return None

    # ------------------------------------------------------------------
    # Internal — normalize
    # ------------------------------------------------------------------

    def _normalize_result(
        self, citation: str, api_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Normalize CourtListener API response into OutClaw seed format.

        CourtListener returns varied fields; we extract the stable subset.
        """
        case_name = (
            api_data.get("caseName")
            or api_data.get("case_name")
            or api_data.get("cluster_name")
            or citation
        )
        holding = (
            api_data.get("html_with_citations", "")
            or api_data.get("plain_text", "")
            or api_data.get("snippet", "")
        )
        # Truncate long holdings
        if len(holding) > 500:
            holding = holding[:497] + "..."

        court = api_data.get("court", "") or api_data.get("court_id", "")
        date_filed = api_data.get("dateFiled") or api_data.get("date_filed", "")
        status = api_data.get("status", "") or ""

        # Detect overruled status from CourtListener flags
        overruled = "overruled" in str(
            api_data.get("citation", "")
        ).lower() or status.lower() in ("overruled", "superseded", "abrogated")

        # Infer legal area from court or case name keywords
        area = self._infer_area(case_name, holding, court)

        return {
            "name": case_name,
            "citation": citation,
            "holding": holding,
            "court": court,
            "date_filed": date_filed,
            "overruled": overruled,
            "area": area,
            "source": "courtlistener",
        }

    @staticmethod
    def _infer_area(case_name: str, holding: str, court: str) -> str:
        """Infer legal area from available metadata."""
        text = f"{case_name} {holding} {court}".lower()
        if any(
            w in text
            for w in (
                "criminal",
                "fourth amendment",
                "fifth amendment",
                "sixth amendment",
                "miranda",
                "search",
                "seizure",
            )
        ):
            return "criminal procedure"
        if any(
            w in text
            for w in (
                "civil right",
                "§ 1983",
                "discrimination",
                "equal protection",
                "due process",
            )
        ):
            return "civil rights"
        if any(w in text for w in ("contract", "breach", "consideration")):
            return "contracts"
        if any(w in text for w in ("tort", "negligence", "damages")):
            return "torts"
        if any(
            w in text for w in ("constitution", "first amendment", "commerce clause")
        ):
            return "constitutional law"
        if any(w in text for w in ("administrative", "agency", "regulation")):
            return "administrative law"
        if any(w in text for w in ("habeas", "2254", "2255")):
            return "habeas corpus"
        return "general"

    # ------------------------------------------------------------------
    # Internal — cache
    # ------------------------------------------------------------------

    def _cache_key(self, citation: str) -> str:
        return hashlib.sha256(citation.lower().encode()).hexdigest()[:16]

    def _cache_get(self, citation: str) -> dict[str, Any] | None:
        key = self._cache_key(citation)
        if key in self._cache:
            entry = self._cache[key]
            if not entry.is_stale:
                return entry.data
        return None

    def _cache_put(self, citation: str, data: dict[str, Any]) -> None:
        key = self._cache_key(citation)
        self._cache[key] = CacheEntry(citation=citation, data=data)
        self._save_cache()

    def _load_cache(self) -> None:
        cache_file = self._cache_dir / "cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    raw = json.load(f)
                for key, entry_data in raw.items():
                    self._cache[key] = CacheEntry(
                        citation=entry_data.get("citation", ""),
                        data=entry_data.get("data", {}),
                        fetched_at=entry_data.get("fetched_at", 0.0),
                    )
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_cache(self) -> None:
        cache_file = self._cache_dir / "cache.json"
        with open(cache_file, "w") as f:
            json.dump(
                {
                    key: {
                        "citation": e.citation,
                        "data": e.data,
                        "fetched_at": e.fetched_at,
                    }
                    for key, e in self._cache.items()
                },
                f,
                indent=2,
            )


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_scout: CourtListenerScout | None = None


def get_scout() -> CourtListenerScout:
    """Get or create the default CourtListener scout."""
    global _default_scout
    if _default_scout is None:
        _default_scout = CourtListenerScout()
    return _default_scout


def quick_lookup(citation: str) -> dict[str, Any] | None:
    """One-liner: look up a citation in CourtListener."""
    return get_scout().lookup_citation(citation)


# ---------------------------------------------------------------------------
# Smoke test (offline — won't hit API)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scout = CourtListenerScout()
    print("CourtListener Scout initialized")
    print(f"  API base: {CL_BASE}")
    print(f"  Cache dir: {scout._cache_dir}")
    print(f"  Cache entries: {len(scout._cache)}")
    print(f"  Ready: {scout.diagnostics()}")
    print()
    print("Try: scout.lookup_citation('410 U.S. 113')")
    print("Note: requires internet connectivity for live lookups.")
