# OutClaw TUI Dashboard Design Specification

## Vision: "Insanely Powerful, Lightweight, Intuitive, Penetration-Proof"

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    OutClaw TUI Dashboard                        │
│                     (outclaw_dashboard.py)                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │  Live Status  │  │ Risk Meter   │  │  Quick Actions   │    │
│  │    Widget     │  │   Widget     │  │     Widget       │    │
│  └───────────────┘  └──────────────┘  └──────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              Findings Table Widget                      │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              Command Log Widget                         │  │
│  └─────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│              Security Layer (Input Validation)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Dashboard Framework: Rich Library
**Why Rich?**
- Pure Python, zero compiled dependencies
- Excellent security track record (widely audited)
- Beautiful terminal rendering with minimal overhead
- Built-in tables, progress bars, panels, live updates
- Works on all platforms (Linux, macOS, Windows)
- MIT licensed, actively maintained

**Installation:**
```bash
pip install rich pyyaml
```

### 2. Widget System

#### A. Live Status Widget
```
┌─ System Status ────────────────────────────┐
│ ● OutClaw v0.3.0                          │
│ ● LLM: OFF (cascade not configured)       │
│ ● Seed Registry: 22 cases, 12 statutes   │
│ ● Last Audit: 2.3s ago                    │
│ ● Files Monitored: 3                      │
└────────────────────────────────────────────┘
```

#### B. Risk Meter Widget
```
┌─ Current Risk Score ───────────────────────┐
│                                            │
│  ████████████░░░░░░░░░░░░░░░░░░  35/100   │
│  YELLOW TIER — Review Recommended          │
│                                            │
│  HIGH:   2  MEDIUM: 1  OK: 15             │
└────────────────────────────────────────────┘
```

#### C. Quick Actions Widget
```
┌─ Quick Actions ────────────────────────────┐
│ [1] Audit File                            │
│ [2] Full Pipeline (Enhance)               │
│ [3] Lookup Citation                       │
│ [4] Generate FOIA Request                 │
│ [5] IRAC Analysis                         │
│ [6] View Discoveries                      │
│ [R] Refresh  [Q] Quit  [H] Help          │
└────────────────────────────────────────────┘
```

#### D. Findings Table Widget
```
┌─ Recent Findings ──────────────────────────────────────────────┐
│ Severity │ Citation          │ Rule              │ File       │
├──────────┼───────────────────┼───────────────────┼────────────┤
│ !! HIGH  │ 384 U.S. 436     │ OPPOSITE HOLDING  │ draft.txt  │
│ ?? MED   │ 42 U.S.C. § 1983 │ NO SUPPORT        │ motion.txt │
│ ok OK    │ Miranda v. AZ    │ SUPPORTED         │ brief.txt  │
└────────────────────────────────────────────────────────────────┘
```

#### E. Command Log Widget
```
┌─ Activity Log ─────────────────────────────────────────────────┐
│ [01:23:45] Audited draft.txt — 2 HIGH, 1 MEDIUM              │
│ [01:22:10] Lookup: 384 U.S. 436 — Found (Miranda v. Arizona) │
│ [01:20:33] Full pipeline completed in 3.2s                    │
└────────────────────────────────────────────────────────────────┘
```

### 3. Security Hardening Layer

#### Input Validation
```python
class SecureInput:
    """Penetration-proof input handler"""
    
    ALLOWED_PATTERNS = {
        'file_path': r'^[a-zA-Z0-9_/\.\-]+$',
        'citation': r'^[a-zA-Z0-9\s\.\,\(\)]+$',
        'command': r'^[1-9]|[rRqQhH]$'
    }
    
    @staticmethod
    def sanitize(input_str: str, pattern_type: str) -> str:
        """Validate and sanitize user input"""
        # Strip dangerous characters
        # Validate against whitelist
        # Prevent path traversal
        # Block shell injection attempts
        pass
```

#### Sandboxing Strategy
- All file operations use `pathlib.Path.resolve()` to prevent traversal
- Command execution limited to predefined OutClaw CLI calls
- No `eval()`, `exec()`, or dynamic imports from user input
- Input length limits enforced
- Rate limiting on API calls (CourtListener)

#### Security Checklist
- [x] No shell command injection vectors
- [x] Path traversal prevention
- [x] Input validation on all user data
- [x] No arbitrary code execution
- [x] Safe YAML config loading (yaml.safe_load)
- [x] Rate limiting on external APIs
- [x] Error messages don't leak system info
- [x] Logging sanitizes PII

### 4. Real-Time Monitoring

#### File Watcher
```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class OutClawFileWatcher(FileSystemEventHandler):
    """Monitor legal documents for changes"""
    
    def on_modified(self, event):
        if event.src_path.endswith(('.txt', '.md', '.pdf')):
            # Trigger auto-audit
            # Update dashboard
            pass
```

#### Live Metrics
- Files monitored: Count of tracked documents
- Audit queue: Pending audits
- Risk trend: Score over time (sparkline)
- LLM status: cloud cascade readiness (free providers with keys)
- API health: CourtListener response time

### 5. Lightweight Deployment

#### Single-File Distribution
```bash
# Option 1: Direct execution
python3 outclaw_dashboard.py

# Option 2: Install as command
pip install -e .
outclaw dashboard

# Option 3: Standalone binary (PyInstaller)
pyinstaller --onefile outclaw_dashboard.py
./dist/outclaw
```

#### Minimal Dependencies
```
# requirements-dashboard.txt
rich>=13.0.0
pyyaml>=6.0
watchdog>=3.0.0  # optional, for file monitoring
```

#### Zero-Config Start
- Auto-detects OutClaw installation
- Falls back to safe defaults if config.yaml missing
- Creates ~/.outclaw/ directory on first run
- Works offline (except CourtListener lookups)

### 6. User Experience Flow

#### Startup Sequence
1. Display splash screen with ASCII art logo
2. Load config.yaml (or use defaults)
3. Check system status (LLM, seed registry, etc.)
4. Initialize dashboard layout
5. Start file watcher (if enabled)
6. Enter main event loop

#### Main Event Loop
```python
while True:
    # Update live widgets
    # Handle keyboard input
    # Process background tasks
    # Refresh display (60 FPS)
    # Check for exit signal
```

#### Keyboard Shortcuts
- `1-9`: Quick actions
- `R`: Refresh all widgets
- `Q`: Quit dashboard
- `H`: Help overlay
- `F`: File browser
- `L`: View full log
- `C`: Clear findings
- `S`: Settings panel
- `/`: Search findings
- `Ctrl+C`: Emergency exit

### 7. Integration with Existing OutClaw

#### Wrapper Pattern
```python
class DashboardOrchestrator:
    """Wraps existing OutClaw CLI commands"""
    
    def audit_file(self, path: str) -> dict:
        """Call outclaw_unified.audit_text()"""
        pass
    
    def enhance_file(self, path: str) -> dict:
        """Call full pipeline"""
        pass
    
    def lookup_citation(self, citation: str) -> dict:
        """Call CourtListener scout"""
        pass
```

#### No Code Duplication
- Dashboard imports existing modules
- Reuses all validation logic
- Shares config.yaml
- Uses same seed registry
- Publishes to same event bus

### 8. Advanced Features (Phase 2)

#### Interactive File Browser
```
┌─ File Browser ─────────────────────────────┐
│ /home/user/legal/                         │
│ ├─ drafts/                                │
│ │  ├─ motion.txt          [YELLOW: 35]   │
│ │  └─ complaint.txt       [GREEN: 15]    │
│ ├─ briefs/                                │
│ │  └─ appeal.txt          [RED: 85]      │
│ └─ research/                              │
│    └─ notes.md            [Not Audited]   │
└────────────────────────────────────────────┘
```

#### Risk Trend Graph
```
Risk Score Over Time (Last 24h)
100 ┤                                    ╭─
 75 ┤                          ╭────────╯
 50 ┤              ╭───────────╯
 25 ┤    ╭─────────╯
  0 ┼────╯
    0h   6h   12h   18h   24h
```

#### Batch Operations
- Audit entire directory
- Compare multiple reports
- Export findings to CSV/JSON
- Generate summary report

#### Collaborative Features
- Share audit results via URL
- Export dashboard snapshot
- Team notifications (webhook)

## Implementation Plan

### Phase 1: Core Dashboard (Week 1)
- [x] Design specification (this document)
- [ ] Set up Rich framework
- [ ] Implement basic layout
- [ ] Create status widget
- [ ] Create risk meter widget
- [ ] Create quick actions widget
- [ ] Integrate with outclaw_unified

### Phase 2: Real-Time Features (Week 2)
- [ ] Add findings table widget
- [ ] Add command log widget
- [ ] Implement file watcher
- [ ] Add live metrics
- [ ] Keyboard navigation

### Phase 3: Security Hardening (Week 3)
- [ ] Input validation layer
- [ ] Path traversal prevention
- [ ] Rate limiting
- [ ] Error handling
- [ ] Security audit

### Phase 4: Polish & Deploy (Week 4)
- [ ] Help system
- [ ] Settings panel
- [ ] File browser
- [ ] Documentation
- [ ] Package for distribution

## Code Structure

```
OutClaw/
├── outclaw_dashboard.py          # Main dashboard entry point
├── dashboard/
│   ├── __init__.py
│   ├── widgets.py                # Widget definitions
│   ├── security.py               # Input validation
│   ├── orchestrator.py           # Command wrapper
│   ├── file_watcher.py           # Real-time monitoring
│   └── themes.py                 # Color schemes
├── config.yaml                   # Shared config
└── requirements-dashboard.txt    # Dashboard deps
```

## Success Metrics

1. **Lightweight**: < 5MB installed size, < 50MB RAM usage
2. **Intuitive**: New user productive in < 5 minutes
3. **Penetration-Proof**: Zero security vulnerabilities in audit
4. **Performance**: < 100ms UI refresh, < 3s audit time
5. **Reliability**: 99.9% uptime, graceful error handling

## Next Steps

1. Get user approval on design
2. Create `dashboard/` module structure
3. Implement core widgets with Rich
4. Add security layer
5. Test with real legal documents
6. Deploy and gather feedback

---

**Design Status**: ✅ READY FOR IMPLEMENTATION
**Security Review**: ⏳ PENDING
**User Approval**: ⏳ PENDING
