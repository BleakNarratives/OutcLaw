#!/usr/bin/env python3
"""
OutClaw/outclaw_foia.py — FOIA Request Generator.

LWM INTEGRATION (2026-07-26): Adapted from Llama's Module C (FOIA Generator
Micro-Agent) and DeepSeek's tactical FOIA language from DS LWM.txt.

Generates jurisdiction-specific FOIA/Open Records requests with:
  - Tactical statutory language (forces faster responses)
  - MuckRock-compatible formatting
  - Oklahoma-specific and general federal templates
  - Auto-populated from OutClaw audit findings

Usage:
    from OutClaw.outclaw_foia import FOIAGenerator
    gen = FOIAGenerator()
    request = gen.generate(
        agency="Oklahoma County Sheriff",
        description="All records related to warrant #2024-XXXX",
        jurisdiction="oklahoma"
    )
    print(request)
"""

from __future__ import annotations

from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# Jurisdiction-specific templates with tactical language
# ---------------------------------------------------------------------------

JURISDICTION_CONFIG: dict[str, dict[str, str]] = {
    "federal": {
        "statute": "5 U.S.C. § 552 (Freedom of Information Act)",
        "deadline": "20 business days",
        "expedite_language": "Pursuant to 5 U.S.C. § 552(a)(6)(E), I request expedited processing on the grounds of compelling need involving public interest.",
        "appeal_language": "If denied, I reserve the right to appeal under 5 U.S.C. § 552(a)(6).",
    },
    "oklahoma": {
        "statute": "Okla. Stat. tit. 51, § 24A.1 et seq. (Oklahoma Open Records Act)",
        "deadline": "10 business days",
        "expedite_language": "Pursuant to Okla. Stat. tit. 51, § 24A.5(B), failure to respond within 10 business days constitutes a denial subject to judicial review in the district court.",
        "appeal_language": "Any denial must be in writing with specific statutory exemption cited per Okla. Stat. tit. 51, § 24A.5.",
    },
    "kansas": {
        "statute": "K.S.A. 45-215 et seq. (Kansas Open Records Act)",
        "deadline": "3 business days (acknowledgment); reasonable time for production",
        "expedite_language": "I request expedited access under K.S.A. 45-218 given the public interest in governmental transparency.",
        "appeal_language": "Any denial may be appealed to the Kansas Attorney General under K.S.A. 45-222.",
    },
    "generic": {
        "statute": "applicable state open records / freedom of information law",
        "deadline": "statutory timeframe",
        "expedite_language": "I request expedited processing on grounds of public interest.",
        "appeal_language": "I reserve all rights to appeal any denial or inadequate response.",
    },
}

TEMPLATE = """{date}

VIA {method}

{agency}
{address}

Re: Open Records / FOIA Request — {subject}

To the Custodian of Records:

Pursuant to {statute}, I hereby request access to and copies of the following records:

{description}

I request that these records be provided in {format} format. If any portion of this request is denied, please provide a written explanation citing the specific statutory exemption relied upon, as required by law.

{expedite}

{scope}

{appeal}

Please direct all correspondence regarding this request to:

{requester_name}
{requester_contact}

{closing}

Sincerely,

{requester_name}
"""


# ═══════════════════════════════════════════════════════
#  OUTCLAW_FOIA
# ═══════════════════════════════════════════════════════════════

class FOIAGenerator:
    """Generates jurisdiction-specific FOIA / Open Records requests."""

    def generate(
        self,
        agency: str,
        description: str,
        jurisdiction: str = "generic",
        requester_name: str = "[Your Name]",
        requester_contact: str = "[Your Contact Information]",
        format: str = "electronic (PDF or native)",
        method: str = "CERTIFIED MAIL — RETURN RECEIPT REQUESTED",
        address: str = "[Agency Address]",
        subject: str = "",
        scope: str = "",
        closing: str = "",
    ) -> str:
        """
        Generate a FOIA request letter.

        Args:
            agency: Name of the agency/department.
            description: Detailed description of records requested.
            jurisdiction: 'federal', 'oklahoma', 'kansas', or 'generic'.
            requester_name: Your name.
            requester_contact: Email, phone, or mailing address.
            format: Desired format (electronic, paper, etc.).
            method: Delivery method for the request.
            address: Agency mailing address.
            subject: Optional subject line override.
            scope: Optional scope limitation language.
            closing: Optional closing paragraph.
        """
        config = JURISDICTION_CONFIG.get(
            jurisdiction.lower(), JURISDICTION_CONFIG["generic"]
        )

        # Escape curly braces in user-supplied values to prevent .format() KeyError
        def _esc(s: str) -> str:
            return s.replace("{", "{{").replace("}", "}}")

        if not subject:
            subject = f"Request for Records — {agency}"

        if not scope:
            scope = (
                "This request encompasses all records, correspondence, emails, "
                "memoranda, reports, data, and investigative files, including "
                "exhibits and attachments, regardless of physical form or storage medium."
            )

        if not closing:
            closing = (
                "I look forward to your response within the statutorily prescribed "
                "timeframe. Please note that this request is made for non-commercial, "
                "public-interest purposes."
            )

        return TEMPLATE.format(
            date=date.today().strftime("%B %d, %Y"),
            method=method,
            agency=agency,
            address=address,
            subject=subject,
            statute=config["statute"],
            description=_esc(description),
            format=format,
            expedite=config["expedite_language"],
            scope=scope,
            appeal=config["appeal_language"],
            requester_name=requester_name,
            requester_contact=requester_contact,
            closing=closing,
        )

    def from_audit_findings(
        self,
        findings: list[dict[str, Any]],
        agency: str = "",
        jurisdiction: str = "generic",
    ) -> str:
        """
        Generate a FOIA request automatically from OutClaw audit findings.

        The request cites the specific documents and issues identified
        by the audit pipeline.
        """
        if not findings:
            raise ValueError(
                "No audit findings provided — cannot generate targeted FOIA."
            )

        # Build description from findings
        lines = []
        for f in findings[:10]:
            citation = f.get("citation", f.get("category", "Unknown"))
            rule = f.get("rule", f.get("label", "issue"))
            detail = f.get("detail", "")
            lines.append(f"- Records related to {citation} ({rule}): {detail}"[:200])

        description = (
            "The following specific records and categories of records "
            "are requested:\n\n" + "\n".join(lines)
        )

        return self.generate(
            agency=agency or "Appropriate Agency",
            description=description,
            jurisdiction=jurisdiction,
            subject=f"Targeted Records Request — Audit Findings ({len(findings)} items)",
        )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def generate_foia(agency: str, description: str, jurisdiction: str = "generic") -> str:
    """One-liner: generate a FOIA request."""
    return FOIAGenerator().generate(agency, description, jurisdiction)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    gen = FOIAGenerator()

    # Federal FOIA
    print("=== Federal FOIA ===")
    print(
        gen.generate(
            agency="Department of Justice, Office of Information Policy",
            description="All records, correspondence, and investigative files "
            "related to Case No. 2024-CR-00123, including but not "
            "limited to Brady/Giglio material, witness statements, "
            "and forensic reports.",
            jurisdiction="federal",
        )[:500]
        + "...\n"
    )

    # Oklahoma-specific with tactical language
    print("=== Oklahoma Open Records (tactical) ===")
    print(
        gen.generate(
            agency="Oklahoma County Sheriff's Office",
            description="All records pertaining to VPO #PO-2024-XXXXX filed "
            "on or about March 15, 2024, including the original "
            "petition, supporting affidavits, service records, "
            "and any ex parte communications with the issuing judge.",
            jurisdiction="oklahoma",
        )[:500]
        + "...\n"
    )

    # From audit findings
    print("=== FOIA from Audit Findings ===")
    sample_findings = [
        {
            "citation": "99 U.S.C. § 9999",
            "rule": "EXISTENCE",
            "detail": "Fabricated citation — no such statute exists.",
        },
        {
            "citation": "999 F.3d 111",
            "rule": "NEGATIVE TREATMENT",
            "detail": "Doe v. State has been overruled.",
        },
    ]
    print(
        gen.from_audit_findings(
            sample_findings, agency="Wellington Police Dept", jurisdiction="kansas"
        )[:500]
        + "..."
    )
