# Security

PHAEMA holds council property, lease and financial records, and some personal data about tenants and contacts.
This page says how to report a security problem, what protection is built in today, what is not yet done, and how
security will be assured before councils use PHAEMA for live work.

PHAEMA is in **alpha**. It has not yet had an independent penetration test or accessibility audit, and it should not
be used for live estate management until it has.

## Reporting a vulnerability

Please report security problems privately by email to **stuart@phaema.co.uk**, not in a public GitHub issue.

Please include what you found, how to reproduce it, which version or commit you tested, and what someone could do by
exploiting it. Test only against your own installation or the public test site (which holds fictional data only):
do not access other people's data, degrade the service or use social engineering.

What happens next:

| Step | Target |
|---|---|
| Acknowledgement | Within 5 working days |
| First assessment and severity | Within 10 working days |
| Fix for a critical or high-severity problem | As soon as possible, aiming for 30 days |
| Public disclosure | Agreed with you once a fix is released, normally within 90 days of the report |

PHAEMA is a volunteer-run open-source project and cannot pay bug bounties. With your agreement, you will be credited
in the release notes.

## Supported versions

Fixes are made on the `main` branch. Councils running PHAEMA should update with `./phaema.sh update`. Numbered
releases with release notes and a security support period for each will start before the first council goes live.

## Protection built in

**Signing in and accounts**

- Two-step sign-in (multi-factor authentication) with any standard authenticator app (TOTP, RFC 6238), with
  single-use recovery codes. Councils choose whether it is required for administrators (the default), for everyone,
  or optional. Codes cannot be reused, and five wrong codes end the sign-in attempt.
- The admin site signs in through the same page, so two-step sign-in cannot be bypassed there. The API refuses a
  username and password for anyone with two-step sign-in.
- Passwords are at least 12 characters, checked against common passwords and the person's own details, and stored
  using Django's salted PBKDF2 hashing. Recovery codes are stored only as hashes.
- Access is by role (administrator, surveyor, contributor, viewer) and access area, enforced on the server for every
  page, download, report and API call. Surveyors see finance information only for their own patch.
- Hand over work stops a leaver signing in and moves their work in one step.

**Data and the application**

- Built on Django, which protects against SQL injection, cross-site scripting, cross-site request forgery and
  clickjacking by default. Uploaded and generated files are served only to signed-in people with access.
- A change log records who changed what, and when, across properties, leases, cases, finance, access areas, cover
  for absence and two-step sign-in.
- The code is open, so any council, supplier or security tester can review it.
- Data stays where the council chooses: its own servers, or UK or EU hosting. PHAEMA sends nothing to the project or
  to third parties. Optional map tiles from Ordnance Survey or OpenStreetMap are loaded by the user's browser.

**Servers set up by the installer** (`deploy/install-server.sh`)

- HTTPS with automatically renewed certificates, HTTP Strict Transport Security and secure, HTTPS-only cookies.
- A firewall allowing only SSH, HTTP and HTTPS; fail2ban; automatic operating system security updates.
- The database and application are not reachable from the internet, only through the web server.
- Nightly backups of the database and uploaded files.
- Secrets (the Django secret key, database and email passwords) are kept in the server's environment file, not in
  the code or the database.

## Not yet done

These are known gaps, listed so councils can judge the risk. They are on the [roadmap](docs/roadmap.md).

- **Independent penetration test** by a CREST or CHECK accredited tester, before the first live use. Results and
  fixes will be summarised here.
- **Single sign-on** with the council's own accounts (OpenID Connect: Microsoft Entra ID, Keycloak, Google), so
  councils can apply their own conditional access and password rules. This is the first planned connector.
- **Limits on repeated failed passwords** across sessions. Fail2ban on the installer's servers and two-step sign-in
  reduce the risk today.
- **API tokens** with limited scope, for systems that read PHAEMA's API.
- **Automated dependency and code scanning** on every pull request.
- **Independent accessibility audit** against WCAG 2.2 AA.
- **Template documents for councils**: a data protection impact assessment (DPIA), a record of processing, and
  answers to common security questionnaires.

## For councils assessing PHAEMA

The [technical manual](https://claude.ai/artifact/8sTYq44xi5Ps3NuVFDrEm2) describes the architecture, data model,
hosting and security in more detail. To arrange a security review or pilot, email stuart@phaema.co.uk.
