# Licensing

PHAEMA uses different open licences for different parts of the project.

| Part | Licence | Why |
|---|---|---|
| The PHAEMA application (everything in this repository unless stated otherwise) | [AGPL-3.0-or-later](LICENSE) | Anyone may use, study, change and share PHAEMA. Anyone who runs a changed version as an online service must publish their changes, so improvements return to all councils. |
| Connectors, client libraries and SDKs (published in separate folders or repositories, each with its own `LICENSE`) | Apache-2.0 | Finance, GIS, legal and maintenance system suppliers can build integrations freely. |
| Data model and schema documentation | CC BY 4.0 | Free reuse of the data standard with attribution. |
| Data published by councils through PHAEMA | Open Government Licence v3.0 (set by each council) | The standard licence for UK public sector open data. |

## Third-party components

- **GOV.UK Frontend** (`static/vendor/govuk-frontend/`): MIT licence, © Crown copyright. Modified to remove the GDS Transport typeface, which is licensed only for GOV.UK services. PHAEMA does not use GOV.UK branding.
- Python packages listed in `requirements.txt` are used under their own open-source licences.

## Licensed data and standards

PHAEMA never bundles licensed content. Councils connect their own licences for:

- SFG20 maintenance schedules
- Ordnance Survey premium data under the Public Sector Geospatial Agreement
- HM Land Registry National Polygon Service and Business Gateway

## Trademark

"PHAEMA" is the project name. Hosting and support partners may describe themselves as offering PHAEMA services; use of the name to imply official certification will be governed by a trademark policy to be published.
