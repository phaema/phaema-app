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
- The admin site signs in through the same page, so two-step sign-in cannot be bypassed there.
- Other systems use the API with API tokens made by administrators. Each token acts for one account and never has
  more than that account's role; it can be limited to read only and to parts of the API, ends on a set date (at
  most two years), and can be cancelled on its own. Only a SHA-256 hash of the key is stored, the key is shown
  once, and changes made with a token are named in the change log. Signing in to the API with a username and
  password is off unless the council switches it on (`PHAEMA_API_PASSWORD_SIGN_IN`), and never works for anyone
  with two-step sign-in.
- People sign in with their username or their email address. An email address only works when exactly one
  account has it, and the sign-in page gives the same answer whether the name or the password was wrong.
- Passwords are at least 12 characters, checked against common passwords and the person's own details, and stored
  using Django's salted PBKDF2 hashing. Recovery codes are stored only as hashes.
- A forgotten password is reset by a link emailed to the address on the account. The link works once and for one
  hour (`PHAEMA_PASSWORD_RESET_MINUTES`), the page gives the same answer whether or not an account was found, and
  requests are limited per connection and per account. Resetting a password does not sign the person in or bypass
  two-step sign-in, and it signs out their other sessions.
- Optional single sign-on with the council's own accounts (OpenID Connect: Microsoft Entra ID, Keycloak and
  others), off by default ([set-up guide](docs/single-sign-on.md)). PHAEMA uses the authorisation code flow with
  PKCE and checks the signature, issuer, audience, expiry and nonce of every ID token. It asks only for name, email
  address and groups, and stores no tokens. The client secret is kept in the server's environment file. Councils
  can stop PHAEMA passwords for people with a council account; administrators keep a password and two-step
  sign-in as a fallback, and the installation superuser is never linked to a council account.
- Access is by role (administrator, surveyor, contributor, viewer) and access area, enforced on the server for every
  page, download, report and API call. Surveyors see finance information only for their own patch.
- Hand over work stops a leaver signing in and moves their work in one step.

**Data and the application**

- Built on Django, which protects against SQL injection, cross-site scripting, cross-site request forgery and
  clickjacking by default. Uploaded and generated files are served only to signed-in people with access, and are
  checked by their content, not only their name.
- A Content-Security-Policy on every page lets the browser run only PHAEMA's own scripts (each inline script carries
  a nonce made for that request), refuses plug-ins and framing, and keeps forms posting to PHAEMA. A
  Permissions-Policy turns off the camera, microphone, location and payment features. Councils can run the policy
  in report-only mode first (`PHAEMA_CSP_REPORT_ONLY`) and add map tile addresses.
- Letter templates, which administrators can edit, run in a reduced template language: merge fields, `if`, `for`,
  `comment` and formatting filters only. Merge data is plain text, so a template cannot reach other fields of a
  record, print debugging data, load code or read files.
- Sign-in attempts are limited after repeated wrong passwords, per account and per connection, on the sign-in page,
  the admin site and the API.
- A change log records who changed what, and when, across properties, leases, cases, finance, access areas, cover
  for absence and two-step sign-in, including changes made in bulk. A database trigger refuses to change or delete
  change log entries, so they cannot be altered through PHAEMA or its ordinary database connection. This protects
  the log against alteration through the application; it is not absolute: someone with administrator rights over the
  database server can still change the data and its controls, so councils should restrict that access, keep
  backups and keep the database server's own logs. A database administrator carrying out a lawful retention purge
  switches the trigger off for one transaction (see the technical manual).
- Uploaded files open only for people who can open the record they belong to: files held by valuations, compliance
  or maintenance need that module. Knowing a file's address is not enough, and files that belong to no record are
  never served.
- Records saved through the API go through the same checks as on screen, such as "a property cannot be part of
  itself".
- Every pull request runs the tests, a coverage minimum, Ruff (including its security rules), CodeQL code scanning
  and a check of the Python packages against known vulnerabilities. The actions are pinned to commit hashes and
  Dependabot proposes updates.
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
- **Single sign-on tested against a live council tenant.** The code is tested against a stand-in sign-in service;
  it has not yet been proved against a council's Microsoft Entra conditional access rules.
- **Independent accessibility audit** against WCAG 2.2 AA.

## For councils assessing PHAEMA

The [procurement and information governance pack](docs/procurement/README.md) has a one-page service definition,
security questionnaire answers, and templates for the accessibility statement, DPIA, record of processing and
retention schedule.

The [technical manual](https://phaema.co.uk/docs/technical-manual.html) describes the architecture, data model,
hosting and security in more detail. To arrange a security review or pilot, email stuart@phaema.co.uk.
