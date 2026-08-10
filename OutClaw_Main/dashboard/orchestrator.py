"""
Dashboard Orchestrator — Command Wrapper Layer

Provides a clean interface between the TUI dashboard and OutClaw core modules.
All operations go through this layer for consistent error handling and logging.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .security import SecureInput, SecurityViolation

logger = logging.getLogger(__name__)


@dataclass
class OperationResult:
    """Standardized result container for all operations"""
    success: bool
    operation: str
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'operation': self.operation,
            'data': self.data,
            'error': self.error,
            'elapsed_ms': self.elapsed_ms,
            'timestamp': self.timestamp,
        }


class DashboardOrchestrator:
    """
    Orchestrates OutClaw operations for the dashboard.
    
    This class wraps all OutClaw CLI functionality with:
    - Security validation
    - Error handling
    - Performance tracking
    - Consistent result format
    """
    
    def __init__(self, config: Optional[dict] = None):
        """
        Initialize orchestrator.
        
        Args:
            config: Optional configuration dict (from config.yaml)
        """
        self.config = config or {}
        self._operation_history: list[OperationResult] = []
        self._max_history = 100
        
        # Lazy-load OutClaw modules (only when needed)
        self._unified = None
        self._scorer = None
        self._courtlistener = None
        self._discover = None
        self._foia = None
        self._irac = None
        self._safety = None
    
    @property
    def unified(self):
        """Lazy-load outclaw_unified module"""
        if self._unified is None:
            try:
                import sys
                from pathlib import Path
                # Add OutClaw to path if needed
                outclaw_dir = Path(__file__).parent.parent
                if str(outclaw_dir) not in sys.path:
                    sys.path.insert(0, str(outclaw_dir))
                import outclaw_unified as unified
                self._unified = unified
            except ImportError as e:
                logger.error(f"Failed to import outclaw_unified: {e}")
                raise
        return self._unified
    
    @property
    def scorer(self):
        """Lazy-load outclaw_scorer module"""
        if self._scorer is None:
            try:
                from OutClaw.outclaw_scorer import AuditRiskScorer
                self._scorer = AuditRiskScorer()
            except ImportError as e:
                logger.error(f"Failed to import outclaw_scorer: {e}")
                raise
        return self._scorer
    
    @property
    def courtlistener(self):
        """Lazy-load outclaw_courtlistener module"""
        if self._courtlistener is None:
            try:
                from OutClaw.outclaw_courtlistener import CourtListenerScout
                self._courtlistener = CourtListenerScout()
            except ImportError as e:
                logger.error(f"Failed to import outclaw_courtlistener: {e}")
                raise
        return self._courtlistener
    
    @property
    def discover(self):
        """Lazy-load outclaw_discover module"""
        if self._discover is None:
            try:
                from OutClaw.outclaw_discover import DiscoveryEngine
                self._discover = DiscoveryEngine()
            except ImportError as e:
                logger.error(f"Failed to import outclaw_discover: {e}")
                raise
        return self._discover
    
    @property
    def foia(self):
        """Lazy-load outclaw_foia module"""
        if self._foia is None:
            try:
                from OutClaw.outclaw_foia import FOIAGenerator
                self._foia = FOIAGenerator()
            except ImportError as e:
                logger.error(f"Failed to import outclaw_foia: {e}")
                raise
        return self._foia
    
    @property
    def irac(self):
        """Lazy-load outclaw_irac module"""
        if self._irac is None:
            try:
                from OutClaw.outclaw_irac import IRACAnalyzer
                self._irac = IRACAnalyzer()
            except ImportError as e:
                logger.error(f"Failed to import outclaw_irac: {e}")
                raise
        return self._irac
    
    @property
    def safety(self):
        """Lazy-load outclaw_safety module"""
        if self._safety is None:
            try:
                import outclaw_safety as safety
                self._safety = safety
            except ImportError as e:
                logger.error(f"Failed to import outclaw_safety: {e}")
                raise
        return self._safety
    
    def _record_operation(self, result: OperationResult) -> None:
        """Record operation in history"""
        self._operation_history.append(result)
        if len(self._operation_history) > self._max_history:
            self._operation_history.pop(0)
    
    def get_operation_history(self, limit: int = 10) -> list[OperationResult]:
        """Get recent operation history"""
        return self._operation_history[-limit:]
    
    def audit_file(self, file_path: str, use_llm: bool = False) -> OperationResult:
        """
        Audit a legal text file for citation fraud.
        
        Args:
            file_path: Path to file to audit
            use_llm: Enable LLM-assisted classification
            
        Returns:
            OperationResult with audit report
        """
        start = time.time()
        
        try:
            # Security validation
            path = SecureInput.validate_file_path(file_path, must_exist=True)
            
            # Read file content with error handling for encoding issues
            is_pdf = path.suffix.lower() == '.pdf'
            
            try:
                if is_pdf:
                    from pypdf import PdfReader
                    reader = PdfReader(path)
                    text = ""
                    for page in reader.pages:
                        text += (page.extract_text() or "") + "\n"
                else:
                    text = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                # Try with latin-1 encoding as fallback
                try:
                    text = path.read_text(encoding='latin-1')
                except Exception:
                    # Last resort: read as binary and decode with errors='ignore'
                    text = path.read_bytes().decode('utf-8', errors='ignore')
            
            text = SecureInput.validate_text_content(text, is_binary=is_pdf)
            
            # Run audit
            report = self.unified.audit_text(text, use_llm=use_llm)
            
            # Calculate risk score
            try:
                risk = self.scorer.score_report(report)
                risk_data = {
                    'score': risk.score,
                    'tier': risk.tier,
                    'safe_to_file': risk.safe_to_file,
                }
            except Exception as e:
                logger.warning(f"Risk scoring failed: {e}")
                risk_data = {'score': 50, 'tier': 'UNKNOWN', 'safe_to_file': False}
            
            elapsed = (time.time() - start) * 1000
            
            result = OperationResult(
                success=True,
                operation='audit_file',
                data={
                    'file_path': str(path),
                    'summary': report.summary,
                    'findings': [f.__dict__ for f in report.findings],
                    'risk': risk_data,
                    'llm_enabled': use_llm,
                },
                elapsed_ms=elapsed,
            )
            
        except SecurityViolation as e:
            result = OperationResult(
                success=False,
                operation='audit_file',
                error=f"Security violation: {e}",
            )
        except FileNotFoundError as e:
            result = OperationResult(
                success=False,
                operation='audit_file',
                error=f"File not found: {e}",
            )
        except Exception as e:
            logger.exception("Audit failed")
            result = OperationResult(
                success=False,
                operation='audit_file',
                error=f"Audit failed: {e}",
            )
        
        self._record_operation(result)
        return result
    
    def full_audit(
        self,
        file_path: str,
        use_llm: bool = False,
        enable_aura: bool = True,
        enable_benford: bool = False,
        numeric_data: Optional[list] = None,
    ) -> OperationResult:
        """
        Run full audit pipeline (citation + aura + benford + risk).
        
        Args:
            file_path: Path to file to audit
            use_llm: Enable LLM-assisted classification
            enable_aura: Enable Aura pattern detection
            enable_benford: Enable Benford's Law analysis
            numeric_data: Optional numeric data for Benford
            
        Returns:
            OperationResult with full audit report
        """
        start = time.time()
        
        try:
            # Security validation
            path = SecureInput.validate_file_path(file_path, must_exist=True)
            
            # Read file content with error handling for encoding issues
            is_pdf = path.suffix.lower() == '.pdf'
            
            try:
                if is_pdf:
                    from pypdf import PdfReader
                    reader = PdfReader(path)
                    text = ""
                    for page in reader.pages:
                        text += (page.extract_text() or "") + "\n"
                else:
                    text = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                # Try with latin-1 encoding as fallback
                try:
                    text = path.read_text(encoding='latin-1')
                except Exception:
                    # Last resort: read as binary and decode with errors='ignore'
                    text = path.read_bytes().decode('utf-8', errors='ignore')
            
            text = SecureInput.validate_text_content(text, is_binary=is_pdf)
            
            # Run full audit
            result_data = self.unified.full_audit_text(
                text,
                use_llm=use_llm,
                enable_aura=enable_aura,
                enable_benford=enable_benford,
                numeric_data=numeric_data,
            )
            
            # Apply SoWhatFilter
            from outclaw_so_what_filter import SoWhatFilter
            filter_system = SoWhatFilter()
            # This requires some context that we might not have in a generic full audit.
            # We'll pass empty/default context for now.
            reality_check = filter_system.apply_reality_check(
                result_data['citation_audit']['findings'],
                {}, # attorney_history
                {}  # case_context
            )
            result_data['so_what_impact'] = reality_check.__dict__
            
            elapsed = (time.time() - start) * 1000
            
            result = OperationResult(
                success=True,
                operation='full_audit',
                data={
                    'file_path': str(path),
                    'citation_audit': result_data['citation_audit'],
                    'aura': result_data.get('aura', {}),
                    'benford': result_data.get('benford', {}),
                    'risk': result_data.get('risk', {}),
                    'verdict': result_data.get('verdict', 'UNKNOWN'),
                },
                elapsed_ms=elapsed,
            )
            
        except SecurityViolation as e:
            result = OperationResult(
                success=False,
                operation='full_audit',
                error=f"Security violation: {e}",
            )
        except Exception as e:
            logger.exception("Full audit failed")
            result = OperationResult(
                success=False,
                operation='full_audit',
                error=f"Full audit failed: {e}",
            )
        
        self._record_operation(result)
        return result
    
    def lookup_citation(self, citation: str, expand_seed: bool = False) -> OperationResult:
        """
        Look up a citation in CourtListener.
        
        Args:
            citation: Citation string to look up
            expand_seed: Add result to seed registry
            
        Returns:
            OperationResult with case data
        """
        start = time.time()
        
        try:
            # Security validation
            citation = SecureInput.validate_citation(citation)
            
            # Rate limiting check
            if not SecureInput.rate_limit_check('courtlistener_lookup'):
                raise SecurityViolation("Rate limit exceeded")
            
            # Lookup
            case_data = self.courtlistener.lookup_citation(citation)
            
            if case_data is None:
                result = OperationResult(
                    success=False,
                    operation='lookup_citation',
                    error=f"Citation not found: {citation}",
                )
            else:
                # Optionally expand seed
                if expand_seed:
                    added = self.courtlistener.expand_seed_registry(case_data)
                    case_data['added_to_seed'] = added
                
                elapsed = (time.time() - start) * 1000
                
                result = OperationResult(
                    success=True,
                    operation='lookup_citation',
                    data={
                        'citation': citation,
                        'case': case_data,
                    },
                    elapsed_ms=elapsed,
                )
            
        except SecurityViolation as e:
            result = OperationResult(
                success=False,
                operation='lookup_citation',
                error=f"Security violation: {e}",
            )
        except Exception as e:
            logger.exception("Lookup failed")
            result = OperationResult(
                success=False,
                operation='lookup_citation',
                error=f"Lookup failed: {e}",
            )
        
        self._record_operation(result)
        return result
    
    def discover_citations(self, file_path: str) -> OperationResult:
        """
        Scan file for undiscovered citations.
        
        Args:
            file_path: Path to file to scan
            
        Returns:
            OperationResult with discoveries
        """
        start = time.time()
        
        try:
            # Security validation
            path = SecureInput.validate_file_path(file_path, must_exist=True)
            
            # Read file content
            is_pdf = path.suffix.lower() == '.pdf'
            
            try:
                if is_pdf:
                    from pypdf import PdfReader
                    reader = PdfReader(path)
                    text = ""
                    for page in reader.pages:
                        text += (page.extract_text() or "") + "\n"
                else:
                    text = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                # Try with latin-1 encoding as fallback
                try:
                    text = path.read_text(encoding='latin-1')
                except Exception:
                    # Last resort: read as binary and decode with errors='ignore'
                    text = path.read_bytes().decode('utf-8', errors='ignore')
            
            text = SecureInput.validate_text_content(text, is_binary=is_pdf)
            
            # Discover
            discoveries = self.discover.scan_text(text, source=str(path))
            
            # Group by confidence
            high = [d for d in discoveries if d['confidence'] >= 0.7]
            medium = [d for d in discoveries if 0.4 <= d['confidence'] < 0.7]
            low = [d for d in discoveries if d['confidence'] < 0.4]
            
            elapsed = (time.time() - start) * 1000
            
            result = OperationResult(
                success=True,
                operation='discover_citations',
                data={
                    'file_path': str(path),
                    'total': len(discoveries),
                    'high': len(high),
                    'medium': len(medium),
                    'low': len(low),
                    'discoveries': discoveries,
                },
                elapsed_ms=elapsed,
            )
            
        except SecurityViolation as e:
            result = OperationResult(
                success=False,
                operation='discover_citations',
                error=f"Security violation: {e}",
            )
        except Exception as e:
            logger.exception("Discovery failed")
            result = OperationResult(
                success=False,
                operation='discover_citations',
                error=f"Discovery failed: {e}",
            )
        
        self._record_operation(result)
        return result
    
    def generate_foia(
        self,
        agency: str,
        description: str,
        jurisdiction: str = 'generic',
        requester_name: Optional[str] = None,
        requester_contact: Optional[str] = None,
    ) -> OperationResult:
        """
        Generate FOIA/Open Records request.
        
        Args:
            agency: Agency name
            description: Description of records requested
            jurisdiction: Jurisdiction (federal, oklahoma, kansas, generic)
            requester_name: Optional requester name
            requester_contact: Optional contact info
            
        Returns:
            OperationResult with FOIA request text
        """
        start = time.time()
        
        try:
            # Security validation
            agency = SecureInput.validate_agency_name(agency)
            jurisdiction = SecureInput.validate_jurisdiction(jurisdiction)
            
            # Generate request
            request_text = self.foia.generate(
                agency=agency,
                description=description,
                jurisdiction=jurisdiction,
                requester_name=requester_name or "[Your Name]",
                requester_contact=requester_contact or "[Your Contact]",
            )
            
            elapsed = (time.time() - start) * 1000
            
            result = OperationResult(
                success=True,
                operation='generate_foia',
                data={
                    'agency': agency,
                    'jurisdiction': jurisdiction,
                    'request_text': request_text,
                },
                elapsed_ms=elapsed,
            )
            
        except SecurityViolation as e:
            result = OperationResult(
                success=False,
                operation='generate_foia',
                error=f"Security violation: {e}",
            )
        except Exception as e:
            logger.exception("FOIA generation failed")
            result = OperationResult(
                success=False,
                operation='generate_foia',
                error=f"FOIA generation failed: {e}",
            )
        
        self._record_operation(result)
        return result
    
    def analyze_question(
        self,
        question: str,
        jurisdiction: str = 'federal',
        relevant_facts: Optional[list[str]] = None,
    ) -> OperationResult:
        """
        Perform IRAC legal analysis.
        
        Args:
            question: Legal question to analyze
            jurisdiction: Jurisdiction for analysis
            relevant_facts: Optional list of relevant facts
            
        Returns:
            OperationResult with IRAC brief
        """
        start = time.time()
        
        try:
            # Security validation
            jurisdiction = SecureInput.validate_jurisdiction(jurisdiction)
            
            # Analyze
            brief = self.irac.analyze(
                question=question,
                jurisdiction=jurisdiction,
                relevant_facts=relevant_facts or [],
            )
            
            elapsed = (time.time() - start) * 1000
            
            result = OperationResult(
                success=True,
                operation='analyze_question',
                data={
                    'question': question,
                    'jurisdiction': jurisdiction,
                    'brief': brief.__dict__,
                },
                elapsed_ms=elapsed,
            )
            
        except SecurityViolation as e:
            result = OperationResult(
                success=False,
                operation='analyze_question',
                error=f"Security violation: {e}",
            )
        except Exception as e:
            logger.exception("IRAC analysis failed")
            result = OperationResult(
                success=False,
                operation='analyze_question',
                error=f"IRAC analysis failed: {e}",
            )
        
        self._record_operation(result)
        return result
    
    def get_system_status(self) -> dict:
        """
        Get current system status.
        
        Returns:
            Dict with system status information
        """
        status = {
            'version': '0.3.0',
            'llm_available': False,
            'seed_registry': {'cases': 0, 'statutes': 0},
            'recent_operations': len(self._operation_history),
        }
        # CLOUD-ONLY (2026-08-03): the cascade uses free cloud providers;
        # there is no local Ollama rung anymore, so nothing to probe.
        # `llm_available` now reports cloud-cascade readiness (enabled +
        # at least one configured free provider). The old `ollama list`
        # subprocess probe was removed.
        try:
            from OutClaw.outclaw_model_cascade import cascade_status  # type: ignore

            cs = cascade_status()
            providers = cs.get('providers', {})
            ready = [n for n, info in providers.items() if info.get('configured')]
            status['llm_available'] = bool(cs.get('enabled') and ready)
            status['cascade'] = {
                'enabled': cs.get('enabled', False),
                'providers_ready': sorted(ready),
                'providers_total': len(providers),
            }
        except Exception:
            pass
        # Check seed registry
        try:
            seed_path = Path(__file__).parent.parent / 'outclaw_seed.json'
            if seed_path.exists():
                with open(seed_path) as f:
                    seed_data = json.load(f)
                    status['seed_registry'] = {
                        'cases': len(seed_data.get('cases', [])),
                        'statutes': len(seed_data.get('statutes', [])),
                    }
        except Exception:
            pass
        
        return status
