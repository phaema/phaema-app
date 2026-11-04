title: Properties
section: Records
order: 1
summary: The property register, the property hierarchy, floor areas, photos and titles.
---
# Properties

The property register holds every property the council owns, leases or manages, except housing stock.

## How properties fit together

Properties form a hierarchy. Each property can be **part of** another:

- **Estate**: a group of sites managed together, such as an industrial estate.
- **Site**: one piece of land, which can hold buildings.
- **Building**: a building on a site.
- **Lettable unit**: a part of a building that can be let, such as a shop or office suite.
- **Land parcel**: land without buildings, such as a field or car park.

A property's page lists its parts. Lettable parts are shown in bold.

## Key facts

| Field | Meaning |
|---|---|
| Reference | The council's unique asset reference. |
| UPRN / USRN | The national Unique Property and Unique Street Reference Numbers. They link PHAEMA to GIS, council tax, business rates and other systems. |
| Holding purpose | Why the council holds it: operational, investment, community, surplus, or held for disposal. |
| Tenure | Freehold, leasehold, other, or none (managed but not owned). |
| Occupation | Occupied by the council, let, partly let, vacant, or not applicable. |
| Managing surveyor | The surveyor responsible. Surveyors can change the properties they manage (see [roles](users-and-roles.md)). Events on the property's leases are assigned to them. |
| Exclude from open data | Tick for sensitive properties so they are left out of any published asset list. |
| Site hazards | What anyone visiting should know first, such as fragile roofs, confined spaces, lone working or dogs. Shown on cases, jobs and valuations for the property and everything within it. |

## Floor areas

PHAEMA records **gross internal area (GIA)** and **net internal area (NIA)** in square metres, and site area in
hectares. The property page shows how the floor area is made up:

- total GIA and NIA of the buildings within;
- total NIA of the lettable parts;
- **non-lettable area**: GIA less lettable NIA, which covers common parts, circulation, plant and walls;
- **net to gross**: lettable NIA as a percentage of GIA.

### How areas were measured

RICS asks for the measurement basis to be recorded. For each property, record in **Edit this property**:

- **measured to**: the RICS Code of Measuring Practice (6th edition) or IPMS: All Buildings;
- the **source**: a measured survey, drawings, a lease or title plan, or an estimate;
- the **date** the areas were measured.

Estimated areas are marked as estimates wherever they are shown. You can also record the **gross external area
(GEA)**, used for planning, insurance and some valuations. The ready-made report **Floor areas with no measurement basis** lists
properties still to be checked.

## Photos

Add photos in **Edit this property or add photos**. They are resized and their location data removed when
uploaded. Select a photo on the property page to see it full size.

## Titles

Land Registry titles are linked to properties. A title can hold a PDF of the register and plan. Administrators
manage titles. See also [Land Registry boundaries](maps.md#land-registry-inspire-boundaries).

## Leases on a property

The property page lists the leases and licences that include it. See [leases and licences](leases.md).
