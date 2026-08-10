# Security and Privacy

## Scope

OutClaw is local-first software for legal-text review. It can process sensitive
case material, but it is not an encrypted evidence-management system and does not
provide a legal privilege guarantee. Operators are responsible for filesystem
permissions, backups, device security, and the services they enable.

## Sensitive data rules

Do not commit or share:

- original arrest reports, court records, photographs, or audio/video;
- names, addresses, phone numbers, dates of birth, government identifiers, or
  other personally identifying information;
- credentials, API keys, `.env` files, acknowledgment tokens, or private logs;
- generated databases or exports containing case material.

Raw Mel evidence is intentionally outside the normal repository workflow. The
root ignore rules cover the known raw report and JPEG evidence patterns. Verify
with `git check-ignore -v` before staging any case-related path. A redacted copy
may still contain indirect identifiers (such as case number, dates, location, or
offense details); a human must review it before sharing or committing.

## Processing boundary

The core audit, regression, and safety tests are intended to run offline. Optional
features may contact external services when explicitly enabled, including:

- CourtListener or another legal-research endpoint for citation lookup;
- free-tier cloud LLM providers (via the cascade) for assisted classification
  — keys are read from the environment; NO local inference is used;
- a local dashboard HTTP server bound to a machine port.

Review configuration, network behavior, and data minimization before sending any
text outside the local process. Do not paste private case content into public
issues, pull requests, hosted assistants, or third-party APIs.

The safe-draft acknowledgment token is a randomly generated, single-use workflow
confirmation. It is not authentication and must not be treated as a secret that
protects an account or document repository.

## Reporting a vulnerability

Please do not publish a suspected vulnerability with exploit details or private
case data. Report it privately to the repository maintainers through the hosting
provider's private security channel, if enabled. If no private channel is
available, contact the project owner through a trusted private method and include:

- affected file, command, or version;
- minimal reproduction using synthetic data;
- impact and practical attack conditions;
- a suggested mitigation, if known.

Allow maintainers reasonable time to reproduce and address the issue. Never attach
raw evidence or credentials to a security report.

## Operator checklist

- Use a dedicated virtual environment.
- Restrict permissions on local evidence directories and backups.
- Keep raw evidence outside CI workspaces.
- Run the offline tests before and after changes.
- Review `git diff --cached` and `git status --short` before every commit.
- Revoke and rotate any credential accidentally exposed.
