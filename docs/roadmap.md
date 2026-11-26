# PHAEMA roadmap

PHAEMA is in alpha (0.9.x). The first eight weeks built the core (below); the features agreed for the beta follow it. Beta (`v1.0.0-beta.1`) starts when they are built and a trial council is ready; 1.0 is the first version a council runs live, after an independent security test.

## The first eight weeks

| Week | Deliverables | Status |
|---|---|---|
| 1 | Repository, licences, automated tests; Mac setup; data model; property register | Done |
| 2 | Map with HM Land Registry INSPIRE polygon import; spreadsheet import; leases and licences | Done |
| 3 | Lease event engine, reminders and dashboard; rent schedules | Done |
| 3½ | Usability release: user manual and in-app help; colour themes including dark and high contrast; Excel/CSV export of every list; report builder; import of parties, leases and breaks | Done |
| 4 | Rent ledger: demand runs, VAT, receipts and allocation, arrears, statements, finance export. Mid-point review | Done (review with Stuart) |
| 5 | Service charge ledger: budgets, apportionment, on-account demands, year-end reconciliation | Done |
| 6a | Case management engine (phase 1): case types, stages, tasks, targets, automatic lease event cases, emails, documents, fees, Contributor role | Done |
| 6 | Maintenance: components, planned schedules, reactive jobs and works orders, contractors, recharges from lease repairing terms | Done |
| 7 | Compliance certificates; documents; Transparency Code open data export; Golden Thread tiers; example records; import of contractors and components | Done |
| 8 | Testing, fixes, IONOS deployment scripts, installation guide, manual pages for the new modules, demo script | |
| 7a | Asset valuation: CIPFA classes and bases set by finance, valuation records with Red Book fields, the rolling programme run as cases, impairment prompts, year-end schedule for finance | Done |
| 7b | Document template library: letters and notices pre-filled from cases, exported to Word | Done |

## Since the first eight weeks

| Release | Deliverables | Status |
|---|---|---|
| November 2026 | Projects; estates strategy (Asset Challenge, suitability, objectives and action plans, board report); space and costing; site visit sheets; IPMS floor areas; outside users and access areas; single sign-on; scanned documents read by OCR; rents payable | Done |
| 25 November 2026 | Security: limits on wrong passwords (web, admin and API), shorter sessions, refusing to start without a secret key, tighter single sign-on linking; credit notes and service charge credits fixed; dependency and code scanning in CI | Done |
| 25 November 2026 | Index-linked rent reviews; dealings register; credit control, payment plans and interest on late rent; rent deposit account; void marketing and agent instructions; ITZA and rent per m² Zone A | Done |
| 26 November 2026 | IFRS 16 data pack for finance on the leases the council holds | Done |
| Before beta | Microsoft 365 email and calendar; property events pipeline; annual health check; site visit sheet level B; repository mirror | Planned |

## Future work

### Assurance before live use

What councils' procurement and IT security teams will ask for before the first live use. See [SECURITY.md](../SECURITY.md).

- **Done:** two-step sign-in (authenticator app, recovery codes, required for administrators by default); security policy and reporting route; limits on repeated wrong passwords; dependency and code scanning on every pull request.
- **Next:** independent penetration test (CREST or CHECK); scoped API tokens; database-level protection of the audit trail; numbered releases with release notes.
- **Done:** a [procurement and information governance pack](procurement/README.md): service definition, security answers, and templates for the accessibility statement, DPIA, record of processing and retention schedule.
- **With pilot councils:** independent WCAG 2.2 AA accessibility audit; a retention tool that lists and removes records past their date; published case studies.

### Connectors: an optional module

Integrations with other systems are one optional module in the main repository, not a fork. PHAEMA connects through open standards rather than particular products, so the same module serves councils on Microsoft 365, Nextcloud, openDesk, Google Workspace or their own systems. Full review: "PHAEMA integrations: market review and plan" (November 2026).

- **Off by default.** Nothing connects to an outside service until an administrator enters its details and switches it on in Module settings.
- **Each connector switches on separately**, and providers are configurations: sign-in is written once for OpenID Connect, with Microsoft Entra, Keycloak or Google as settings; chat works with Teams, Matrix or Nextcloud Talk; documents with SharePoint or Nextcloud.
- **Nothing depends on it.** Email, PHAEMA passwords and documents stored in PHAEMA stay the defaults and keep working when a connector is off or the outside service is down.
- **Security.** Keys and secrets are set by the installer, never stored in the database; each connector asks only for the permissions it needs; actions through a connector go in the change log. PHAEMA stays on UK hosting.
- **Self-contained code** in its own app (`apps/connectors`), tested with each connector on and off.

### Planned connectors, in priority order

1. **Single sign-on (OpenID Connect): built**, see [the set-up guide](single-sign-on.md); still to be proved against a council's live tenant. Staff sign in with their council account (Microsoft Entra ID, Keycloak, openDesk, Google). Groups map to roles and access areas; two-factor and password rules come from the provider; people disabled there can no longer sign in, and any open PHAEMA session ends within the session limit (10 hours, or 2 hours without use); one local administrator is kept as a backup sign-in.
2. **Ordnance Survey and EPC lookups.** OS Places address search and UPRN when adding a property (free to councils under the Public Sector Geospatial Agreement), OS NGD building footprints, vector map tiles; energy ratings and certificate expiry from the EPC register by UPRN.
3. **Map layers for GIS.** OGC API Features and WFS layers of properties, leases, projects and proposed sites, following access areas and confidentiality, for QGIS, ArcGIS, Cadcorp, MapInfo, GeoServer and Lizmap; read-only PostGIS views for internal GIS teams.
4. **GOV.UK Notify.** Rent demands, arrears reminders and key-date letters to tenants by text, email or post, with "pay now" links to the council's own payment platform.
5. **Chat notifications and approvals.** Reminders, approvals waiting and missed milestones sent to Teams, Matrix (Element, Tchap) or Nextcloud Talk; approve cases and works orders from Teams.
6. **Documents.** Case and project documents kept in the council's SharePoint or Nextcloud, with PHAEMA holding the link; letters edited in the browser with Word online or Collabora; OpenDocument (.odt) output alongside Word.
7. **As councils ask:** filing email to a case or project from any mailbox (IMAP); calendar entries added directly (CalDAV or Outlook), beyond the existing calendar feed; planning constraints on maps; Companies House checks on tenant companies; FixMyStreet Pro reports into maintenance; links to Open Digital Planning (BOPS) applications.

### Other later releases

Estate casework, live finance/legal/CRM connectors, tenant and contractor portals, condition surveys and lifecycle planning, full Golden Thread information management (ISO 19650, COBie, IFC), Welsh translation.
