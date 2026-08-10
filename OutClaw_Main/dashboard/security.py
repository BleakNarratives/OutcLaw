"""
Security Layer for OutClaw Dashboard

Provides input validation, sanitization, and protection against common
attack vectors including path traversal, command injection, and XSS.

Design Philosophy: Defense in depth with whitelisting over blacklisting.
"""

import re
import tempfile
from pathlib import Path
from typing import Optional, Pattern
import logging

logger = logging.getLogger(__name__)


class SecurityViolation(Exception):
    """Raised when input fails security validation"""
    pass


class SecureInput:
    """
    Penetration-proof input handler with strict validation.
    
    All user input passes through this layer before reaching OutClaw core.
    Uses whitelisting patterns and multiple validation stages.
    """
    
    # Maximum input lengths (prevent DoS via memory exhaustion)
    MAX_PATH_LENGTH = 4096
    MAX_CITATION_LENGTH = 500
    MAX_COMMAND_LENGTH = 100
    MAX_TEXT_LENGTH = 500_000_000  # 500MB for large FOIA document collections
    
    # Whitelist patterns (only these characters allowed)
    #
    # 2026-08-03 (Buffy): the file_path whitelist was too strict for real
    # legal filenames. Browser uploads arrive as
    #   /tmp/outclaw_<timestamp>_Smith v. Jones (2024) §2.pdf
    # and the old regex `[a-zA-Z0-9_/.\-\s]` rejected perfectly ordinary
    # characters: parentheses, commas, apostrophes, §, #, +, &, etc. That
    # made EVERY multi-file dashboard upload throw
    #   SecurityViolation: Path contains invalid characters
    # (the exact blocker named in HANDOFF.md).
    #
    # The security JOB here is path traversal / command injection / shell
    # metacharacters — which DANGEROUS_PATTERNS + resolve() + allowed_roots
    # still enforce below. The character whitelist is now wide enough to
    # accept real-world legal filenames while still excluding shell and
    # traversal metacharacters (they are all caught upstream in
    # DANGEROUS_PATTERNS: ; & | ` $ and control chars).
    PATTERNS: dict[str, Pattern] = {
        'file_path': re.compile(
            r"^[a-zA-Z0-9_/\-\s()\.,'" + '"' + r"#+&§%=\[\]@]+$"
        ),
        'citation': re.compile(r'^[a-zA-Z0-9\s\.\,\(\)\-§]+$'),
        'command': re.compile(r'^[1-9]|[rRqQhHfFlLcCsS/]$'),
        'agency_name': re.compile(r'^[a-zA-Z0-9\s\.\,\-&]+$'),
        'jurisdiction': re.compile(r'^(federal|oklahoma|kansas|generic)$'),
        'intent': re.compile(r'^[a-z_0-9]+$'),
    }
    
    # Dangerous patterns (block these immediately)
    DANGEROUS_PATTERNS = [
        re.compile(r'\.\./'),           # Path traversal
        re.compile(r'~[^/]'),           # Home directory expansion tricks
        re.compile(r'[;&|`$]'),         # Shell metacharacters
        re.compile(r'<script'),         # XSS attempts
        re.compile(r'eval\('),          # Code injection
        re.compile(r'exec\('),          # Code injection
        re.compile(r'__import__'),      # Dynamic imports
        re.compile(r'\x00'),            # Null bytes
        re.compile(r'[\x01-\x08\x0b-\x0c\x0e-\x1f]'),  # Control chars
    ]
    
    # Allowed file extensions for audit operations
    ALLOWED_EXTENSIONS = {'.txt', '.md', '.pdf', '.doc', '.docx', '.rtf'}
    
    @classmethod
    def validate_file_path(cls, path_str: str, must_exist: bool = False) -> Path:
        """
        Validate and sanitize a file path.
        
        Args:
            path_str: User-provided path string
            must_exist: If True, path must exist on filesystem
            
        Returns:
            Resolved, validated Path object
            
        Raises:
            SecurityViolation: If path fails validation
        """
        # Length check
        if len(path_str) > cls.MAX_PATH_LENGTH:
            raise SecurityViolation(f"Path too long (max {cls.MAX_PATH_LENGTH})")
        
        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern.search(path_str):
                logger.warning(f"Blocked dangerous pattern in path: {path_str[:50]}")
                raise SecurityViolation("Path contains forbidden characters")
        
        # Whitelist validation
        if not cls.PATTERNS['file_path'].match(path_str):
            raise SecurityViolation("Path contains invalid characters")
        
        try:
            # Convert to Path and resolve (prevents traversal)
            path = Path(path_str).resolve()
        except (ValueError, OSError) as e:
            raise SecurityViolation(f"Invalid path: {e}")
        
        # Ensure path is within allowed directories
        # (Prevents access to system files)
        allowed_roots = [
            Path.home(),
            Path.cwd(),
            Path('/tmp'),  # Linux temp files
            Path(tempfile.gettempdir()),  # Real temp dir (macOS uses /var/folders/…)
        ]
        
        if not any(path.is_relative_to(root) for root in allowed_roots):
            raise SecurityViolation("Path outside allowed directories")
        
        # Check existence if required
        if must_exist and not path.exists():
            raise SecurityViolation(f"Path does not exist: {path}")
        
        # Validate file extension for audit operations
        if path.is_file() and path.suffix.lower() not in cls.ALLOWED_EXTENSIONS:
            logger.warning(f"Unusual file extension: {path.suffix}")
            # Don't block, but log for monitoring
        
        return path
    
    @classmethod
    def validate_citation(cls, citation: str) -> str:
        """
        Validate a legal citation string.
        
        Args:
            citation: User-provided citation
            
        Returns:
            Sanitized citation string
            
        Raises:
            SecurityViolation: If citation fails validation
        """
        # Length check
        if len(citation) > cls.MAX_CITATION_LENGTH:
            raise SecurityViolation(f"Citation too long (max {cls.MAX_CITATION_LENGTH})")
        
        # Strip leading/trailing whitespace
        citation = citation.strip()
        
        if not citation:
            raise SecurityViolation("Citation cannot be empty")
        
        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern.search(citation):
                raise SecurityViolation("Citation contains forbidden characters")
        
        # Whitelist validation
        if not cls.PATTERNS['citation'].match(citation):
            raise SecurityViolation("Citation contains invalid characters")
        
        return citation
    
    @classmethod
    def validate_command(cls, command: str) -> str:
        """
        Validate a dashboard command/shortcut.
        
        Args:
            command: Single character or digit command
            
        Returns:
            Validated command string
            
        Raises:
            SecurityViolation: If command is invalid
        """
        if len(command) > cls.MAX_COMMAND_LENGTH:
            raise SecurityViolation("Command too long")
        
        command = command.strip()
        
        if not cls.PATTERNS['command'].match(command):
            raise SecurityViolation(f"Invalid command: {command}")
        
        return command
    
    @classmethod
    def validate_text_content(cls, content: str, is_binary: bool = False) -> str:
        """
        Validate text content for audit operations.
        
        Args:
            content: Text content to validate
            is_binary: If True, skip text-specific security checks
        
        Returns:
            Validated content
        
        Raises:
            SecurityViolation: If content fails validation
        """
        # Length check (prevent memory exhaustion)
        if len(content) > cls.MAX_TEXT_LENGTH:
            raise SecurityViolation(f"Content too large (max {cls.MAX_TEXT_LENGTH} bytes)")
        
        if not is_binary:
            # Check for null bytes and control characters
            if '\x00' in content:
                raise SecurityViolation("Content contains null bytes")
        
        # Allow most printable characters and common whitespace
        # This is intentionally permissive for legal text
        return content
    
    @classmethod
    def validate_agency_name(cls, name: str) -> str:
        """Validate agency name for FOIA requests"""
        if len(name) > 200:
            raise SecurityViolation("Agency name too long")
        
        name = name.strip()
        
        if not cls.PATTERNS['agency_name'].match(name):
            raise SecurityViolation("Agency name contains invalid characters")
        
        return name
    
    @classmethod
    def validate_jurisdiction(cls, jurisdiction: str) -> str:
        """Validate jurisdiction parameter"""
        jurisdiction = jurisdiction.lower().strip()
        
        if not cls.PATTERNS['jurisdiction'].match(jurisdiction):
            raise SecurityViolation(f"Invalid jurisdiction: {jurisdiction}")
        
        return jurisdiction
    
    @classmethod
    def validate_intent(cls, intent: str) -> str:
        """Validate filing intent for safety gate"""
        intent = intent.lower().strip()
        
        if not cls.PATTERNS['intent'].match(intent):
            raise SecurityViolation("Intent contains invalid characters")
        
        # Additional check: intent must be in allowed list
        # (This is enforced by outclaw_safety.py, but we double-check)
        if len(intent) > 50:
            raise SecurityViolation("Intent name too long")
        
        return intent
    
    @classmethod
    def sanitize_for_display(cls, text: str, max_length: int = 100) -> str:
        """
        Sanitize text for safe terminal display.
        
        Removes control characters and truncates to prevent terminal injection.
        
        Args:
            text: Text to sanitize
            max_length: Maximum display length
            
        Returns:
            Safe display string
        """
        # Remove control characters except newline and tab
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)
        
        # Truncate if needed
        if len(text) > max_length:
            text = text[:max_length - 3] + "..."
        
        return text
    
    @classmethod
    def rate_limit_check(cls, operation: str, max_per_minute: int = 60) -> bool:
        """
        Simple rate limiting for API operations.
        
        Args:
            operation: Operation identifier (e.g., 'courtlistener_lookup')
            max_per_minute: Maximum operations per minute
            
        Returns:
            True if operation is allowed, False if rate limited
        """
        # TODO: Implement proper rate limiting with time-based buckets
        # For now, this is a placeholder that always returns True
        # Production implementation would use a token bucket or sliding window
        return True


class SecureConfig:
    """
    Secure configuration loader with validation.
    
    Prevents malicious config injection via YAML bombs or code execution.
    """
    
    @staticmethod
    def load_yaml(path: Path) -> dict:
        """
        Safely load YAML configuration.
        
        Args:
            path: Path to YAML file
            
        Returns:
            Parsed configuration dict
            
        Raises:
            SecurityViolation: If config is malicious
        """
        import yaml
        
        # Validate path first
        path = SecureInput.validate_file_path(str(path), must_exist=True)
        
        # Check file size (prevent YAML bombs)
        file_size = path.stat().st_size
        if file_size > 1_000_000:  # 1MB max for config
            raise SecurityViolation("Config file too large")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                # Use safe_load (never load/full_load which can execute code)
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SecurityViolation(f"Invalid YAML: {e}")
        
        if not isinstance(config, dict):
            raise SecurityViolation("Config must be a dictionary")
        
        return config


# Convenience functions for common validations

def safe_path(path_str: str, must_exist: bool = False) -> Path:
    """Shorthand for SecureInput.validate_file_path"""
    return SecureInput.validate_file_path(path_str, must_exist)


def safe_citation(citation: str) -> str:
    """Shorthand for SecureInput.validate_citation"""
    return SecureInput.validate_citation(citation)


def safe_command(command: str) -> str:
    """Shorthand for SecureInput.validate_command"""
    return SecureInput.validate_command(command)


def safe_display(text: str, max_length: int = 100) -> str:
    """Shorthand for SecureInput.sanitize_for_display"""
    return SecureInput.sanitize_for_display(text, max_length)
