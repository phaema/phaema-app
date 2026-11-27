# PHAEMA service definition

The facts procurement teams ask for, in the order G-Cloud service listings use. PHAEMA is software, not a hosted
service: a council runs it on its own servers or asks a supplier to host and support it. Where the answer depends on
that choice, it says so.

| Question | Answer |
| --- | --- |
| What it is | Property holding and estate management for councils in England and Wales: property register and maps, leases and licences, rent and service charges, cases and approvals, valuations, maintenance and compliance, projects, space and costs, estates strategy, reports and an open API; an optional tenant portal for the council's tenants, and pages for departments occupying council buildings |
| Who it is for | Council estates, property, finance and facilities teams; their tenants (through the tenant portal, if switched on) and departmental property liaisons |
| Licence | GNU Affero General Public License v3.0 or later (AGPL-3.0). No licence fee. The council may use, study, change and share it; changes it offers to others over a network must be shared under the same licence |
| Current version | 0.9.x alpha. Beta (1.0.0-beta) follows a pilot council; 1.0 follows an independent penetration test. See [CHANGELOG.md](../../CHANGELOG.md) |
| Deployment | The council's own servers (Linux with Docker), its cloud tenancy (any UK or EU region), or a supplier's hosting. A one-step installer sets up HTTPS, a firewall, automatic security updates and nightly backups |
| Technology | Python and Django 5.2 (long-term support), PostgreSQL with PostGIS, GOV.UK Design System, server-rendered pages that work without JavaScript for most tasks |
| Data location | Wherever the council installs it. PHAEMA sends nothing to the project or to third parties, except emails to tenants through GOV.UK Notify if the council switches on emailing demands or the tenant portal. Map tiles (OpenStreetMap, or Ordnance Survey with the council's key) are loaded by the user's browser |
| Sign-in | PHAEMA accounts with two-step sign-in (required for administrators by default), or single sign-on with the council's accounts (OpenID Connect: Microsoft Entra ID, Keycloak and others) |
| Access control | Roles (administrator, surveyor, contributor, viewer) and access areas (ledger, service charges, valuations, compliance, maintenance), enforced on every page, download, report and API call; outside users have an access end date |
| Audit | A change log of who changed what and when, which the database refuses to alter or delete through the application; database server administrators remain able to alter data, so access to the database server should be restricted and logged |
| Security testing | Automated on every change: tests with a coverage minimum, CodeQL, Ruff security rules and a dependency vulnerability check. Independent CREST penetration test planned before 1.0. Certifications such as Cyber Essentials Plus and ISO 27001 belong to whoever hosts it, usually the council |
| Accessibility | Built with the GOV.UK Design System and aimed at WCAG 2.2 AA; not yet independently audited. See the [accessibility statement](accessibility-statement.md) |
| Browsers | Current Edge, Chrome, Firefox and Safari, on desktop, tablet and phone |
| Integrations | Open REST API with an OpenAPI description, reached with scoped API tokens; spreadsheet import; finance export (CSV or Excel) and receipts import; calendar feed; Government Property Data Standard export; open data publishing |
| Data export | Every list and report downloads as Excel or CSV; the whole estate exports in the Government Property Data Standard layout; the database is standard PostgreSQL, so a full copy can be taken at any time |
| Exit | Nothing to hand back: the council already holds the database and files. Exports above, or a database dump, move the data to another system |
| Availability | Set by the hosting. The installer's single-server set-up suits most councils; a supplier can run it with a service level agreement |
| Backups | The installer takes a nightly database and files backup, keeping 14 days; councils copy them off the server or use their own backup service |
| Support | Documentation, e-learning and a test site are free. Help for early adopters from the maintainer; paid support, hosting and change from support partners (being arranged). Security reports to stuart@phaema.co.uk |
| Training | Built-in help on every page, a user manual with worked examples, e-learning for five roles, a self-running tour and a test programme |
| Welsh | A full Welsh (Cymraeg) interface, chosen by each person once the council offers it. The Welsh is a draft awaiting review by a qualified translator; records, council-kept lists, the manual and letters stay as entered |
| Price | Software free. Costs are hosting (a single Linux server; 2 cores and 4 GB of memory runs a test site, and a live site with OCR wants more), any support or change from a supplier, and the council's own staff time to set up and migrate data |
| Contact | stuart@phaema.co.uk · [phaema.co.uk](https://phaema.co.uk) · [github.com/phaema/phaema-app](https://github.com/phaema/phaema-app) |
