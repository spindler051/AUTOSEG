# Security policy

## Reporting a vulnerability

Do not open a public issue containing credentials, personal data, client data,
database files, attachments or reproduction data from a real installation.
Use GitHub's private vulnerability reporting for this repository:

<https://github.com/spindler051/AUTOSEG/security/advisories/new>

## Data policy for the public repository

The public repository must not contain:

- production databases, backups, attachments, PDFs, logs or receipts;
- passwords, tokens, private keys, cookies or session data;
- CPF, CNPJ, addresses, phone numbers, e-mails or names of real clients;
- private hostnames, internal IP addresses or local user paths.

Tests and examples must use fictional data and `.invalid`/`example`
addresses. Company identity values (CNPJ and WhatsApp) are configured outside
the repository through `AUTOSEG_COMPANY_CNPJ` and `AUTOSEG_WHATSAPP`.

## Supported version

The `main` branch receives public fixes. Development happens in `develop`.
Security-sensitive changes require external human review before promotion.
