"""
OutClaw Hybrid Intelligence System
Code Judo: Using Fraud Against Itself

Phase 1 Implementation: Citation Graph Foundation
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import networkx as nx
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
# ═══════════════════════════════════════════════════════
#  OUTCLAW_HYBRID_INTELLIGENCE
# ═══════════════════════════════════════════════════════════════

class CitationNode:
    """Represents a legal citation in the knowledge graph"""
    id: str
    citation_string: str
    case_name: str
    year: int
    court: str
    verified: bool = False
    trust_score: float = 0.5
    verification_sources: List[str] = field(default_factory=list)
    first_seen: datetime = field(default_factory=datetime.now)
    last_verified: Optional[datetime] = None
    incoming_citations: List[str] = field(default_factory=list)
    outgoing_citations: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class CitationEdge:
    """Represents a citation relationship"""
    citing_case: str
    cited_case: str
    context: str = ""
    relationship_type: str = "cites"  # cites, overrules, distinguishes, follows
    verified: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


class CitationGraph:
    """
    Knowledge graph of legal citations for fraud detection.
    
    Uses graph theory to detect:
    - Citation islands (fake cases citing each other)
    - Temporal impossibilities (future citations)
    - Orphan citations (no verified sources)
    - Broken citation chains
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, CitationNode] = {}
        self.verified_nodes: Set[str] = set()
        self.suspicious_clusters: List[Set[str]] = []
        self.temporal_anomalies: List[Tuple[str, str, str]] = []
        
    def add_citation(self, citing_case: str, cited_case: str, 
                    citing_year: int, cited_year: int,
                    metadata: Optional[Dict] = None) -> bool:
        """
        Add citation relationship with temporal validation.
        
        Returns:
            True if citation added, False if rejected (temporal anomaly)
        """
        # Temporal validation: citing case must be after cited case
        if citing_year < cited_year:
            self.temporal_anomalies.append((
                citing_case, 
                cited_case, 
                f"Citing case ({citing_year}) predates cited case ({cited_year})"
            ))
            logger.warning(f"Temporal anomaly: {citing_case} ({citing_year}) cites {cited_case} ({cited_year})")
            return False
        
        # Add nodes if they don't exist
        if citing_case not in self.nodes:
            self.nodes[citing_case] = CitationNode(
                id=citing_case,
                citation_string=citing_case,
                case_name=citing_case,
                year=citing_year,
                court="unknown"
            )
        
        if cited_case not in self.nodes:
            self.nodes[cited_case] = CitationNode(
                id=cited_case,
                citation_string=cited_case,
                case_name=cited_case,
                year=cited_year,
                court="unknown"
            )
        
        # Add edge
        self.graph.add_edge(citing_case, cited_case, **(metadata or {}))
        
        # Update node relationships
        self.nodes[citing_case].outgoing_citations.append(cited_case)
        self.nodes[cited_case].incoming_citations.append(citing_case)
        
        return True
    
    def mark_verified(self, case_id: str, source: str):
        """Mark a citation as verified from a trusted source"""
        if case_id in self.nodes:
            self.nodes[case_id].verified = True
            self.nodes[case_id].verification_sources.append(source)
            self.nodes[case_id].last_verified = datetime.now()
            self.verified_nodes.add(case_id)
            
            # Increase trust score
            self.nodes[case_id].trust_score = min(1.0, self.nodes[case_id].trust_score + 0.2)
    
    def detect_citation_islands(self, min_cluster_size: int = 3) -> List[Set[str]]:
        """
        Find clusters of cases that only cite each other (potential fraud).
        
        Citation islands are groups of cases that:
        1. Cite each other extensively
        2. Have few or no citations from verified sources
        3. Are isolated from the main citation network
        """
        islands = []
        
        # Find strongly connected components
        components = list(nx.strongly_connected_components(self.graph))
        
        for component in components:
            if len(component) < min_cluster_size:
                continue
            
            # Check if component is isolated
            if self._is_isolated_cluster(component):
                islands.append(component)
                logger.warning(f"Citation island detected: {component}")
        
        self.suspicious_clusters = islands
        return islands
    
    def _is_isolated_cluster(self, cluster: Set[str]) -> bool:
        """
        Check if a cluster is isolated from verified citations.
        
        A cluster is isolated if:
        - Less than 20% of nodes are verified
        - Less than 30% of citations come from outside the cluster
        """
        verified_count = sum(1 for node in cluster if node in self.verified_nodes)
        verified_ratio = verified_count / len(cluster) if cluster else 0
        
        # Count external citations
        external_citations = 0
        total_citations = 0
        
        for node in cluster:
            for cited in self.nodes[node].incoming_citations:
                total_citations += 1
                if cited not in cluster:
                    external_citations += 1
        
        external_ratio = external_citations / total_citations if total_citations > 0 else 0
        
        return verified_ratio < 0.2 and external_ratio < 0.3
    
    def calculate_trust_score(self, case_id: str) -> float:
        """
        Calculate trust score based on graph position and verification.
        
        Factors:
        - PageRank (importance in citation network)
        - Verified citations (how many verified cases cite this)
        - Citation diversity (variety of citing sources)
        - Temporal consistency (no temporal anomalies)
        """
        if case_id not in self.nodes:
            return 0.0
        
        node = self.nodes[case_id]
        
        # Base score from verification
        score = 0.3 if node.verified else 0.0
        
        # PageRank contribution (importance in network)
        try:
            pagerank = nx.pagerank(self.graph).get(case_id, 0)
            score += pagerank * 0.3
        except:
            pass
        
        # Verified citations contribution
        verified_citations = sum(
            1 for citing in node.incoming_citations 
            if citing in self.verified_nodes
        )
        verified_ratio = verified_citations / max(1, len(node.incoming_citations))
        score += verified_ratio * 0.2
        
        # Citation diversity (not all from same source)
        unique_courts = len(set(
            self.nodes[citing].court 
            for citing in node.incoming_citations 
            if citing in self.nodes
        ))
        diversity_score = min(1.0, unique_courts / 5)  # 5+ courts = max diversity
        score += diversity_score * 0.2
        
        return min(1.0, score)
    
    def find_orphan_citations(self) -> List[str]:
        """
        Find citations with no verified incoming citations.
        
        Orphans are suspicious because legitimate cases are usually
        cited by other verified cases.
        """
        orphans = []
        
        for case_id, node in self.nodes.items():
            if case_id in self.verified_nodes:
                continue  # Skip verified cases
            
            # Check if any incoming citations are verified
            has_verified_citation = any(
                citing in self.verified_nodes 
                for citing in node.incoming_citations
            )
            
            if not has_verified_citation and len(node.incoming_citations) > 0:
                orphans.append(case_id)
        
        return orphans
    
    def analyze_citation_chain(self, case_id: str, max_depth: int = 5) -> Dict:
        """
        Analyze the citation chain for a case.
        
        Returns:
            Dict with chain analysis including:
            - depth: How many levels deep the chain goes
            - verified_ratio: % of chain that's verified
            - broken_links: Citations that lead nowhere
            - suspicious_patterns: Detected anomalies
        """
        if case_id not in self.nodes:
            return {'error': 'Case not found'}
        
        visited = set()
        chain = []
        broken_links = []
        
        def traverse(node_id, depth):
            if depth > max_depth or node_id in visited:
                return
            
            visited.add(node_id)
            chain.append(node_id)
            
            if node_id not in self.nodes:
                broken_links.append(node_id)
                return
            
            for cited in self.nodes[node_id].outgoing_citations:
                traverse(cited, depth + 1)
        
        traverse(case_id, 0)
        
        verified_count = sum(1 for c in chain if c in self.verified_nodes)
        
        return {
            'depth': len(chain),
            'verified_ratio': verified_count / len(chain) if chain else 0,
            'broken_links': broken_links,
            'chain': chain,
            'suspicious': len(broken_links) > len(chain) * 0.3  # >30% broken
        }
    
    def get_fraud_indicators(self, case_id: str) -> Dict:
        """
        Get comprehensive fraud indicators for a citation.
        
        Returns dict with:
        - trust_score: Overall trust (0-1)
        - is_orphan: No verified citations
        - in_island: Part of isolated cluster
        - temporal_issues: Date inconsistencies
        - chain_broken: Citation chain has breaks
        - recommendation: SAFE, SUSPICIOUS, or FRAUDULENT
        """
        if case_id not in self.nodes:
            return {'error': 'Case not found'}
        
        node = self.nodes[case_id]
        trust_score = self.calculate_trust_score(case_id)
        
        # Check if in citation island
        in_island = any(case_id in cluster for cluster in self.suspicious_clusters)
        
        # Check if orphan
        is_orphan = case_id in self.find_orphan_citations()
        
        # Check temporal issues
        temporal_issues = [
            anomaly for anomaly in self.temporal_anomalies
            if case_id in (anomaly[0], anomaly[1])
        ]
        
        # Analyze citation chain
        chain_analysis = self.analyze_citation_chain(case_id)
        
        # Calculate fraud risk
        risk_factors = sum([
            trust_score < 0.3,
            in_island,
            is_orphan,
            len(temporal_issues) > 0,
            chain_analysis.get('suspicious', False)
        ])
        
        if risk_factors >= 3:
            recommendation = "FRAUDULENT"
        elif risk_factors >= 1:
            recommendation = "SUSPICIOUS"
        else:
            recommendation = "SAFE"
        
        return {
            'case_id': case_id,
            'trust_score': trust_score,
            'is_orphan': is_orphan,
            'in_island': in_island,
            'temporal_issues': len(temporal_issues),
            'chain_broken': chain_analysis.get('suspicious', False),
            'verified': node.verified,
            'risk_factors': risk_factors,
            'recommendation': recommendation,
            'details': {
                'verification_sources': node.verification_sources,
                'incoming_citations': len(node.incoming_citations),
                'outgoing_citations': len(node.outgoing_citations),
                'chain_depth': chain_analysis.get('depth', 0),
                'chain_verified_ratio': chain_analysis.get('verified_ratio', 0)
            }
        }
    
    def export_graph_stats(self) -> Dict:
        """Export graph statistics for monitoring"""
        return {
            'total_nodes': len(self.nodes),
            'total_edges': self.graph.number_of_edges(),
            'verified_nodes': len(self.verified_nodes),
            'suspicious_clusters': len(self.suspicious_clusters),
            'temporal_anomalies': len(self.temporal_anomalies),
            'orphan_citations': len(self.find_orphan_citations()),
            'average_trust_score': sum(
                self.calculate_trust_score(n) for n in self.nodes
            ) / len(self.nodes) if self.nodes else 0
        }


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create citation graph
    graph = CitationGraph()
    
    # Add some legitimate citations
    graph.add_citation("Smith v. Jones, 100 F.3d 1", "Brown v. Board, 347 U.S. 483", 2020, 1954)
    graph.add_citation("Doe v. Roe, 200 F.3d 1", "Brown v. Board, 347 U.S. 483", 2021, 1954)
    graph.mark_verified("Brown v. Board, 347 U.S. 483", "courtlistener")
    
    # Add suspicious citation island
    graph.add_citation("FakeCase1 v. X", "FakeCase2 v. Y", 2022, 2022)
    graph.add_citation("FakeCase2 v. Y", "FakeCase3 v. Z", 2022, 2022)
    graph.add_citation("FakeCase3 v. Z", "FakeCase1 v. X", 2022, 2022)
    
    # Detect fraud
    islands = graph.detect_citation_islands()
    print(f"\n🏝️  Citation Islands Detected: {len(islands)}")
    for island in islands:
        print(f"   - {island}")
    
    # Analyze specific case
    print("\n📊 Fraud Analysis for 'FakeCase1 v. X':")
    analysis = graph.get_fraud_indicators("FakeCase1 v. X")
    for key, value in analysis.items():
        print(f"   {key}: {value}")
    
    # Graph stats
    print("\n📈 Graph Statistics:")
    stats = graph.export_graph_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
