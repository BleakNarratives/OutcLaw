"""
OutClaw Evidentiary Objections Engine
Code Judo: Automated Objection Generation

Focuses on:
1. Hearsay objections (largest category)
2. Trensey v. Pagliaro principle (counsel statements ≠ evidence)
3. Voir dire objections
4. Prosecutor/attorney statements without firsthand knowledge
5. State-specific and federal rules

Federal Rules of Evidence (FRE) and state equivalents
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum
import re

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
#  OUTCLAW_OBJECTIONS_ENGINE
# ═══════════════════════════════════════════════════════════════

class ObjectionType(Enum):
    """Types of evidentiary objections"""
    HEARSAY = "hearsay"
    RELEVANCE = "relevance"
    FOUNDATION = "foundation"
    SPECULATION = "speculation"
    ARGUMENTATIVE = "argumentative"
    ASKED_ANSWERED = "asked_and_answered"
    LEADING = "leading"
    COMPOUND = "compound"
    ASSUMES_FACTS = "assumes_facts_not_in_evidence"
    IMPROPER_OPINION = "improper_opinion"
    BEST_EVIDENCE = "best_evidence_rule"
    AUTHENTICATION = "authentication"
    PRIVILEGE = "privilege"
    PREJUDICIAL = "unfairly_prejudicial"
    COUNSEL_TESTIMONY = "counsel_testifying"


class HearsayException(Enum):
    """Common hearsay exceptions (FRE 803, 804)"""
    PRESENT_SENSE = "803(1) - Present Sense Impression"
    EXCITED_UTTERANCE = "803(2) - Excited Utterance"
    STATE_OF_MIND = "803(3) - Then-Existing Mental/Emotional/Physical Condition"
    MEDICAL_DIAGNOSIS = "803(4) - Statement Made for Medical Diagnosis"
    RECORDED_RECOLLECTION = "803(5) - Recorded Recollection"
    BUSINESS_RECORDS = "803(6) - Records of Regularly Conducted Activity"
    PUBLIC_RECORDS = "803(8) - Public Records"
    LEARNED_TREATISE = "803(18) - Learned Treatises"
    FORMER_TESTIMONY = "804(b)(1) - Former Testimony"
    DYING_DECLARATION = "804(b)(2) - Statement Under Belief of Imminent Death"
    STATEMENT_AGAINST_INTEREST = "804(b)(3) - Statement Against Interest"
    ADMISSION_PARTY_OPPONENT = "801(d)(2) - Admission by Party-Opponent"


@dataclass
class ObjectionContext:
    """Context for generating objection"""
    statement: str
    speaker: str  # Who said it
    speaker_role: str  # witness, attorney, prosecutor, judge
    purpose: str  # Why it's being offered (truth of matter, impeachment, etc.)
    jurisdiction: str  # federal, state
    state: Optional[str] = None
    trial_phase: str = "trial"  # voir_dire, opening, trial, closing
    transcript_page: Optional[int] = None
    line_number: Optional[int] = None


@dataclass
class Objection:
    """Generated objection with legal basis"""
    objection_type: ObjectionType
    objection_text: str  # What to say in court
    legal_basis: str  # Rule citation
    explanation: str  # Why it applies
    response_to_overruled: str  # What to say if judge overrules
    offer_of_proof: Optional[str] = None  # If your objection is sustained
    case_law: List[str] = field(default_factory=list)
    severity: str = "MEDIUM"  # HIGH, MEDIUM, LOW


class ObjectionsEngine:
    """
    Automated evidentiary objections generator.
    
    Analyzes statements and generates proper objections with legal basis.
    """
    
    # Federal Rules of Evidence
    FEDERAL_RULES = {
        'hearsay': {
            'rule': 'FRE 802',
            'text': 'Hearsay is not admissible unless an exception applies',
            'definition': 'FRE 801(c): Statement offered to prove the truth of the matter asserted'
        },
        'relevance': {
            'rule': 'FRE 401, 402',
            'text': 'Evidence must be relevant and probative value must outweigh prejudice'
        },
        'foundation': {
            'rule': 'FRE 602',
            'text': 'Witness must have personal knowledge'
        },
        'opinion': {
            'rule': 'FRE 701, 702',
            'text': 'Lay witness opinion must be rationally based on perception; expert must be qualified'
        },
        'authentication': {
            'rule': 'FRE 901',
            'text': 'Evidence must be authenticated before admission'
        },
        'best_evidence': {
            'rule': 'FRE 1002',
            'text': 'Original writing required to prove content'
        },
        'prejudice': {
            'rule': 'FRE 403',
            'text': 'Court may exclude if probative value substantially outweighed by unfair prejudice'
        }
    }
    
    # State-specific rules (Oklahoma example)
    STATE_RULES = {
        'oklahoma': {
            'hearsay': {
                'rule': '12 O.S. § 2801-2806',
                'text': 'Oklahoma Evidence Code mirrors Federal Rules'
            },
            'relevance': {
                'rule': '12 O.S. § 2401-2403',
                'text': 'Evidence must be relevant'
            }
        },
        'kansas': {
            'hearsay': {
                'rule': 'K.S.A. 60-460',
                'text': 'Kansas follows Federal Rules of Evidence'
            }
        }
    }
    
    # Trensey v. Pagliaro principle
    TRENSEY_PRINCIPLE = {
        'case': 'Trensey v. Pagliaro, 291 N.J. Super. 18 (App. Div. 1996)',
        'holding': 'Statements of adverse counsel, while enlightening, do not rise to the level of preponderance of the evidence',
        'application': 'Attorney arguments and statements are NOT evidence and cannot be considered as proof',
        'objection': 'Objection: Counsel is testifying. Statements of counsel are not evidence per Trensey v. Pagliaro.'
    }
    
    # Hearsay indicators (words/phrases that suggest hearsay)
    HEARSAY_INDICATORS = [
        r'\b(he|she|they) (said|told|stated|claimed|mentioned|reported)\b',
        r'\bI (heard|was told|learned)\b',
        r'\baccording to\b',
        r'\b(someone|somebody) (said|told|heard)\b',
        r'\bthe (report|document|letter) (says|states)\b',
        r'\bthe (witness|officer|accuser|victim|complainant) (said|told|stated|claimed)\b',
        r'\b(testified|stated) in (deposition|affidavit)\b'
    ]
    
    # Attorney testimony indicators
    ATTORNEY_TESTIMONY_INDICATORS = [
        r'^(I|We) (know|believe|think|understand) that',
        r'^The (evidence|facts) (show|demonstrate|prove)',
        r'^It is (clear|obvious|evident) that',
        r'^(My client|The defendant|The plaintiff) (did|was|had)',
        r'^(This|That) (happened|occurred|took place)'
    ]
    
    def __init__(self, jurisdiction: str = 'federal', state: Optional[str] = None):
        self.jurisdiction = jurisdiction
        self.state = state
        self.objections_generated = []
    
    def analyze_statement(self, context: ObjectionContext) -> List[Objection]:
        """
        Analyze statement and generate applicable objections.
        
        Returns list of objections that apply (may be multiple).
        """
        objections = []
        
        # Check for hearsay
        hearsay_obj = self._check_hearsay(context)
        if hearsay_obj:
            objections.append(hearsay_obj)
        
        # Check for attorney testimony (Trensey principle)
        if context.speaker_role in ['attorney', 'prosecutor']:
            attorney_obj = self._check_attorney_testimony(context)
            if attorney_obj:
                objections.append(attorney_obj)
        
        # Check for lack of foundation
        foundation_obj = self._check_foundation(context)
        if foundation_obj:
            objections.append(foundation_obj)
        
        # Check for speculation
        speculation_obj = self._check_speculation(context)
        if speculation_obj:
            objections.append(speculation_obj)
        
        # Check for relevance
        relevance_obj = self._check_relevance(context)
        if relevance_obj:
            objections.append(relevance_obj)
        
        # Voir dire specific objections
        if context.trial_phase == 'voir_dire':
            voir_dire_objs = self._check_voir_dire_violations(context)
            objections.extend(voir_dire_objs)
        
        self.objections_generated.extend(objections)
        return objections
    
    def _check_hearsay(self, context: ObjectionContext) -> Optional[Objection]:
        """
        Check if statement is hearsay.
        
        Hearsay = Out of court statement offered for truth of matter asserted
        """
        # Check if statement contains hearsay indicators
        is_hearsay = False
        for pattern in self.HEARSAY_INDICATORS:
            if re.search(pattern, context.statement, re.IGNORECASE):
                is_hearsay = True
                break
        
        if not is_hearsay:
            return None
        
        # Check if offered for truth
        if context.purpose.lower() not in ['truth', 'prove', 'establish']:
            # May not be hearsay if not offered for truth
            return None
        
        # Get applicable rule
        if self.jurisdiction == 'federal':
            rule_info = self.FEDERAL_RULES['hearsay']
        else:
            rule_info = self.STATE_RULES.get(self.state, {}).get('hearsay', self.FEDERAL_RULES['hearsay'])
        
        objection_text = f"Objection: Hearsay. {rule_info['rule']}."
        
        explanation = f"""
This statement is hearsay because:
1. It is an out-of-court statement (not made by witness on stand)
2. It is being offered to prove the truth of the matter asserted
3. No exception applies

{rule_info['text']}

The statement contains hearsay indicators: "{context.statement}"
"""
        
        response_to_overruled = f"""
Your Honor, I respectfully note my continuing objection to hearsay testimony.
For the record, this out-of-court statement is being offered for its truth without
the declarant being subject to cross-examination, violating {rule_info['rule']}.
I request that the jury be instructed that statements of third parties are not evidence
unless the declarant testifies and is subject to cross-examination.
"""
        
        return Objection(
            objection_type=ObjectionType.HEARSAY,
            objection_text=objection_text,
            legal_basis=rule_info['rule'],
            explanation=explanation,
            response_to_overruled=response_to_overruled,
            case_law=[
                'Crawford v. Washington, 541 U.S. 36 (2004) - Confrontation Clause',
                'Williamson v. United States, 512 U.S. 594 (1994) - Hearsay exceptions'
            ],
            severity="HIGH"
        )
    
    def _check_attorney_testimony(self, context: ObjectionContext) -> Optional[Objection]:
        """
        Check if attorney is testifying (Trensey v. Pagliaro principle).
        
        Attorneys cannot testify. Their statements are not evidence.
        They have no firsthand knowledge.
        """
        # Check if attorney is making factual assertions
        is_testifying = False
        for pattern in self.ATTORNEY_TESTIMONY_INDICATORS:
            if re.search(pattern, context.statement, re.IGNORECASE):
                is_testifying = True
                break
        
        if not is_testifying:
            return None
        
        objection_text = f"""Objection: Counsel is testifying. Statements of counsel are not evidence and counsel has no firsthand knowledge of the facts. {self.TRENSEY_PRINCIPLE['case']}."""
        
        explanation = f"""
This objection applies because:

1. ATTORNEY HAS NO FIRSTHAND KNOWLEDGE
   - Attorneys were not present when events occurred
   - They cannot testify to facts
   - They only know what they've been told (hearsay)

2. TRENSEY V. PAGLIARO PRINCIPLE
   {self.TRENSEY_PRINCIPLE['holding']}
   
   Application: {self.TRENSEY_PRINCIPLE['application']}

3. STATEMENTS OF COUNSEL ARE NOT EVIDENCE
   - Only witness testimony under oath is evidence
   - Only exhibits admitted into evidence are evidence
   - Attorney arguments are NOT evidence

4. VIOLATES RULES OF PROFESSIONAL CONDUCT
   - Attorney cannot be both advocate and witness
   - Creates conflict of interest
   - Undermines adversarial process

The statement "{context.statement}" is counsel making factual assertions
without personal knowledge, which is improper testimony.
"""
        
        response_to_overruled = f"""
Your Honor, I respectfully request that the jury be instructed that:

1. Statements of counsel are NOT evidence
2. Only testimony of witnesses under oath is evidence
3. Only exhibits admitted into evidence are evidence
4. Counsel's assertions about facts are not proof

As held in {self.TRENSEY_PRINCIPLE['case']}, statements of adverse counsel,
while enlightening, do not rise to the level of preponderance of the evidence.

I request this instruction be given immediately and in final jury instructions.
"""
        
        return Objection(
            objection_type=ObjectionType.COUNSEL_TESTIMONY,
            objection_text=objection_text,
            legal_basis=self.TRENSEY_PRINCIPLE['case'],
            explanation=explanation,
            response_to_overruled=response_to_overruled,
            case_law=[
                self.TRENSEY_PRINCIPLE['case'],
                'Model Rules of Professional Conduct 3.7 - Lawyer as Witness',
                'FRE 602 - Need for Personal Knowledge'
            ],
            severity="HIGH"
        )
    
    def _check_foundation(self, context: ObjectionContext) -> Optional[Objection]:
        """Check if proper foundation has been laid"""
        
        if context.speaker_role != 'witness':
            return None
        
        # Check if witness has personal knowledge
        lacks_foundation = any([
            'I heard' in context.statement,
            'I was told' in context.statement,
            'I believe' in context.statement,
            'I think' in context.statement,
            'someone said' in context.statement.lower()
        ])
        
        if not lacks_foundation:
            return None
        
        rule = 'FRE 602' if self.jurisdiction == 'federal' else '12 O.S. § 2602'
        
        objection_text = f"Objection: Lack of foundation. Witness has not established personal knowledge. {rule}."
        
        explanation = f"""
Proper foundation requires:
1. Witness must have personal knowledge
2. Witness must have perceived the event with their own senses
3. Witness cannot testify based on what others told them

{rule}: A witness may testify to a matter only if evidence is introduced
sufficient to support a finding that the witness has personal knowledge of the matter.

The statement "{context.statement}" indicates the witness lacks personal knowledge.
"""
        
        return Objection(
            objection_type=ObjectionType.FOUNDATION,
            objection_text=objection_text,
            legal_basis=rule,
            explanation=explanation,
            response_to_overruled="Your Honor, I request voir dire of the witness to establish foundation.",
            severity="MEDIUM"
        )
    
    def _check_speculation(self, context: ObjectionContext) -> Optional[Objection]:
        """Check if witness is speculating"""
        
        speculation_indicators = [
            'I think', 'I believe', 'I assume', 'I guess',
            'probably', 'maybe', 'might have', 'could have',
            'I suppose', 'it seems', 'appears to be'
        ]
        
        is_speculation = any(
            indicator in context.statement.lower()
            for indicator in speculation_indicators
        )
        
        if not is_speculation:
            return None
        
        objection_text = "Objection: Speculation. Witness is guessing rather than testifying to facts."
        
        explanation = f"""
Witness testimony must be based on personal knowledge and observation,
not speculation or conjecture.

The statement "{context.statement}" contains speculative language indicating
the witness is guessing rather than testifying to facts they know.
"""
        
        return Objection(
            objection_type=ObjectionType.SPECULATION,
            objection_text=objection_text,
            legal_basis="FRE 602",
            explanation=explanation,
            response_to_overruled="Your Honor, I request the jury be instructed to disregard speculation.",
            severity="MEDIUM"
        )
    
    def _check_relevance(self, context: ObjectionContext) -> Optional[Objection]:
        """Check relevance (requires context about case issues)"""
        # This would need more context about the case to determine relevance
        # Placeholder for now
        return None
    
    def _check_voir_dire_violations(self, context: ObjectionContext) -> List[Objection]:
        """
        Check for voir dire specific violations.
        
        Voir dire is critical for jury selection and has special rules.
        """
        objections = []
        
        # Check for improper commitment questions
        commitment_patterns = [
            r'will you (always|never)',
            r'do you promise to',
            r'can you guarantee',
            r'will you vote for'
        ]
        
        for pattern in commitment_patterns:
            if re.search(pattern, context.statement, re.IGNORECASE):
                objections.append(Objection(
                    objection_type=ObjectionType.IMPROPER_OPINION,
                    objection_text="Objection: Improper commitment question. Counsel is asking juror to pre-commit to a verdict.",
                    legal_basis="Voir dire must not elicit commitments to verdict",
                    explanation="""
Voir dire questions cannot ask jurors to commit to a particular verdict or outcome.
Jurors must remain impartial and base their decision on evidence presented at trial.

This question improperly seeks a commitment before evidence is heard.
""",
                    response_to_overruled="Your Honor, I request the jury panel be instructed that they are not bound by any commitments and must base their verdict solely on the evidence.",
                    severity="HIGH"
                ))
        
        # Check for improper questions about law
        if 'do you agree with the law' in context.statement.lower():
            objections.append(Objection(
                objection_type=ObjectionType.IMPROPER_OPINION,
                objection_text="Objection: Improper question. Jurors must follow the law as instructed by the court, regardless of personal opinion.",
                legal_basis="Juror oath requires following law as given by court",
                explanation="""
Jurors take an oath to follow the law as instructed by the court.
Their personal opinions about the law are irrelevant.

This question improperly suggests jurors can disregard the law if they disagree with it.
""",
                response_to_overruled="Your Honor, I request the jury be instructed they must follow the law as you instruct them.",
                severity="HIGH"
            ))
        
        # Check for improper questions about damages
        if re.search(r'how much (money|damages)', context.statement, re.IGNORECASE):
            objections.append(Objection(
                objection_type=ObjectionType.IMPROPER_OPINION,
                objection_text="Objection: Improper question about damages before evidence is presented.",
                legal_basis="Damages must be based on evidence, not pre-trial speculation",
                explanation="""
Jurors cannot determine damages before hearing evidence.
This question improperly asks jurors to speculate about damages.
""",
                response_to_overruled="Your Honor, I request the jury be instructed that damages must be based solely on evidence presented at trial.",
                severity="MEDIUM"
            ))
        
        return objections
    
    def generate_objection_script(self, objections: List[Objection]) -> str:
        """
        Generate a script for making objections in court.
        
        Provides exact language to use.
        """
        if not objections:
            return "No objections applicable."
        
        script = "OBJECTION SCRIPT\n"
        script += "="*80 + "\n\n"
        
        for i, obj in enumerate(objections, 1):
            script += f"OBJECTION #{i}: {obj.objection_type.value.upper()}\n"
            script += "-"*80 + "\n\n"
            
            script += "WHAT TO SAY:\n"
            script += f'"{obj.objection_text}"\n\n'
            
            script += "LEGAL BASIS:\n"
            script += f"{obj.legal_basis}\n\n"
            
            script += "WHY IT APPLIES:\n"
            script += f"{obj.explanation}\n\n"
            
            if obj.case_law:
                script += "SUPPORTING CASE LAW:\n"
                for case in obj.case_law:
                    script += f"- {case}\n"
                script += "\n"
            
            script += "IF OVERRULED, SAY:\n"
            script += f'"{obj.response_to_overruled}"\n\n'
            
            script += "="*80 + "\n\n"
        
        return script
    
    def generate_voir_dire_objection_guide(self) -> str:
        """Generate comprehensive voir dire objection guide"""
        
        guide = """
VOIR DIRE OBJECTION GUIDE
========================

Voir dire is the most critical phase of trial. Improper voir dire can taint the entire jury.

COMMON VOIR DIRE VIOLATIONS:

1. COMMITMENT QUESTIONS
   Improper: "Will you always believe a police officer?"
   Objection: "Objection: Improper commitment question."
   Why: Jurors cannot pre-commit to believing any witness.

2. QUESTIONS ABOUT THE LAW
   Improper: "Do you agree with the law on self-defense?"
   Objection: "Objection: Jurors must follow the law as instructed by the court."
   Why: Jurors' personal opinions about law are irrelevant.

3. ARGUING THE CASE
   Improper: "The evidence will show my client is innocent..."
   Objection: "Objection: Counsel is arguing the case during voir dire."
   Why: Voir dire is for jury selection, not argument.

4. ASKING FOR VERDICT
   Improper: "Can you find for my client if..."
   Objection: "Objection: Improper to ask for verdict before evidence."
   Why: Verdict must be based on evidence, not voir dire promises.

5. IMPROPER REHABILITATION
   Improper: "Even though you said X, you can still be fair, right?"
   Objection: "Objection: Improper rehabilitation of juror for cause."
   Why: Cannot rehabilitate juror who has shown bias.

6. GOLDEN RULE ARGUMENTS
   Improper: "What if this happened to you or your family?"
   Objection: "Objection: Improper golden rule argument."
   Why: Jurors must be impartial, not put themselves in party's shoes.

PROPER OBJECTION PROCEDURE IN VOIR DIRE:

1. Stand immediately
2. State: "Objection, Your Honor. May we approach?"
3. At sidebar, explain objection out of jury's hearing
4. Request curative instruction if needed
5. Request juror be struck for cause if bias shown

CRITICAL: Most voir dire objections should be made at sidebar to avoid
alerting the jury to the improper question's purpose.

TRENSEY V. PAGLIARO IN VOIR DIRE:

When opposing counsel makes factual assertions during voir dire:
"Objection: Counsel is testifying. Statements of counsel are not evidence.
Per Trensey v. Pagliaro, counsel's assertions do not constitute proof."

SAMPLE OBJECTIONS:

Attorney: "The evidence will show my client was at home that night."
You: "Objection: Counsel is testifying and arguing the case during voir dire."

Attorney: "Will you always believe a police officer over a civilian?"
You: "Objection: Improper commitment question. Jurors must evaluate each witness individually."

Attorney: "Do you think the law on [X] is fair?"
You: "Objection: Jurors must follow the law as instructed, regardless of personal opinion."

Attorney: "If I prove [X], will you find for my client?"
You: "Objection: Improper to ask for verdict commitment before evidence is presented."

REMEMBER: Voir dire objections are often waived if not made timely.
Object immediately to preserve the record.
"""
        
        return guide


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    engine = ObjectionsEngine(jurisdiction='federal')
    
    print("\n" + "="*80)
    print("EXAMPLE 1: Hearsay Objection")
    print("="*80)
    
    context1 = ObjectionContext(
        statement="The witness told me that the defendant was at the scene",
        speaker="John Doe",
        speaker_role="witness",
        purpose="truth",
        jurisdiction="federal",
        trial_phase="trial"
    )
    
    objections1 = engine.analyze_statement(context1)
    if objections1:
        print(engine.generate_objection_script(objections1))
    
    print("\n" + "="*80)
    print("EXAMPLE 2: Attorney Testimony (Trensey Principle)")
    print("="*80)
    
    context2 = ObjectionContext(
        statement="I know that my client was at home that night",
        speaker="Defense Attorney",
        speaker_role="attorney",
        purpose="truth",
        jurisdiction="federal",
        trial_phase="trial"
    )
    
    objections2 = engine.analyze_statement(context2)
    if objections2:
        print(engine.generate_objection_script(objections2))
    
    print("\n" + "="*80)
    print("EXAMPLE 3: Voir Dire Violations")
    print("="*80)
    
    context3 = ObjectionContext(
        statement="Will you always believe a police officer over a civilian?",
        speaker="Prosecutor",
        speaker_role="prosecutor",
        purpose="voir_dire",
        jurisdiction="federal",
        trial_phase="voir_dire"
    )
    
    objections3 = engine.analyze_statement(context3)
    if objections3:
        print(engine.generate_objection_script(objections3))
    
    print("\n" + "="*80)
    print("VOIR DIRE OBJECTION GUIDE")
    print("="*80)
    print(engine.generate_voir_dire_objection_guide())
    
    print(f"\n📊 Total Objections Generated: {len(engine.objections_generated)}")
