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
- Adjustable text size (standard, large, largest)
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
