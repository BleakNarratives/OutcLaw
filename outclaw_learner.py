#!/usr/bin/env python3
"""
outclaw_learner.py - AI-Powered Pattern Learner for OutClaw

This module implements a machine learning approach to discover new citation patterns
from real legal text, expanding OutClaw's semantic registry automatically.

Features:
- Pattern extraction from legal corpora
- Cluster-based pattern discovery
- Confidence scoring for new patterns
- Integration with existing SeedRegistry
- Continuous learning from new examples

Usage:
    python3 outclaw_learner.py train --corpus legal_texts.txt
    python3 outclaw_learner.py suggest --text "new legal document"
    python3 outclaw_learner.py export --output new_patterns.json
"""

import re
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict, Counter
from datetime import datetime
import hashlib

# Add OutClaw to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from outclaw_semantic import SeedRegistry
    HAS_SEMANTIC = True
except ImportError:
    HAS_SEMANTIC = False


# ═══════════════════════════════════════════════════════
#  PATTERN LEARNER
# ═══════════════════════════════════════════════════════════════

class PatternLearner:
    """
    Discovers new citation patterns from legal text using statistical analysis.
    """
    
    # Known citation pattern prefixes/suffixes
    CITATION_MARKERS = [
        # Statutes
        r'\d+\s+U\.S\.C\.',
        r'\d+\s+C\.F\.R\.',
        r'§\s*\d+',
        # Cases
        r'\d+\s+F\.\s*\d+d\s+\d+',
        r'\d+\s+U\.S\.\s+\d+',
        # State
        r'[A-Z][a-z]+\s+Code\s+§',
        r'[A-Z]{2}\s+[A-Z][a-z]+\s+Stat\.',
    ]
    
    # Common citation verbs
    CITATION_VERBS = [
        'held', 'ruled', 'found', 'stated', 'decided', 'established',
        'cited', 'quotes', 'references', 'pursuant', 'under',
        'according', 'see', 'but see', 'cf', 'contra',
    ]
    
    # Legal area keywords
    LEGAL_AREAS = [
        'criminal', 'civil', 'contract', 'tort', 'property', 'family',
        'constitutional', 'administrative', 'tax', 'securities', 'labor',
        'intellectual property', 'environmental', 'international',
    ]
    
    def __init__(self, min_support: int = 3, min_confidence: float = 0.7):
        """
        Initialize the pattern learner.
        
        Args:
            min_support: Minimum number of examples for a pattern to be considered
            min_confidence: Minimum confidence score (0-1) for a pattern
        """
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.patterns = defaultdict(dict)  # pattern -> {count, examples, confidence}
        self.verb_contexts = defaultdict(Counter)
        self.area_contexts = defaultdict(Counter)
        self.learned_at = {}
        self.version = "1.0.0"
        
    def extract_candidates(self, text: str) -> List[Tuple[str, str, int, int]]:
        """
        Extract potential citation candidates from text.
        
        Returns: List of (candidate_text, context, start_pos, end_pos)
        """
        candidates = []
        
        # Remove existing known patterns to find new ones
        for marker in self.CITATION_MARKERS:
            pattern = re.compile(marker, re.IGNORECASE)
            for match in pattern.finditer(text):
                start, end = match.span()
                # Expand context window
                context_start = max(0, start - 100)
                context_end = min(len(text), end + 100)
                context = text[context_start:context_end]
                candidates.append((match.group(0), context, start, end))
        
        # Also look for verb-based patterns
        for verb in self.CITATION_VERBS:
            verb_pattern = re.compile(r'\b' + verb + r'\b', re.IGNORECASE)
            for match in verb_pattern.finditer(text):
                # Look for citation-like text near the verb
                search_start = max(0, match.end())
                search_end = min(len(text), match.end() + 50)
                snippet = text[search_start:search_end]
                if any(char.isdigit() for char in snippet):
                    candidates.append((verb, snippet, match.start(), match.end()))
        
        return candidates
    
    def analyze_context(self, context: str) -> Dict[str, Any]:
        """
        Analyze the context around a citation candidate.
        """
        words = re.findall(r'[a-z]+', context.lower())
        
        features = {
            'word_count': len(words),
            'verbs': defaultdict(int),
            'legal_areas': defaultdict(int),
            'has_number': any(char.isdigit() for char in context),
            'has_section': '§' in context,
            'has_usc': 'u.s.c' in context.lower(),
            'has_cfr': 'c.f.r' in context.lower(),
            'has_f3d': re.search(r'\d+\s+f\.?\s*\d+d', context, re.IGNORECASE) is not None,
        }
        
        for word in words:
            if word in self.CITATION_VERBS:
                features['verbs'][word] += 1
            if word in [a.replace(' ', '_') for a in self.LEGAL_AREAS]:
                features['legal_areas'][word] += 1
        
        return features
    
    def learn_from_text(self, text: str, source: str = "unknown") -> Dict[str, Any]:
        """
        Learn new patterns from a legal text document.
        
        Args:
            text: The legal text to analyze
            source: Identifier for the source of the text
            
        Returns: Summary of what was learned
        """
        candidates = self.extract_candidates(text)
        new_patterns = 0
        updated_patterns = 0
        
        for candidate, context, start, end in candidates:
            # Normalize the candidate
            normalized = self._normalize(candidate)
            
            if not normalized or len(normalized) < 3:
                continue
            
            # Analyze context
            features = self.analyze_context(context)
            
            # Calculate confidence score
            confidence = self._calculate_confidence(features)
            
            if confidence < self.min_confidence:
                continue
            
            # Update pattern statistics
            if normalized not in self.patterns:
                self.patterns[normalized] = {
                    'count': 0,
                    'examples': [],
                    'confidence': 0.0,
                    'features': defaultdict(int),
                    'sources': set(),
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                }
                new_patterns += 1
            
            self.patterns[normalized]['count'] += 1
            self.patterns[normalized]['examples'].append({
                'text': candidate,
                'context': context[:100],
                'source': source,
                'timestamp': datetime.now().isoformat(),
            })
            self.patterns[normalized]['sources'].add(source)
            self.patterns[normalized]['last_seen'] = datetime.now().isoformat()
            
            # Update features
            for feature, value in features.items():
                if isinstance(value, dict):
                    for k, v in value.items():
                        self.patterns[normalized]['features'][f' {k}'] = (
                            self.patterns[normalized]['features'].get(f' {k}', 0) + v
                        )
                else:
                    self.patterns[normalized]['features'][feature] = (
                        self.patterns[normalized]['features'].get(feature, 0) + (1 if value else 0)
                    )
            
            # Recalculate confidence
            self.patterns[normalized]['confidence'] = min(
                1.0,
                self.patterns[normalized]['count'] / self.min_support * 0.3 + confidence * 0.7
            )
            
            if normalized in self.patterns:
                updated_patterns += 1
        
        return {
            'new_patterns': new_patterns,
            'updated_patterns': updated_patterns,
            'total_patterns': len(self.patterns),
            'source': source,
            'timestamp': datetime.now().isoformat(),
        }
    
    def _normalize(self, text: str) -> str:
        """Normalize a pattern for comparison."""
        text = text.strip()
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Standardize common variations
        text = text.replace('U.S.C.', 'USC')
        text = text.replace('C.F.R.', 'CFR')
        text = text.replace('§', 'section')
        return text.lower()
    
    def _calculate_confidence(self, features: Dict[str, Any]) -> float:
        """Calculate confidence score for a pattern based on features."""
        score = 0.0
        
        # Base score
        score += 0.2
        
        # Has numbers (likely a citation)
        if features.get('has_number', False):
            score += 0.25
        
        # Has section symbol
        if features.get('has_section', False):
            score += 0.2
        
        # Has known citation markers
        if features.get('has_usc', False):
            score += 0.2
        if features.get('has_cfr', False):
            score += 0.2
        if features.get('has_f3d', False):
            score += 0.2
        
        # Has citation verbs nearby
        verb_count = sum(features.get('verbs', {}).values())
        if verb_count > 0:
            score += min(0.15, verb_count * 0.05)
        
        return min(1.0, score)
    
    def get_suggestions(self, min_confidence: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Get pattern suggestions sorted by confidence and support.
        """
        min_conf = min_confidence if min_confidence is not None else self.min_confidence
        
        suggestions = []
        for pattern, data in self.patterns.items():
            if data['count'] >= self.min_support and data['confidence'] >= min_conf:
                suggestions.append({
                    'pattern': pattern,
                    'normalized': pattern,
                    'count': data['count'],
                    'confidence': round(data['confidence'], 3),
                    'examples': data['examples'][:3],
                    'sources': list(data['sources']),
                    'first_seen': data['first_seen'],
                    'last_seen': data['last_seen'],
                    'features': dict(data['features']),
                })
        
        # Sort by confidence, then support
        suggestions.sort(key=lambda x: (x['confidence'], x['count']), reverse=True)
        return suggestions
    
    def integrate_with_registry(self, registry: 'SeedRegistry') -> Dict[str, Any]:
        """
        Integrate learned patterns into an existing SeedRegistry.
        
        Adds new patterns to the registry based on what's been learned.
        """
        if not HAS_SEMANTIC:
            return {'error': 'SeedRegistry not available'}
        
        suggestions = self.get_suggestions(min_confidence=0.8)
        integrated = 0
        
        for suggestion in suggestions:
            pattern = suggestion['pattern']
            
            # Determine category based on features
            category = self._classify_pattern(pattern, suggestion['features'])
            
            if category:
                # Add to the appropriate category
                weight = 1.0 + (suggestion['confidence'] * 0.3)
                registry.signals[category]['patterns'].append(pattern)
                integrated += 1
        
        # Recompile patterns
        registry._compile_patterns()
        
        return {
            'integrated': integrated,
            'suggestions': suggestions,
            'registry_size': {
                'SUPPORT': len(registry.signals['SUPPORT']['patterns']),
                'OPPOSE': len(registry.signals['OPPOSE']['patterns']),
                'NEUTRAL': len(registry.signals['NEUTRAL']['patterns']),
            }
        }
    
    def _classify_pattern(self, pattern: str, features: Dict[str, int]) -> Optional[str]:
        """Classify a learned pattern into SUPPORT, OPPOSE, or NEUTRAL."""
        pattern_lower = pattern.lower()
        
        # Check for opposite signals
        oppose_indicators = ['see also', 'but see', 'cf', 'contra', 'however', 
                           'nevertheless', 'distinguish', 'reject', 'overrule',
                           'disagree', 'contrary']
        for indicator in oppose_indicators:
            if indicator in pattern_lower:
                return 'OPPOSE'
        
        # Check for support signals
        support_indicators = ['held', 'ruled', 'established', 'pursuant', 
                             'under', 'provided', 'accord', 'consistent', 'relies',
                             'cites', 'supports', 'confirms', 'quoted']
        for indicator in support_indicators:
            if indicator in pattern_lower:
                return 'SUPPORT'
        
        # Check for neutral signals
        neutral_indicators = ['see generally', 'compare', 'contrast', 'mentioned',
                            'referenced', 'noted', 'discussed']
        for indicator in neutral_indicators:
            if indicator in pattern_lower:
                return 'NEUTRAL'
        
        # Default based on context features
        if features.get('has_usc', 0) or features.get('has_cfr', 0) or features.get('has_f3d', 0):
            return 'SUPPORT'  # Citations are typically supportive
        
        return None  # Not enough information to classify
    
    def export_patterns(self, output_path: str) -> str:
        """Export learned patterns to a JSON file."""
        suggestions = self.get_suggestions()
        
        export_data = {
            'metadata': {
                'exporter': 'OutClaw Pattern Learner',
                'version': self.version,
                'export_time': datetime.now().isoformat(),
                'min_support': self.min_support,
                'min_confidence': self.min_confidence,
            },
            'patterns': [
                {
                    'pattern': p['pattern'],
                    'normalized': p['normalized'],
                    'category': self._classify_pattern(p['pattern'], p['features']),
                    'count': p['count'],
                    'confidence': p['confidence'],
                    'sources': p['sources'],
                    'first_seen': p['first_seen'],
                    'examples': p['examples'],
                }
                for p in suggestions
            ],
            'stats': {
                'total_patterns': len(suggestions),
                'by_category': self._count_by_category(suggestions),
            }
        }
        
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        return output_path
    
    def _count_by_category(self, suggestions: List[Dict]) -> Dict[str, int]:
        """Count patterns by their inferred category."""
        counts = {'SUPPORT': 0, 'OPPOSE': 0, 'NEUTRAL': 0, 'UNKNOWN': 0}
        for s in suggestions:
            category = self._classify_pattern(s['pattern'], s['features'])
            counts[category if category else 'UNKNOWN'] += 1
        return counts
    
    def load_corpus(self, corpus_path: str) -> Dict[str, Any]:
        """
        Load and learn from a corpus of legal documents.
        
        Args:
            corpus_path: Path to a text file or directory of text files
            
        Returns: Summary of learning results
        """
        path = Path(corpus_path)
        total_docs = 0
        total_patterns_learned = 0
        
        if path.is_file():
            with open(path, 'r') as f:
                text = f.read()
            result = self.learn_from_text(text, path.name)
            total_docs = 1
            total_patterns_learned = result['new_patterns']
        elif path.is_dir():
            for txt_file in path.glob('*.txt'):
                with open(txt_file, 'r') as f:
                    text = f.read()
                result = self.learn_from_text(text, txt_file.name)
                total_docs += 1
                total_patterns_learned += result['new_patterns']
        
        return {
            'documents_processed': total_docs,
            'total_patterns_learned': total_patterns_learned,
            'total_patterns_in_learner': len(self.patterns),
            'timestamp': datetime.now().isoformat(),
        }
    
    def save_state(self, state_path: str) -> None:
        """Save the learner's state to a file."""
        state = {
            'version': self.version,
            'min_support': self.min_support,
            'min_confidence': self.min_confidence,
            'patterns': {
                k: {
                    'count': v['count'],
                    'confidence': v['confidence'],
                    'examples': v['examples'],
                    'sources': list(v['sources']),
                    'first_seen': v['first_seen'],
                    'last_seen': v['last_seen'],
                    'features': dict(v['features']),
                }
                for k, v in self.patterns.items()
            },
            'saved_at': datetime.now().isoformat(),
        }
        
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)
    
    def load_state(self, state_path: str) -> None:
        """Load the learner's state from a file."""
        with open(state_path, 'r') as f:
            state = json.load(f)
        
        self.version = state.get('version', '1.0.0')
        self.min_support = state.get('min_support', 3)
        self.min_confidence = state.get('min_confidence', 0.7)
        
        for pattern, data in state.get('patterns', {}).items():
            self.patterns[pattern] = {
                'count': data['count'],
                'confidence': data['confidence'],
                'examples': data['examples'],
                'sources': set(data['sources']),
                'first_seen': data['first_seen'],
                'last_seen': data['last_seen'],
                'features': Counter(data['features']),
            }


# ═══════════════════════════════════════════════════════
#  SWARM INTELLIGENCE
# ═══════════════════════════════════════════════════════════════

class SwarmIntelligence:
    """
    Multi-model consensus system for citation validation.
    
    Collects votes from multiple AI models and uses consensus
    to determine citation validity with higher confidence.
    """
    
    def __init__(self):
        self.votes = {}  # citation_hash -> {model: vote}
        self.models = {'mistral', 'claude', 'gemini', 'deepseek'}
        self.thresholds = {
            'SUPPORT': 0.7,
            'OPPOSE': 0.7,
            'NEUTRAL': 0.5,
        }
    
    def record_vote(self, citation: str, model: str, vote: str, confidence: float, 
                   reason: str = "") -> None:
        """
        Record a vote from a model on a citation.
        
        Args:
            citation: The citation text
            model: Which AI model voted (mistral, claude, gemini, deepseek)
            vote: SUPPORT, OPPOSE, or NEUTRAL
            confidence: 0-1 confidence score
            reason: Optional reason for the vote
        """
        citation_hash = hashlib.sha256(citation.encode()).hexdigest()[:16]
        
        if citation_hash not in self.votes:
            self.votes[citation_hash] = {}
        
        self.votes[citation_hash][model] = {
            'vote': vote,
            'confidence': confidence,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'citation': citation,
        }
    
    def get_consensus(self, citation: str) -> Dict[str, Any]:
        """
        Get the consensus vote for a citation.
        
        Returns: Consensus result with weighted voting
        """
        citation_hash = hashlib.sha256(citation.encode()).hexdigest()[:16]
        
        if citation_hash not in self.votes:
            return {'citation': citation, 'consensus': None, 'votes': {}}
        
        votes_data = self.votes[citation_hash]
        
        # Calculate weighted consensus
        vote_counts = {'SUPPORT': 0.0, 'OPPOSE': 0.0, 'NEUTRAL': 0.0}
        total_weight = 0.0
        
        for model, vote_info in votes_data.items():
            weight = vote_info['confidence']
            vote_counts[vote_info['vote']] += weight
            total_weight += weight
        
        if total_weight == 0:
            return {'citation': citation, 'consensus': None, 'votes': votes_data}
        
        # Normalize
        for vote_type in vote_counts:
            vote_counts[vote_type] /= total_weight
        
        # Determine consensus
        consensus = max(vote_counts.items(), key=lambda x: x[1])
        
        return {
            'citation': citation,
            'consensus': consensus[0],
            'confidence': consensus[1],
            'votes': votes_data,
            'vote_counts': {k: round(v, 3) for k, v in vote_counts.items()},
            'quorum': len(votes_data) / len(self.models),
        }
    
    def is_consensus_strong(self, citation: str, min_quorum: float = 0.5, 
                           min_confidence: float = 0.7) -> bool:
        """
        Check if consensus is strong enough to trust.
        """
        result = self.get_consensus(citation)
        if result['consensus'] is None:
            return False
        
        return (result['quorum'] >= min_quorum and 
                result['confidence'] >= min_confidence)
    
    def export_consensus_report(self, output_path: str) -> str:
        """Export full consensus report to JSON."""
        report = {
            'metadata': {
                'generated': datetime.now().isoformat(),
                'models': list(self.models),
                'total_citations': len(self.votes),
            },
            'consensus': {
                c_hash: {
                    'citation': data[c_hash]['citation'],
                    **self.get_consensus(data[c_hash]['citation'])
                }
                for c_hash, data in self.votes.items()
            }
        }
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        return output_path


# ═══════════════════════════════════════════════════════
#  BRAIN — central intelligence
# ═══════════════════════════════════════════════════════════════

class OutClawBrain:
    """
    The central intelligence layer for OutClaw.
    
    Combines:
    - Pattern learning from legal text
    - Multi-model consensus voting
    - Real-time sync bus integration
    - Continuous improvement
    """
    
    def __init__(self):
        self.learner = PatternLearner()
        self.swarm = SwarmIntelligence()
        self.sync_bus_path = Path.home() / '.outclaw' / 'sync_bus'
        self.registry_path = Path(__file__).parent / 'OutClaw' / 'outclaw_seed.json'
        
    def process_document(self, text: str, source: str = "api") -> Dict[str, Any]:
        """
        Process a legal document through the full OutClaw brain.
        
        Steps:
        1. Learn new patterns from the text
        2. Extract citations using both learned and built-in patterns
        3. Return comprehensive analysis
        """
        # Step 1: Learn from the text
        learn_result = self.learner.learn_from_text(text, source)
        
        # Step 2: Get suggestions for new patterns
        suggestions = self.learner.get_suggestions()
        
        # Step 3: Extract citations using existing patterns
        candidates = self.learner.extract_candidates(text)
        
        return {
            'document': {
                'source': source,
                'length': len(text),
                'timestamp': datetime.now().isoformat(),
            },
            'learning': learn_result,
            'suggestions': suggestions[:10],  # Top 10 suggestions
            'candidates': [
                {
                    'text': c[0],
                    'context': c[1][:100],
                    'position': (c[2], c[3]),
                }
                for c in candidates
            ],
            'stats': {
                'total_candidates': len(candidates),
                'total_suggestions': len(suggestions),
                'total_learned_patterns': len(self.learner.patterns),
            }
        }
    
    def record_model_vote(self, citation: str, model: str, vote: str, 
                         confidence: float, reason: str = "") -> Dict[str, Any]:
        """
        Record a vote from an AI model on a citation.
        """
        self.swarm.record_vote(citation, model, vote, confidence, reason)
        consensus = self.swarm.get_consensus(citation)
        
        return {
            'citation': citation,
            'model': model,
            'vote': vote,
            'confidence': confidence,
            'consensus': consensus,
        }
    
    def get_full_analysis(self, citation: str) -> Dict[str, Any]:
        """
        Get complete analysis of a citation including:
        - Semantic analysis
        - Multi-model consensus
        - Pattern suggestions
        """
        result = {
            'citation': citation,
            'timestamp': datetime.now().isoformat(),
        }
        
        # Get consensus
        consensus = self.swarm.get_consensus(citation)
        result['consensus'] = consensus
        
        # Get pattern analysis
        candidates = self.learner.extract_candidates(citation)
        result['pattern_analysis'] = [
            {
                'text': c[0],
                'context': c[1][:100] if len(c) > 1 else '',
            }
            for c in candidates
        ]
        
        return result
    
    def save_state(self, state_dir: str = None) -> Dict[str, str]:
        """Save the complete brain state."""
        if state_dir is None:
            state_dir = str(self.sync_bus_path / 'state')
        
        Path(state_dir).mkdir(parents=True, exist_ok=True)
        
        learner_path = Path(state_dir) / 'learner_state.json'
        self.learner.save_state(learner_path)
        
        # Save swarm state
        swarm_data = {
            'votes': {
                c_hash: {
                    m: {
                        'vote': v['vote'],
                        'confidence': v['confidence'],
                        'reason': v['reason'],
                        'timestamp': v['timestamp'],
                    }
                    for m, v in votes.items()
                }
                for c_hash, votes in self.swarm.votes.items()
            }
        }
        swarm_path = Path(state_dir) / 'swarm_state.json'
        with open(swarm_path, 'w') as f:
            json.dump(swarm_data, f, indent=2)
        
        return {
            'learner_state': str(learner_path),
            'swarm_state': str(swarm_path),
        }
    
    def load_state(self, state_dir: str = None) -> Dict[str, str]:
        """Load the complete brain state."""
        if state_dir is None:
            state_dir = str(self.sync_bus_path / 'state')
        
        learner_path = Path(state_dir) / 'learner_state.json'
        if learner_path.exists():
            self.learner.load_state(learner_path)
        
        swarm_path = Path(state_dir) / 'swarm_state.json'
        if swarm_path.exists():
            with open(swarm_path, 'r') as f:
                swarm_data = json.load(f)
            for c_hash, votes in swarm_data.get('votes', {}).items():
                for model, vote_info in votes.items():
                    # Find the citation
                    citation = vote_info.get('citation', c_hash)
                    self.swarm.record_vote(
                        citation, model, vote_info['vote'], 
                        vote_info['confidence'], vote_info.get('reason', '')
                    )
        
        return {
            'learner_loaded': learner_path.exists(),
            'swarm_loaded': swarm_path.exists(),
        }


# ═══════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

def main():
    """CLI for OutClaw Brain."""
    import argparse
    
    parser = argparse.ArgumentParser(description='OutClaw Brain - AI Learning & Consensus')
    subparsers = parser.add_subparsers(dest='command')
    
    # Train command
    train_parser = subparsers.add_parser('train', help='Train on legal text')
    train_parser.add_argument('corpus', help='Text file or directory of text files')
    train_parser.add_argument('--min-support', type=int, default=3, help='Minimum support count')
    train_parser.add_argument('--min-confidence', type=float, default=0.7, help='Minimum confidence')
    
    # Suggest command
    suggest_parser = subparsers.add_parser('suggest', help='Get pattern suggestions')
    suggest_parser.add_argument('--min-confidence', type=float, default=0.7)
    suggest_parser.add_argument('--output', help='Export to JSON file')
    
    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze a citation')
    analyze_parser.add_argument('citation', help='Citation text to analyze')
    
    # Vote command
    vote_parser = subparsers.add_parser('vote', help='Record a model vote')
    vote_parser.add_argument('citation', help='Citation text')
    vote_parser.add_argument('model', help='Model name (mistral, claude, gemini, deepseek)')
    vote_parser.add_argument('vote', choices=['SUPPORT', 'OPPOSE', 'NEUTRAL'], help='Vote type')
    vote_parser.add_argument('confidence', type=float, help='Confidence score (0-1)')
    vote_parser.add_argument('--reason', default='', help='Reason for vote')
    
    # Consensus command
    consensus_parser = subparsers.add_parser('consensus', help='Get consensus for a citation')
    consensus_parser.add_argument('citation', help='Citation text')
    
    # Process command
    process_parser = subparsers.add_parser('process', help='Process a legal document')
    process_parser.add_argument('file', help='Text file to process')
    
    args = parser.parse_args()
    
    brain = OutClawBrain()
    
    if args.command == 'train':
        result = brain.learner.load_corpus(args.corpus)
        print(f"Trained on {result['documents_processed']} documents")
        print(f"Learned {result['total_patterns_learned']} new patterns")
        print(f"Total patterns: {result['total_patterns_in_learner']}")
        
    elif args.command == 'suggest':
        suggestions = brain.learner.get_suggestions(args.min_confidence)
        print(f"Found {len(suggestions)} pattern suggestions:")
        for i, s in enumerate(suggestions[:10], 1):
            cat = brain.learner._classify_pattern(s['pattern'], s['features'])
            print(f"  {i}. {s['pattern']:30} | {cat:8} | conf={s['confidence']:.2f} | count={s['count']}")
        
        if args.output:
            brain.learner.export_patterns(args.output)
            print(f"Exported to {args.output}")
        
    elif args.command == 'analyze':
        result = brain.get_full_analysis(args.citation)
        print(json.dumps(result, indent=2))
        
    elif args.command == 'vote':
        result = brain.record_model_vote(
            args.citation, args.model, args.vote, args.confidence, args.reason
        )
        print(json.dumps(result, indent=2))
        
    elif args.command == 'consensus':
        consensus = brain.swarm.get_consensus(args.citation)
        print(json.dumps(consensus, indent=2))
        
    elif args.command == 'process':
        with open(args.file, 'r') as f:
            text = f.read()
        result = brain.process_document(text, args.file)
        print(json.dumps(result, indent=2))
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
