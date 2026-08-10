# Cross-Device Sync Protocol — bleaknarratives swarm

This document is the canonical reference for how the Chromebook (penguin),
Motorola 4 5G 2024 (moto4), and Samsung A9 (a9) communicate via the
rclone 'cloud' carrier. It locks in the contracts that the bridge
implementation in `SyntaxIntelligence/sync_bridge.py`, the bootstrap in
`OutClaw/outclaw_bridge_bootstrap.py`, and the script
`scripts/sync_bus_pull.sh` all share.

## 1. Topology

| Device  | Role           | How it addresses peers                |
|---------|----------------|---------------------------------------|
| penguin | Initiator      | Has `outclaw-cloud:` rclone remote    |
| moto4   | TermuxNode     | Writes to its own folder under sync   |
| a9      | TermuxNode     | Writes to its own folder under sync   |

Devices are behind carrier NAT. The rclone 'cloud' carrier is the only
direct carrier. There is NO peer-to-peer SSH fallback path inside the
swarm (SSH is used for one-off operator maintenance, not for swarm comms).

## 2. Directory layout (Writer-Owns)

```
~/bleaknarratives/sync_bus/
├── penguin/
│   ├── presence.json          # {device_id, last_seen, system_load, ...}
│   ├── .seen_ids.json         # local dedupe set, capped at 10k entries
│   └── messages/
│       └── 1709420000_<message_id>.json
├── moto4/
│   ├── presence.json
│   ├── .seen_ids.json         # moto4's local set, NEVER written by penguin
│   └── messages/
└── a9/
    ├── presence.json
    ├── .seen_ids.json
    └── messages/
```

**Writer-Owns rule**: a device MUST NEVER modify a peer's subdirectory.
`scripts/sync_bus_pull.sh` enforces this on the push side (only pushes
the device's own subdirectory). `rclone sync --delete-from` semantics
remain safe because each device owns its own subtree.

`.seen_ids.json` is excluded from rclone sync (it's per-device state).
`*.tmp` is also excluded (atomic-write interim files).

## 3. Envelope (wire format)

Every message is a single JSON file:

```json
{
  "message_id": "1709420000123-a1b2c3d4",
  "sender_id": "outclaw-orchestrator",
  "channel": "outclaw.findings",
  "payload": { ... },
  "timestamp": 1709420000.123,
  "origin_device": "penguin",
  "ttl": 604800
}
```

The `payload` is whatever the originating module chose to publish. OutClaw
publishes a digest calibrated for redaction (see `OutClaw/outclaw_bus.py:
publish_findings`). No `_bridge_origin` metadata tag is persisted on
disk — it is added ONLY in-memory by `_forward_to_local_bus` when
re-publishing to the local bus (so the per-device egress listener can
detect and skip the re-broadcast). The on-disk envelope is clean.

## 4. Idempotency

A device MUST NOT redactively dispatch the same `message_id` twice.
The mechanism is the local `.seen_ids.json`:
- On ingress (`_process_peer_file`), seen is checked BEFORE dispatch.
- The set is FIFO-capped at `BUS_SEEN_CAP` (default 10,000).
- Loss of `.seen_ids.json` is non-fatal (treated as empty set; bus
  remains consistent, minor risk of double-dispatch on cold start).

We rejected file-rename-based dedup because rclone sync would interpret
a consumer-side rename as a deletion-conflict, and we have no way to
control how moto4's Termux rclone treats a remote rename.

## 5. Loop guard

The bridge is bidirectional: it both publishes (egress) and consumes
(ingress). Three loop patterns are blocked:

1. **`publish_local` -> `_egress_cb`:** `publish_local` does NOT call
   `_forward_to_local_bus`. Local-bus subscribers see the original data
   via their own direct publishes; the bridge's egress subscription
   picks those up. Disk-write happens exactly once per event.

2. **`_egress_cb` -> `_forward_to_local_bus` -> re-fire `_egress_cb`:** the
   re-broadcast carries `_bridge_origin: "egress"` (NOT "ingress") so
   the loop guard reads `_bridge_origin == "ingress"` and only blocks
   ingress-echo events. (Egress-tagged events mean a fresh publish by
   the bridge; we trust they don't loop because they originate from
   the same device's writer.)

3. **Ingress poll -> `_forward_to_local_bus` -> re-fire `_egress_cb`:**
   the ingress re-broadcast carries `_bridge_origin: "ingress"`. The
   egress callback short-circuits before any disk write.

## 6. TTL + cleanup

- Default TTL is 7 days (`BUS_TTL_SECONDS=604800`).
- The AUTHORING device deletes its own messages past TTL in
  `_cleanup_local_expired`, which runs each poll cycle.
- Deletions propagate via rclone sync naturally.
- `presence.json` is regenerated on each heartbeat tick; consumers
  consider peers stale after `now - last_seen > 600s`.

## 7. Cadence

| Event                       | Cadence                | Why                                       |
|----------------------------|------------------------|-------------------------------------------|
| Local-bus egress           | event-driven (synchronous) | zero latency; same-process pubsub |
| Heartbeat (`presence.json`)| every 5 min            | cheap; lets us detect dead peers           |
| Peer poll (file scan)      | every 30 s             | disk-IO is cheap; rclone is the bottleneck |
| rclone pull/push push      | every 5-10 min (cron)  | rclone invocation cost is high              |
| TTL cleanup                | each poll cycle        | idle CPU until expiry                      |

These cadences are independent. The fastest cadence is the local
event bus (microseconds). The slowest is rclone (minutes). Operators
should size cron accordingly.

## 8. Failure modes

| Failure                                | Effect                                       | Recovery                                     |
|----------------------------------------|----------------------------------------------|----------------------------------------------|
| rclone remote missing                  | `sync_bus_pull.sh` exits 1, logs to stderr    | operator runs `rclone config` then retries    |
| rclone push fails                      | peer misses THIS cycle's messages            | TTL = 7 days absorbs drift; retry on next cron|
| `.seen_ids.json` corrupted             | dispatch may double on next poll             | TTL cleanup + idempotent re-dispatch is OK    |
| `presence.json` older than 600s        | device shows in `diagnostics()` as stale     | designer decides; bridge has no auto-eviction |
| Duplicate `rclone sync` invocation     | idempotent (Writer-Owns)                     | no action needed                             |
| Network partition (carrier NAT change) | events queue locally; rclone sync enqueues   | resumes when connectivity returns            |
| Process crash mid-write                 | atomic rename leaves `.tmp` file            | `.tmp` is excluded from rclone; safe to ignore|

## 9. Operator workflow (production)

Once on penguin (the originator):

```bash
rclone config create outclaw-cloud drive \
    client_id="" client_secret="" scope=drive.file
mkdir -p ~/bleaknarratives/sync_bus
crontab -e
# Add:
# * * * * * /home/bleaknarratives/scripts/sync_bus_pull.sh >> ~/sync_bus.log 2>&1
```

In any OutClaw session on each device:

```python
from OutClaw.outclaw_bridge_bootstrap import bridge_session

with bridge_session() as bundle:
    audit = bundle.orchestrator.audit_text(my_draft)
    bundle.bus.publish_findings(audit.to_dict())
```

That's it. The bridge:
1. Subscribes to all OutClaw channels on the local bus.
2. Writes each event to `<device>/messages/<timestamp>_<message_id>.json`.
3. Rclone cron pushes penguin's subtree to cloud → cloud pushes to
   moto4/a9 → their bridges poll and dispatch.

## 10. Backbone of record

- `SyntaxIntelligence/sync_bridge.py` — implementation.
- `SyntaxIntelligence/sync_bridge_test.py` — egress, ingress, writer-owns,
  TTL, idempotency tests.
- `OutClaw/outclaw_bridge_bootstrap.py` — context-manager wiring + the
  orchestrator facade `OutclawOrchestrator` (round-9 polish).
- `OutClaw/outclaw_tests/test_cross_device_bridge.py` — integration tests.
- `scripts/sync_bus_pull.sh` — rclone two-way sync wrapper.
- `MRD.txt` — the original MT-02 mobil-blocker this design resolves.

## 11. First-time setup (the operator onboarding flow)

When you want to bring a new host onto the swarm (penguin / moto4 / a9 / any
Linux dev box / Windows 10+ dev box), use the four-file launcher set below.
Every host goes through the same five steps; only the launcher shell differs.

| Step | What happens                                                  |
|------|---------------------------------------------------------------|
| 1    | Launcher validates `python3` (or `python` on Windows) + `rclone` are on PATH. |
| 2    | Heavy-lifter `scripts/setup_cross_device.py` checks `rclone listremotes` for `outclaw-cloud:` and skips the OAuth-aware interactive flow if present. |
| 3    | If `outclaw-cloud:` is missing, the heavy-lifter runs `rclone config create outclaw-cloud drive scope=drive.file` non-interactively. Operators who need OAuth-paste should run `rclone config` (the wizard) SEPARATELY first. |
| 4    | Heavy-lifter installs the scheduler entry: cron on Linux/Termux, schtasks on Windows. Idempotent (skip-if-present on POSIX, `/F` flag on Windows). |
| 5    | On Termux, `install_termux_extras` ensures `pkg install cronie termux-api` is present and that crond is actually running (poll-with-pgrep-verified, not just "started cleanly"). |

Launcher files:
- `scripts/setup.sh` — bash (Linux + Termux). Run `./scripts/setup.sh` or `./scripts/setup.sh moto4`.
- `scripts/setup.ps1` — Windows PowerShell 5.1+. Run `.\scripts\setup.ps1` or `.\scripts\setup.ps1 -DeviceId moto4`.
- `scripts/setup.cmd` — Windows cmd.exe. Run `scripts\setup.cmd` or `scripts\setup.cmd moto4`.

Every launcher forwards flags to the heavy-lifter verbatim. Run with `--dry-run` first to validate the local environment without mutating anything:

```bash
./scripts/setup.sh --dry-run --skip-rclone-config
powershell -File scripts\setup.ps1 -DryRun -SkipRcloneConfig
scripts\setup.cmd --dry-run --skip-rclone-config
```

After setup, validate the bridge end-to-end:

```bash
python3 scripts/bleaknarratives_smoke.py            # all 9 checks PASS
python3 scripts/bleaknarratives_smoke.py --no-color  # plain-text output (Windows cmd-friendly)
python3 scripts/bleaknarratives_smoke.py --only=orch # subset
```

The smoke is the canonical "did the bootstrap break anything?" probe. Re-run
it after any bridge-side change.

### Known limits of the current setup wave

- `scripts/sync_bus_pull.sh` is bash-only. The Windows-side schtasks entry fires
  python smoke only; a Windows operator who wants the sync mirror must install
  WSL or run sync interactively. Future: ship a `bleaknarratives_sync.py`
  Python twin that uses `rclone.exe` directly so Windows gets the full
  cron-without-WSL experience.
- `scripts/setup.cmd`'s `%*` flag-forwarding loses double-quotes around
  path-with-spaces arguments; this does not affect the current command set, but
  a future Windows-side flag that takes a path will need explicit re-quoting.
- The rclone `outclaw-cloud` name is hard-coded; multi-carrier setups (e.g.
  staging vs production) would need an `--rclone-remote NAME` flag. Out of
  scope for now.
