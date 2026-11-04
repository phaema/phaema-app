# PHAEMA

**Property Holding and Estate Management Application** – open-source estate management software for local authorities in England and Wales.

PHAEMA helps a council's estates team manage its land and property: the property register (terrier), titles, leases and lease events, rent and service charge accounts, maintenance and compliance, and the Golden Thread of building information. It is built on open standards and publishes open data.

> **Status: alpha.** PHAEMA is in early development and is not yet ready for live use.

## What works so far

- Property register: estates, sites, buildings, lettable units and land parcels in a hierarchy, with UPRN, address, classification, areas, grid reference and boundary
- Managing surveyor for each property, with a "My properties" and per-surveyor filter
- Search, filters and sortable columns
- Property pages with a photo gallery, and a breakdown of how the floor area (GIA and NIA) is made up from the parts
- Title records with stored PDF documents (official copies, plans, deeds, leases)
- Dashboard: lettable units, vacant floor space (NIA and GIA), vacancy rate, and links into filtered lists
- A full, tamper-proof audit trail, with a change log showing who changed what and when, field by field
- Maps on every property and a register map, with OpenStreetMap or Ordnance Survey background mapping (OS Maps API key under the PSGA)
- HM Land Registry INSPIRE polygons: import for your area, show on maps, and set property boundaries from them
- Spreadsheet import of properties, parties, and leases with their break options (Excel templates with drop-downs and guidance; a preview with row-by-row checks; nothing is saved unless every row is clean)
- Excel and CSV download of every list, honouring the current filters and sort order
- A report builder: choose records, columns, filters (including rolling dates such as "in the next 90 days"), sort and totals; save, share, copy, and run on screen or download. Six ready-made reports (rent roll, expiries, vacant properties, overdue events, terrier, tenant contacts)
- A user manual built into the application, with search, cross-links, and a "Help with this page" link and short hints on the main screens. The manual is written in Markdown in [`apps/help/pages`](apps/help/pages) so it also reads on GitHub
- Leases, licences, wayleaves and other agreements, both let out and held by the council: parties, term, 1954 Act status, rent, reviews, breaks with notice deadlines, repairing and insurance terms
- Key dates with red/amber/green warnings, and a lease register with filters (including expiring soon and overdue events) and sorting
- Signed leases, notices and other agreement documents stored as PDFs against each lease
- Tenants and other parties: a searchable list, and for each party every agreement (as tenant, landlord or guarantor) and every property involved
- Lease events: rent reviews, break dates, break notice deadlines and expiries generated from each lease, plus events added by hand; assigned to the managing surveyor; outcomes recorded on screen (a settled review updates the rent schedule and sets up the next review)
- Email reminders at lead times set by the council (e.g. 180, 90 and 30 days), weekly overdue reminders, and a private calendar feed for Outlook
- Rent schedules: rent history, review outcomes, fixed steps, concessions and indexation, with future rents taking effect automatically; next payments preview
- Dashboard: overdue and upcoming lease events by type, rent roll by holding purpose, WAULT to expiry and to first break
- Rent ledger (optional module): demand runs with day-based apportionment of part periods and VAT on opted leases; PHAEMA-numbered invoices or charges sent for the finance system to invoice; credit notes; receipts imported from finance and set against the oldest debt; rent accounts and printable statements; aged arrears; collection rate on the dashboard; a documented finance export in CSV or Excel
- Service charges (optional module): schedules over an estate or building, shares by floor area, fixed percentage or equal units, with the council bearing empty units and any caps; budgets by cost heading; on-account demands in the rent demand runs, split at the year end; spending entered or imported from finance; budget against actual; year-end reconciliation by days in force, raising balancing charges and credits; printable tenant statements; RICS 2nd edition timetable (budgets one month before the year, statements within four months) with dashboard and weekly email reminders; income and credits, and costs not recoverable from tenants; a yearly apportionment matrix; tenant budget statements
- Measurement basis (RICS Code of Measuring Practice or IPMS), source and date recorded for floor areas, plus gross external area
- Case management: about 30 case types (consents, lease events, lease management, income recovery, asset valuation, enquiries, other activities) with five stages, task lists, targets (28 days for consents, 10 working days to acknowledge), Landlord and Tenant Act 1988 prompts, cases opened automatically ahead of rent reviews, breaks and expiries and closed when the outcome is recorded, notes (with confidential notes), saved emails (.eml and Outlook .msg) filed with their attachments, documents, fixed fees charged to the rent account, case references such as CAS-2026-0042/DM-E01-U04, a Contributor role for colleagues such as the legal team, and supervisor approval: each surveyor has a supervisor who approves their recommendation before a decision (by email and on the dashboard), with returns, comments and the full history kept on the case; heads of terms covering the 16 items in the RICS Code for leasing business premises for new lettings and renewals, and section 25 and 26 notice deadlines
- Maintenance (optional module): reactive repairs with priorities and working-day targets; works orders emailed to contractors and printable, with supervisor approval above a set value; who pays worked out from the lease repairing terms (tenant, council, service charge or recharge), with recharges to the rent account and costs added to the service charge; planned and statutory maintenance from an open task library (gas, EICR, fire alarms, emergency lighting, legionella, asbestos, lifts and more), with jobs raised automatically before each is due; a component register (Uniclass 2015, NRM3, condition A to D, life and replacement cost) with a lifecycle replacement forecast; contractors with insurance and accreditation checks; a contracts register with RICS three-yearly re-tender dates; seven ready-made reports
- Compliance: certificates each building needs (fire risk assessment, fire alarm, emergency lighting, gas, EICR, legionella, asbestos, lifts, EPC, DEC and more) with expiry worked out, red/amber/green status and remedial actions that can become repair jobs; who holds each certificate from the lease terms; higher-risk building screening with Golden Thread tiers A, B and C confirmed by an officer; building information kept by category with every version
- Open data: the Transparency Code land and assets list and available property, published as CSV, JSON and GeoJSON under the Open Government Licence, leaving out sensitive sites
- Asset valuation (optional module): asset classes, bases and cycles set by finance (CIPFA Code defaults); dated classification history; the yearly programme worked out and started as cases, with a valuer's data pack; valuations recorded with the Red Book fields (terms of engagement, inspection, assumptions, material uncertainty, valuer status and conflicts), land and buildings split and components; acceptance for the accounts; impairment prompts; valuer rotation; import of the valuer's figures; year-end schedule for finance
- Four roles: Administrators (change anything), Surveyors (change the properties they manage) and Viewers (read only), applied on every screen, in data entry and in the API. See [users and roles](docs/roles.md)
- Adjustable text size (smaller, standard, large, largest) and colour themes: standard, dark, high contrast, or match the device; plus a council brand colour for the header
- Photos and documents are only available to signed-in users; photos are stripped of location data on upload
- Optional modules that each council switches on or off (rent ledger, service charges, maintenance, compliance, Golden Thread)
- An open REST API with OpenAPI documentation at `/api/docs/`

See the [roadmap](docs/roadmap.md) for what is coming next.

## Try it on your computer

You need Docker (or Colima) and Git. Mac users: follow the [Mac setup guide](docs/setup-mac.md).

```
git clone https://github.com/phaema/phaema-app.git
cd phaema-app
./phaema.sh start
./phaema.sh admin        # create your sign-in
```

Then open http://localhost:8000.

## Technology

Python and Django (GeoDjango), PostgreSQL with PostGIS, the GOV.UK Design System (without GOV.UK branding), packaged as containers that run the same on a laptop, a council's own servers or a UK/EU hosted service.

## Licence

- Application: [GNU Affero General Public License v3.0 or later](LICENSE)
- Connectors and client libraries (when published): Apache-2.0
- Data model documentation: CC BY 4.0

See [LICENSING.md](LICENSING.md). Contributions are welcome under the [Developer Certificate of Origin](CONTRIBUTING.md).
