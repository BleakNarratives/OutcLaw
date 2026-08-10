"""
OutClaw "So What?" Filter
The Brutal Reality Check

Every grievance must pass the "Who gives a shit?" test from the perspective of:
- Overworked bar association clerks (50 cases/day)
- Jaded attorneys who've seen everything
- Administrative law judges (not real judges, glorified clerks)
- Insurance adjusters looking for reasons to deny

If it doesn't pass this filter, it's noise. Noise gets ignored.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
#  OUTCLAW_SO_WHAT_FILTER
# ═══════════════════════════════════════════════════════════════

class ImpactLevel(Enum):
    """How much does anyone actually care?"""
    NOBODY_CARES = "Nobody gives a shit - will be ignored"
    MINOR_ANNOYANCE = "Mild irritation - filed and forgotten"
    ACTUAL_PROBLEM = "Someone might look at this"
    CAREER_THREAT = "Attorney's insurance company cares"
    LICENSE_RISK = "Bar association must act"


@dataclass
class RealityCheck:
    """The brutal truth about whether anyone cares"""
    impact_level: ImpactLevel
    why_they_care: str
    why_they_dont_care: str
    clerk_reaction: str  # What the overworked clerk thinks
    attorney_reaction: str  # What the opposing attorney thinks
    judge_reaction: str  # What the administrative law clerk thinks
    insurance_reaction: str  # What the insurance adjuster thinks
    actionable: bool
    recommendation: str


class SoWhatFilter:
    """
    Brutal reality check for grievances.
    
    Asks "So what? Who gives a shit?" from every angle.
    Filters out noise that will be ignored.
    """
    
    # Things that ACTUALLY matter to bar associations
    REAL_TRIGGERS = {
        'money': [
            'Client funds misappropriation',
            'Fee disputes over $10,000',
            'Insurance fraud',
            'Trust account violations'
        ],
        'publicity': [
            'Media coverage',
            'Multiple complaints from different clients',
            'Pattern of behavior',
            'Criminal charges filed'
        ],
        'liability': [
            'Malpractice claim filed',
            'Court sanctions imposed',
            'Judge written complaint',
            'Federal court involvement'
        ],
        'easy_win': [
            'Clear rule violation with evidence',
            'Attorney already on probation',
            'Multiple grievances (approaching 3)',
            'Admission of wrongdoing'
        ]
    }
    
    # Things that DON'T matter (will be ignored)
    IGNORED_COMPLAINTS = [
        'Single citation error (could be mistake)',
        'Vague allegations without evidence',
        'Personality conflicts',
        'Disagreement with legal strategy',
        'Pro se litigant complaining (automatic skepticism)',
        'No financial harm',
        'No pattern of behavior',
        'Attorney has clean record'
    ]
    
    def __init__(self):
        self.filters_applied = 0
        self.passed_filters = 0
        self.failed_filters = 0
    
    def apply_reality_check(
        self,
        fraud_evidence: List,
        attorney_history: Dict,
        case_context: Dict
    ) -> RealityCheck:
        """
        Apply the "So What?" filter.
        
        Returns brutal honest assessment of whether anyone will care.
        """
        self.filters_applied += 1
        
        # Calculate actual impact
        impact_score = self._calculate_impact_score(
            fraud_evidence, attorney_history, case_context
        )
        
        # Determine impact level
        impact_level = self._determine_impact_level(impact_score)
        
        # Get reactions from different stakeholders
        reactions = self._get_stakeholder_reactions(
            fraud_evidence, attorney_history, case_context, impact_level
        )
        
        # Determine if actionable
        actionable = impact_level in [
            ImpactLevel.CAREER_THREAT,
            ImpactLevel.LICENSE_RISK
        ]
        
        if actionable:
            self.passed_filters += 1
        else:
            self.failed_filters += 1
        
        # Generate recommendation
        recommendation = self._generate_recommendation(
            impact_level, reactions, fraud_evidence, attorney_history
        )
        
        return RealityCheck(
            impact_level=impact_level,
            why_they_care=reactions['why_care'],
            why_they_dont_care=reactions['why_dont_care'],
            clerk_reaction=reactions['clerk'],
            attorney_reaction=reactions['attorney'],
            judge_reaction=reactions['judge'],
            insurance_reaction=reactions['insurance'],
            actionable=actionable,
            recommendation=recommendation
        )
    
    def _calculate_impact_score(
        self,
        fraud_evidence: List,
        attorney_history: Dict,
        case_context: Dict
    ) -> int:
        """
        Calculate actual impact score (0-100).
        
        Higher score = more people give a shit.
        """
        score = 0
        
        # Evidence quality (0-30 points)
        high_severity = sum(1 for e in fraud_evidence if e.severity == 'HIGH')
        score += min(30, high_severity * 10)
        
        # Attorney history (0-25 points)
        prior_grievances = attorney_history.get('grievance_count', 0)
        if prior_grievances >= 2:
            score += 25  # One away from license loss - THEY CARE
        elif prior_grievances == 1:
            score += 15  # Pattern forming
        
        # Financial impact (0-20 points)
        financial_harm = case_context.get('financial_harm', 0)
        if financial_harm > 50000:
            score += 20
        elif financial_harm > 10000:
            score += 10
        
        # Pattern of behavior (0-15 points)
        if len(fraud_evidence) > 5:
            score += 15  # Multiple violations = pattern
        elif len(fraud_evidence) > 2:
            score += 8
        
        # Court involvement (0-10 points)
        if case_context.get('court_sanctions'):
            score += 10  # Judge already pissed = bar must act
        elif case_context.get('opposing_counsel_complaint'):
            score += 5  # Another attorney complaining = credible
        
        return score
    
    def _determine_impact_level(self, score: int) -> ImpactLevel:
        """Convert score to impact level"""
        if score >= 70:
            return ImpactLevel.LICENSE_RISK
        elif score >= 50:
            return ImpactLevel.CAREER_THREAT
        elif score >= 30:
            return ImpactLevel.ACTUAL_PROBLEM
        elif score >= 15:
            return ImpactLevel.MINOR_ANNOYANCE
        else:
            return ImpactLevel.NOBODY_CARES
    
    def _get_stakeholder_reactions(
        self,
        fraud_evidence: List,
        attorney_history: Dict,
        case_context: Dict,
        impact_level: ImpactLevel
    ) -> Dict[str, str]:
        """Get realistic reactions from each stakeholder"""
        
        reactions = {}
        
        # Why they MIGHT care
        care_reasons = []
        if attorney_history.get('grievance_count', 0) >= 2:
            care_reasons.append("Attorney already has 2 strikes - one more = license loss")
        if case_context.get('financial_harm', 0) > 10000:
            care_reasons.append(f"${case_context['financial_harm']:,} in damages - insurance company will care")
        if len(fraud_evidence) > 5:
            care_reasons.append(f"{len(fraud_evidence)} violations = pattern of behavior")
        if case_context.get('court_sanctions'):
            care_reasons.append("Judge already sanctioned attorney - bar must follow up")
        
        reactions['why_care'] = "; ".join(care_reasons) if care_reasons else "Nothing compelling"
        
        # Why they DON'T care
        dont_care_reasons = []
        if attorney_history.get('grievance_count', 0) == 0:
            dont_care_reasons.append("Attorney has clean record - benefit of doubt")
        if not case_context.get('financial_harm'):
            dont_care_reasons.append("No financial harm - just academic")
        if len(fraud_evidence) < 3:
            dont_care_reasons.append("Could be honest mistake")
        if case_context.get('pro_se_complainant'):
            dont_care_reasons.append("Pro se litigant - probably doesn't understand law")
        
        reactions['why_dont_care'] = "; ".join(dont_care_reasons) if dont_care_reasons else "No obvious reasons to ignore"
        
        # Clerk reaction (overworked, cynical, 50 cases today)
        if impact_level == ImpactLevel.LICENSE_RISK:
            reactions['clerk'] = "😰 'Shit, this is serious. Need to escalate to supervisor.'"
        elif impact_level == ImpactLevel.CAREER_THREAT:
            reactions['clerk'] = "🤔 'Hmm, this might actually be something. Better document it.'"
        elif impact_level == ImpactLevel.ACTUAL_PROBLEM:
            reactions['clerk'] = "😑 'Another one. Add it to the pile. Maybe look at it next month.'"
        elif impact_level == ImpactLevel.MINOR_ANNOYANCE:
            reactions['clerk'] = "🙄 'Pro se litigant mad they lost. File and forget.'"
        else:
            reactions['clerk'] = "💤 'Delete. Next.'"
        
        # Attorney reaction (seen it all, knows the game)
        if impact_level == ImpactLevel.LICENSE_RISK:
            reactions['attorney'] = "😱 'I need to call my insurance carrier NOW. This could end my career.'"
        elif impact_level == ImpactLevel.CAREER_THREAT:
            reactions['attorney'] = "😬 'This is bad. Need to hire defense counsel. $15k minimum.'"
        elif impact_level == ImpactLevel.ACTUAL_PROBLEM:
            reactions['attorney'] = "😒 'Annoying. Write a response, bill client for my time.'"
        else:
            reactions['attorney'] = "🤷 'Bar will dismiss this. Not worried.'"
        
        # Judge reaction (administrative clerk, not real judge)
        if case_context.get('court_sanctions'):
            reactions['judge'] = "⚖️ 'I already sanctioned them. Bar better follow up or I will.'"
        elif impact_level == ImpactLevel.LICENSE_RISK:
            reactions['judge'] = "📋 'Pattern of fraud. Will note in future cases.'"
        else:
            reactions['judge'] = "📄 'Not my problem. Bar handles discipline.'"
        
        # Insurance reaction (looking for reasons to deny coverage)
        if impact_level == ImpactLevel.LICENSE_RISK:
            reactions['insurance'] = "💰 'Intentional fraud = no coverage. Deny claim. Drop client.'"
        elif impact_level == ImpactLevel.CAREER_THREAT:
            reactions['insurance'] = "📈 'Increase premiums 150%. High risk client.'"
        elif impact_level == ImpactLevel.ACTUAL_PROBLEM:
            reactions['insurance'] = "📊 'Note in file. Watch for pattern.'"
        else:
            reactions['insurance'] = "✅ 'Isolated incident. No action needed.'"
        
        return reactions
    
    def _generate_recommendation(
        self,
        impact_level: ImpactLevel,
        reactions: Dict,
        fraud_evidence: List,
        attorney_history: Dict
    ) -> str:
        """Generate actionable recommendation"""
        
        if impact_level == ImpactLevel.LICENSE_RISK:
            return """
🎯 FILE IMMEDIATELY - HIGH IMPACT

This grievance will be taken seriously because:
- {why_care}

Action Plan:
1. File grievance with bar association
2. File malpractice claim with insurance carrier
3. Request court sanctions (Rule 11)
4. Coordinate with other victims if any
5. Follow up every 2 weeks

Expected Outcome:
- Bar investigation opened within 30 days
- Attorney must respond (cost: $15,000+)
- Insurance premiums increase 100-200%
- Possible license suspension
- Settlement likely to avoid discipline

This is worth your time.
""".format(why_care=reactions['why_care'])
        
        elif impact_level == ImpactLevel.CAREER_THREAT:
            return """
⚠️ FILE - MODERATE IMPACT

This grievance has teeth because:
- {why_care}

However, be aware:
- {why_dont_care}

Action Plan:
1. File grievance (free, low effort)
2. Document everything meticulously
3. Be prepared to follow up
4. Consider coordinating with other victims

Expected Outcome:
- Bar will investigate (may take 3-6 months)
- Attorney must respond (cost: $10,000+)
- Insurance premiums will increase
- Creates permanent record

Worth filing, but manage expectations.
""".format(why_care=reactions['why_care'], why_dont_care=reactions['why_dont_care'])
        
        elif impact_level == ImpactLevel.ACTUAL_PROBLEM:
            return """
🤔 MARGINAL - CONSIDER ALTERNATIVES

Why it might work:
- {why_care}

Why it might not:
- {why_dont_care}

Recommendation:
Instead of bar grievance, consider:
1. Motion for sanctions in your case (Rule 11)
2. Malpractice claim (if you have damages)
3. Complaint to judge (if in active case)
4. Wait for more evidence of pattern

Bar grievance alone may be ignored. Need stronger case.
""".format(why_care=reactions['why_care'], why_dont_care=reactions['why_dont_care'])
        
        else:
            return """
❌ DO NOT FILE - WASTE OF TIME

Reality check:
- {why_dont_care}

Clerk reaction: {clerk}

This grievance will be:
1. Filed
2. Ignored
3. Dismissed in 6 months
4. You'll never hear back

Better options:
1. Focus on winning your case
2. Document for future malpractice claim
3. Wait for pattern to develop
4. Coordinate with other victims

Don't waste your time on this. Bar won't care.
""".format(why_dont_care=reactions['why_dont_care'], clerk=reactions['clerk'])
    
    def generate_enhanced_grievance(
        self,
        original_grievance: str,
        reality_check: RealityCheck
    ) -> str:
        """
        Enhance grievance to pass the "So What?" test.
        
        Adds the elements that make people actually care.
        """
        if not reality_check.actionable:
            return "⚠️ GRIEVANCE NOT ACTIONABLE - DO NOT FILE\n\n" + reality_check.recommendation
        
        enhancement = f"""
{'='*80}
ENHANCED GRIEVANCE - REALITY-TESTED
{'='*80}

IMPACT ASSESSMENT: {reality_check.impact_level.value}

WHY THIS MATTERS:
{reality_check.why_they_care}

STAKEHOLDER REACTIONS:

Bar Clerk: {reality_check.clerk_reaction}
Attorney: {reality_check.attorney_reaction}
Judge: {reality_check.judge_reaction}
Insurance: {reality_check.insurance_reaction}

{'='*80}
ORIGINAL GRIEVANCE (ENHANCED WITH IMPACT ELEMENTS)
{'='*80}

"""
        
        # Add impact-focused opening
        enhancement += """
⚠️ URGENT: This complaint requires immediate attention due to:
1. Pattern of intentional fraud (not isolated mistake)
2. Substantial harm to administration of justice
3. Attorney's duty to notify insurance carrier
4. Potential license implications

"""
        
        enhancement += original_grievance
        
        # Add impact-focused closing
        enhancement += f"""

{'='*80}
IMPACT STATEMENT
{'='*80}

This is not an isolated incident or honest mistake. This is a pattern of intentional
fraud that requires disciplinary action because:

{reality_check.why_they_care}

The respondent's insurance carrier must be notified immediately as this conduct
constitutes intentional fraud which may void coverage.

{reality_check.recommendation}
"""
        
        return enhancement


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    filter_system = SoWhatFilter()
    
    # Test Case 1: High impact (attorney with 2 prior grievances)
    print("\n" + "="*80)
    print("TEST CASE 1: High Impact Scenario")
    print("="*80)
    
    from outclaw_grievance_generator import FraudEvidence
    
    evidence = [
        FraudEvidence(
            citation_string="Fake v. Case, 999 F.3d 999",
            issue_type="fabricated",
            severity="HIGH",
            description="Completely fabricated citation",
            document_reference="Motion to Dismiss",
            page_number=5,
            verification_attempts=["CourtListener: Not found", "Manual search: Not found"]
        )
    ] * 6  # 6 violations = pattern
    
    attorney_history = {
        'grievance_count': 2,  # Two strikes already!
        'clean_record': False
    }
    
    case_context = {
        'financial_harm': 50000,
        'court_sanctions': True,
        'pro_se_complainant': False
    }
    
    reality_check = filter_system.apply_reality_check(
        evidence, attorney_history, case_context
    )
    
    print(f"\nImpact Level: {reality_check.impact_level.value}")
    print(f"Actionable: {reality_check.actionable}")
    print(f"\nWhy They Care: {reality_check.why_they_care}")
    print(f"\nClerk Reaction: {reality_check.clerk_reaction}")
    print(f"\nAttorney Reaction: {reality_check.attorney_reaction}")
    print(f"\nRecommendation:\n{reality_check.recommendation}")
    
    # Test Case 2: Low impact (single error, clean record)
    print("\n" + "="*80)
    print("TEST CASE 2: Low Impact Scenario")
    print("="*80)
    
    evidence_low = [
        FraudEvidence(
            citation_string="Smith v. Jones, 100 F.3d 1",
            issue_type="misrepresented",
            severity="MEDIUM",
            description="Wrong page citation",
            document_reference="Brief",
            page_number=10,
            verification_attempts=["Found case but wrong page"]
        )
    ]
    
    attorney_history_clean = {
        'grievance_count': 0,
        'clean_record': True
    }
    
    case_context_low = {
        'financial_harm': 0,
        'court_sanctions': False,
        'pro_se_complainant': True
    }
    
    reality_check_low = filter_system.apply_reality_check(
        evidence_low, attorney_history_clean, case_context_low
    )
    
    print(f"\nImpact Level: {reality_check_low.impact_level.value}")
    print(f"Actionable: {reality_check_low.actionable}")
    print(f"\nWhy They Don't Care: {reality_check_low.why_they_dont_care}")
    print(f"\nClerk Reaction: {reality_check_low.clerk_reaction}")
    print(f"\nRecommendation:\n{reality_check_low.recommendation}")
    
    print(f"\n{'='*80}")
    print(f"Filter Statistics:")
    print(f"Total Checks: {filter_system.filters_applied}")
    print(f"Passed (Actionable): {filter_system.passed_filters}")
    print(f"Failed (Not Worth Filing): {filter_system.failed_filters}")
    print(f"{'='*80}")
