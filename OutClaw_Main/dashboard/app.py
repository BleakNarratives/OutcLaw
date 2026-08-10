"""
OutClaw TUI Dashboard — Main Application

Interactive terminal dashboard for OutClaw citation audit operations.
Provides real-time monitoring, visualization, and control.
"""

import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .orchestrator import DashboardOrchestrator, OperationResult
from .security import SecureInput, SecurityViolation, SecureConfig
from .widgets import (
    CommandLogWidget,
    FindingsTableWidget,
    HelpOverlay,
    QuickActionsWidget,
    RiskMeterWidget,
    StatusWidget,
    create_dashboard_layout,
)


class DashboardApp:
    """
    Main dashboard application.
    
    Manages the TUI layout, widgets, and user interaction loop.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize dashboard application.
        
        Args:
            config_path: Optional path to config.yaml
        """
        self.console = Console()
        self.orchestrator = DashboardOrchestrator()
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Initialize widgets
        self.status_widget = StatusWidget()
        self.risk_widget = RiskMeterWidget()
        self.actions_widget = QuickActionsWidget()
        self.findings_widget = FindingsTableWidget()
        self.log_widget = CommandLogWidget()
        
        # State
        self.running = False
        self.show_help = False
        self.last_result: Optional[OperationResult] = None
        
        # Update initial status
        self._update_status()
    
    def _load_config(self, config_path: Optional[Path]) -> dict:
        """Load configuration from YAML file"""
        if config_path is None:
            # Try default location
            config_path = Path(__file__).parent.parent / 'config.yaml'
        
        if config_path.exists():
            try:
                return SecureConfig.load_yaml(config_path)
            except Exception as e:
                self.console.print(f"[yellow]Warning: Failed to load config: {e}[/]")
                self.console.print("[yellow]Using default configuration[/]")
        
        # Return default config
        return {
            'llm': {'enabled': False},
            'audit': {'block_threshold': 'HIGH_AND_MEDIUM'},
            'terminal': {'colors': True, 'emoji': True},
        }
    
    def _update_status(self) -> None:
        """Update system status"""
        status = self.orchestrator.get_system_status()
        self.status_widget.update(status)
    
    def _render_layout(self) -> Layout:
        """Render the current dashboard layout"""
        layout = create_dashboard_layout()
        
        # Header
        header_text = Text()
        header_text.append("OutClaw", style="bold cyan")
        header_text.append(" — Citation Fraud Audit Dashboard", style="bold white")
        layout["header"].update(
            Panel(
                header_text,
                border_style="cyan",
                padding=(1, 2),
            )
        )
        
        # Widgets
        layout["status"].update(self.status_widget.render())
        layout["risk"].update(self.risk_widget.render())
        layout["actions"].update(self.actions_widget.render())
        layout["findings"].update(self.findings_widget.render())
        layout["log"].update(self.log_widget.render())
        
        # Footer
        footer_text = "[dim]OutClaw v0.3.0 | Press [bold]H[/bold] for help | [bold]Q[/bold] to quit[/]"
        layout["footer"].update(Panel(footer_text, border_style="cyan"))
        
        return layout
    
    def _show_splash(self) -> None:
        """Show startup splash screen"""
        splash = """
[bold cyan]
   ___        _   _____ _               
  / _ \\ _   _| |_/ ____| | __ ___      __
 | | | | | | | __| |   | |/ _` \\ \\ /\\ / /
 | |_| | |_| | |_| |___| | (_| |\\ V  V / 
  \\___/ \\__,_|\\__|\\____|_|\\__,_| \\_/\\_/  
[/]
[bold white]Citation Fraud Audit Dashboard[/]
[dim]v0.3.0 — Lightweight, Intuitive, Secure[/]

[cyan]Initializing...[/]
"""
        self.console.print(splash)
        time.sleep(1)
        self.console.clear()
    
    def _handle_audit_file(self) -> None:
        """Handle audit file action"""
        self.console.clear()
        self.console.print("[bold cyan]Audit File[/]\n")
        
        try:
            file_path = self.console.input("[cyan]Enter file path:[/] ").strip()
            
            if not file_path:
                self.log_widget.add_entry("[yellow]Audit cancelled[/]")
                return
            
            # Validate path
            path = SecureInput.validate_file_path(file_path, must_exist=True)
            
            # Ask about LLM
            use_llm = self.config.get('llm', {}).get('enabled', False)
            if not use_llm:
                llm_input = self.console.input(
                    "[cyan]Enable LLM assistance? (y/N):[/] "
                ).strip().lower()
                use_llm = llm_input == 'y'
            
            self.console.print("\n[cyan]Running audit...[/]")
            
            # Run audit
            result = self.orchestrator.audit_file(str(path), use_llm=use_llm)
            
            if result.success:
                # Update widgets
                summary = result.data.get('summary', {})
                findings = result.data.get('findings', [])
                risk = result.data.get('risk', {})
                
                self.risk_widget.update({**risk, 'summary': summary})
                self.findings_widget.update(findings)
                
                # Log
                high = summary.get('severity_counts', {}).get('HIGH', 0)
                medium = summary.get('severity_counts', {}).get('MEDIUM', 0)
                self.log_widget.add_entry(
                    f"Audited [cyan]{path.name}[/] — {high} HIGH, {medium} MEDIUM"
                )
                
                self.console.print(f"\n[green]✓ Audit complete in {result.elapsed_ms:.0f}ms[/]")
                self.console.print(f"[cyan]Risk Score:[/] {risk.get('score', 0)}/100 ({risk.get('tier', 'UNKNOWN')})")
            else:
                self.log_widget.add_entry(f"[red]Audit failed: {result.error}[/]")
                self.console.print(f"\n[red]✗ Audit failed: {result.error}[/]")
            
            self.last_result = result
            
        except SecurityViolation as e:
            self.log_widget.add_entry(f"[red]Security violation: {e}[/]")
            self.console.print(f"\n[red]✗ Security violation: {e}[/]")
        except Exception as e:
            self.log_widget.add_entry(f"[red]Error: {e}[/]")
            self.console.print(f"\n[red]✗ Error: {e}[/]")
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
    
    def _handle_full_pipeline(self) -> None:
        """Handle full pipeline action"""
        self.console.clear()
        self.console.print("[bold cyan]Full Pipeline (Enhance)[/]\n")
        
        try:
            file_path = self.console.input("[cyan]Enter file path:[/] ").strip()
            
            if not file_path:
                self.log_widget.add_entry("[yellow]Pipeline cancelled[/]")
                return
            
            # Validate path
            path = SecureInput.validate_file_path(file_path, must_exist=True)
            
            # Configuration
            use_llm = self.config.get('llm', {}).get('enabled', False)
            enable_aura = self.config.get('aura', {}).get('enabled', True)
            
            self.console.print("\n[cyan]Running full pipeline...[/]")
            self.console.print("[dim]• Citation audit[/]")
            self.console.print("[dim]• Aura pattern detection[/]")
            self.console.print("[dim]• Risk scoring[/]")
            self.console.print("[dim]• Citation discovery[/]\n")
            
            # Run full audit
            result = self.orchestrator.full_audit(
                str(path),
                use_llm=use_llm,
                enable_aura=enable_aura,
            )
            
            if result.success:
                # Update widgets
                citation = result.data.get('citation_audit', {})
                risk = result.data.get('risk', {})
                verdict = result.data.get('verdict', 'UNKNOWN')
                
                summary = citation.get('summary', {})
                findings = citation.get('findings', [])
                
                self.risk_widget.update({**risk, 'summary': summary})
                self.findings_widget.update(findings)
                
                # Log
                self.log_widget.add_entry(
                    f"Full pipeline on [cyan]{path.name}[/] — {verdict}"
                )
                
                self.console.print(f"\n[green]✓ Pipeline complete in {result.elapsed_ms:.0f}ms[/]")
                self.console.print(f"[cyan]Verdict:[/] {verdict}")
            else:
                self.log_widget.add_entry(f"[red]Pipeline failed: {result.error}[/]")
                self.console.print(f"\n[red]✗ Pipeline failed: {result.error}[/]")
            
            self.last_result = result
            
        except SecurityViolation as e:
            self.log_widget.add_entry(f"[red]Security violation: {e}[/]")
            self.console.print(f"\n[red]✗ Security violation: {e}[/]")
        except Exception as e:
            self.log_widget.add_entry(f"[red]Error: {e}[/]")
            self.console.print(f"\n[red]✗ Error: {e}[/]")
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
    
    def _handle_lookup_citation(self) -> None:
        """Handle citation lookup action"""
        self.console.clear()
        self.console.print("[bold cyan]Lookup Citation[/]\n")
        
        try:
            citation = self.console.input("[cyan]Enter citation:[/] ").strip()
            
            if not citation:
                self.log_widget.add_entry("[yellow]Lookup cancelled[/]")
                return
            
            # Validate citation
            citation = SecureInput.validate_citation(citation)
            
            self.console.print(f"\n[cyan]Looking up: {citation}...[/]")
            
            # Lookup
            result = self.orchestrator.lookup_citation(citation)
            
            if result.success:
                case = result.data.get('case', {})
                name = case.get('name', citation)
                court = case.get('court', 'Unknown')
                
                self.console.print(f"\n[green]✓ Found[/]")
                self.console.print(f"[cyan]Case:[/] {name}")
                self.console.print(f"[cyan]Court:[/] {court}")
                
                self.log_widget.add_entry(
                    f"Lookup: [cyan]{citation}[/] — Found ({name})"
                )
            else:
                self.console.print(f"\n[yellow]⚠ Not found[/]")
                self.log_widget.add_entry(f"Lookup: [cyan]{citation}[/] — Not found")
            
            self.last_result = result
            
        except SecurityViolation as e:
            self.log_widget.add_entry(f"[red]Security violation: {e}[/]")
            self.console.print(f"\n[red]✗ Security violation: {e}[/]")
        except Exception as e:
            self.log_widget.add_entry(f"[red]Error: {e}[/]")
            self.console.print(f"\n[red]✗ Error: {e}[/]")
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
    
    def _handle_command(self, command: str) -> bool:
        """
        Handle user command.
        
        Args:
            command: Command character
            
        Returns:
            True to continue running, False to quit
        """
        command = command.lower().strip()
        
        if command == 'q':
            return False
        elif command == 'h':
            self.show_help = True
        elif command == 'r':
            self._update_status()
            self.log_widget.add_entry("Refreshed dashboard")
        elif command == '1':
            self._handle_audit_file()
        elif command == '2':
            self._handle_full_pipeline()
        elif command == '3':
            self._handle_lookup_citation()
        elif command == '4':
            self.console.print("[yellow]FOIA generation coming soon...[/]")
            time.sleep(1)
        elif command == '5':
            self.console.print("[yellow]IRAC analysis coming soon...[/]")
            time.sleep(1)
        elif command == '6':
            self.console.print("[yellow]Discovery view coming soon...[/]")
            time.sleep(1)
        elif command == 'c':
            self.findings_widget.findings = []
            self.log_widget.add_entry("Cleared findings table")
        
        return True
    
    def run(self) -> None:
        """Run the dashboard application"""
        self._show_splash()
        
        self.running = True
        
        try:
            while self.running:
                # Show help overlay if requested
                if self.show_help:
                    self.console.clear()
                    self.console.print(HelpOverlay.render())
                    self.console.input("\n[dim]Press Enter to continue...[/]")
                    self.show_help = False
                    continue
                
                # Render dashboard
                self.console.clear()
                layout = self._render_layout()
                self.console.print(layout)
                
                # Get user input
                try:
                    self.console.print("\n[bold cyan]Enter command:[/] ", end="")
                    command = input().strip()
                    
                    if command:
                        # Validate command
                        try:
                            command = SecureInput.validate_command(command)
                            self.running = self._handle_command(command)
                        except SecurityViolation as e:
                            self.log_widget.add_entry(f"[red]Invalid command: {e}[/]")
                            self.console.print(f"\n[red]✗ Invalid command: {e}[/]")
                            time.sleep(1)
                
                except KeyboardInterrupt:
                    self.running = False
                except EOFError:
                    self.running = False
        
        except KeyboardInterrupt:
            pass
        finally:
            self.console.clear()
            self.console.print("\n[cyan]OutClaw Dashboard closed.[/]\n")


def main() -> int:
    """Main entry point for dashboard"""
    try:
        app = DashboardApp()
        app.run()
        return 0
    except Exception as e:
        console = Console()
        console.print(f"\n[red]Fatal error: {e}[/]\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
