"""
Dashboard Widgets — Rich-based UI Components

Provides reusable widget components for the OutClaw TUI dashboard.
Each widget is self-contained and can be updated independently.
"""

from datetime import datetime
from typing import Optional

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text


class StatusWidget:
    """
    System status widget showing OutClaw version, LLM status, and seed registry.
    
    Example:
        ┌─ System Status ────────────────────────────┐
        │ ● OutClaw v0.3.0                          │
        │ ● LLM: OFF (cascade not configured)       │
        │ ● Seed Registry: 22 cases, 12 statutes   │
        │ ● Last Audit: 2.3s ago                    │
        └────────────────────────────────────────────┘
    """
    
    def __init__(self):
        self.version = "0.3.0"
        self.llm_available = False
        self.seed_cases = 0
        self.seed_statutes = 0
        self.last_audit_time: Optional[float] = None
        self.files_monitored = 0
    
    def update(self, status: dict) -> None:
        """Update widget with new status data"""
        self.llm_available = status.get('llm_available', False)
        seed = status.get('seed_registry', {})
        self.seed_cases = seed.get('cases', 0)
        self.seed_statutes = seed.get('statutes', 0)
        self.files_monitored = status.get('files_monitored', 0)
    
    def render(self) -> Panel:
        """Render the status widget"""
        lines = []
        
        # Version
        lines.append(f"[bold cyan]●[/] OutClaw v{self.version}")
        
        # LLM status (cloud cascade only — no local inference by design)
        llm_status = "[green]ON[/]" if self.llm_available else "[dim]OFF (cascade not configured)[/]"
        lines.append(f"[bold cyan]●[/] LLM: {llm_status}")
        
        # Seed registry
        lines.append(
            f"[bold cyan]●[/] Seed Registry: {self.seed_cases} cases, {self.seed_statutes} statutes"
        )
        
        # Last audit
        if self.last_audit_time:
            elapsed = datetime.now().timestamp() - self.last_audit_time
            if elapsed < 60:
                time_str = f"{elapsed:.1f}s ago"
            elif elapsed < 3600:
                time_str = f"{elapsed/60:.1f}m ago"
            else:
                time_str = f"{elapsed/3600:.1f}h ago"
            lines.append(f"[bold cyan]●[/] Last Audit: {time_str}")
        
        # Files monitored
        if self.files_monitored > 0:
            lines.append(f"[bold cyan]●[/] Files Monitored: {self.files_monitored}")
        
        content = "\n".join(lines)
        return Panel(content, title="[bold]System Status[/]", border_style="cyan")


class RiskMeterWidget:
    """
    Risk score visualization widget with color-coded meter.
    
    Example:
        ┌─ Current Risk Score ───────────────────────┐
        │                                            │
        │  ████████████░░░░░░░░░░░░░░░░░░  35/100   │
        │  YELLOW TIER — Review Recommended          │
        │                                            │
        │  HIGH:   2  MEDIUM: 1  OK: 15             │
        └────────────────────────────────────────────┘
    """
    
    def __init__(self):
        self.score = 0
        self.tier = "UNKNOWN"
        self.high_count = 0
        self.medium_count = 0
        self.ok_count = 0
        self.safe_to_file = False
    
    def update(self, risk_data: dict) -> None:
        """Update widget with new risk data"""
        self.score = risk_data.get('score', 0)
        self.tier = risk_data.get('tier', 'UNKNOWN')
        self.safe_to_file = risk_data.get('safe_to_file', False)
        
        # Extract severity counts from summary if available
        summary = risk_data.get('summary', {})
        if summary:
            counts = summary.get('severity_counts', {})
            self.high_count = counts.get('HIGH', 0)
            self.medium_count = counts.get('MEDIUM', 0)
            self.ok_count = counts.get('OK', 0)
    
    def render(self) -> Panel:
        """Render the risk meter widget"""
        # Color based on tier
        tier_colors = {
            'GREEN': 'green',
            'YELLOW': 'yellow',
            'ORANGE': 'bright_yellow',
            'RED': 'red',
            'UNKNOWN': 'white',
        }
        color = tier_colors.get(self.tier, 'white')
        
        # Progress bar
        bar_width = 30
        filled = int((self.score / 100) * bar_width)
        empty = bar_width - filled
        bar = f"[{color}]{'█' * filled}[/][dim]{'░' * empty}[/]"
        
        # Tier message
        tier_messages = {
            'GREEN': 'Safe to File',
            'YELLOW': 'Review Recommended',
            'ORANGE': 'Significant Issues',
            'RED': 'DO NOT FILE',
            'UNKNOWN': 'Not Analyzed',
        }
        message = tier_messages.get(self.tier, 'Unknown Status')
        
        lines = [
            "",
            f"  {bar}  [{color}]{self.score}/100[/]",
            f"  [{color}]{self.tier} TIER[/] — {message}",
            "",
            f"  [red]HIGH:[/]   {self.high_count}  [yellow]MEDIUM:[/] {self.medium_count}  [green]OK:[/] {self.ok_count}",
        ]
        
        content = "\n".join(lines)
        return Panel(content, title="[bold]Current Risk Score[/]", border_style=color)


class QuickActionsWidget:
    """
    Quick action menu widget with keyboard shortcuts.
    
    Example:
        ┌─ Quick Actions ────────────────────────────┐
        │ [1] Audit File                            │
        │ [2] Full Pipeline (Enhance)               │
        │ [3] Lookup Citation                       │
        │ [4] Generate FOIA Request                 │
        │ [5] IRAC Analysis                         │
        │ [6] View Discoveries                      │
        │ [R] Refresh  [Q] Quit  [H] Help          │
        └────────────────────────────────────────────┘
    """
    
    ACTIONS = [
        ("1", "Audit File"),
        ("2", "Full Pipeline (Enhance)"),
        ("3", "Lookup Citation"),
        ("4", "Generate FOIA Request"),
        ("5", "IRAC Analysis"),
        ("6", "View Discoveries"),
    ]
    
    SHORTCUTS = [
        ("R", "Refresh"),
        ("Q", "Quit"),
        ("H", "Help"),
    ]
    
    def render(self) -> Panel:
        """Render the quick actions widget"""
        lines = []
        
        # Main actions
        for key, label in self.ACTIONS:
            lines.append(f"[bold cyan][{key}][/] {label}")
        
        # Shortcuts (on one line)
        shortcuts = "  ".join(
            f"[bold cyan][{key}][/] {label}" for key, label in self.SHORTCUTS
        )
        lines.append(shortcuts)
        
        content = "\n".join(lines)
        return Panel(content, title="[bold]Quick Actions[/]", border_style="cyan")


class FindingsTableWidget:
    """
    Table widget showing recent audit findings.
    
    Example:
        ┌─ Recent Findings ──────────────────────────────────────────────┐
        │ Severity │ Citation          │ Rule              │ File       │
        ├──────────┼───────────────────┼───────────────────┼────────────┤
        │ !! HIGH  │ 384 U.S. 436     │ OPPOSITE HOLDING  │ draft.txt  │
        │ ?? MED   │ 42 U.S.C. § 1983 │ NO SUPPORT        │ motion.txt │
        │ ok OK    │ Miranda v. AZ    │ SUPPORTED         │ brief.txt  │
        └────────────────────────────────────────────────────────────────┘
    """
    
    def __init__(self):
        self.findings: list[dict] = []
        self.max_findings = 10
    
    def update(self, findings: list[dict]) -> None:
        """Update widget with new findings"""
        self.findings = findings[-self.max_findings:]
    
    def render(self) -> Panel:
        """Render the findings table widget"""
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Severity", style="bold", width=10)
        table.add_column("Citation", width=20)
        table.add_column("Rule", width=20)
        table.add_column("File", width=15)
        
        if not self.findings:
            table.add_row("[dim]No findings yet[/]", "", "", "")
        else:
            for finding in self.findings:
                severity = finding.get('severity', 'UNKNOWN')
                citation = finding.get('citation', 'N/A')[:20]
                rule = finding.get('rule', 'N/A')[:20]
                file_path = finding.get('file_path', 'N/A')
                
                # Extract filename only
                if '/' in file_path:
                    file_path = file_path.split('/')[-1]
                file_path = file_path[:15]
                
                # Color-code severity
                if severity == 'HIGH':
                    sev_display = "[red]!! HIGH[/]"
                elif severity == 'MEDIUM':
                    sev_display = "[yellow]?? MED[/]"
                else:
                    sev_display = "[green]ok OK[/]"
                
                table.add_row(sev_display, citation, rule, file_path)
        
        return Panel(table, title="[bold]Recent Findings[/]", border_style="cyan")


class CommandLogWidget:
    """
    Activity log widget showing recent operations.
    
    Example:
        ┌─ Activity Log ─────────────────────────────────────────────────┐
        │ [01:23:45] Audited draft.txt — 2 HIGH, 1 MEDIUM              │
        │ [01:22:10] Lookup: 384 U.S. 436 — Found (Miranda v. Arizona) │
        │ [01:20:33] Full pipeline completed in 3.2s                    │
        └────────────────────────────────────────────────────────────────┘
    """
    
    def __init__(self):
        self.log_entries: list[str] = []
        self.max_entries = 5
    
    def add_entry(self, message: str) -> None:
        """Add a new log entry"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[dim][{timestamp}][/] {message}"
        self.log_entries.append(entry)
        if len(self.log_entries) > self.max_entries:
            self.log_entries.pop(0)
    
    def render(self) -> Panel:
        """Render the command log widget"""
        if not self.log_entries:
            content = "[dim]No activity yet[/]"
        else:
            content = "\n".join(self.log_entries)
        
        return Panel(content, title="[bold]Activity Log[/]", border_style="cyan")


class ProgressWidget:
    """
    Progress indicator for long-running operations.
    
    Shows a spinner and progress bar during audits, lookups, etc.
    """
    
    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )
        self.task_id: Optional[int] = None
    
    def start(self, description: str, total: int = 100) -> None:
        """Start a new progress task"""
        if self.task_id is not None:
            self.progress.remove_task(self.task_id)
        self.task_id = self.progress.add_task(description, total=total)
    
    def update(self, advance: int = 1) -> None:
        """Update progress"""
        if self.task_id is not None:
            self.progress.update(self.task_id, advance=advance)
    
    def complete(self) -> None:
        """Complete the current task"""
        if self.task_id is not None:
            self.progress.update(self.task_id, completed=100)
            self.task_id = None
    
    def render(self) -> Panel:
        """Render the progress widget"""
        return Panel(self.progress, title="[bold]Processing[/]", border_style="cyan")


class HelpOverlay:
    """
    Help overlay showing keyboard shortcuts and usage.
    """
    
    @staticmethod
    def render() -> Panel:
        """Render the help overlay"""
        help_text = """
[bold cyan]OutClaw Dashboard — Keyboard Shortcuts[/]

[bold]Quick Actions:[/]
  [cyan]1[/] — Audit a file for citation fraud
  [cyan]2[/] — Run full pipeline (audit + aura + benford + risk)
  [cyan]3[/] — Look up a citation in CourtListener
  [cyan]4[/] — Generate FOIA/Open Records request
  [cyan]5[/] — Perform IRAC legal analysis
  [cyan]6[/] — View discovered citations

[bold]Navigation:[/]
  [cyan]R[/] — Refresh all widgets
  [cyan]F[/] — Open file browser
  [cyan]L[/] — View full activity log
  [cyan]C[/] — Clear findings table
  [cyan]S[/] — Open settings panel
  [cyan]/[/] — Search findings

[bold]System:[/]
  [cyan]H[/] — Show this help
  [cyan]Q[/] — Quit dashboard
  [cyan]Ctrl+C[/] — Emergency exit

[bold]Tips:[/]
  • All file paths are validated for security
  • LLM features use free cloud providers (no local models needed)
  • CourtListener lookups require internet connection
  • Press any key to close this help overlay
"""
        return Panel(
            help_text.strip(),
            title="[bold]Help[/]",
            border_style="cyan",
            padding=(1, 2),
        )


def create_dashboard_layout() -> Layout:
    """
    Create the main dashboard layout structure.
    
    Returns:
        Rich Layout object with nested panels
    """
    layout = Layout()
    
    # Split into header and body
    layout.split_column(
        Layout(name="header", size=7),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    
    # Split body into left and right
    layout["body"].split_row(
        Layout(name="left", ratio=2),
        Layout(name="right", ratio=1),
    )
    
    # Split left into top and bottom
    layout["left"].split_column(
        Layout(name="findings", ratio=2),
        Layout(name="log", ratio=1),
    )
    
    # Split right into status, risk, and actions
    layout["right"].split_column(
        Layout(name="status", size=8),
        Layout(name="risk", size=10),
        Layout(name="actions", size=12),
    )
    
    return layout
