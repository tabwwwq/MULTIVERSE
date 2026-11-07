# Support

MULTIVERSE is a research prototype maintained by one person. There is no service, no hosted instance and no guarantee of answers.

## Before you ask

- Read the [scientific limitations](README.md#scientific-limitations-read-first): scenarios are not history, forecasts are not effects, results are not advice.
- Start the app with `npm run app` and check [`docs/releases/runbook.md`](docs/releases/runbook.md) for the usual problems.
- Known gaps are listed in [`docs/releases/acceptance-audit.md`](docs/releases/acceptance-audit.md) and in the [issue register](docs/security/issue-register.md).

## Reporting a problem

Open an issue on <https://github.com/tabwwwq/MULTIVERSE/issues> with the commit (`git log -n 1`), the command or page, and what you expected. For a report that does not replay, include its report id and the three SHA-256 values of its manifest. Do not attach `.env`, tokens, `var/` or downloaded source files.

## Security

Do not open a public issue for a vulnerability. Follow [`docs/security/incident-response.md`](docs/security/incident-response.md) and contact the owner privately through GitHub.

## Data and licences

Sources and their terms are in [`docs/security/license-inventory.md`](docs/security/license-inventory.md). The repository does not redistribute raw source data; rebuild it with the commands of the runbook under the terms of each source.
