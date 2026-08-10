# OutClaw compatibility shell

The canonical OutClaw implementation is in [`../OutClaw_Main/`](../OutClaw_Main/).
This root directory is retained only for historical compatibility and should not
receive new feature work.

## Verified acceptance command

```bash
cd /home/bleaknarratives/OutClaw_Main
python3 -m unittest discover -s outclaw_tests -t . -v
python3 outclaw_regression.py
```

The root `OutClaw` package redirects module lookup to `OutClaw_Main` so legacy
`OutClaw.<module>` imports do not select an empty or stale implementation.
