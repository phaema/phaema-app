# Security answers

Short answers to the questions council security questionnaires usually ask, for a council hosting PHAEMA itself.
Where the answer depends on the hosting, it says so. The detail is in [SECURITY.md](../../SECURITY.md) and the
technical manual.

| Question | Answer |
| --- | --- |
| Where is the data held? | Where the council installs PHAEMA: its own servers or a UK or EU hosting region it chooses |
| Is data encrypted in transit? | Yes: HTTPS only, with HSTS. The installer obtains and renews certificates automatically |
| Is data encrypted at rest? | Depends on the hosting: use an encrypted disk or volume (all major UK clouds offer this by default) |
| How do users sign in? | PHAEMA accounts with passwords of at least 12 characters and two-step sign-in, or single sign-on with the council's accounts (OpenID Connect) |
| Is multi-factor authentication supported? | Yes: authenticator app codes with recovery codes, required for administrators by default and for everyone if the council chooses; or the council's own MFA through single sign-on |
| How is access controlled? | Roles and access areas, checked on the server for every page, download, report and API call; outside users have an access end date |
| How do other systems use the API? | With API tokens made by an administrator: each is limited to read only or read and change, to parts of the API and to the role of the account it acts for, ends within two years, can be cancelled on its own, and is stored only as a hash. Password sign-in to the API is off by default |
| How are leavers handled? | Hand over work blocks sign-in and reassigns their work in one step; with single sign-on, disabling the council account stops access |
| Is there an audit trail? | Yes: who changed what and when, for every audited record; the database refuses to change or delete entries |
| Is the application tested for vulnerabilities? | Automated on every change: CodeQL, Ruff security rules, a dependency vulnerability check and the test suite. An independent CREST penetration test is planned before 1.0; councils may commission their own |
| How are security updates delivered? | As patch releases with notes ([docs/releasing.md](../releasing.md)); the installer applies operating system security updates automatically |
| How are vulnerabilities reported? | To stuart@phaema.co.uk, as set out in SECURITY.md |
| Is the code open to review? | Yes: all of it, under AGPL-3.0, at github.com/phaema/phaema-app |
| Which third parties receive data? | None. Map tiles are fetched by the user's browser from OpenStreetMap or Ordnance Survey without personal data; email goes through the council's own mail server |
| Are cookies used? | Only those needed to run the service: the session cookie (Secure, HttpOnly), the CSRF cookie (Secure) and preference cookies for theme, text size and dashboard view. No analytics or advertising cookies |
| What browser protections are set? | Content-Security-Policy (only PHAEMA's own scripts), Permissions-Policy, X-Frame-Options DENY, nosniff, same-origin referrer |
| Can administrators run code through letter templates? | No. Templates may use merge fields, if, for and formatting filters only; merge data is plain text, so a template cannot print other data, load code or read files |
| How are uploads checked? | Size limits and a check of each file's content type by its first bytes (PDF, images, drawings); files are served only to signed-in users with access |
| Backups and recovery? | Nightly database and file backups kept 14 days by the installer; restore with one command. Recovery time and point objectives are set by the council's hosting |
| Is PHAEMA certified (Cyber Essentials, ISO 27001)? | Certification applies to organisations and their systems, so it belongs to whoever hosts PHAEMA, normally the council within its own Cyber Essentials Plus and PSN scope |
| Is it accessible? | Built on the GOV.UK Design System and aimed at WCAG 2.2 AA; an accessibility statement template is in this pack |
| What happens if the project stops? | The council keeps the code, the database and the files, and can run, change or hand them to another supplier under the AGPL licence |
