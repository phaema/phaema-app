title: Properties
section: Records
order: 1
summary: The property register, the property hierarchy, floor areas, photos and titles.
---
# Properties

The property register holds every property the council owns, leases or manages, except housing stock.

## How properties fit together

Properties form a hierarchy. Each property can be **part of** another:

![The record for Northfield Business Park](/static/help/property.jpg)
*An estate's record, with its location and photo.*


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
| Estate strategy section | The section of the council's estate strategy or asset management plan that covers the property. Blank until the council fills it in. |
| Holding purpose review date | When the reason for holding the property is next due for review. The register can be filtered to reviews that are overdue or due in the next 12 months. |
| Portfolio | The service or portfolio the property belongs to, such as Investment, Leisure, Children's services or Adult social care. See [portfolios](#portfolios). |
| Tenure | Freehold, leasehold, other, or none (managed but not owned). |
| Acquired on | When the council acquired its interest. If only the year is known, enter 1 January of that year. |
| Occupation | Occupied by the council, let, partly let, vacant, or not applicable. For a vacant property, see [vacancy](#vacancy). |
| Use | The main use, chosen from the council's [list of uses](#uses), with a description in your own words and the planning use class. |
| Designations | Whether it is a listed building (and its grade), a scheduled monument, a site of special scientific interest or in a conservation area. See [designations](#designations). |
| Managing surveyor | The surveyor responsible. Surveyors can change the properties they manage (see [roles](users-and-roles.md)). Events on the property's leases are assigned to them. |
| Exclude from open data | Tick for sensitive properties so they are left out of any published asset list. |
| Disposed of, disposal price | When the council sold or transferred it, and for how much. A disposed property is kept for its history but left out of open data. Usually recorded from a disposal project's [completion checklist](projects.md#completion-checklist). |
| Planned disposal | The reason, method, expected date and expected value, once a disposal is planned. See [planning a disposal](#planning-a-disposal). |
| Running costs and rates | What the property cost to run, and the business rates on it, for each financial year. See [running costs and rates](#running-costs-and-rates). |
| Site hazards | What anyone visiting should know first, such as fragile roofs, confined spaces, lone working or dogs. Shown on cases, jobs and valuations for the property and everything within it. |

![The property register filtered to Northfield](/static/help/property-list.jpg)
*The register, searched for Northfield.*


## Portfolios

A portfolio groups properties by the service or purpose they belong to, alongside the holding purpose. Each
council keeps its own list: an administrator opens **Manage data**, **Portfolios** to add, rename or reorder them.
PHAEMA starts with a list typical of a large council (Investment, Corporate estate, Leisure, Libraries,
Children's services, Education, Adult social care, Highways and transport, Bereavement services and others).

- Choose a property's portfolio in **Edit this property**, under Classification, or in the
  **Portfolio** column of a [spreadsheet import](import-export.md).
- Filter the register by portfolio, sort it by the **Portfolio** column, or select a portfolio on a property's
  page to see everything in it.
- In the [report builder](reports.md), Portfolio is a column and a filter in the Properties dataset, so you can
  total floor areas, rents or values by portfolio.
- A portfolio with properties in it cannot be deleted. Untick **In use** to stop offering it for new
  properties; properties already in it keep it.

## Uses

Each property has a **use** chosen from a list, so that properties can be counted and compared by use. Each
council keeps its own list: an administrator opens **Manage data**, **Property uses** to add, rename or reorder
entries. PHAEMA starts with a list of about forty, from Office and Shop to Allotments and Telecoms mast.

- Choose the use in **Edit this property**, under Classification. Put anything more exact in **Use
  description**, in your own words: for example the use "Car park" with the description "Surface car park (180
  spaces)".
- Each entry in the list can be matched to a term in the Government Property Data Standard. That term is what the
  [standard's export](#government-property-data-standard) shows.
- A use with properties in it cannot be deleted. Untick **In use** to stop offering it for new properties.
- In the [report builder](reports.md), Use is a column and a filter in the Properties dataset.

## Designations

In **Edit this property**, under Designations, record whether the property is:

- a **listed building**: Grade I, Grade II*, Grade II, locally listed, or not listed
- a **scheduled monument**
- a **site of special scientific interest (SSSI)**
- **in a conservation area**

Leave a designation blank where nobody has checked. Choose **Not listed** or **No** where it has been checked and
does not apply. The difference matters: a blank is a gap in the records, and reports can find those. Use
**Designation notes** for the list entry number or which part of the property is covered.

Designations are shown on the property's page and in the property report.

## Vacancy

When a property's occupation status is **Vacant**, record under Vacancy in **Edit this property**:

| Field | Meaning |
|---|---|
| Vacant since | The date it became vacant. |
| Vacancy status | **Available**, **Under offer**, **Underlet** or **Withdrawn** (not on the market). |
| Available from, Available until | When it can be occupied, and until when if it is only available for a time, for example until redevelopment starts. |

The status shows as a coloured tag beside the occupation on the property's page. When the occupation status
changes from Vacant to anything else, PHAEMA clears these details, because they no longer apply.

## Planning a disposal

Once a disposal is planned, fill in under Disposal in **Edit this property**: the **reason for disposal**, the
**method** (private treaty, auction, formal or informal tender, development or building agreement, community asset
transfer, or other), the date it is **expected**, and the **expected value**. These appear on the property's page
as **Planned disposal**.

When the sale or long lease completes, fill in **Disposed of on** and the **disposal price**. The page then shows
what happened in place of the plan, and the property leaves open data.

The disposal itself is still run as a [case](cases.md) or a [project](projects.md). These fields are the summary
on the property, which reports and the standard's export can read.

## Running costs and rates

Under **Running costs and rates** in **Edit this property**, add a line for each financial year:

| Field | Meaning |
|---|---|
| Financial year starting | The year the financial year starts in: 2025 for 2025-26. One line for each year. |
| Running cost | The cost of occupying and running the property for the year: energy, water, cleaning, security, repairs and maintenance, insurance and service charges. Leave out rates, rent and capital works. |
| Business rates | The rates payable by the council for the year. |
| Notes | Where the figures came from, or what is estimated. |

Enter either figure or both. The figures usually come from the finance system: PHAEMA does not work them out.
The latest five years are shown on the property's page, and the latest year is a column in the report builder.

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

## Site and buildings

The **Site and buildings** section on a property's page describes what is physically there, so that whoever
manages or values it can understand it without a visit. Fill it in from **Edit this property**, under **Site and
buildings** and **Services**. Leave blank anything you do not know: blanks are not shown.

| What | Notes |
|---|---|
| Location | Where the property is and what surrounds it: the part of town, road links, neighbouring uses, access. |
| Site area | In hectares or square metres. Type either one and PHAEMA works out the other. |
| Description | For a site, the buildings and land. For a building, its layout and accommodation. |
| Built | A year or a period, such as 1987 or 1930s. |
| Construction | Chosen from a list, with a line of detail such as "cavity brick walls, solid concrete floors". |
| Storeys | Above ground, with basement levels counted separately. |
| Roof type and covering | Each chosen from a list, with a line of detail for mixed roofs or the date of re-covering. |
| Windows | Chosen from a list, with a line of detail. |
| Parking | A description and the number of spaces. |
| Services | Mains gas, electricity (three-phase or single-phase), mains water and drainage, with notes for heating, capacity or meters. |
| Solar panels | Yes or no, and the capacity in kWp. |

**Sites with several blocks.** Record the site as a whole (location, site area, parking) on the site or estate,
and the construction, storeys, roof, windows and services on each building within it. See
[how properties fit together](#how-properties-fit-together).

**Floor plans.** On the property's page, open **Add floor plans or photos** and drag the plans onto the box, or
choose them: up to 20 at a time, each titled with its file name. Plans can be PDFs or AutoCAD drawings (.dwg or
.dxf), up to 50 MB each. PDFs open in PHAEMA's [reader](getting-started.md#reading-a-pdf); AutoCAD drawings download to open in your drawing software.
Change a title or date, or remove a plan, in **Edit this property**, under **Floor plans**. Surveyors can add
plans to the properties they manage.

All of these can be chosen as columns and filters in [reports](reports.md), and filled in from a spreadsheet with
the [property import](import-export.md).

### Year built and overall condition

Beside **Built**, which takes a year or a period in words ("1930s", "c. 1987, extended 2004"), there is **Year
built**: a single year for reports. PHAEMA fills it in from the first year in **Built** if you leave it blank.

**Overall condition** is the grade for the building as a whole from its last condition survey, with the date it
was **surveyed**:

| Grade | Meaning |
|---|---|
| A | Good, performing as intended |
| B | Satisfactory, minor deterioration |
| C | Poor, major repair or replacement soon |
| D | Bad, life expired or serious risk |

This is separate from the grades given to individual components (the roof, the boilers) under
[maintenance](maintenance.md).

### The property report

**Property report** on a property's page gathers everything PHAEMA holds about it into one document: the key
facts, location, description, construction and services (with each building in turn), floor areas and how they
are made up, floor plans, titles, current tenancies and other agreements with their main terms, and the cases in
hand. It ends with a list of what a valuer is likely to ask for that has not been recorded yet. Read it on
screen, print it, or select **Download as Word** to edit and send.

On an asset valuation case the same report is headed **Initial valuation report**: see
[cases](cases.md#initial-valuation-report).

## Government Property Data Standard

The [Government Property Data Standard](https://www.gov.uk/government/publications/government-property-data-standard)
is the Cabinet Office's list of the facts central government bodies should hold about their property, each with a
reference number. It does not bind councils, but it is a recognised yardstick.

Administrators and surveyors can open **Reports**, then **Government Property Data Standard export**. The page
shows:

- a **Download the workbook** button
- how many records are in each sheet
- **how complete the records are**: for each of the standard's fields, how many current properties have it
  recorded
- the standard's fields that are **not exported**, and why

The workbook is an Excel file with six sheets:

| Sheet | What it holds |
|---|---|
| About | What the workbook is, when it was produced, and notes on how to read it. |
| Properties | Every site, building, unit and parcel of land, including those disposed of. |
| Contracts | Agreements under which the council holds property as tenant or licensee. |
| Vacant spaces | Vacant property that has no parts of its own. |
| FM assets | Building components from maintenance. |
| Fields not exported | The standard's fields PHAEMA does not hold, holds partly, or that do not apply to a council. |

Each column is headed with the standard's field name and its reference number in square brackets, for example
"Listed Building [2.2.0004]". Columns with no number are PHAEMA's own, so that a row can be traced back.

Things to know:

- **It is a mapping, not a certificate.** PHAEMA's records are set out in the standard's layout. That does not
  make the council "compliant" with a standard that does not apply to it.
- **A blank cell means not recorded.** Nothing is estimated or filled in by default.
- **Lettings by the council are not in it.** The standard's contract fields describe what an organisation
  holds, not what it lets. Use the [reports](reports.md) for lettings.
- **Names and contact details are left out**, for tenants and officers alike.
- **You only get what you can see.** Valuations, energy certificates and components are included only if those
  parts of PHAEMA are switched on and open to you.
- A **unit** is given its building's name as the primary name and its own name as the secondary name, and takes
  the building's address if it has none of its own.

## Photos

On the property's page, open **Add floor plans or photos** and drag photos onto the box, or choose them: up to
20 at a time, each captioned with its file name. You can also add them in **Edit this property**, where you change
captions and choose the main photo. They are resized and their location data removed when uploaded. Select a photo on the property page to see it full size.

## Titles

Land Registry titles are linked to properties. A title can hold a PDF of the register and plan. Administrators
manage titles. See also [Land Registry boundaries](maps.md#land-registry-inspire-boundaries).

## Leases on a property

The property page lists the leases and licences that include it. See [leases and licences](leases.md).

## Projects on a property

The property page lists the [projects](projects.md) it is part of, including those of the estate or building it
belongs to. Confidential projects are listed only for their team and administrators.

## Worked example

In the demonstration data, **DM-N01 Northfield Business Park** is an estate. Its parts are the **Hangar block**
(DM-N01-B01, units 1 to 5), the **Workshop block** (DM-N01-B02, units 6 to 10) and the estate roads (DM-N01-L01).
Units 4 and 10 are vacant, so the estate shows as partly let.

Lena Chen is the managing surveyor of DM-N01, so she also manages every block and unit within it: their events
are assigned to her and she can change them. **DM-N06 Former Northfield bus depot** has no managing surveyor (filter
the register by **Managing surveyor: Nobody** to find it) and records site hazards, which appear on every case,
job and valuation for it.
