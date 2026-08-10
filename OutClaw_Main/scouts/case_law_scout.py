#!/usr/bin/env python3
"""
OutClaw Case Law Scout
Paralegal Superpowers: Legal Precedent Research

Searches for:
- Relevant case law
- Similar fact patterns
- Winning arguments
- Adverse rulings to avoid
- Circuit splits
- Recent developments

Based on Blindsight EDGAR scout architecture.
Zero cost. Maximum legal intelligence.
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse
import re
from pathlib import Path
from datetime import datetime, timedelta

# Shared jurisdiction detection: jurisdiction is a FACT of the case, and
# is auto-detected from arrest reports, court names, and statute cites.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jurisdiction import detect_jurisdiction, normalize_jurisdiction  # noqa: E402

HEADERS = {
    'User-Agent': 'OutClaw-CaseLaw-Scout/1.0 research@outclaw.legal'
}

# Free legal research sources
SOURCES = {
    'courtlistener': 'https://www.courtlistener.com/api/rest/v3/search/',
    'justia': 'https://law.justia.com/search/',
    'google_scholar': 'https://scholar.google.com/scholar',
    'casetext': 'https://casetext.com/search',
    'findlaw': 'https://caselaw.findlaw.com/search'
}

# ---------------------------------------------------------------------------
# Jurisdiction pinning
# ---------------------------------------------------------------------------
# CourtListener's `court` filter ONLY accepts court IDs ("kan", "kanctapp"),
# never free text like "Sumner County, Kansas, 30th judicial district". An
# unknown ID is silently ignored by the API, which is exactly how unrelated
# states (Oklahoma, etc.) leak into the results. These maps translate user
# intent into real API filters AND post-filter every result by state so
# out-of-state noise never reaches the dossier.

JURISDICTION_META = {
    "kansas": {
        "court_ids": ["kan", "kanctapp"],
        "state_terms": ["kansas", "kan."],
        "exclude_terms": ["oklahoma", "okla.", "missouri", "colorado", "nebraska"],
        "site_terms": ["site:kscourts.org", "site:ks.gov", "site:wellingtonks.org"],
    },
    "oklahoma": {
        "court_ids": ["okla", "oklactapp", "oklactcivapp", "oklacrimapp"],
        "state_terms": ["oklahoma", "okla."],
        "exclude_terms": ["kansas"],
        "site_terms": ["site:oscn.net", "site:ok.gov"],
    },
    "federal": {
        "court_ids": [],
        "state_terms": [],
        "exclude_terms": [],
        "site_terms": [],
    },
}

# CourtListener court IDs for state appellate courts we may pin to.
KNOWN_COURT_IDS = set().union(*[meta["court_ids"] for meta in JURISDICTION_META.values()])


def _normalize_jurisdiction(jurisdiction):
    """Normalize a jurisdiction string (delegates to the shared module)."""
    return normalize_jurisdiction(jurisdiction)


def load_case_profile(profile_path):
    """Load an OutClaw case profile (e.g. case_context.json)."""
    path = Path(profile_path)
    if not path.exists() and not path.is_absolute():
        # Fall back to the scout's own directory so the default profile
        # resolves even when run from another working directory.
        alt = Path(__file__).resolve().parent / path
        if alt.exists():
            path = alt
    if not path.exists():
        raise FileNotFoundError(f"Case profile not found: {profile_path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Words that add no signal to a compact search query.
_QUERY_STOPWORDS = {
    'the', 'and', 'for', 'with', 'without', 'that', 'this', 'from', 'into',
    'under', 'upon', 'before', 'after', 'their', 'which', 'where', 'when',
    'while', 'would', 'should', 'must', 'have', 'has', 'had', 'was', 'were',
    'are', 'not', 'use', 'used', 'using', 'of', 'in', 'on', 'at', 'by', 'to',
    'a', 'an', 'or', 'as', 'is', 'be', 'been', 'being',
}


def _compact_query(text, max_words=8):
    """Turn a long natural-language issue into a compact keyword query.

    CourtListener/Google do poorly with 40-word sentences; they do well
    with a handful of distinctive keywords.
    """
    cleaned = re.sub(r'\([^)]*\)', ' ', str(text))
    cleaned = re.sub(r'[;:,."“”]+', ' ', cleaned)
    words = [
        w for w in cleaned.split()
        if len(w) > 2 and w.lower() not in _QUERY_STOPWORDS
    ]
    if not words:
        return str(text).strip()[:80]
    return ' '.join(words[:max_words])


class CaseLawScout:
    """
    Scout case law for relevant precedents and legal arguments.
    
    Free sources:
    - CourtListener (20M+ opinions, free API)
    - Google Scholar (comprehensive, free)
    - Justia (free case law)
    - Casetext (limited free)
    - FindLaw (free case summaries)
    """
    
    def __init__(self, output_dir='../OutClaw_Research'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dossier = {
            'timestamp': datetime.utcnow().isoformat(),
            'scout_type': 'case_law',
            'research_queries': [],
            'cases_found': [],
            'legal_arguments': [],
            'flags': [],
            'summary': ''
        }
    
    def search_courtlistener(self, query, court=None, date_range=None, jurisdiction=None):
        """
        Search CourtListener for case law.
        
        CourtListener advantages:
        - Free API (no key required for basic search)
        - 20M+ opinions
        - Federal and state courts
        - Full text search
        - Citation network
        
        `court` is a free-text court name ("Sumner County, Kansas, 30th
        judicial district"). Free text is NEVER passed to the API's `court`
        parameter (which only accepts court IDs); instead it is folded into
        the keyword query, and known IDs are applied as real API filters.
        When `jurisdiction` is given, results are post-filtered by state so
        out-of-state cases are dropped before they reach the dossier.
        """
        
        params = {
            'q': query,
            'type': 'o',  # opinions
            'order_by': 'score desc'
        }
        
        # Translate free-text court / jurisdiction into real CourtListener
        # court-ID filters; fold unknown text into the keyword query.
        court_ids = []
        if court:
            tokens = [t.strip().lower() for t in re.split(r'[,;]|\s+', court) if t.strip()]
            court_ids = [t for t in tokens if t in KNOWN_COURT_IDS]
            free_text = [t for t in tokens if t not in KNOWN_COURT_IDS]
            if free_text:
                params['q'] = f"{query} {' '.join(free_text)}"
        if not court_ids and jurisdiction:
            meta = JURISDICTION_META.get(_normalize_jurisdiction(jurisdiction), {})
            court_ids = meta.get("court_ids", [])
        if court_ids:
            params['court'] = ' '.join(court_ids)
        
        if date_range:
            params['filed_after'] = date_range['start']
            params['filed_before'] = date_range['end']
        
        url = SOURCES['courtlistener'] + '?' + urllib.parse.urlencode(params)
        
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode())
            
            cases = []
            for result in data.get('results', [])[:20]:
                case = {
                    'source': 'CourtListener',
                    'case_name': result.get('caseName', 'Unknown'),
                    'court': result.get('court', 'Unknown'),
                    # CourtListener returns the court as an ID ("kan") plus
                    # display names in these fields; keep them for filtering.
                    'court_name': result.get('court_exact', '') or result.get('court_citation_string', '') or '',
                    'court_citation': result.get('court_citation_string', '') or '',
                    'date_filed': result.get('dateFiled', 'Unknown'),
                    'citation': result.get('citation', []),
                    'url': f"https://www.courtlistener.com{result.get('absolute_url', '')}",
                    'snippet': result.get('snippet', '')[:500],
                    'relevance_score': result.get('score', 0)
                }
                cases.append(case)
            
            if jurisdiction:
                cases = self._filter_by_jurisdiction(cases, jurisdiction)
            
            return cases
        
        except Exception as e:
            self.dossier['flags'].append(f"CourtListener search error: {e}")
            return []
    
    def search_google_scholar(self, query, court=None, date_range=None, jurisdiction=None):
        """
        Search Google Scholar for case law.
        
        Google Scholar advantages:
        - Comprehensive coverage
        - Free access
        - Citation analysis
        - "How cited" feature
        """
        
        # Build Google Scholar legal search URL
        base_url = "https://scholar.google.com/scholar"
        params = {
            'q': query,
            'hl': 'en',
            'as_sdt': '6',  # case law
            'as_vis': '1'   # include citations
        }
        
        # Fold the jurisdiction label into the query so Scholar returns
        # in-state authority, and drop cross-state results after parsing.
        if jurisdiction:
            norm = _normalize_jurisdiction(jurisdiction)
            state_label = "Kansas" if norm == "kansas" else "Oklahoma" if norm == "oklahoma" else jurisdiction
            params['q'] = f"{query} {state_label}"
        if court:
            court_label = re.sub(r'[^a-zA-Z0-9 ]', ' ', court).strip()
            if court_label:
                params['q'] = f"{params['q']} {court_label}"
        
        if date_range:
            params['as_ylo'] = date_range['start'][:4]  # year only
            params['as_yhi'] = date_range['end'][:4]
        
        url = base_url + '?' + urllib.parse.urlencode(params)
        
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as r:
                html = r.read().decode(errors='ignore')
            
            # Parse results (basic extraction)
            cases = []
            # Extract case titles
            titles = re.findall(r'<h3[^>]*><a[^>]*>(.*?)</a>', html)
            # Extract citations
            citations = re.findall(r'<div class="gs_a">(.*?)</div>', html)
            # Extract snippets
            snippets = re.findall(r'<div class="gs_rs">(.*?)</div>', html)
            
            for i in range(min(len(titles), 10)):
                case = {
                    'source': 'Google Scholar',
                    'case_name': re.sub(r'<[^>]+>', '', titles[i]).strip(),
                    'citation': re.sub(r'<[^>]+>', '', citations[i]).strip() if i < len(citations) else '',
                    'snippet': re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else '',
                    'url': url
                }
                cases.append(case)
            
            if jurisdiction:
                cases = self._filter_by_jurisdiction(cases, jurisdiction)
            
            return cases
        
        except Exception as e:
            self.dossier['flags'].append(f"Google Scholar search error: {e}")
            return []
    
    def _filter_by_jurisdiction(self, cases, jurisdiction):
        """
        Drop out-of-state results so the dossier stays pinned to the case.

        A case is kept only when it mentions the target state (or its
        reporter abbreviation or CourtListener court ID, e.g. "kan") and
        does not mention an excluded state. Dropped cases are recorded in
        the dossier so the run history shows exactly what was filtered
        (e.g. "3 Oklahoma cases dropped").
        """
        norm = _normalize_jurisdiction(jurisdiction)
        meta = JURISDICTION_META.get(norm, {})
        state_terms = meta.get("state_terms", [])
        exclude_terms = meta.get("exclude_terms", [])
        court_ids = meta.get("court_ids", [])
        if not state_terms and not exclude_terms and not court_ids:
            return cases

        kept, dropped = [], []
        for case in cases:
            court_id = str(case.get("court", "")).strip().lower()
            court_text = " ".join([
                court_id,
                case.get("court_name", ""),
                case.get("court_citation", ""),
            ]).lower()
            body_text = " ".join([
                case.get("case_name", ""),
                case.get("snippet", ""),
            ]).lower()

            # The court field is the authoritative state signal. Body text
            # (case name/snippet) is only a tiebreaker: Kansas opinions
            # routinely cite Oklahoma/Missouri authority, so a snippet
            # mention of an excluded state must NOT drop a case whose court
            # is Kansas.
            in_state_by_court = (
                (not state_terms and not court_ids)
                or any(t in court_text for t in state_terms)
                or court_id in court_ids
                or any(t in court_text for t in court_ids)
            )
            in_state_by_body = any(t in body_text for t in state_terms) if state_terms else False
            in_state = in_state_by_court or in_state_by_body
            out_state = (
                (not in_state_by_court)
                and any(t in body_text for t in exclude_terms)
            )
            if in_state and not out_state:
                kept.append(case)
            else:
                dropped.append(case)

        if dropped:
            self.dossier.setdefault("filtered_out_by_jurisdiction", []).append({
                "jurisdiction": jurisdiction,
                "dropped_count": len(dropped),
                "examples": [
                    {"case": c.get("case_name"), "court": c.get("court")}
                    for c in dropped[:5]
                ],
            })
            print(
                f"    > Jurisdiction filter ({jurisdiction}): dropped "
                f"{len(dropped)} out-of-state result(s), kept {len(kept)}"
            )

        return kept

    def build_research_queries(self, issue, jurisdiction=None, keywords=None):
        """
        Build comprehensive research queries for legal issue.
        
        Query strategies:
        - Issue-based: "hearsay exception business records"
        - Fact-based: "attorney misrepresentation discovery"
        - Procedural: "motion to compel sanctions"
        - Defensive: "defense to breach of contract"
        """
        
        queries = []
        state_label = ""
        
        # Core issue query — compact keyword phrase, not the raw sentence
        queries.append({
            'type': 'core_issue',
            'query': _compact_query(issue),
            'purpose': 'Find cases directly on point'
        })
        
        # Add jurisdiction if specified (Kansas-pinned searches use the full
        # state name so CourtListener/Google return in-state authority; the
        # issue is compacted so the API isn't throttled by a long sentence)
        if jurisdiction:
            norm = _normalize_jurisdiction(jurisdiction)
            state_label = "Kansas" if norm == "kansas" else "Oklahoma" if norm == "oklahoma" else str(jurisdiction)
            compact = _compact_query(issue)
            if state_label and state_label.lower() in compact.lower():
                query = compact
            else:
                query = f'{compact} {state_label}'.strip()
            queries.append({
                'type': 'jurisdictional',
                'query': query,
                'purpose': f'Find {state_label} precedent'
            })
        
        # Add keywords if specified (keyword alone + state label: compact,
        # effective, and far less likely to throttle the API than the full
        # issue sentence repeated per keyword). Skip the state label when
        # the keyword already contains it (e.g. "Wellington Kansas").
        if keywords:
            for keyword in keywords:
                kw = _compact_query(keyword)
                if state_label and state_label.lower() in kw.lower():
                    query = kw
                else:
                    query = f'{kw} {state_label}'.strip()
                queries.append({
                    'type': 'keyword_focused',
                    'query': query,
                    'purpose': f'Find cases involving {keyword}'
                })
        
        # Procedural variations
        procedural_terms = ['motion', 'objection', 'appeal', 'summary judgment']
        for term in procedural_terms:
            if term.lower() in issue.lower():
                queries.append({
                    'type': 'procedural',
                    'query': f'{issue} standard of review',
                    'purpose': 'Find procedural standards'
                })
                break
        
        # Defense/opposition research
        queries.append({
            'type': 'opposition',
            'query': f'defense {_compact_query(issue)}',
            'purpose': 'Anticipate opposing arguments'
        })
        
        # Deduplicate identical query strings (per type, so a jurisdictional
        # query that happens to match the core query is still preserved)
        seen, unique = set(), []
        for q in queries:
            key = f"{q['type']}|{q['query'].lower().strip()}"
            if key not in seen:
                seen.add(key)
                unique.append(q)
        return unique
    
    def research_issue(self, issue, jurisdiction=None, keywords=None, 
                      court=None, date_range=None):
        """
        Complete research on legal issue.
        
        Returns:
        - Relevant cases
        - Legal arguments
        - Procedural standards
        - Adverse authority
        """
        
        print(f"\n[*] Researching Legal Issue: {issue}")
        if jurisdiction:
            print(f"    Jurisdiction: {jurisdiction}")
        if keywords:
            print(f"    Keywords: {', '.join(keywords)}")
        
        # Build queries
        queries = self.build_research_queries(issue, jurisdiction, keywords)
        self.dossier['research_queries'] = queries
        
        all_cases = []
        
        for query_info in queries:
            query = query_info['query']
            print(f"\n  [{query_info['type'].upper()}] {query}")
            print(f"    Purpose: {query_info['purpose']}")
            
            # Search CourtListener
            print("    > Searching CourtListener...")
            cl_cases = self.search_courtlistener(query, court, date_range, jurisdiction)
            all_cases.extend(cl_cases)
            print(f"      Found: {len(cl_cases)} cases")
            
            # Search Google Scholar
            print("    > Searching Google Scholar...")
            gs_cases = self.search_google_scholar(query, court, date_range, jurisdiction)
            all_cases.extend(gs_cases)
            print(f"      Found: {len(gs_cases)} cases")
        
        # Deduplicate by case name. (Jurisdiction filtering already happens
        # inside each source, so out-of-state cases never reach this pool.)
        seen = set()
        unique_cases = []
        for case in all_cases:
            case_id = case.get('case_name', '') + case.get('date_filed', '')
            if case_id not in seen:
                seen.add(case_id)
                unique_cases.append(case)
        
        self.dossier['cases_found'] = unique_cases
        
        # Analyze cases
        self._analyze_cases(unique_cases, issue)
        
        return unique_cases
    
    def _analyze_cases(self, cases, issue):
        """
        Analyze cases for legal arguments and patterns.
        
        Extracts:
        - Winning arguments
        - Procedural standards
        - Key holdings
        - Adverse authority
        """
        
        analysis = {
            'total_cases': len(cases),
            'sources': {},
            'courts': {},
            'date_range': {'earliest': None, 'latest': None},
            'key_holdings': [],
            'winning_arguments': [],
            'adverse_authority': []
        }
        
        # Count by source
        for case in cases:
            source = case.get('source', 'Unknown')
            analysis['sources'][source] = analysis['sources'].get(source, 0) + 1
        
        # Count by court
        for case in cases:
            court = case.get('court', 'Unknown')
            analysis['courts'][court] = analysis['courts'].get(court, 0) + 1
        
        # Date range
        dates = [case.get('date_filed', '') for case in cases if case.get('date_filed')]
        if dates:
            analysis['date_range']['earliest'] = min(dates)
            analysis['date_range']['latest'] = max(dates)
        
        # Extract key holdings from snippets
        for case in cases[:10]:  # Top 10 most relevant
            snippet = case.get('snippet', '')
            if snippet:
                # Look for holding indicators
                if any(term in snippet.lower() for term in ['held', 'holding', 'we hold', 'court held']):
                    analysis['key_holdings'].append({
                        'case': case.get('case_name'),
                        'holding': snippet[:300]
                    })
        
        # Identify winning arguments (cases with favorable outcomes)
        for case in cases:
            snippet = case.get('snippet', '').lower()
            if any(term in snippet for term in ['granted', 'reversed', 'vacated', 'remanded']):
                analysis['winning_arguments'].append({
                    'case': case.get('case_name'),
                    'argument': snippet[:300]
                })
        
        # Identify adverse authority (cases to distinguish)
        for case in cases:
            snippet = case.get('snippet', '').lower()
            if any(term in snippet for term in ['denied', 'affirmed', 'dismissed']):
                analysis['adverse_authority'].append({
                    'case': case.get('case_name'),
                    'holding': snippet[:300]
                })
        
        self.dossier['analysis'] = analysis
        
        # Generate summary
        self._generate_summary(issue, analysis)
    
    def _generate_summary(self, issue, analysis):
        """Generate plain-English research summary"""
        
        summary = f"""
{'='*80}
CASE LAW RESEARCH SUMMARY
{'='*80}

Issue Researched: {issue}
Research Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

RESULTS:
- Total Cases Found: {analysis['total_cases']}
- Sources: {', '.join(f"{k} ({v})" for k, v in analysis['sources'].items())}
- Courts: {', '.join(f"{k} ({v})" for k, v in analysis['courts'].items())}
- Date Range: {analysis['date_range']['earliest']} to {analysis['date_range']['latest']}

KEY HOLDINGS ({len(analysis['key_holdings'])}):
"""
        
        for i, holding in enumerate(analysis['key_holdings'][:5], 1):
            summary += f"\n{i}. {holding['case']}\n   {holding['holding']}\n"
        
        summary += f"\nWINNING ARGUMENTS ({len(analysis['winning_arguments'])}):\n"
        for i, arg in enumerate(analysis['winning_arguments'][:5], 1):
            summary += f"\n{i}. {arg['case']}\n   {arg['argument']}\n"
        
        summary += f"\nADVERSE AUTHORITY TO DISTINGUISH ({len(analysis['adverse_authority'])}):\n"
        for i, adv in enumerate(analysis['adverse_authority'][:5], 1):
            summary += f"\n{i}. {adv['case']}\n   {adv['holding']}\n"
        
        summary += f"\n{'='*80}\n"
        
        self.dossier['summary'] = summary
        print(summary)
    
    def save_research(self, issue):
        """Save research dossier to file"""
        
        safe_issue = re.sub(r'[^a-zA-Z0-9]', '_', issue.lower())[:50]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = self.output_dir / f'case_law_{safe_issue}_{timestamp}.json'
        
        with open(filename, 'w') as f:
            json.dump(self.dossier, f, indent=2)
        
        print(f"\n[+] Research dossier saved: {filename}")
        
        # Also save summary as text
        summary_file = self.output_dir / f'case_law_{safe_issue}_{timestamp}.txt'
        with open(summary_file, 'w') as f:
            f.write(self.dossier['summary'])
        
        print(f"[+] Research summary saved: {summary_file}")
        
        return filename
    
    def generate_brief_outline(self, issue):
        """
        Generate brief outline from research.
        
        Creates:
        - Statement of facts
        - Legal standard
        - Argument outline
        - Supporting cases
        - Distinguishing adverse authority
        """
        
        analysis = self.dossier.get('analysis', {})
        
        outline = f"""
{'='*80}
BRIEF OUTLINE
{'='*80}

Issue: {issue}

I. STATEMENT OF FACTS
   [Insert your facts here]

II. LEGAL STANDARD

   The legal standard for {issue} is:
   [Based on research, insert standard]

   Supporting Authority:
"""
        
        for i, holding in enumerate(analysis.get('key_holdings', [])[:3], 1):
            outline += f"   {i}. {holding['case']}\n"
        
        outline += f"""

III. ARGUMENT

   A. [Your First Argument Point]
   
      Supporting Cases:
"""
        
        for i, arg in enumerate(analysis.get('winning_arguments', [])[:3], 1):
            outline += f"      {i}. {arg['case']}\n"
        
        outline += f"""
   
   B. [Your Second Argument Point]
   
      [Continue pattern]

IV. DISTINGUISHING ADVERSE AUTHORITY

   Opposing counsel may cite:
"""
        
        for i, adv in enumerate(analysis.get('adverse_authority', [])[:3], 1):
            outline += f"   {i}. {adv['case']}\n      Distinguish: [Insert distinguishing facts]\n\n"
        
        outline += f"""

V. CONCLUSION

   For the foregoing reasons, [your requested relief].

{'='*80}
"""
        
        # Save outline
        safe_issue = re.sub(r'[^a-zA-Z0-9]', '_', issue.lower())[:50]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        outline_file = self.output_dir / f'brief_outline_{safe_issue}_{timestamp}.txt'
        
        with open(outline_file, 'w') as f:
            f.write(outline)
        
        print(f"\n[+] Brief outline saved: {outline_file}")
        print(outline)
        
        return outline


def main():
    parser = argparse.ArgumentParser(
        description='OutClaw Case Law Scout - Legal precedent research'
    )
    parser.add_argument('--issue', help='Legal issue to research (defaults to first issue in --profile)')
    parser.add_argument('--profile', help='Case profile (e.g. case_context.json) — pins THIS run to that case; omit to auto-load from the case workspace or run generic')
    parser.add_argument('--file', help='Path to a case document (arrest report, complaint) — jurisdiction is auto-detected from its text')
    parser.add_argument('--jurisdiction', help='Jurisdiction (e.g., "kansas")')
    parser.add_argument('--keywords', nargs='+', help='Additional keywords')
    parser.add_argument('--court', help='Specific court to search')
    parser.add_argument('--date-start', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--date-end', help='End date (YYYY-MM-DD)')
    parser.add_argument('--out', default='../OutClaw_Research', help='Output directory')
    parser.add_argument('--brief', action='store_true', help='Generate brief outline')
    
    args = parser.parse_args()

    # Load the case document (if any) — its text carries the facts,
    # including the jurisdiction where the alleged offense occurred.
    case_text = ""
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            parser.error(f'--file not found: {args.file}')
        case_text = file_path.read_text(encoding='utf-8', errors='ignore')
        print(f"[*] Case document loaded: {args.file}")

    # Load case profile (case_context.json) for pinned defaults.
    # Auto-load the nearest workspace profile above the cwd when --profile
    # is omitted (running from inside case_data/ or a subfolder of it).
    if not args.profile:
        import os
        env_case = os.environ.get('OUTCLAW_CASE', '').strip()
        if env_case:
            env_path = Path(env_case)
            if env_path.exists() or (Path(__file__).resolve().parent / env_case).exists():
                args.profile = env_case
                print(f"[*] Profile from OUTCLAW_CASE: {env_case}", file=sys.stderr)
            else:
                print(f"[!] OUTCLAW_CASE is set but profile not found: {env_case} — this run is NOT pinned", file=sys.stderr)
        else:
            try:
                from jurisdiction import find_workspace_profile
            except ImportError:
                find_workspace_profile = None
            if find_workspace_profile:
                found = find_workspace_profile(Path(__file__).resolve().parent.parent)
                if found:
                    args.profile = found
                    print(f"[*] Profile auto-loaded: {found} (cwd is inside this case workspace)", file=sys.stderr)
    profile = None
    if args.profile:
        profile = load_case_profile(args.profile)
        research = profile.get('research') or {}
        case = profile.get('case') or {}
        # NOTE: no hardcoded state fallback here — a profile without a
        # jurisdiction field falls through to auto-detection below.
        args.jurisdiction = args.jurisdiction or research.get('jurisdiction')
        args.court = args.court or case.get('court')
        args.date_start = args.date_start or research.get('date_start')
        if not args.issue and research.get('issues'):
            args.issue = research['issues'][0]
        if not args.keywords and research.get('keywords'):
            args.keywords = research['keywords']
        print(f"[*] Case profile loaded: {profile.get('profile_name', args.profile)}")
        pin_label = args.jurisdiction.upper() if args.jurisdiction else "AUTO-DETECT"
        print(f"    Pinned: {pin_label} // {case.get('court', '')}")

    # Jurisdiction is a FACT of the case. When nothing pinned it already,
    # detect it from the case document, court name, and issue text, then
    # enforce it (out-of-state results filtered).
    if not args.jurisdiction:
        detected = detect_jurisdiction(
            case_text, args.court, args.issue,
            (profile or {}).get('research', {}).get('jurisdiction'),
        )
        if detected and detected != 'federal':
            args.jurisdiction = detected
            print(f"[*] Jurisdiction auto-detected: {detected.upper()} (from case facts)")
            print(f"    Results will be state-filtered — out-of-state cases dropped.")
        else:
            print("[!] ⚠ JURISDICTION NOT DETECTED — results will NOT be state-filtered.")
            print("    Pass --jurisdiction <state> or --file <case-doc> to pin results.")

    if not args.issue:
        parser.error('--issue is required (or pass --profile with research.issues)')
    
    # Build date range if specified
    date_range = None
    if args.date_start and args.date_end:
        date_range = {
            'start': args.date_start,
            'end': args.date_end
        }
    elif args.date_start:
        date_range = {
            'start': args.date_start,
            'end': datetime.now().strftime('%Y-%m-%d')
        }
    
    scout = CaseLawScout(output_dir=args.out)
    
    print(f"""
{'='*80}
OUTCLAW CASE LAW SCOUT
Paralegal Superpowers: Legal Precedent Research
{'='*80}
""")
    
    # Research issue
    cases = scout.research_issue(
        issue=args.issue,
        jurisdiction=args.jurisdiction,
        keywords=args.keywords,
        court=args.court,
        date_range=date_range
    )
    
    # Save research
    scout.save_research(args.issue)
    
    # Generate brief outline if requested
    if args.brief:
        scout.generate_brief_outline(args.issue)
    
    print(f"\n{'='*80}")
    print(f"RESEARCH COMPLETE: {len(cases)} cases found")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    main()
