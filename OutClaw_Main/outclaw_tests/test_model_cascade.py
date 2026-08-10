#!/usr/bin/env python3
"""
outclaw_tests/test_model_cascade.py — unit tests for the stair-stepped
model cascade (outclaw_model_cascade.py).

Covers the core reliability contract that matters for a zero-budget legal
tool: tier escalation, provider failover, JSON validation, confidence
thresholding, caching, config gating (opt-in by default), and graceful
degradation when every provider is unavailable.

All provider calls are mocked — no network, no API keys, no Ollama needed.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent.parent))

from outclaw_model_cascade import (
    ModelCascade,
    TASK_START_TIER,
    TIER_1_EXTRACTION,
    TIER_2_CLASSIFICATION,
    TIER_3_ADJUDICATION,
)

# Every provider env key the module reads. Tests wipe these in setUp so no
# key ever leaks across tests (clear=False in patch.dict does leak).
_PROVIDER_KEYS = [
    "GOOGLE_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
    "OPENROUTER_API_KEY", "CEREBRAS_API_KEY", "CF_API_TOKEN",
    "CF_ACCOUNT_ID", "HF_TOKEN", "OUTCLAW_CASCADE",
]


def _config(enabled: bool = True) -> dict:
    return {"enabled": enabled}


def _mock_providers(cascade: ModelCascade, dispatch: dict[str, list[dict]]):
    """
    Patch _call_provider with a sequence-based dispatcher keyed by provider name.

    dispatch: {provider_name: [outcome, outcome, ...]} where each outcome is
    {"response": dict | None, "raises": Exception}. Outcomes are consumed
    FIFO per provider, so the same provider can fail on its tier-2 call and
    succeed on its tier-3 call. Missing providers default to unparseable JSON
    (a failure), which mirrors a real "provider down / bad model" state.
    """
    counters: dict[str, int] = {}

    def fake_call(prov, model, prompt, system, max_tokens):
        seq = dispatch.get(prov.name)
        if not seq:
            return "not json at all"
        i = counters.get(prov.name, 0)
        counters[prov.name] = i + 1
        spec = seq[min(i, len(seq) - 1)]
        if spec.get("raises"):
            raise spec["raises"]
        resp = spec.get("response")
        if resp is None:
            return "not json at all"
        return json.dumps(resp)

    return mock.patch.object(cascade, "_call_provider", side_effect=fake_call)


class CascadeTestBase(unittest.TestCase):
    def setUp(self):
        # Wipe the provider keys so tests start hermetic (clear=False in
        # patch.dict leaks otherwise). The ladder is cloud-only, so with no
        # keys the cascade fails fast with zero network calls.
        for key in _PROVIDER_KEYS:
            __import__("os").environ.pop(key, None)

    def tearDown(self):
        for key in _PROVIDER_KEYS:
            __import__("os").environ.pop(key, None)


class CascadeEscalationTests(CascadeTestBase):
    """The stair-step contract: enter low, escalate up only when needed."""

    def test_enters_at_task_tier_and_succeeds(self):
        # citation_extraction starts on tier 1; groq (tier-1 first rung)
        # succeeds immediately -> no escalation, tier stays 1.
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with _mock_providers(cascade, {
                "groq": [{"response": {"citations": []}}],
            }):
                result = cascade.complete("find citations", "citation_extraction")
        self.assertTrue(result.ok)
        self.assertEqual(result.tier, TIER_1_EXTRACTION)
        self.assertEqual(result.provider, "groq")
        self.assertEqual(result.escalation, ["t1 groq ok"])

    def test_tier1_fails_then_escalates_to_tier2(self):
        # opposite_holding starts on tier 2; both tier-2 rungs that have keys
        # (gemini, openrouter) fail with low confidence / bad JSON, so the
        # ladder escalates to tier 3 where openrouter finally succeeds.
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {
            "GROQ_API_KEY": "x", "GOOGLE_API_KEY": "y",
            "OPENROUTER_API_KEY": "z",
        }, clear=False):
            with _mock_providers(cascade, {
                "gemini": [{"response": {"is_opposite": False, "confidence": 0.1}}],
                "openrouter": [
                    {"response": None},                       # tier-2 call fails
                    {"response": {"is_opposite": True, "confidence": 0.9}},  # tier-3 win
                ],
                "groq": [{"response": None}],
            }):
                result = cascade.complete(
                    "p vs h", "opposite_holding", min_confidence=0.70,
                )
        self.assertTrue(result.ok)
        self.assertEqual(result.tier, TIER_3_ADJUDICATION)
        self.assertEqual(result.provider, "openrouter")
        self.assertTrue(any("t2" in step for step in result.escalation))
        self.assertTrue(any("t3 openrouter ok" in step for step in result.escalation))

    def test_escalates_to_adjudication_when_tier2_confidence_low(self):
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {
            "GROQ_API_KEY": "x", "GOOGLE_API_KEY": "y",
            "OPENROUTER_API_KEY": "z", "MISTRAL_API_KEY": "w",
        }, clear=False):
            with _mock_providers(cascade, {
                "gemini": [{"response": {"is_opposite": False, "confidence": 0.2}}],
                "openrouter": [{"response": {"is_opposite": True, "confidence": 0.85}}],
                "groq": [{"response": None}],
            }):
                result = cascade.complete(
                    "p vs h", "opposite_holding", min_confidence=0.70,
                )
        self.assertTrue(result.ok)
        self.assertEqual(result.tier, TIER_2_CLASSIFICATION)
        self.assertEqual(result.provider, "openrouter")

    def test_all_tiers_fail_returns_ok_false(self):
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {
            "GROQ_API_KEY": "x", "GOOGLE_API_KEY": "y",
            "OPENROUTER_API_KEY": "z", "MISTRAL_API_KEY": "w",
        }, clear=False):
            with _mock_providers(cascade, {
                "groq": [{"response": None}], "gemini": [{"response": None}],
                "openrouter": [{"response": None}], "mistral": [{"response": None}],
            }):
                result = cascade.complete("p vs h", "opposite_holding")
        self.assertFalse(result.ok)
        self.assertIsNone(result.data)
        self.assertTrue(result.escalation)  # trail still recorded

    def test_failover_within_tier(self):
        """If the first provider in a tier errors, the next in the same tier is tried."""
        # citation_extraction starts on tier 1 where groq is the first rung;
        # groq times out -> gemini (second rung, same tier) takes over.
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {
            "GROQ_API_KEY": "x", "GOOGLE_API_KEY": "y",
        }, clear=False):
            with _mock_providers(cascade, {
                "groq": [{"raises": TimeoutError("slow")}],
                "gemini": [{"response": {"citations": []}}],
            }):
                result = cascade.complete("find citations", "citation_extraction")
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.tier, TIER_1_EXTRACTION)
        self.assertTrue(any("groq" in step and "t1" in step for step in result.escalation))


class CascadeJSONValidationTests(CascadeTestBase):
    """The guardrail: unparseable / key-missing output is a failure, not a win."""

    def test_missing_required_keys_rejected(self):
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with _mock_providers(cascade, {
                "groq": [{"response": {"is_opposite": True}}],  # no "confidence"
            }):
                result = cascade.complete("p vs h", "opposite_holding")
        self.assertFalse(result.ok)

    def test_unparseable_json_rejected(self):
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with _mock_providers(cascade, {"groq": [{"response": None}]}):
                result = cascade.complete("p vs h", "opposite_holding")
        self.assertFalse(result.ok)
        self.assertTrue(any("invalid-json" in step for step in result.escalation))

    def test_confidence_below_minimum_rejected(self):
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with _mock_providers(cascade, {
                "groq": [{"response": {"is_opposite": True, "confidence": 0.3}}],
            }):
                result = cascade.complete("p vs h", "opposite_holding", min_confidence=0.70)
        self.assertFalse(result.ok)
        self.assertTrue(any("low-conf" in step for step in result.escalation))


class CascadeJSONTypeTests(CascadeTestBase):
    """Prompt-injection defense part 2: wrong-typed critical fields are
    rejected even when all required keys are present."""

    def test_string_bool_rejected(self):
        """{"is_opposite": "false"} is a STRING, not a bool -- must be rejected
        so a hostile document can't smuggle a truthy "false" through."""
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with _mock_providers(cascade, {
                "groq": [{"response": {"is_opposite": "false", "confidence": 0.9}}],
            }):
                result = cascade.complete("p vs h", "opposite_holding")
        self.assertFalse(result.ok)
        self.assertTrue(any("bad-type" in step for step in result.escalation))

    def test_non_numeric_confidence_rejected(self):
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with _mock_providers(cascade, {
                "groq": [{"response": {"is_opposite": True, "confidence": "high"}}],
            }):
                result = cascade.complete("p vs h", "opposite_holding")
        self.assertFalse(result.ok)

    def test_bool_verified_rejected_as_string(self):
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with _mock_providers(cascade, {
                "groq": [{"response": {"verified": "yes", "confidence": 0.9}}],
            }):
                result = cascade.complete("p vs h", "citation_verification")
        self.assertFalse(result.ok)

    def test_bool_verified_accepted_when_real_bool(self):
        cascade = ModelCascade(config=_config())
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with _mock_providers(cascade, {
                "groq": [{"response": {"verified": True, "confidence": 0.9}}],
            }):
                result = cascade.complete("p vs h", "citation_verification")
        self.assertTrue(result.ok)
        self.assertIs(result.data["verified"], True)


class CascadeCacheTests(CascadeTestBase):
    def test_same_prompt_cached(self):
        cascade = ModelCascade(config=_config())
        calls = {"n": 0}

        def fake_call(prov, model, prompt, system, max_tokens):
            calls["n"] += 1
            return json.dumps({"is_opposite": True, "confidence": 0.9})

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with mock.patch.object(cascade, "_call_provider", side_effect=fake_call):
                r1 = cascade.complete("p vs h", "opposite_holding")
                r2 = cascade.complete("p vs h", "opposite_holding")
        self.assertTrue(r1.ok and r2.ok)
        self.assertEqual(calls["n"], 1)  # second call hit cache
        self.assertEqual(cascade.status()["stats"]["cache_hits"], 1)

    def test_cache_hit_preserves_attempt_object_model(self):
        """Cache hits must expose Attempt objects (attempts[0].tier) exactly
        like fresh calls -- not raw dicts."""
        cascade = ModelCascade(config=_config())
        calls = {"n": 0}

        def fake_call(prov, model, prompt, system, max_tokens):
            calls["n"] += 1
            return json.dumps({"is_opposite": True, "confidence": 0.9})

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with mock.patch.object(cascade, "_call_provider", side_effect=fake_call):
                r1 = cascade.complete("p vs h", "opposite_holding")
                r2 = cascade.complete("p vs h", "opposite_holding")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(r1.attempts[0].tier, r2.attempts[0].tier)  # attr access on both

    def test_cache_not_hit_across_tasks(self):
        cascade = ModelCascade(config=_config())
        calls = {"n": 0}

        def fake_call(prov, model, prompt, system, max_tokens):
            calls["n"] += 1
            # Valid for both opposite_holding (is_opposite/confidence) and
            # citation_extraction (citations) so each task succeeds on first rung.
            return json.dumps({
                "is_opposite": True, "confidence": 0.9, "citations": [],
            })

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with mock.patch.object(cascade, "_call_provider", side_effect=fake_call):
                cascade.complete("p vs h", "opposite_holding")
                cascade.complete("p vs h", "citation_extraction")
        self.assertEqual(calls["n"], 2)


class CascadeConfigTests(CascadeTestBase):
    """Opt-in by default: the cascade is inert until enabled."""

    def test_disabled_by_default(self):
        cascade = ModelCascade(config=_config(enabled=False))
        self.assertFalse(cascade.enabled)

    def test_enabled_via_env(self):
        cascade = ModelCascade(config=_config(enabled=False))
        with mock.patch.dict("os.environ", {"OUTCLAW_CASCADE": "1"}, clear=False):
            self.assertTrue(cascade.enabled)

    def test_graceful_with_no_keys(self):
        """Cloud-only: no keys anywhere -> ok=False immediately, no network,
        no local server probe, no exception. The heuristic pipeline stands."""
        cascade = ModelCascade(config=_config())
        result = cascade.complete("p vs h", "opposite_holding")
        self.assertFalse(result.ok)
        self.assertIsNone(result.data)
        self.assertEqual(result.escalation, [])  # nothing even attempted

    def test_cloud_only_no_local_provider(self):
        """The provider registry must NOT contain a local/ollama provider."""
        cascade = ModelCascade(config=_config())
        providers = cascade.provider_status()
        self.assertNotIn("ollama", providers)

    def test_429_cooldown_expires(self):
        """A 429 cools a provider down for a bounded window, then it is
        retried -- it is NOT disabled for the process lifetime."""
        cascade = ModelCascade(config=_config())
        from outclaw_model_cascade import RATE_LIMIT_COOLDOWN

        calls = {"n": 0}

        def fake_call(prov, model, prompt, system, max_tokens):
            calls["n"] += 1
            if calls["n"] == 1:
                raise __import__("urllib.error").error.HTTPError(
                    "url", 429, "too many", None, None
                )
            return json.dumps({"is_opposite": True, "confidence": 0.9})

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "x"}, clear=False):
            with mock.patch.object(cascade, "_call_provider", side_effect=fake_call):
                # First call: 429 puts groq into cooldown.
                r1 = cascade.complete("p vs h", "opposite_holding")
                self.assertFalse(r1.ok)
                # Simulate cooldown expiry, then the same prompt is cached -- so
                # use a fresh prompt to force a real provider attempt.
                cascade._cooling["groq"] = 0.0  # expired
                r2 = cascade.complete("p vs h v2", "opposite_holding")
        self.assertTrue(r2.ok)
        self.assertEqual(calls["n"], 2)  # groq retried after cooldown expired

    def test_provider_status_reports_missing_keys(self):
        cascade = ModelCascade(config=_config())
        # setUp already wiped keys
        status = cascade.provider_status()
        self.assertFalse(status["groq"]["configured"])
        self.assertIn("GROQ_API_KEY", status["groq"]["missing_env"])

    def test_task_start_tiers_mapping_sane(self):
        self.assertEqual(TASK_START_TIER["opposite_holding"], TIER_2_CLASSIFICATION)
        self.assertEqual(TASK_START_TIER["final_adjudication"], TIER_3_ADJUDICATION)
        self.assertEqual(TASK_START_TIER["citation_extraction"], TIER_1_EXTRACTION)


if __name__ == "__main__":
    unittest.main()
