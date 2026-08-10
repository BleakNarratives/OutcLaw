#!/usr/bin/env python3
"""
OutClaw Legal Docket Scout
Paralegal Superpowers: Court Docket Intelligence

Searches public court dockets for:
- Attorney litigation patterns
- Judge ruling patterns
- Case outcomes
- Motion success rates
- Discovery abuse patterns

Based on Blindsight dork_scout architecture.
Zero cost. Maximum intelligence.
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse
import re
import time
import random
from pathlib import Path
from datetime import datetime, timedelta

# Shared jurisdiction detection: jurisdiction is a FACT of the case, and
# is auto-detected from case documents, court names, and attorney/judge
# names so dorks stay in-state automatically.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jurisdiction import detect_jurisdiction, normalize_jurisdiction  # noqa: E402

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

# ---------------------------------------------------------------------------
# Jurisdiction pinning
# ---------------------------------------------------------------------------
# The old code appended `site:{jurisdiction}.gov` to dorks, which produced
# `site:kansas.gov` — a domain that does not exist, so results drifted to
# every state (Oklahoma included). These are real Kansas web properties,
# and the post-search filter drops clear out-of-state noise.

JURISDICTION_SITES = {
    'kansas': [
        'site:kscourts.org',
        'site:ks.gov',
        'site:wellingtonks.org',
        'site:sumnercounty.org',
    ],
    'oklahoma': [
        'site:oscn.net',
        'site:ok.gov',
    ],
}

# States that must never dominate a Kansas-pinned dossier.
EXCLUDED_STATE_TERMS = [
    'oklahoma', 'okla.', 'missouri', 'colorado', 'nebraska', 'texas',
    'california', 'new york', 'illinois', 'arizona', 'utah', 'new mexico',
    'arkansas', 'tennessee', 'iowa', 'kentucky', 'virginia', 'georgia',
]


def _norm_jurisdiction(jurisdiction):
    """Normalize a jurisdiction string (delegates to the shared module)."""
    return normalize_jurisdiction(jurisdiction)


def _filter_out_of_state(results):
    """
    Drop clear out-of-state results while keeping Kansas-tagged or
    ambiguous results. Returns (kept, dropped).
    """
    kept, dropped = [], []
    for r in results:
        if 'error' in r:
            kept.append(r)
            continue
        text = (str(r.get('snippet', '')) + ' ' + str(r.get('title', ''))).lower()
        mentions_ks = 'kansas' in text or 'kscourts' in text
        mentions_other = any(t in text for t in EXCLUDED_STATE_TERMS)
        if mentions_ks or not mentions_other:
            kept.append(r)
        else:
            dropped.append(r)
    return kept, dropped

class LegalDocketScout:
    """
    Scout public court dockets for attorney/judge intelligence.
    
    Targets:
    - PACER (federal courts) - requires account but search is public
    - State court websites (varies by state)
    - CourtListener (free federal docket search)
    - UniCourt (limited free tier)
    """
    
    def __init__(self, output_dir='../OutClaw_Intelligence'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results = {
            'timestamp': datetime.utcnow().isoformat(),
            'scout_type': 'legal_docket',
            'targets': [],
            'intelligence': {}
        }
    
    def build_attorney_dorks(self, attorney_name, bar_number=None, jurisdiction=None):
        """
        Build search queries for attorney intelligence.
        
        Searches for:
        - Cases filed by attorney
        - Cases where attorney sanctioned
        - Cases where attorney lost
        - Discovery disputes involving attorney
        - Bar grievances (public records)
        """
        
        dorks = {
            'case_history': [
                f'"{attorney_name}" attorney site:courtlistener.com',
                f'"{attorney_name}" counsel site:pacer.gov',
                f'"{attorney_name}" lawyer site:*.gov'
            ],
            'sanctions': [
                f'"{attorney_name}" sanctioned OR "Rule 11"',
                f'"{attorney_name}" "bad faith" OR "frivolous"',
                f'"{attorney_name}" "attorney fees" awarded against'
            ],
            'discovery_abuse': [
                f'"{attorney_name}" "motion to compel"',
                f'"{attorney_name}" "discovery abuse"',
                f'"{attorney_name}" "failure to respond" discovery'
            ],
            'bar_discipline': [
                f'"{attorney_name}" bar discipline OR grievance',
                f'"{attorney_name}" suspended OR disbarred',
                f'"{attorney_name}" reprimand OR censure'
            ]
        }
        
        if bar_number:
            dorks['bar_verification'] = [
                f'"{bar_number}" attorney',
                f'"{attorney_name}" "{bar_number}"'
            ]
        
        if jurisdiction:
            # Kansas-pinned dorks: scope to real Kansas web properties and
            # append the state name. The old `site:{jurisdiction}.gov`
            # produced site:kansas.gov (a dead domain) and let results drift.
            norm = _norm_jurisdiction(jurisdiction)
            sites = JURISDICTION_SITES.get(norm, [])
            state_label = "Kansas" if norm == "kansas" else "Oklahoma" if norm == "oklahoma" else str(jurisdiction)
            for category in dorks:
                scoped = []
                for q in dorks[category]:
                    pinned = f'{q} "{state_label}"'
                    if sites:
                        scoped.extend(f'{pinned} {s}' for s in sites)
                    else:
                        scoped.append(pinned)
                dorks[category] = scoped or dorks[category]
        
        return dorks
    
    def build_judge_dorks(self, judge_name, court=None, jurisdiction=None):
        """
        Build search queries for judge intelligence.
        
        Searches for:
        - Reversal rate
        - Bias complaints
        - Recusal history
        - Notable rulings
        """
        
        dorks = {
            'reversal_history': [
                f'"{judge_name}" reversed OR overturned',
                f'"{judge_name}" appeal affirmed OR reversed',
                f'"{judge_name}" "abuse of discretion"'
            ],
            'bias_complaints': [
                f'"{judge_name}" bias OR prejudice',
                f'"{judge_name}" recusal OR disqualification',
                f'"{judge_name}" judicial misconduct'
            ],
            'notable_rulings': [
                f'"{judge_name}" ruling site:courtlistener.com',
                f'"{judge_name}" opinion site:*.gov',
                f'"{judge_name}" order site:pacer.gov'
            ]
        }
        
        if court:
            for category in dorks:
                dorks[category] = [
                    q + f' "{court}"' for q in dorks[category]
                ]
        
        if jurisdiction and not court:
            norm = _norm_jurisdiction(jurisdiction)
            sites = JURISDICTION_SITES.get(norm, [])
            state_label = "Kansas" if norm == "kansas" else "Oklahoma" if norm == "oklahoma" else str(jurisdiction)
            for category in dorks:
                scoped = []
                for q in dorks[category]:
                    pinned = f'{q} "{state_label}"'
                    if sites:
                        scoped.extend(f'{pinned} {s}' for s in sites)
                    else:
                        scoped.append(pinned)
                dorks[category] = scoped or dorks[category]
        
        return dorks
    
    def fetch_courtlistener(self, query, retries=2):
        """
        Search CourtListener (free federal docket database).
        
        CourtListener has:
        - 20+ million federal opinions
        - PACER dockets (free)
        - Oral arguments
        - Judge data
        """
        
        base_url = "https://www.courtlistener.com/api/rest/v3/search/"
        params = {
            'q': query,
            'type': 'o',  # opinions
            'order_by': 'score desc'
        }
        
        url = base_url + '?' + urllib.parse.urlencode(params)
        headers = {
            'User-Agent': random.choice(USER_AGENTS)
        }
        
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read().decode())
                
                results = []
                for result in data.get('results', [])[:10]:
                    results.append({
                        'title': result.get('caseName', 'Unknown'),
                        'court': result.get('court', 'Unknown'),
                        'date': result.get('dateFiled', 'Unknown'),
                        'url': f"https://www.courtlistener.com{result.get('absolute_url', '')}",
                        'snippet': result.get('snippet', '')[:300]
                    })
                
                return results
            
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(3)
                else:
                    return [{'error': str(e), 'query': query}]
        
        return []
    
    def fetch_duckduckgo(self, query, retries=2):
        """
        Fallback to DuckDuckGo for general web search.
        Useful for state court websites and bar discipline records.
        """
        
        url = "https://duckduckgo.com/html/"
        params = {'q': query}
        data = urllib.parse.urlencode(params).encode('utf-8')
        
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as r:
                    html = r.read().decode(errors='ignore')
                
                results = []
                # Extract search results
                links = re.findall(r'<a class="result__a" href="([^"]+)"', html)
                snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
                
                for i in range(min(len(links), 10)):
                    url_clean = urllib.parse.unquote(links[i])
                    if '?uddg=' in url_clean:
                        url_clean = url_clean.split('?uddg=')[1].split('&')[0]
                    
                    snip_clean = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ''
                    
                    if 'duckduckgo.com' not in url_clean:
                        results.append({
                            'title': f"Result {i+1}",
                            'url': url_clean,
                            'snippet': snip_clean[:300]
                        })
                
                return results
            
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(3)
                else:
                    return [{'error': str(e), 'query': query}]
        
        return []
    
    def scout_attorney(self, attorney_name, bar_number=None, jurisdiction=None):
        """
        Complete intelligence gathering on attorney.
        
        Returns:
        - Case history
        - Sanction history
        - Discovery abuse patterns
        - Bar discipline records
        - Win/loss patterns
        """
        
        print(f"\n[*] Scouting Attorney: {attorney_name}")
        if bar_number:
            print(f"    Bar Number: {bar_number}")
        if jurisdiction:
            print(f"    Jurisdiction: {jurisdiction}")
        
        dorks = self.build_attorney_dorks(attorney_name, bar_number, jurisdiction)
        intelligence = {
            'attorney_name': attorney_name,
            'bar_number': bar_number,
            'jurisdiction': jurisdiction,
            'scout_date': datetime.utcnow().isoformat(),
            'findings': {}
        }
        
        for category, queries in dorks.items():
            print(f"\n  [{category.upper()}]")
            intelligence['findings'][category] = []
            
            for query in queries:
                print(f"    > {query}")
                
                # Try CourtListener first for legal content
                # CourtListener cannot parse site: operators — strip ALL of
                # them before the API call (jurisdiction site-scoping is
                # DuckDuckGo only).
                if 'site:courtlistener.com' in query:
                    q_for_cl = re.sub(r'\s*site:[^\s]+', '', query).strip()
                    results = self.fetch_courtlistener(q_for_cl)
                else:
                    results = self.fetch_duckduckgo(query)
                
                intelligence['findings'][category].extend(results)
                time.sleep(random.uniform(2, 4))  # Be polite
        
        # Kansas-pinned: drop out-of-state noise before analysis
        if _norm_jurisdiction(jurisdiction) in ('kansas', 'oklahoma'):
            for category, results in intelligence['findings'].items():
                kept, dropped = _filter_out_of_state(results)
                intelligence['findings'][category] = kept
                if dropped:
                    print(f"    > Jurisdiction filter: dropped {len(dropped)} out-of-state result(s) from {category}")
        
        # Analyze findings
        intelligence['analysis'] = self._analyze_attorney_findings(intelligence['findings'])
        
        self.results['intelligence'][attorney_name] = intelligence
        return intelligence
    
    def scout_judge(self, judge_name, court=None, jurisdiction=None):
        """
        Complete intelligence gathering on judge.
        
        Returns:
        - Reversal rate indicators
        - Bias complaints
        - Recusal history
        - Notable rulings
        """
        
        print(f"\n[*] Scouting Judge: {judge_name}")
        if court:
            print(f"    Court: {court}")
        if jurisdiction:
            print(f"    Jurisdiction: {jurisdiction}")
        
        dorks = self.build_judge_dorks(judge_name, court, jurisdiction)
        intelligence = {
            'judge_name': judge_name,
            'court': court,
            'scout_date': datetime.utcnow().isoformat(),
            'findings': {}
        }
        
        for category, queries in dorks.items():
            print(f"\n  [{category.upper()}]")
            intelligence['findings'][category] = []
            
            for query in queries:
                print(f"    > {query}")
                
                # CourtListener cannot parse site: operators — strip ALL of
                # them before the API call (jurisdiction site-scoping is
                # DuckDuckGo only).
                if 'site:courtlistener.com' in query:
                    q_for_cl = re.sub(r'\s*site:[^\s]+', '', query).strip()
                    results = self.fetch_courtlistener(q_for_cl)
                else:
                    results = self.fetch_duckduckgo(query)
                
                intelligence['findings'][category].extend(results)
                time.sleep(random.uniform(2, 4))
        
        # Kansas-pinned: drop out-of-state noise before analysis
        if _norm_jurisdiction(jurisdiction) in ('kansas', 'oklahoma'):
            for category, results in intelligence['findings'].items():
                kept, dropped = _filter_out_of_state(results)
                intelligence['findings'][category] = kept
                if dropped:
                    print(f"    > Jurisdiction filter: dropped {len(dropped)} out-of-state result(s) from {category}")
        
        # Analyze findings
        intelligence['analysis'] = self._analyze_judge_findings(intelligence['findings'])
        
        self.results['intelligence'][judge_name] = intelligence
        return intelligence
    
    def _analyze_attorney_findings(self, findings):
        """Analyze attorney findings for red flags"""
        
        analysis = {
            'red_flags': [],
            'risk_level': 'UNKNOWN',
            'recommendation': ''
        }
        
        # Check for sanctions
        sanction_count = len([r for r in findings.get('sanctions', []) if 'error' not in r])
        if sanction_count > 3:
            analysis['red_flags'].append(f'HIGH SANCTION HISTORY: {sanction_count} results found')
            analysis['risk_level'] = 'HIGH'
        
        # Check for discovery abuse
        discovery_count = len([r for r in findings.get('discovery_abuse', []) if 'error' not in r])
        if discovery_count > 5:
            analysis['red_flags'].append(f'DISCOVERY ABUSE PATTERN: {discovery_count} results found')
            if analysis['risk_level'] != 'HIGH':
                analysis['risk_level'] = 'MEDIUM'
        
        # Check for bar discipline
        discipline_count = len([r for r in findings.get('bar_discipline', []) if 'error' not in r])
        if discipline_count > 0:
            analysis['red_flags'].append(f'BAR DISCIPLINE RECORDS: {discipline_count} results found')
            analysis['risk_level'] = 'HIGH'
        
        if not analysis['red_flags']:
            analysis['risk_level'] = 'LOW'
            analysis['recommendation'] = 'No significant red flags found in public records.'
        else:
            analysis['recommendation'] = 'CAUTION: Multiple red flags detected. Consider filing bar grievance if misconduct occurs.'
        
        return analysis
    
    def _analyze_judge_findings(self, findings):
        """Analyze judge findings for bias indicators"""
        
        analysis = {
            'red_flags': [],
            'bias_risk': 'UNKNOWN',
            'recommendation': ''
        }
        
        # Check for reversals
        reversal_count = len([r for r in findings.get('reversal_history', []) if 'error' not in r])
        if reversal_count > 5:
            analysis['red_flags'].append(f'HIGH REVERSAL RATE: {reversal_count} results found')
            analysis['bias_risk'] = 'MEDIUM'
        
        # Check for bias complaints
        bias_count = len([r for r in findings.get('bias_complaints', []) if 'error' not in r])
        if bias_count > 2:
            analysis['red_flags'].append(f'BIAS COMPLAINTS: {bias_count} results found')
            analysis['bias_risk'] = 'HIGH'
        
        if not analysis['red_flags']:
            analysis['bias_risk'] = 'LOW'
            analysis['recommendation'] = 'No significant bias indicators found in public records.'
        else:
            analysis['recommendation'] = 'CAUTION: Bias indicators detected. Document all rulings carefully. Consider recusal motion if bias becomes apparent.'
        
        return analysis
    
    def save_intelligence(self):
        """Save intelligence dossier to file"""
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = self.output_dir / f'legal_docket_intelligence_{timestamp}.json'
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n[+] Intelligence dossier saved: {filename}")
        return filename
    
    def generate_report(self):
        """Generate human-readable intelligence report"""
        
        report = f"""
{'='*80}
OUTCLAW LEGAL DOCKET INTELLIGENCE REPORT
{'='*80}

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Scout Type: Legal Docket Intelligence
Targets Scouted: {len(self.results['intelligence'])}

{'='*80}
INTELLIGENCE SUMMARY
{'='*80}

"""
        
        for target_name, intel in self.results['intelligence'].items():
            report += f"\n{'='*80}\n"
            report += f"TARGET: {target_name}\n"
            report += f"{'='*80}\n\n"
            
            if 'attorney_name' in intel:
                report += f"Type: ATTORNEY\n"
                if intel.get('bar_number'):
                    report += f"Bar Number: {intel['bar_number']}\n"
                if intel.get('jurisdiction'):
                    report += f"Jurisdiction: {intel['jurisdiction']}\n"
            else:
                report += f"Type: JUDGE\n"
                if intel.get('court'):
                    report += f"Court: {intel['court']}\n"
            
            report += f"\nScout Date: {intel['scout_date']}\n"
            
            # Analysis
            analysis = intel.get('analysis', {})
            report += f"\nRISK LEVEL: {analysis.get('risk_level', 'UNKNOWN')}\n"
            
            if analysis.get('red_flags'):
                report += f"\nRED FLAGS:\n"
                for flag in analysis['red_flags']:
                    report += f"  ⚠️  {flag}\n"
            
            report += f"\nRECOMMENDATION:\n{analysis.get('recommendation', 'No recommendation available.')}\n"
            
            # Findings summary
            report += f"\nFINDINGS SUMMARY:\n"
            for category, results in intel.get('findings', {}).items():
                valid_results = [r for r in results if 'error' not in r]
                report += f"  - {category}: {len(valid_results)} results\n"
        
        report += f"\n{'='*80}\n"
        report += "END OF REPORT\n"
        report += f"{'='*80}\n"
        
        # Save report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = self.output_dir / f'legal_docket_report_{timestamp}.txt'
        
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(report)
        print(f"\n[+] Report saved: {report_file}")
        
        return report


def main():
    parser = argparse.ArgumentParser(
        description='OutClaw Legal Docket Scout - Paralegal-powered intelligence gathering'
    )
    parser.add_argument('--attorney', help='Attorney name to scout')
    parser.add_argument('--bar-number', help='Attorney bar number')
    parser.add_argument('--judge', help='Judge name to scout')
    parser.add_argument('--court', help='Court name (for judge scouting)')
    parser.add_argument('--file', help='Path to a case document (arrest report, complaint) — jurisdiction is auto-detected from its text')
    parser.add_argument('--jurisdiction', help='Jurisdiction (state/federal)')
    parser.add_argument('--profile', help='Case profile (e.g. case_context.json) — pins THIS run to that case; omit to auto-load from the case workspace or run generic')
    parser.add_argument('--out', default='../OutClaw_Intelligence', help='Output directory')
    
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
    
    # Load case profile for pinned defaults. Auto-load the nearest workspace
    # profile above the cwd when --profile is omitted.
    if not args.profile:
        import os
        env_case = os.environ.get('OUTCLAW_CASE', '').strip()
        if env_case:
            env_path = Path(env_case)
            if env_path.exists() or (Path(__file__).resolve().parent.parent / env_case).exists():
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
    if args.profile:
        try:
            profile = json.loads(Path(args.profile).read_text(encoding='utf-8'))
        except Exception as e:
            parser.error(f'Could not load --profile {args.profile}: {e}')
        research = profile.get('research') or {}
        case = profile.get('case') or {}
        # NOTE: no hardcoded state fallback here — a profile without a
        # jurisdiction field falls through to auto-detection below.
        args.jurisdiction = args.jurisdiction or research.get('jurisdiction')
        args.court = args.court or case.get('court')
        args.attorney = args.attorney or case.get('prosecutor')
        args.judge = args.judge or case.get('judge')
        if 'PLACEHOLDER' in str(args.attorney or ''):
            args.attorney = None
        if 'PLACEHOLDER' in str(args.judge or ''):
            args.judge = None
        print(f"[*] Case profile loaded: {profile.get('profile_name', args.profile)}")

    # Jurisdiction is a FACT of the case. When nothing pinned it already,
    # detect it from the case document, court, and target names, then
    # scope the dorks automatically.
    if not args.jurisdiction:
        detected = detect_jurisdiction(case_text, args.court, args.attorney, args.judge)
        if detected and detected != 'federal':
            args.jurisdiction = detected
            print(f"[*] Jurisdiction auto-detected: {detected.upper()} (from case facts)")
            print(f"    Dorks will be state-scoped — out-of-state results dropped.")
        else:
            print("[!] ⚠ JURISDICTION NOT DETECTED — dorks will NOT be state-scoped.")
            print("    Pass --jurisdiction <state> or --file <case-doc> to pin results.")
    
    if not args.attorney and not args.judge:
        parser.error('Must specify --attorney or --judge')
    
    scout = LegalDocketScout(output_dir=args.out)
    
    print(f"""
{'='*80}
OUTCLAW LEGAL DOCKET SCOUT
Paralegal Superpowers: Court Intelligence Gathering
{'='*80}
""")
    
    if args.attorney:
        scout.scout_attorney(
            attorney_name=args.attorney,
            bar_number=args.bar_number,
            jurisdiction=args.jurisdiction
        )
    
    if args.judge:
        scout.scout_judge(
            judge_name=args.judge,
            court=args.court,
            jurisdiction=args.jurisdiction
        )
    
    # Save results
    scout.save_intelligence()
    scout.generate_report()
    
    print(f"\n{'='*80}")
    print("SCOUT MISSION COMPLETE")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    main()
