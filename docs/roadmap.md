# PHAEMA MVP roadmap (eight weeks)

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

## Future work

### Single sign-on

Let staff sign in with their council Microsoft account (Microsoft Entra ID) instead of a separate PHAEMA password.

- OpenID Connect sign-in with Entra ID. The council's IT team registers PHAEMA as an app in their Entra tenant; PHAEMA stores only the tenant ID, client ID and secret, set by the installer, never in the database.
- Two-factor sign-in, password rules and lock-outs come from the council's Entra policies (Conditional Access), so PHAEMA does not need its own.
- Entra security groups map to PHAEMA roles (Administrators, Surveyors, Contributors, Viewers) and access areas, set under Manage data. People are created on first sign-in and their groups refreshed at each sign-in.
- Leavers: someone disabled in Entra can no longer sign in. Hand over work is still needed to move their work.
- One local administrator account is kept as a break-glass sign-in if Entra is unavailable. Councils without Microsoft 365 keep PHAEMA passwords.
- Other OpenID Connect providers (for example Google Workspace) can follow the same route.

### Microsoft Teams and Microsoft 365 integration

Connect PHAEMA to the tools council staff already work in, through Microsoft Graph, using the same Entra app registration as single sign-on.

- **Teams notifications**: reminders, approvals waiting, overdue tasks and missed project milestones sent to the person in Teams (and to a team channel for a project or a case type), each linking back to the record. Email stays as the fallback.
- **Approvals from Teams**: approve or return a case or works order from an actionable message; the decision is recorded in PHAEMA and its change log as if made there.
- **Outlook calendar**: key dates (rent reviews, breaks, expiries, gateway dates, inspections) added to a person's or a shared calendar and kept up to date as they change.
- **Filing email**: file an Outlook message to a case or project from Outlook itself, instead of saving and uploading it.
- **SharePoint and OneDrive**: option to keep case and project documents in a SharePoint library the council controls, with PHAEMA holding the link, and to open generated letters straight into Word online.
- **PHAEMA in Teams**: a Teams tab showing a project, case or property page, so a project team can work from its channel.
- Implications: the council's IT team grants Graph permissions with administrator consent; PHAEMA asks only for the permissions each switched-on feature needs; each feature is switched on in Module settings; data stays in the council's own Microsoft 365 tenant and the UK hosting of PHAEMA itself is unchanged.

### Other later releases

Estate casework, live finance/legal/CRM connectors, tenant and contractor portals, condition surveys and lifecycle planning, full Golden Thread information management (ISO 19650, COBie, IFC), Welsh translation.
