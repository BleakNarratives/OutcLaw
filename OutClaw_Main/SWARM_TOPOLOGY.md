# OutClaw Swarm Topology

> **TL;DR**: "OutClaw," "Moto 4 5G project," and "Samsung A9 project" are not three
> separate code repositories. They are **the same codebase deployed on three
> devices** as a sync-protocol swarm. One source tree, three runtime nodes.

## 1. The Three Nodes

| Device  | Hardware             | Role in the swarm                                      |
|---------|----------------------|--------------------------------------------------------|
| penguin | Chromebook           | Initiator; owns the project's `outclaw-cloud:` rclone alias (which itself binds to a personal Google Drive account, scope `drive.file`). Pushes the local `bleaknarratives/sync_bus/` subtree to Drive. |
| moto4   | Motorola 4 5G 2024   | TermuxNode; owner of `~/bleaknarratives/sync_bus/moto4/`. Same codebase. |
| a9      | Samsung A9           | TermuxNode; owner of `~/bleaknarratives/sync_bus/a9/`. Same codebase. |

All three run **the same `OutClaw/` codebase**. The only divergence between nodes
is **per-device runtime state** — heartbeat files, outgoing event messages, and
locally-cached discoveries.

## 1b. Carrier: Google Drive via `outclaw-cloud:`

The swarm's only direct cross-device carrier is **Google Drive**, accessed through
an rclone alias:

```
outclaw-cloud:   →  cloud:   (type=drive, scope=drive.file)
```

- `outclaw-cloud:` is an rclone **alias** that points at `cloud:`. `cloud:` is a
  Google Drive backend at `type=drive`. The codebase intentionally uses an alias
  rather than binding Drive directly so the carrier can change (S3, B2, etc.) by
  editing one rclone config line.
- Scope is the tightest one that still allows OutClaw to read/write files in
  folders **it created** (`drive.file`). It cannot see, list, or modify anything
  else on the user's Drive. This is the recommended security posture; the broader
  `drive` scope is reserved for trusted operators only.
- Free space available on this Google Drive account is **~4.985 GiB** at
  last check (15 GiB total minus ~7.289 GiB used); per-device sync_bus files
  must remain tiny so the swarm doesn't crowd out other Drive content.
  Each envelope is < 2 KB; a 7-day TTL window per device is well under 1 MB.
- For belt-and-suspenders against quota exhaustion, sync envelope messages are
  pruned on TTL expiry by `_cleanup_local_expired` (see `SYNC_PROTOCOL.md` §6).

The authoritative description of the cross-device protocol lives in
`OutClaw/SYNC_PROTOCOL.md`; this file restates only what's relevant for ingestion.

## 2. Sync Bus Layout (Writer-Owns)

```
~/bleaknarratives/sync_bus/
├── penguin/
│   ├── presence.json                 ← last-seen heartbeat (penguin-local)
│   ├── .seen_ids.json                ← FIFO dedupe set (per-device, not synced)
│   └── messages/
│       └── <unix_ms>_<message_id>.json
├── moto4/                            ← owned by moto4; penguin must NOT write here
│   ├── presence.json
│   └── messages/
└── a9/                               ← owned by a9; penguin must NOT write here
    ├── presence.json
    └── messages/
```

## 3. What This Means for Ingestion

When you ingest "OutClaw," **ingest one codebase** (this directory tree).

The per-device event streams are bookkeeping for **distributed runtime
coordination**, not separate software products. If you want per-device ingestion
of those streams separately:

1. Pull `~/bleaknarratives/sync_bus/<node>/messages/*.json` per device.
2. Treat each `*.json` as an **event log** — audit findings, bridge heartbeats, etc.
3. Tag each event with `origin_device` (Penguin|moto4|a9) per the wire envelope.
4. Ingest as a separate target from the canonical source tree.

## 4. The moto4 / a9 Storage Paths (Local + Drive)

Two layers of storage were checked. The local Termux/Android paths were not
mounted; the swarm's canonical Google Drive carrier exists but the swarm hasn't
seeded it yet:

| Layer                                         | Where                          | Status in packaging session        |
|-----------------------------------------------|--------------------------------|------------------------------------|
| Termux local (out of session)                 | `/storage/emulated/0/BleakNarratives/`, `/storage/emulated/0/RootBase/` | not mounted                       |
| SD card (out of session)                      | `/storage/ED7B-AD5A/eoot/2026/` | not mounted / not inserted        |
| Drive carrier (canonical, in-session)        | `outclaw-cloud:bleaknarratives/sync_bus/{moto4,a9}/` | directory does not exist yet (no peer devices have pushed) |

Healthy state, once a peer device boots and runs `sync_bus_pull.sh`, is:
`outclaw-cloud:bleaknarratives/sync_bus/<node>/messages/<unix_ms>_<msg_id>.json`
files accumulate per `SYNC_PROTOCOL.md` cadence.

Until that happens, the per-device event-log side of ingest has nothing to pull
**even with Drive access**. See `BLOCKER.md` for the fuller reframing.

## 5. What Is and Is Not Versioned Per-Node

| Type                          | Per-device? | Included in source zip? |
|-------------------------------|-------------|-------------------------|
| Python source modules         | no          | ✅ Yes (one copy)        |
| Documentation (.md, .txt)     | no          | ✅ Yes (one copy)        |
| Test fixtures / scout configs | no          | ✅ Yes (one copy)        |
| `presence.json`               | yes         | ❌ No (excluded as tmp)   |
| `.seen_ids.json`              | yes         | ❌ No                    |
| `messages/*.json` event logs  | yes         | ❌ No                    |
| `~/.outclaw/` runtime cache   | yes         | ❌ No (excluded)         |

## 6. Recovery Path (Future Sessions)

If you want to package per-device event logs in a future session:

1. Run `termux-setup-storage` to grant Termux Android shared-storage permission, **then restart** the session.
2. Insert/mount the SD card whose UUID begins `ED7B-AD5A-`.
3. Run `scripts/package_for_ingest.sh` after the mounts succeed.
4. Extend the script with: for each `<node>` in `penguin moto4 a9`, if
   `~/bleaknarratives/sync_bus/<node>/messages/` exists and is non-empty, emit
   `OutClaw_<node>_eventlog_<timestamp>.zip` containing only the `*.json` files.

Until then, this ingest package contains **exactly one source tree** plus a
separate vendored bundle (`extracted_legal_ai/`) packaged as the
"diabetes limb bundle."
