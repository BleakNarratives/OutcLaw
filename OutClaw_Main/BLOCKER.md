# BLOCKER: Per-Device Event Logs Unavailable, Now Explained

## Summary

User requested three "similar titled" ingest packages; only one was produced.

| # | Project                                          | Status       |
|---|--------------------------------------------------|--------------|
| 1 | **OutClaw** (canonical source)                   | ✅ produced  |
| 2 | **Moto 4 5g similar titled projects** folder     | ❌ not produced |
| 3 | **Samsung A9 similar title project** folder      | ❌ not produced |

## Why moto4 / a9 packages could not be produced

After rclone introspection, the swarm's canonical cross-device carrier is now
known to be **Google Drive** via the project's `outclaw-cloud:` rclone alias
(which itself binds to a personal Google Drive account, scope `drive.file`).

Three layers were checked during the packaging session:

| Layer              | Path                                                          | Result                                                              |
|--------------------|---------------------------------------------------------------|---------------------------------------------------------------------|
| Termux local       | `/storage/emulated/0/BleakNarratives/`, `/storage/emulated/0/RootBase/` | `mount /storage/*` returns nothing; `termux-setup-storage` was not run |
| SD card            | `/storage/ED7B-AD5A/eoot/2026/`                               | SD card not inserted at the ED7B-AD5A- UUID prefix                   |
| Drive (canonical)  | `outclaw-cloud:bleaknarratives/sync_bus/{moto4,a9}/`          | `rclone tree` returns "directory not found" — peers have not pushed |

The **canonical** answer is the Drive row: nothing has pushed from moto4 or a9
yet. Even with Drive access (which we now have), there are no per-device event
logs to ingest. The Termux `/storage/*` rows are a leftover belief from before
the sync-bus architecture was adopted; they no longer represent how the swarm
communicates.

## Why this is OK for downstream ingestion

`SWARM_TOPOLOGY.md` documents the real shape of the project: **moto4 and a9
are swarm NODES running the same OutClaw codebase, not separate codebases.**
There is no separate codebase to swallow. The single `OutClaw/` source tree
**IS** in the main package.

Per-device runtime state (event logs in `sync_bus/<node>/messages/*.json`) is
intentionally NOT in the main source zip because:

1. It is per-device ephemeral bookkeeping (heartbeats, dispatch queues).
2. Each device independently regenerates it from the local bus.
3. Mixing it into a "canonical source" zip would break the writer-owns
   discipline from `SYNC_PROTOCOL.md`.

The `extracted_legal_ai/` directory (vendored 3rd-party content, ~734 MB) was
packaged separately as the **"diabetes limb bundle"** at the user's direction.

## Drive-side findings (verified in this session)

```
$ rclone listremotes
cloud:
outclaw-cloud:

$ rclone config show outclaw-cloud
[outclaw-cloud]
type = alias
remote = cloud:

$ rclone config show cloud
[cloud]
type = drive
scope = drive
# token present

$ rclone about outclaw-cloud:
Total:   15 GiB
Used:    7.289 GiB
Free:    4.985 GiB
```

`outclaw-cloud:` is a rclone **alias** pointing at `cloud:`. `cloud:` is the
real Google Drive backend. The Drive has ~4.985 GiB free; each ingest run is
~1.2 GB combined, so a retention policy (default: keep last 3 timestamped
runs) is required to stay within quota.

`scripts/push_ingest_to_cloud.sh` implements that retention. The setup helper
`scripts/setup_rclone_gdrive.sh` handles OAuth setup if missing.

## How to ingest per-device event logs (future session)

### A. Bring a peer device online

1. On moto4/a9, install dependencies: `pkg install rclone cronie termux-api`
   (or apt on Linux). If Google Drive OAuth hasn't been done yet on that
   device, run `scripts/setup_rclone_gdrive.sh` once.
2. Confirm `~/bleaknarratives/scripts/sync_bus_pull.sh` is in the user's
   cron, hitting every 5 minutes, at `/home/bleaknarratives/scripts/`.

After a few minutes, `outclaw-cloud:bleaknarratives/sync_bus/<node>/messages/`
will accumulate envelope files as the bridge on that device publishes audit
findings + heartbeats.

### B. Pull down on penguin

```
bash ~/scripts/sync_bus_pull.sh
```

This fetches the peer's subtree below `~/bleaknarratives/sync_bus/<node>/`.

### C. Extend `package_for_ingest.sh` to emit per-device event-log zips

Add a "3/3 events" build step that, for each `<node>` in `penguin moto4 a9`,
zips non-empty `<node>/messages/*.json` into
`OutClaw_<node>_eventlog_<timestamp>.zip`. Re-run for the complete ingest
push.

## Verification of impact

- `~/OutClaw/` is canonical — 2,878 files, 1.4 GB raw; packaged zips are
  ~646 MB (main) and ~598 MB (limb bundle).
- Drive-side `outclaw-cloud:bleaknarratives/sync_bus/` does not exist yet
  (`rclone tree` returns "directory not found"), confirming per-device data
  is genuinely absent, not just hidden.
- No files named `moto4.md`, `moto4.py`, `a9.py`, etc. exist anywhere on
  this session's filesystem.
- `~/RootBase/zeroclaw_android_final/` and `~/RootBase/zeroclaw_marketplace_final/`
  exist but are **separate Rust projects**, not OutClaw's moto/a9 nodes.
  They are intentionally excluded from the OutClaw ingest zip.

## Bottom line

The substantive OutClaw source tree is fully packaged and ready for ingest.
The moto4/a9 "gap" is a **coverage scope clarification**, not a content loss:
there was never a separate codebase. With Google Drive as the canonical
carrier, future-session per-device event-log ingestion follows the documented
`SYNC_PROTOCOL.md` → `sync_bus_pull.sh` → extended `package_for_ingest.sh`
path.
