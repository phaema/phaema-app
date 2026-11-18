title: Space and occupiers
section: Key dates
order: 9
summary: Which departments and outside organisations occupy each building, floor and room, the stacking plan, headcount, use of space and public use.
---
# Space and occupiers

An optional module for operational buildings: offices, depots, libraries, leisure centres and community
buildings. It records **who occupies each building, floor and room**, how much space each occupier holds, and
**how well the space is used**. It is the evidence for the estates strategy: stay, share, remodel or release.

Administrators switch it on in **Manage data**, **Module settings**, under Modules (**Space and costing**). It is
opened for people by [access areas](users-and-roles.md#access-areas); the standard **Estates** area includes it.
Switching it off hides every page and keeps the data. A second tick, **Space and costing: show costs**, adds
[costs by occupier](#costs-by-occupier). Costs are seen only by administrators and people whose access areas open
**Space costs** (the standard **Finance** area does).

## Occupiers

**Manage data**, **Occupiers** holds the council's own structure and the outside organisations it shares
buildings with. Administrators keep this list.

- **Directorates, departments and teams**: each can be "part of" the level above. Figures for a directorate
  include everything below it.
- **Outside organisations**: NHS, police, fire and rescue, other public bodies, charities. They are shown with a
  blue tag and striped in the stacking plan. Sharing buildings with them is the **One Public Estate** picture.
- Each occupier can have a **head of service**, a **property liaison** (the person in the department who deals with
  estates about its buildings) and a **cost centre**, ready for costs.

An occupier in use cannot be deleted: untick **Active** instead, so its history stays.

## Floors, rooms and shared space

From a building's page, select **Space and occupiers**, then **Add a floor, room or shared space**.

| Kind | Notes |
|---|---|
| Floor | The whole floor, with its floor number (0 for ground, -1 for a basement) and area. |
| Room or area | On a floor: an office, a clinic, a public counter. Give its area and its **capacity** (desks or places). |
| Shared space | Reception, meeting rooms, kitchens, circulation, plant. Not held by anyone; shared out in proportion to the space each occupier holds. |

Floor level is enough to start; rooms are optional.

## Who occupies what

**Add an occupier** records an occupier in a space (or the whole building if the space is left blank), from a date
and, when they leave, until a date. History is kept, so the position on any past date can be shown.

Several occupiers can share a space. For each, give **either a percentage or an area in square metres**, and PHAEMA
works out the other. Leave both blank if they have all of it. PHAEMA refuses an area larger than the space, and
warns on the building page if the shares in a space add up to more than 100%.

## The building page

**Space and occupiers** on a building shows:

- the **stacking plan**: floors top first, each occupier a coloured block as wide as its area, shared space grey and
  vacant space hatched (there is a table version for screen readers);
- **occupiers**: own space, their share of shared space, people based here, capacity, **use** (people against
  desks or places) and square metres a person;
- **public use** figures.

Use the date in the address (`?on=2026-04-01`) to see an earlier date.

## Headcount and use of space

**Record headcount** gives the people based in the building for an occupier, as at a date, with the full-time
equivalent and the **source** (for example the HR establishment list). The latest figure on or before the date
shown is used.

With hybrid working, people based in a building against desks overstates how much the space is used. Occupancy
surveys (counts at set times over a week or two) and imported desk booking or door counter figures are later
stages. PHAEMA records counts only, never named people.

## Public use

For buildings where visitors are the measure, **Record public use** gives a figure for a period: visits, bookings,
hours used, registered members. Give "out of" (for example hours open) to show a percentage. The list of measures is
in **Manage data**, **Public use measures**, and councils can add their own.

**Flexibility but accountability.** Councils can change these lists, but every figure shows its source, who entered
it and when, and every change is in the [change log](change-log.md).

## Costs by occupier

Costs are entered **per building per financial year** (April to March), one figure per **cost line**, each with its
**source**. From the building's **Space and occupiers** page, select **Add a cost**. The cost lines are a list the
council keeps in **Manage data**, **Cost lines**, starting with rent paid, business rates, energy, water, cleaning,
security, repairs and maintenance, insurance, facilities management contracts, capital charges (off to start with)
and **notional rent**.

- **Notional rent** is what a freehold building would cost to rent, usually the valuer's estimate of market rent.
  It is not cash, so it is tagged **Notional** and totals are shown both with and without it. It lets departments
  in freehold buildings see a realistic cost of occupancy, comparable with leased space.
- If no figures are entered for a year, the **running cost** and **business rates** on the property record are
  used, marked "from the property record".
- If no repairs figure is entered and the maintenance module is on, PHAEMA totals the maintenance jobs completed in
  the year at the council's cost, marked "from the maintenance jobs".

**How a building's cost is shared.** By **floor area held** unless the council chooses otherwise for the building
(**Change how costs are shared**):

| Method | How |
|---|---|
| By floor area held | Each occupier's own space plus its share of shared space, as a share of the building's whole floor area. The cost of **vacant space stays with the corporate landlord** and is shown as its own line. |
| By headcount | People based in the building. An occupier with no headcount takes no share, and PHAEMA says so. |
| Fixed percentages | Shares agreed with finance, entered per occupier. PHAEMA warns if they do not add up to 100% or an occupier has none. |

Every table says which method was used. The figures **show** what occupation costs; they are not recharges, which
stay with the council's finance system.

**Costs by occupier** (from the Space and occupiers pages) totals each occupier across the estate for a year, with
cost a square metre and a person, and the cost of vacant space. **Download for finance** gives an Excel workbook:
by occupier, by building, every cost with its source, and a note on the method. Each occupier's own page shows its
costs building by building; a directorate includes its departments.

## Who can change what

| Role | Can |
|---|---|
| Administrators | Everything, including the occupiers list, public use measures and cost lines. |
| People with Space costs open (for example Finance) | Enter building costs and choose how each building's costs are shared. |
| Surveyors | Spaces, occupation, headcount and public use for the buildings they manage. |
| Others with the module open | Look. |

## Worked example

On the demonstration site, open **Buildings**, **Space and occupiers**, then **DM-S30 Exampleton Civic Centre** (an
invented building). Four departments, the library and an NHS clinic share three floors, with reception, meeting
rooms and a kitchen shared. Planning and Customer Services share the second-floor office 60% and 20%, leaving 100 m²
of it vacant. **Northfield Library** shows public use figures. Signed in as the finance officer, both buildings show
two years of costs with notional rent, and **Costs by occupier** shows the estate total.
