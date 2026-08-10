#!/usr/bin/env python3
"""
OutClaw/outclaw_irac.py — IRAC Legal Analysis Engine.

LWM INTEGRATION (2026-07-26): Adapted from DeepSeek's legal analysis in
legal_cli.txt which demonstrated the full IRAC (Issue, Rule, Analysis,
Conclusion) methodology applied to real legal questions.

This module provides a structured legal analysis framework that:
  1. Accepts a legal question and jurisdiction context
  2. Maps to relevant case law from OutClaw's seed registry
  3. Generates an IRAC-structured analysis
  4. Flags relevant statutes and precedents

The analysis is heuristic (not LLM-based) for offline reliability,
but structured to mirror what a legal research memo would contain.

Usage:
    from OutClaw.outclaw_irac import IRACAnalyzer
    analyzer = IRACAnalyzer()
    brief = analyzer.analyze(
        question="Was probable cause established for the warrant?",
        jurisdiction="federal",
        relevant_facts=["Affidavit signed by non-witness officer",
                        "Hearsay from alleged victim used"]
    )
    print(brief)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# IRAC Section
# ---------------------------------------------------------------------------


@dataclass
# ═══════════════════════════════════════════════════════
#  OUTCLAW_IRAC
# ═══════════════════════════════════════════════════════════════

class IRACBrief:
    question: str
    jurisdiction: str
    facts: list[str]
    issue: str
    rules: list[dict[str, str]]  # {citation, holding, relevance}
    analysis: str
    conclusion: str
    confidence: str  # HIGH, MEDIUM, LOW
    action_steps: list[str] = field(default_factory=list)
    disclaimer: str = (
        "This is an informational analysis, not legal advice. Consult an attorney."
    )


# ---------------------------------------------------------------------------
# Rule database — key legal principles keyed by topic
# ---------------------------------------------------------------------------

RULE_DATABASE: dict[str, list[dict[str, str]]] = {
    "probable cause": [
        {
            "citation": "Beck v. Ohio, 379 U.S. 89 (1964)",
            "holding": "Probable cause exists where facts and circumstances within the officers' knowledge warrant a reasonable belief that an offense has been committed.",
            "relevance": "Defines the constitutional standard for probable cause.",
        },
        {
            "citation": "Illinois v. Gates, 462 U.S. 213 (1983)",
            "holding": "Probable cause can be based on hearsay; the test is the totality of the circumstances.",
            "relevance": "Establishes that non-witness officer affidavits based on hearsay can satisfy probable cause.",
        },
        {
            "citation": "Franks v. Delaware, 438 U.S. 154 (1978)",
            "holding": "A defendant may challenge the veracity of a warrant affidavit; false statements made knowingly or recklessly invalidate probable cause.",
            "relevance": "Provides mechanism to challenge affidavits containing false information.",
        },
    ],
    "brady material": [
        {
            "citation": "Brady v. Maryland, 373 U.S. 83 (1963)",
            "holding": "Suppression of evidence favorable to the accused violates due process where the evidence is material to guilt or punishment.",
            "relevance": "Foundational duty of prosecution to disclose exculpatory evidence.",
        },
        {
            "citation": "United States v. Bagley, 473 U.S. 667 (1985)",
            "holding": "Evidence is material if there is a reasonable probability that its disclosure would have changed the proceeding's outcome.",
            "relevance": "Defines the materiality standard for Brady violations.",
        },
    ],
    "qualified immunity": [
        {
            "citation": "Harlow v. Fitzgerald, 457 U.S. 202 (1982)",
            "holding": "Government officials are entitled to qualified immunity unless their conduct violates clearly established statutory or constitutional rights.",
            "relevance": "Defines qualified immunity standard.",
        },
    ],
    "due process": [
        {
            "citation": "Mathews v. Eldridge, 424 U.S. 319 (1976)",
            "holding": "Due process requires consideration of the private interest affected, the risk of erroneous deprivation, and the government's interest.",
            "relevance": "Framework for evaluating procedural due process claims.",
        },
    ],
    "judicial immunity": [
        {
            "citation": "Stump v. Sparkman, 435 U.S. 349 (1978)",
            "holding": "Judges are immune from civil suit for judicial acts unless taken in clear absence of all jurisdiction.",
            "relevance": "Defines the scope of judicial immunity and its exception for extra-jurisdictional acts.",
        },
        {
            "citation": "Pulliam v. Allen, 466 U.S. 522 (1984)",
            "holding": "Judicial immunity does not bar injunctive relief or attorney's fees under § 1988.",
            "relevance": "Establishes that injunctive relief against judges is available.",
        },
    ],
    "search and seizure": [
        {
            "citation": "Mapp v. Ohio, 367 U.S. 643 (1961)",
            "holding": "Evidence obtained through unreasonable search and seizure is inadmissible in state court.",
            "relevance": "Establishes the exclusionary rule for Fourth Amendment violations.",
        },
    ],
    "self-defense": [
        {
            "citation": "The Castle Doctrine (state-specific)",
            "holding": "An individual has no duty to retreat and may use force, including deadly force, against an intruder in their home if they reasonably believe it necessary to prevent death or great bodily harm.",
            "relevance": "Affirmative defense to battery/assault charges in Castle Doctrine states.",
        },
    ],
    "section 1983": [
        {
            "citation": "Monell v. Dept of Social Services, 436 U.S. 658 (1978)",
            "holding": "Local governments may be sued under § 1983 for constitutional violations resulting from an official policy or custom.",
            "relevance": "Establishes municipal liability under § 1983.",
        },
    ],
}


class IRACAnalyzer:
    """
    Generates IRAC-structured legal analysis from questions and facts.

    Uses OutClaw's seed registry and built-in rule database to map
    questions to relevant precedents.
    """

    def analyze(
        self,
        question: str,
        jurisdiction: str = "federal",
        relevant_facts: list[str] | None = None,
    ) -> IRACBrief:
        """
        Analyze a legal question using IRAC methodology.

        Args:
            question: The legal question to analyze.
            jurisdiction: 'federal', 'oklahoma', 'kansas', etc.
            relevant_facts: List of relevant factual assertions.

        Returns:
            IRACBrief with structured analysis.
        """
        facts = relevant_facts or []

        # Identify relevant topics from the question
        topics = self._identify_topics(question)
        rules = self._gather_rules(topics)
        issue = self._formulate_issue(question, jurisdiction)
        analysis = self._generate_analysis(question, facts, rules, jurisdiction)
        conclusion = self._generate_conclusion(analysis, rules)
        confidence = self._assess_confidence(rules, analysis)
        action_steps = self._generate_actions(question, rules, facts)

        return IRACBrief(
            question=question,
            jurisdiction=jurisdiction,
            facts=facts,
            issue=issue,
            rules=rules,
            analysis=analysis,
            conclusion=conclusion,
            confidence=confidence,
            action_steps=action_steps,
        )

    def _identify_topics(self, question: str) -> list[str]:
        """Identify legal topics mentioned in the question."""
        q = question.lower()
        topics = []
        topic_keywords = {
            "probable cause": ["probable cause", "warrant", "affidavit", "arrest"],
            "brady material": ["brady", "exculpatory", "disclosure", "evidence"],
            "qualified immunity": ["qualified immunity", "immunity", "official"],
            "due process": ["due process", "procedural", "fair hearing"],
            "judicial immunity": ["judicial immunity", "judge", "immunity from suit"],
            "search and seizure": [
                "search",
                "seizure",
                "fourth amendment",
                "exclusionary",
            ],
            "self-defense": ["self.defense", "castle doctrine", "stand your ground"],
            "section 1983": ["§ 1983", "section 1983", "1983 claim", "civil rights"],
        }
        for topic, keywords in topic_keywords.items():
            if any(kw in q for kw in keywords):
                topics.append(topic)
        if not topics:
            topics.append("general")
        return topics

    def _gather_rules(self, topics: list[str]) -> list[dict[str, str]]:
        """Gather relevant rules from the database."""
        seen: set = set()
        rules: list[dict[str, str]] = []
        for topic in topics:
            for rule in RULE_DATABASE.get(topic, []):
                if rule["citation"] not in seen:
                    rules.append(rule)
                    seen.add(rule["citation"])
        return rules

    def _formulate_issue(self, question: str, jurisdiction: str) -> str:
        """Formulate the legal issue from the question."""
        jx = jurisdiction.title()
        return f"Under {jx} law, {question[0].lower() + question[1:].rstrip('?')}?"

    def _generate_analysis(
        self,
        question: str,
        facts: list[str],
        rules: list[dict[str, str]],
        jurisdiction: str,
    ) -> str:
        """Generate the analysis section."""
        lines = [f"Under {jurisdiction.title()} law, the following principles apply:"]
        lines.append("")

        for i, rule in enumerate(rules, 1):
            lines.append(f"{i}. {rule['citation']}: {rule['holding']}")
            lines.append(f"   Relevance: {rule['relevance']}")
            lines.append("")

        if facts:
            lines.append("Applied to the facts presented:")
            for fact in facts:
                lines.append(f"  • {fact}")
            lines.append("")

        if rules:
            lines.append(
                "The resolution depends on whether the specific facts satisfy "
                "the legal standards articulated above. Further factual "
                "development may be necessary to reach a definitive conclusion. "
                "Counsel should conduct jurisdiction-specific research to "
                "verify the current status of cited authorities."
            )

        return "\n".join(lines)

    def _generate_conclusion(self, analysis: str, rules: list[dict[str, str]]) -> str:
        """Generate the conclusion."""
        if not rules:
            return (
                "Insufficient legal authority identified to reach a conclusion. "
                "Additional research in the specific jurisdiction is required."
            )
        return (
            "Based on the authorities identified, a reasoned legal argument can "
            "be constructed. The outcome will depend on how the specific facts "
            "align with the legal standards set forth in the cited precedents. "
            "Consultation with licensed counsel in this jurisdiction is recommended "
            "before filing any pleading or motion."
        )

    def _assess_confidence(self, rules: list[dict[str, str]], analysis: str) -> str:
        """Assess confidence level."""
        if len(rules) >= 3:
            return "HIGH — multiple directly relevant authorities identified"
        elif len(rules) >= 1:
            return (
                "MEDIUM — relevant authority identified; further research recommended"
            )
        return (
            "LOW — limited authority identified; jurisdiction-specific research needed"
        )

    def _generate_actions(
        self, question: str, rules: list[dict[str, str]], facts: list[str]
    ) -> list[str]:
        """Generate recommended action steps."""
        actions = []

        if "probable cause" in question.lower() or "affidavit" in question.lower():
            actions.append(
                "Review the charging affidavit for facial validity under Franks v. Delaware."
            )
            actions.append(
                "Request all police reports, witness statements, and body camera footage through discovery."
            )

        if "brady" in question.lower():
            actions.append(
                "File a specific Brady demand enumerating categories of exculpatory material."
            )
            actions.append(
                "Document all instances of non-disclosure with dates and content descriptions."
            )

        if "judge" in question.lower() or "judicial" in question.lower():
            actions.append(
                "Compile all orders, rulings, and communications for judicial conduct review."
            )
            actions.append(
                "Research jurisdiction-specific judicial conduct commission filing procedures."
            )

        if "§ 1983" in question or "1983" in question.lower():
            actions.append(
                "Draft a complaint identifying the specific constitutional right violated."
            )
            actions.append(
                "Include Monell claim language if municipal policy or custom is involved."
            )

        if not actions:
            actions.append(
                "Conduct jurisdiction-specific legal research on the identified topics."
            )
            actions.append(
                "Consult with licensed counsel before filing any legal document."
            )

        return actions

    def to_markdown(self, brief: IRACBrief) -> str:
        """Render an IRAC brief as Markdown."""
        lines = [
            "# IRAC Legal Analysis",
            "",
            f"**Question:** {brief.question}",
            f"**Jurisdiction:** {brief.jurisdiction.title()}",
            f"**Confidence:** {brief.confidence}",
            "",
            "## ISSUE",
            f"{brief.issue}",
            "",
            "## RULE",
        ]
        for r in brief.rules:
            lines.append(f"- **{r['citation']}**: {r['holding']}")
        lines.append("")
        lines.append("## ANALYSIS")
        lines.append(brief.analysis)
        lines.append("")
        lines.append("## CONCLUSION")
        lines.append(brief.conclusion)
        lines.append("")
        lines.append("## RECOMMENDED ACTIONS")
        for a in brief.action_steps:
            lines.append(f"- {a}")
        lines.append("")
        lines.append("---")
        lines.append(f"*{brief.disclaimer}*")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def analyze_question(
    question: str,
    jurisdiction: str = "federal",
    facts: list[str] | None = None,
) -> IRACBrief:
    """One-liner: analyze a legal question and return an IRAC brief."""
    return IRACAnalyzer().analyze(question, jurisdiction, facts)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    analyzer = IRACAnalyzer()
    brief = analyzer.analyze(
        question="Was probable cause established if the charging affidavit was signed by officers who did not witness the incident?",
        jurisdiction="federal",
        relevant_facts=[
            "Affidavit signed by two officers who did not witness the alleged incident.",
            "Affidavit was based entirely on hearsay from the alleged victim.",
            "Defendant claims self-defense under the Castle Doctrine.",
        ],
    )
    print(analyzer.to_markdown(brief))
