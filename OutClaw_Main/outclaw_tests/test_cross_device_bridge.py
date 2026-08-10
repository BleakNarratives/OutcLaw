#!/usr/bin/env python3
"""
test_cross_device_bridge.py -- OutClawBus <-> SyncBridge integration tests.

Verifies end-to-end behavior:
  * OutClaw publishing to its in-process bus triggers a single egress file
    written by the bridge's _egress_cb subscription.
  * Peer-written envelopes are dispatched to the local bus exactly once
    (idempotent), and the _bridge_origin tag prevents re-egress loops.
  * Fallback path (no local bus): OutClawBus._dispatch writes through the
    bridge so cross-device mirrors survive bus failure.
  * At no point does the same event produce TWO disk files for the same
    message_id (loop-guard invariant).

Each test uses an isolated sync bus root under /tmp; nothing touches
~bleaknarratives/sync_bus.
"""

import json
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_HERE = Path(__file__).resolve().parent
# Canonical layout: <repo>/OutClaw/OutClaw_Main/outclaw_tests.
# The repository root is three levels above this test directory; using only
# parent.parent points at the compatibility shell and hides SyntaxIntelligence.
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))

# Namespace the test runs to a non-real root.
import os

os.environ.setdefault("BUS_SYNC_ROOT", "/tmp/__outclaw_xdevice_test__")

from OutClaw.outclaw_bus import CHANNEL_FINDINGS, OutClawBus
from SyntaxIntelligence.event_bus import SyntaxEventBus
from SyntaxIntelligence.sync_bridge import SyncBridge


def _drop_peer_envelope(root: Path, peer: str, *, mid, channel, payload):
    env_dir = root / peer / "messages"
    env_dir.mkdir(parents=True, exist_ok=True)
    body = {
        "message_id": mid,
        "sender_id": f"{peer}.peer-agent",
        "channel": channel,
        "payload": payload,
        "timestamp": time.time(),
        "origin_device": peer,
        "ttl": 86400,
    }
    (env_dir / f"{int(body['timestamp'])}_{mid}.json").write_text(json.dumps(body))


class TestOutClawBusEgress(unittest.TestCase):
    """OutClawBus publishes -> bridge _egress_cb writes ONE disk file."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.joinpath("me", "messages").mkdir(parents=True)
        self.root.joinpath("peer", "messages").mkdir(parents=True)
        self.local_bus = SyntaxEventBus()
        self.bus = OutClawBus(bus=self.local_bus, sender_id="outclaw-tests")
        self.bridge = SyncBridge(
            sync_root=self.root, device_id="me", local_bus=self.local_bus
        )
        self.bridge.start()
        self.addCleanup(self.bridge.stop)
        self.bus.attach_bridge(self.bridge)

    def test_publish_findings_writes_one_disk_file(self):
        digest = {
            "audit_id": "audit-test-1",
            "severity_counts": {"HIGH": 1, "MEDIUM": 0, "OK": 0},
            "safe_to_draft": False,
            "recovered_by_window_count": 0,
            "high_count": 1,
            "high_findings": [
                {
                    "citation_fp": "abc123",
                    "rule": "MISQUOTE / OPPOSITE",
                    "excerpt": "REDACTED-NAME v. REDACTED-NAME",
                }
            ],
        }
        self.bus.publish_findings({"summary": digest, "findings": [], "text": "x"})
        # Give the local-bus dispatch a moment to fire (synchronous, but be safe).
        time.sleep(0.05)
        files = list((self.root / "me" / "messages").glob("*.json"))
        self.assertEqual(len(files), 1, f"Expected 1 egress file, got {len(files)}")
        body = json.loads(files[0].read_text())
        self.assertEqual(body["channel"], CHANNEL_FINDINGS)
        self.assertEqual(body["origin_device"], "me")
        # Disk payload is CLEAN (no _bridge_origin tag -- publish_local is no longer called,
        # and egress subscription writes the original data dict, not the _forward payload).
        self.assertNotIn("_bridge_origin", body["payload"])

    def test_no_loop_when_bridge_also_subscribes_to_findings(self):
        # Sanity: subscribing to the bridge.on-findings from a downstream
        # consumer should not create a feedback loop.
        seen_messages = []
        self.local_bus.subscribe(
            "downstream", CHANNEL_FINDINGS, lambda a, c, d: seen_messages.append(d)
        )
        digest = {
            "audit_id": "loop-check",
            "severity_counts": {},
            "safe_to_draft": True,
            "recovered_by_window_count": 0,
            "high_count": 0,
            "high_findings": [],
        }
        self.bus.publish_findings({"summary": digest, "findings": [], "text": "x"})
        time.sleep(0.05)
        files = list((self.root / "me" / "messages").glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(len(seen_messages), 1)


class TestOutClawBusIngress(unittest.TestCase):
    """Peer's disk message -> bridge polls -> local bus fires once; no loop."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.joinpath("me", "messages").mkdir(parents=True)
        self.root.joinpath("peer", "messages").mkdir(parents=True)
        self.local_bus = SyntaxEventBus()
        self.bus = OutClawBus(bus=self.local_bus, sender_id="outclaw-tests")
        self.bridge = SyncBridge(
            sync_root=self.root, device_id="me", local_bus=self.local_bus
        )
        self.bridge.start()
        self.addCleanup(self.bridge.stop)
        self.bus.attach_bridge(self.bridge)
        self.dispatched = []
        self.local_bus.subscribe(
            "downstream", CHANNEL_FINDINGS, lambda a, c, d: self.dispatched.append(d)
        )

    def test_peer_message_dispatches_once(self):
        _drop_peer_envelope(
            self.root,
            "peer",
            mid="peer-msg-1",
            channel=CHANNEL_FINDINGS,
            payload={"audit_id": "from-peer", "safe_to_draft": True},
        )
        # Drive _poll_once manually for determinism, then sleep a beat so
        # the local Syntax bus can fan out to the ``downstream`` subscriber
        # (subscription dispatch is synchronous but the bus may have its own
        # deferred-callback semantics on slow CI; sleep is harmless).
        self.bridge._poll_once()
        time.sleep(0.05)
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(self.dispatched[0]["audit_id"], "from-peer")
        self.assertEqual(self.dispatched[0]["_bridge_origin"], "ingress")
        # Re-poll: idempotent (seen_ids check blocks re-dispatch).
        self.bridge._poll_once()
        time.sleep(0.05)
        self.assertEqual(len(self.dispatched), 1)
        # Disk file should NOT loop back to egress (origin_device=peer).
        me_files = list((self.root / "me" / "messages").glob("*.json"))
        self.assertEqual(me_files, [])


class TestFallbackPath(unittest.TestCase):
    """Local bus dead -> OutClawBus._dispatch fans out via attached bridge."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.joinpath("me", "messages").mkdir(parents=True)
        self.root.joinpath("peer", "messages").mkdir(parents=True)
        # Capture + restore module-level _EVT_BUS cache so this test does not
        # leak mutated state into other test classes that import OutClawBus
        # later in the same process. (Belt-and-suspenders alongside force_no_bus.)
        # NB: kept even though `force_no_bus=True` independently forces `_bus=None`;
        # defends against future helpers that re-read `_EVT_BUS` lazily.
        import OutClaw.outclaw_bus as ob

        self._saved_evt_bus = ob._EVT_BUS
        ob._EVT_BUS = None
        self.addCleanup(setattr, ob, "_EVT_BUS", self._saved_evt_bus)
        # Construct an OutClawBus with NO local bus so _dispatch takes the
        # fallback path that calls bridge.publish_local. Use the public
        # ``force_no_bus`` flag rather than poking at ``self._bus``.
        self.bus = OutClawBus(
            bus=None, sender_id="outclaw-tests-fallback", force_no_bus=True
        )
        self.bridge = SyncBridge(sync_root=self.root, device_id="me", local_bus=None)
        self.bridge.start()
        self.addCleanup(self.bridge.stop)
        self.bus.attach_bridge(self.bridge)

    def test_dispatch_fallback_writes_to_bridge(self):
        digest = {
            "audit_id": "fallback-1",
            "severity_counts": {"HIGH": 0, "MEDIUM": 1, "OK": 0},
            "safe_to_draft": False,
            "recovered_by_window_count": 0,
            "high_count": 0,
            "high_findings": [],
        }
        self.bus.publish_findings({"summary": digest, "findings": [], "text": "x"})
        files = list((self.root / "me" / "messages").glob("*.json"))
        self.assertEqual(len(files), 1)
        body = json.loads(files[0].read_text())
        self.assertEqual(body["channel"], CHANNEL_FINDINGS)
        # The digest's audit_id is derived from the input text via SHA256
        # truncated to 10 chars (see OutClawBus.publish_findings), so the
        # id DOES exist but the literal "fallback-1" is NOT preserved --
        # only the digest shape is. Assert the digest is well-formed instead.
        from OutClaw.outclaw_bus import citation_fingerprint

        self.assertIn("audit_id", body["payload"])
        expected_id = citation_fingerprint("x")[:10]
        self.assertEqual(body["payload"]["audit_id"], expected_id)
        self.assertEqual(body["payload"]["safe_to_draft"], False)
        self.assertEqual(body["payload"]["severity_counts"]["MEDIUM"], 1)
        # Fallback log entry should record ``bridged: True`` since the
        # bridge DID publish even though the local bus was dead.
        last_log = self.bus.fallback_log(5)[-1]
        self.assertEqual(last_log["channel"], CHANNEL_FINDINGS)
        self.assertEqual(last_log["live"], False)
        self.assertEqual(last_log["bridged"], True)


class TestBootstrapWiring(unittest.TestCase):
    """bridge_session() builds + tears down cleanly."""

    def test_bootstrap_lifecycle(self):
        import OutClaw.outclaw_bridge_bootstrap as bob

        bob._default_device_id = lambda: "test-device"
        from OutClaw.outclaw_bridge_bootstrap import bridge_session

        with bridge_session() as bundle:
            self.assertIsNotNone(bundle.bus)
            self.assertIsNotNone(bundle.bridge)
            self.assertTrue(bundle.bridge.is_running)
            self.assertTrue(bundle.bus.has_bridge)
            # Use public local_bus property (added in round 2) instead of
            # the underscored private attribute. bundle.is_cross_device_wired
            # is the public bool; regressions will surface there too.
            self.assertIs(bundle.bus.local_bus, bundle.bridge.local_bus)
            self.assertTrue(bundle.is_cross_device_wired)
        # Context manager shutdown: bridge threads joined.
        self.assertFalse(bundle.bridge.is_running)


if __name__ == "__main__":
    unittest.main()
