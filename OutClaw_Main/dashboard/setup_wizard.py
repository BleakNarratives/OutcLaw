"""
Setup Wizard — Interactive Configuration Generator

Guides users through initial setup and config.yaml customization.
Handles platform detection, dependency checking, and personalized configuration.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from .platform import (
    IntegrationHelper,
    PlatformDetector,
    ensure_config_dir,
    get_platform,
)


class SetupWizard:
    """
    Interactive setup wizard for OutClaw dashboard.
    
    Guides users through:
    - Platform detection
    - Dependency checking
    - Configuration customization
    - Integration setup (rclone, ssh, printing, scanning)
    - Initial timeline/workflow setup
    """
    
    def __init__(self):
        self.console = Console()
        self.config: Dict[str, Any] = {}
        self.platform = get_platform()
        self.config_dir = ensure_config_dir()
        self.config_path = self.config_dir / 'config.yaml'
    
    def run(self) -> Dict[str, Any]:
        """
        Run the complete setup wizard.
        
        Returns:
            Generated configuration dict
        """
        self._show_welcome()
        self._detect_platform()
        self._check_dependencies()
        self._configure_llm()
        self._configure_audit()
        self._configure_integrations()
        self._configure_workflow()
        self._configure_ui()
        self._save_config()
        self._show_summary()
        
        return self.config
    
    def _show_welcome(self) -> None:
        """Display welcome screen"""
        welcome = """
[bold cyan]Welcome to OutClaw Setup Wizard![/]

This wizard will help you:
  • Detect your platform and dependencies
  • Configure LLM features (optional)
  • Set up external integrations (rclone, ssh, printing)
  • Customize your workflow and timeline
  • Generate a personalized config.yaml

[dim]Press Enter to continue...[/]
"""
        self.console.print(Panel(welcome, border_style="cyan"))
        self.console.input()
        self.console.clear()
    
    def _detect_platform(self) -> None:
        """Detect and display platform information"""
        self.console.print("\n[bold cyan]Step 1: Platform Detection[/]\n")
        
        platform_names = {
            'termux': 'Termux (Android)',
            'windows': 'Windows',
            'linux': 'Linux',
            'chromebook': 'Chromebook (Crostini)',
            'macos': 'macOS',
            'unknown': 'Unknown',
        }
        
        platform_name = platform_names.get(self.platform, 'Unknown')
        self.console.print(f"[green]✓[/] Detected platform: [bold]{platform_name}[/]")
        
        # Platform-specific notes
        if self.platform == 'termux':
            self.console.print("\n[yellow]Termux Notes:[/]")
            self.console.print("  • Storage access: Run [cyan]termux-setup-storage[/] if needed")
            self.console.print("  • Packages: Install [cyan]python[/] and [cyan]git[/] via pkg")
        elif self.platform == 'windows':
            self.console.print("\n[yellow]Windows Notes:[/]")
            self.console.print("  • PowerShell recommended for best compatibility")
            self.console.print("  • ANSI colors enabled automatically")
        elif self.platform == 'chromebook':
            self.console.print("\n[yellow]Chromebook Notes:[/]")
            self.console.print("  • Running in Crostini Linux container")
            self.console.print("  • File access limited to Linux files area")
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
        self.console.clear()
    
    def _check_dependencies(self) -> None:
        """Check for external dependencies"""
        self.console.print("\n[bold cyan]Step 2: Dependency Check[/]\n")
        
        deps = IntegrationHelper.check_dependencies()
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Tool", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Purpose")
        
        dep_info = {
            'rclone': ('Cloud sync', 'Sync files to cloud storage'),
            'ssh': ('Remote access', 'Connect to remote servers'),
            'printer': ('Printing', 'Print documents'),
            'scanner': ('Scanning', 'Scan documents'),
            'image_viewer': ('Image viewing', 'View images'),
        }
        
        for dep, available in deps.items():
            name, purpose = dep_info.get(dep, (dep, 'Unknown'))
            status = "[green]✓ Available[/]" if available else "[dim]✗ Not found[/]"
            table.add_row(name, status, purpose)
        
        self.console.print(table)
        
        # Store availability in config
        self.config['integrations'] = {
            'available': deps,
        }
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
        self.console.clear()
    
    def _configure_llm(self) -> None:
        """Configure LLM settings (cloud cascade only — no local models)."""
        self.console.print("\n[bold cyan]Step 3: LLM Configuration[/]\n")
        
        self.console.print("OutClaw can use free cloud AI providers for semantic analysis.")
        self.console.print("This improves OPPOSITE HOLDING detection but requires free API keys.\n")
        
        enable_llm = Confirm.ask("Enable LLM features?", default=False)
        
        timeout = 15
        if enable_llm:
            self.console.print("\n[yellow]Cascade (cloud) Settings:[/]")
            
            # Timeout
            timeout = IntPrompt.ask(
                "Timeout (seconds)",
                default=15,
                show_default=True,
            )
            
            self.console.print(
                "\n[green]✓[/] LLM configured (stair-stepped free-cloud cascade)"
            )
            self.console.print(
                "[dim]Providers read free API keys from the environment "
                "(GROQ_API_KEY, GOOGLE_API_KEY, OPENROUTER_API_KEY, etc.).[/]"
            )
        else:
            self.console.print("\n[dim]LLM features disabled (can enable later in config.yaml)[/]")
        
        # The cascade block is the REAL LLM switch (the legacy `llm:` block
        # is a no-op). Write `cascade.enabled` so the wizard actually works.
        self.config['cascade'] = {
            'enabled': enable_llm,
            'timeout_seconds': timeout,
        }
        self.config['llm'] = {
            'enabled': enable_llm,
            'timeout_seconds': timeout,
            'ambiguity_threshold': 0.25,
            'min_confidence': 0.70,
            'cache_size': 256,
        }
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
        self.console.clear()
    
    def _configure_audit(self) -> None:
        """Configure audit pipeline settings"""
        self.console.print("\n[bold cyan]Step 4: Audit Configuration[/]\n")
        
        self.console.print("Configure how OutClaw handles citation findings.\n")
        
        # Block threshold
        self.console.print("[bold]Block Threshold:[/]")
        self.console.print("  1. HIGH_ONLY — Only HIGH severity blocks drafts")
        self.console.print("  2. HIGH_AND_MEDIUM — Both HIGH and MEDIUM block (recommended)")
        
        threshold_choice = IntPrompt.ask(
            "\nSelect threshold",
            choices=["1", "2"],
            default=2,
        )
        
        threshold = "HIGH_ONLY" if threshold_choice == 1 else "HIGH_AND_MEDIUM"
        
        # Aura pattern detection
        enable_aura = Confirm.ask(
            "\nEnable Aura pattern detection? (misconduct patterns)",
            default=True,
        )
        
        # Benford's Law
        enable_benford = Confirm.ask(
            "Enable Benford's Law analysis? (financial fraud detection)",
            default=False,
        )
        
        self.config['audit'] = {
            'block_threshold': threshold,
            'sentence_window': 1,
            'negation_detection': True,
            'min_overlap_score': 0.3,
            'min_shared_words': 4,
        }
        
        self.config['aura'] = {
            'enabled': enable_aura,
            'categories': [
                'financial_misconduct',
                'procedural_violations',
                'abuse_of_power',
                'transparency_issues',
                'civil_rights_violations',
                'judicial_misconduct',
                'rico_patterns',
            ] if enable_aura else [],
            'context_window': 80,
        }
        
        self.config['experimental'] = {
            'benford': enable_benford,
        }
        
        self.console.print(f"\n[green]✓[/] Audit configured: {threshold}")
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
        self.console.clear()
    
    def _configure_integrations(self) -> None:
        """Configure external tool integrations"""
        self.console.print("\n[bold cyan]Step 5: External Integrations[/]\n")
        
        integrations = self.config.get('integrations', {})
        available = integrations.get('available', {})
        
        # rclone configuration
        if available.get('rclone'):
            self.console.print("[bold]rclone (Cloud Sync)[/]")
            enable_rclone = Confirm.ask("Enable rclone integration?", default=False)
            
            if enable_rclone:
                remote = Prompt.ask("rclone remote name", default="outclaw-sync")
                sync_interval = IntPrompt.ask(
                    "Sync interval (seconds)",
                    default=300,
                    show_default=True,
                )
                
                integrations['rclone'] = {
                    'enabled': True,
                    'remote': remote,
                    'sync_interval': sync_interval,
                    'auto_sync': False,
                }
                self.console.print(f"[green]✓[/] rclone configured: {remote}")
        
        # SSH configuration
        if available.get('ssh'):
            self.console.print("\n[bold]SSH (Remote Access)[/]")
            enable_ssh = Confirm.ask("Configure SSH shortcuts?", default=False)
            
            if enable_ssh:
                ssh_host = Prompt.ask("Default SSH host (optional)", default="")
                integrations['ssh'] = {
                    'enabled': True,
                    'default_host': ssh_host if ssh_host else None,
                }
                self.console.print("[green]✓[/] SSH configured")
        
        # Printing configuration
        if available.get('printer'):
            self.console.print("\n[bold]Printing[/]")
            enable_print = Confirm.ask("Enable document printing?", default=True)
            
            if enable_print:
                integrations['printing'] = {
                    'enabled': True,
                    'command': IntegrationHelper.find_printer_command(),
                }
                self.console.print("[green]✓[/] Printing enabled")
        
        # Scanning configuration
        if available.get('scanner'):
            self.console.print("\n[bold]Scanning[/]")
            enable_scan = Confirm.ask("Enable document scanning?", default=True)
            
            if enable_scan:
                integrations['scanning'] = {
                    'enabled': True,
                    'command': IntegrationHelper.find_scanner_command(),
                    'output_format': 'pdf',
                }
                self.console.print("[green]✓[/] Scanning enabled")
        
        self.config['integrations'] = integrations
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
        self.console.clear()
    
    def _configure_workflow(self) -> None:
        """Configure workflow and timeline"""
        self.console.print("\n[bold cyan]Step 6: Workflow & Timeline[/]\n")
        
        self.console.print("Set up your legal workflow timeline.\n")
        
        # Case type
        self.console.print("[bold]Case Type:[/]")
        self.console.print("  1. Criminal Defense")
        self.console.print("  2. Civil Rights (§1983)")
        self.console.print("  3. Habeas Corpus")
        self.console.print("  4. Civil Litigation")
        self.console.print("  5. Appeals")
        self.console.print("  6. Other")
        
        case_type_choice = IntPrompt.ask(
            "\nSelect case type",
            choices=["1", "2", "3", "4", "5", "6"],
            default=6,
        )
        
        case_types = {
            1: 'criminal_defense',
            2: 'civil_rights_1983',
            3: 'habeas_corpus',
            4: 'civil_litigation',
            5: 'appeals',
            6: 'other',
        }
        case_type = case_types[case_type_choice]
        
        # Timeline milestones
        self.console.print("\n[bold]Timeline Milestones:[/]")
        add_milestones = Confirm.ask("Set up timeline milestones?", default=False)
        
        milestones: List[Dict[str, str]] = []
        if add_milestones:
            self.console.print("\n[dim]Enter milestones (leave blank to finish):[/]")
            while True:
                milestone = Prompt.ask("Milestone name", default="")
                if not milestone:
                    break
                date = Prompt.ask("Target date (YYYY-MM-DD)", default="")
                milestones.append({
                    'name': milestone,
                    'date': date if date else None,
                    'completed': False,
                })
        
        # Auto-audit on save
        auto_audit = Confirm.ask(
            "\nAuto-audit files on save? (requires file monitoring)",
            default=False,
        )
        
        self.config['workflow'] = {
            'case_type': case_type,
            'milestones': milestones,
            'auto_audit': auto_audit,
        }
        
        self.console.print(f"\n[green]✓[/] Workflow configured: {case_type}")
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
        self.console.clear()
    
    def _configure_ui(self) -> None:
        """Configure UI preferences"""
        self.console.print("\n[bold cyan]Step 7: UI Preferences[/]\n")
        
        # Colors
        colors = Confirm.ask("Enable ANSI colors?", default=True)
        
        # Emoji
        emoji = Confirm.ask("Enable emoji indicators?", default=True)
        
        # Dashboard width
        width = IntPrompt.ask(
            "Dashboard width (characters)",
            default=70,
            show_default=True,
        )
        
        self.config['terminal'] = {
            'colors': colors,
            'emoji': emoji,
            'dashboard_width': width,
            'risk_bar_width': 40,
        }
        
        self.console.print("\n[green]✓[/] UI preferences configured")
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
        self.console.clear()
    
    def _save_config(self) -> None:
        """Save configuration to YAML file"""
        self.console.print("\n[bold cyan]Step 8: Saving Configuration[/]\n")
        
        # Add default sections not covered by wizard
        self._add_default_sections()
        
        # Convert to YAML
        import yaml
        
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            
            self.console.print(f"[green]✓[/] Configuration saved to:")
            self.console.print(f"    [cyan]{self.config_path}[/]")
        except Exception as e:
            self.console.print(f"[red]✗[/] Failed to save config: {e}")
        
        self.console.input("\n[dim]Press Enter to continue...[/]")
        self.console.clear()
    
    def _add_default_sections(self) -> None:
        """Add default configuration sections"""
        # Risk scoring
        if 'risk' not in self.config:
            self.config['risk'] = {
                'weights': {
                    'EXISTENCE': 30,
                    'NEGATIVE_TREATMENT': 25,
                    'OPPOSITE_HOLDING': 25,
                    'MISQUOTE_OPPOSITE': 20,
                    'NO_SUPPORT': 10,
                },
                'compound_penalty': 10,
                'llm_recovery_discount': 10,
                'tiers': {
                    'GREEN': [0, 24],
                    'YELLOW': [25, 49],
                    'ORANGE': [50, 74],
                    'RED': [75, 100],
                },
                'safe_file_threshold': 50,
            }
        
        # CourtListener
        if 'courtlistener' not in self.config:
            self.config['courtlistener'] = {
                'api_base': 'https://www.courtlistener.com/api/rest/v4',
                'rate_limit': 3,
                'cache_ttl': 604800,
                'auto_expand': False,
            }
        
        # Discovery
        if 'discovery' not in self.config:
            self.config['discovery'] = {
                'min_confidence': 0.4,
                'high_confidence': 0.7,
                'log_file': '~/.outclaw/discoveries.jsonl',
                'max_pending': 100,
            }
        
        # FOIA
        if 'foia' not in self.config:
            self.config['foia'] = {
                'default_jurisdiction': 'generic',
                'default_method': 'CERTIFIED MAIL — RETURN RECEIPT REQUESTED',
                'default_format': 'electronic (PDF or native)',
            }
        
        # IRAC
        if 'irac' not in self.config:
            self.config['irac'] = {
                'default_jurisdiction': 'federal',
                'output_format': 'terminal',
            }
        
        # Seed
        if 'seed' not in self.config:
            self.config['seed'] = {
                'path': 'outclaw_seed.json',
                'auto_reload': True,
            }
        
        # Logging
        if 'logging' not in self.config:
            self.config['logging'] = {
                'level': 'WARNING',
                'file': '~/.outclaw/outclaw.log',
                'max_size': 10485760,
                'backup_count': 3,
            }
        
        # Safety
        if 'safety' not in self.config:
            self.config['safety'] = {
                'require_ack': True,
                'allowed_intents': [
                    'section_1983_complaint',
                    'criminal_appeal',
                    'civil_appeal',
                    'habeas_petition_2254',
                    'motion_to_vacate_2255',
                    'state_habeas',
                    'state_post_conviction',
                    'notice_of_appeal',
                    'appellate_brief',
                    'tro',
                    'preliminary_injunction',
                    'motion_to_dismiss',
                ],
            }
    
    def _show_summary(self) -> None:
        """Show setup summary"""
        summary = f"""
[bold green]✓ Setup Complete![/]

[bold]Configuration saved to:[/]
  [cyan]{self.config_path}[/]

[bold]Platform:[/] {self.platform}
[bold]LLM:[/] {'Enabled' if self.config.get('llm', {}).get('enabled') else 'Disabled'}
[bold]Aura:[/] {'Enabled' if self.config.get('aura', {}).get('enabled') else 'Disabled'}
[bold]Case Type:[/] {self.config.get('workflow', {}).get('case_type', 'Not set')}

[bold cyan]Next Steps:[/]
  1. Review config: [cyan]cat {self.config_path}[/]
  2. Run dashboard: [cyan]python3 outclaw_dashboard.py[/]
  3. Test audit: Press '1' and select a file

[dim]You can edit {self.config_path} anytime to adjust settings.[/]
"""
        self.console.print(Panel(summary, border_style="green"))


def run_setup_wizard() -> Dict[str, Any]:
    """
    Run the setup wizard and return configuration.
    
    Returns:
        Generated configuration dict
    """
    wizard = SetupWizard()
    return wizard.run()


if __name__ == "__main__":
    run_setup_wizard()
