"""
Cross-Platform Compatibility Layer

Handles platform-specific differences for Termux (Android), Windows, and Linux.
Provides unified interface for file operations, terminal detection, and system commands.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


class PlatformDetector:
    """
    Detects the current platform and provides platform-specific utilities.
    
    Supports:
    - Termux (Android)
    - Windows (PowerShell, CMD)
    - Linux (Chromebook Crostini, standard Linux)
    - macOS
    """
    
    @staticmethod
    def get_platform() -> str:
        """
        Detect current platform.
        
        Returns:
            One of: 'termux', 'windows', 'linux', 'chromebook', 'macos', 'unknown'
        """
        system = platform.system().lower()
        
        # Check for Termux (Android)
        if 'TERMUX_VERSION' in os.environ or Path('/data/data/com.termux').exists():
            return 'termux'
        
        # Check for Chromebook (Crostini)
        if system == 'linux':
            # Crostini has specific environment markers
            if os.environ.get('SOMMELIER_VERSION') or Path('/opt/google/cros-containers').exists():
                return 'chromebook'
            return 'linux'
        
        # Windows
        if system == 'windows':
            return 'windows'
        
        # macOS
        if system == 'darwin':
            return 'macos'
        
        return 'unknown'
    
    @staticmethod
    def is_termux() -> bool:
        """Check if running in Termux"""
        return PlatformDetector.get_platform() == 'termux'
    
    @staticmethod
    def is_windows() -> bool:
        """Check if running on Windows"""
        return PlatformDetector.get_platform() == 'windows'
    
    @staticmethod
    def is_chromebook() -> bool:
        """Check if running on Chromebook (Crostini)"""
        return PlatformDetector.get_platform() == 'chromebook'
    
    @staticmethod
    def is_linux() -> bool:
        """Check if running on standard Linux"""
        return PlatformDetector.get_platform() == 'linux'
    
    @staticmethod
    def get_home_dir() -> Path:
        """Get platform-appropriate home directory"""
        platform_type = PlatformDetector.get_platform()
        
        if platform_type == 'termux':
            # Termux uses /data/data/com.termux/files/home
            return Path(os.environ.get('HOME', '/data/data/com.termux/files/home'))
        elif platform_type == 'windows':
            # Windows uses USERPROFILE
            return Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
        else:
            # Standard Unix home
            return Path.home()
    
    @staticmethod
    def get_config_dir() -> Path:
        """Get platform-appropriate config directory"""
        platform_type = PlatformDetector.get_platform()
        home = PlatformDetector.get_home_dir()
        
        if platform_type == 'termux':
            # Termux: ~/.outclaw
            return home / '.outclaw'
        elif platform_type == 'windows':
            # Windows: %APPDATA%\OutClaw
            appdata = os.environ.get('APPDATA', str(home / 'AppData' / 'Roaming'))
            return Path(appdata) / 'OutClaw'
        else:
            # Linux/macOS: ~/.config/outclaw or ~/.outclaw
            xdg_config = os.environ.get('XDG_CONFIG_HOME', str(home / '.config'))
            return Path(xdg_config) / 'outclaw'
    
    @staticmethod
    def get_temp_dir() -> Path:
        """Get platform-appropriate temp directory"""
        platform_type = PlatformDetector.get_platform()
        
        if platform_type == 'termux':
            # Termux: $PREFIX/tmp
            prefix = os.environ.get('PREFIX', '/data/data/com.termux/files/usr')
            return Path(prefix) / 'tmp'
        elif platform_type == 'windows':
            # Windows: %TEMP%
            return Path(os.environ.get('TEMP', 'C:\\Windows\\Temp'))
        else:
            # Unix: /tmp
            return Path('/tmp')
    
    @staticmethod
    def supports_color() -> bool:
        """Check if terminal supports ANSI colors"""
        # Windows CMD needs special handling
        if PlatformDetector.is_windows():
            # Windows 10+ supports ANSI in CMD/PowerShell
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
                return True
            except Exception:
                return False
        
        # Check TERM environment variable
        term = os.environ.get('TERM', '')
        if term in ('dumb', ''):
            return False
        
        # Most modern terminals support color
        return sys.stdout.isatty()
    
    @staticmethod
    def get_shell() -> str:
        """Get platform-appropriate shell"""
        platform_type = PlatformDetector.get_platform()
        
        if platform_type == 'windows':
            # Prefer PowerShell, fallback to CMD
            if shutil.which('powershell'):
                return 'powershell'
            return 'cmd'
        else:
            # Unix-like: prefer bash, fallback to sh
            shell = os.environ.get('SHELL', '/bin/sh')
            return shell
    
    @staticmethod
    def run_command(
        command: str,
        shell: bool = True,
        timeout: Optional[int] = None,
    ) -> Tuple[int, str, str]:
        """
        Run a shell command in a platform-appropriate way.
        
        Args:
            command: Command to run
            shell: Whether to use shell
            timeout: Optional timeout in seconds
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        platform_type = PlatformDetector.get_platform()
        
        # Adjust command for Windows
        if platform_type == 'windows' and shell:
            # Use PowerShell for better compatibility
            if 'powershell' in PlatformDetector.get_shell():
                command = f'powershell -Command "{command}"'
        
        try:
            result = subprocess.run(
                command,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, '', 'Command timed out'
        except Exception as e:
            return -1, '', str(e)


class FileSystemHelper:
    """Platform-aware filesystem operations"""
    
    @staticmethod
    def ensure_dir(path: Path) -> None:
        """Create directory if it doesn't exist (cross-platform)"""
        path.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def get_path_separator() -> str:
        """Get platform-appropriate path separator"""
        return os.sep
    
    @staticmethod
    def normalize_path(path: str) -> Path:
        """Normalize path for current platform"""
        # Convert forward slashes to backslashes on Windows
        if PlatformDetector.is_windows():
            path = path.replace('/', '\\')
        return Path(path).resolve()
    
    @staticmethod
    def is_executable(path: Path) -> bool:
        """Check if file is executable (cross-platform)"""
        if PlatformDetector.is_windows():
            # On Windows, check file extension
            return path.suffix.lower() in ('.exe', '.bat', '.cmd', '.ps1')
        else:
            # On Unix, check execute permission
            return os.access(path, os.X_OK)
    
    @staticmethod
    def make_executable(path: Path) -> None:
        """Make file executable (cross-platform)"""
        if not PlatformDetector.is_windows():
            # Unix: chmod +x
            os.chmod(path, os.stat(path).st_mode | 0o111)


class IntegrationHelper:
    """Helper for external tool integrations (rclone, ssh, etc.)"""
    
    @staticmethod
    def find_rclone() -> Optional[Path]:
        """Find rclone executable"""
        rclone_path = shutil.which('rclone')
        return Path(rclone_path) if rclone_path else None
    
    @staticmethod
    def find_ssh() -> Optional[Path]:
        """Find ssh executable"""
        ssh_path = shutil.which('ssh')
        return Path(ssh_path) if ssh_path else None
    
    @staticmethod
    def find_printer_command() -> Optional[str]:
        """Find platform-appropriate print command"""
        platform_type = PlatformDetector.get_platform()
        
        if platform_type == 'windows':
            # Windows: notepad /p or print command
            return 'notepad /p' if shutil.which('notepad') else None
        elif platform_type == 'termux':
            # Termux: termux-share or lp
            if shutil.which('termux-share'):
                return 'termux-share'
            return None
        else:
            # Linux/macOS: lp or lpr
            if shutil.which('lp'):
                return 'lp'
            elif shutil.which('lpr'):
                return 'lpr'
            return None
    
    @staticmethod
    def find_scanner_command() -> Optional[str]:
        """Find platform-appropriate scan command"""
        platform_type = PlatformDetector.get_platform()
        
        if platform_type == 'termux':
            # Termux: termux-camera-photo
            if shutil.which('termux-camera-photo'):
                return 'termux-camera-photo'
            return None
        elif platform_type == 'linux' or platform_type == 'chromebook':
            # Linux: scanimage (SANE)
            if shutil.which('scanimage'):
                return 'scanimage'
            return None
        else:
            # Windows/macOS: platform-specific
            return None
    
    @staticmethod
    def find_image_viewer() -> Optional[str]:
        """Find platform-appropriate image viewer"""
        platform_type = PlatformDetector.get_platform()
        
        if platform_type == 'windows':
            # Windows: default image viewer
            return 'start'
        elif platform_type == 'termux':
            # Termux: termux-open
            if shutil.which('termux-open'):
                return 'termux-open'
            return None
        else:
            # Linux/macOS: xdg-open or open
            if shutil.which('xdg-open'):
                return 'xdg-open'
            elif shutil.which('open'):
                return 'open'
            return None
    
    @staticmethod
    def check_dependencies() -> dict:
        """Check for available external tools"""
        return {
            'rclone': IntegrationHelper.find_rclone() is not None,
            'ssh': IntegrationHelper.find_ssh() is not None,
            'printer': IntegrationHelper.find_printer_command() is not None,
            'scanner': IntegrationHelper.find_scanner_command() is not None,
            'image_viewer': IntegrationHelper.find_image_viewer() is not None,
        }


# Convenience functions

def get_platform() -> str:
    """Get current platform name"""
    return PlatformDetector.get_platform()


def get_config_dir() -> Path:
    """Get config directory for current platform"""
    return PlatformDetector.get_config_dir()


def supports_color() -> bool:
    """Check if terminal supports colors"""
    return PlatformDetector.supports_color()


def ensure_config_dir() -> Path:
    """Ensure config directory exists and return path"""
    config_dir = get_config_dir()
    FileSystemHelper.ensure_dir(config_dir)
    return config_dir
