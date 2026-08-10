# OutClaw Dashboard — Quick Start Guide

## Installation

### 1. Install Dependencies

```bash
cd /home/bleaknarratives/OutClaw
pip install -r requirements-dashboard.txt
```

### 2. Make Dashboard Executable

```bash
chmod +x outclaw_dashboard.py
```

### 3. Run Dashboard

```bash
# Direct execution
python3 outclaw_dashboard.py

# Or add to CLI
python3 outclaw_cli.py dashboard  # (after integration)
```

## Quick Test

Test the dashboard with a sample file:

```bash
# Create a test file
cat > /tmp/test_legal.txt << 'EOF'
This motion cites Miranda v. Arizona, 384 U.S. 436 (1966), which established
the requirement for police to inform suspects of their rights.

We also reference 42 U.S.C. § 1983, the civil rights statute that provides
a cause of action for constitutional violations.
EOF

# Run dashboard and test audit
python3 outclaw_dashboard.py
# Press '1' for Audit File
# Enter: /tmp/test_legal.txt
# Press 'N' for LLM (or 'Y' if free cloud keys are configured)
# Note: no local models needed — LLM uses free cloud providers only.
```

## Features

### 1. Audit File (Press '1')
- Validates file path for security
- Runs citation audit
- Displays risk score and findings
- Updates dashboard widgets in real-time

### 2. Full Pipeline (Press '2')
- Citation audit
- Aura pattern detection
- Risk scoring
- Citation discovery
- Comprehensive verdict

### 3. Lookup Citation (Press '3')
- Queries CourtListener API
- Displays case information
- Option to expand seed registry

### 4. Generate FOIA (Press '4')
- Coming soon: FOIA request generator
- Jurisdiction-specific templates

### 5. IRAC Analysis (Press '5')
- Coming soon: Legal question analysis
- Issue, Rule, Analysis, Conclusion format

### 6. View Discoveries (Press '6')
- Coming soon: Citation discovery viewer
- High/medium/low confidence grouping

### Navigation
- **R** — Refresh all widgets
- **H** — Show help overlay
- **C** — Clear findings table
- **Q** — Quit dashboard

## Security Features

### Input Validation
- All file paths validated against whitelist patterns
- Path traversal prevention (no `../` allowed)
- Maximum input lengths enforced
- Dangerous characters blocked

### Sandboxing
- File operations restricted to allowed directories
- No shell command execution from user input
- Safe YAML config loading only
- Rate limiting on API calls

### Monitoring
- All operations logged with timestamps
- Security violations logged and blocked
- PII sanitization in error messages

## Configuration

Edit `config.yaml` to customize:

```yaml
# Enable LLM features (cloud cascade — no local models)
cascade:
  enabled: true
# Free cloud keys are read from the environment, e.g.:
#   GOOGLE_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, ...

# Dashboard appearance
terminal:
  colors: true
  emoji: true
  dashboard_width: 70

# Security settings
safety:
  require_ack: true
  allowed_intents:
    - section_1983_complaint
    - criminal_appeal
    # ... add more as needed
```

## Troubleshooting

### Dashboard won't start
```bash
# Check dependencies
pip list | grep rich
pip list | grep pyyaml

# Reinstall if needed
pip install --upgrade rich pyyaml
```

### "Module not found" errors
```bash
# Ensure OutClaw is in Python path
export PYTHONPATH="/home/bleaknarratives/OutClaw:$PYTHONPATH"

# Or run from OutClaw directory
cd /home/bleaknarratives/OutClaw
python3 outclaw_dashboard.py
```

### LLM features not working
```bash
# LLM features use free CLOUD providers — no local models needed.
# Check that cascade is enabled and keys are set:
#   Edit config.yaml: cascade.enabled = true
#   export GOOGLE_API_KEY=... GROQ_API_KEY=... OPENROUTER_API_KEY=...

# See provider readiness:
python3 outclaw_cli.py cascade
```

### CourtListener lookups failing
- Check internet connection
- Verify API is accessible: `curl https://www.courtlistener.com/api/rest/v4/`
- Rate limiting may apply (max 3 requests/second)

## Performance Tips

1. **Disable LLM for faster audits** (if not needed)
   - Set `llm.enabled: false` in config.yaml
   - Or press 'N' when prompted

2. **Reduce widget refresh rate** (if terminal is slow)
   - Edit `app.py`: Change `refresh_per_second=4` to `2`

3. **Clear findings regularly** (press 'C')
   - Keeps table widget responsive
   - Reduces memory usage

4. **Use file monitoring sparingly**
   - Only enable for active development
   - Can impact performance on large directories

## Next Steps

1. **Integrate with existing CLI**
   - Add `dashboard` subcommand to `outclaw_cli.py`
   - Share configuration and state

2. **Add file browser widget**
   - Navigate filesystem visually
   - Show risk scores for multiple files

3. **Implement batch operations**
   - Audit entire directories
   - Compare multiple reports

4. **Add export functionality**
   - Save findings to CSV/JSON
   - Generate summary reports

5. **Team collaboration features**
   - Share audit results via URL
   - Webhook notifications

## Support

For issues or questions:
- Check `DASHBOARD_DESIGN.md` for architecture details
- Review security layer in `dashboard/security.py`
- See widget documentation in `dashboard/widgets.py`

---

**Status**: ✅ Core dashboard implemented and ready for testing
**Version**: 0.3.0
**Last Updated**: 2026-07-27
