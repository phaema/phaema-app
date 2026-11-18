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
Switching it off hides every page and keeps the data. Showing costs by occupier is a later stage.

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

## Who can change what

| Role | Can |
|---|---|
| Administrators | Everything, including the occupiers list and public use measures. |
| Surveyors | Spaces, occupation, headcount and public use for the buildings they manage. |
| Others with the module open | Look. |

## Worked example

On the demonstration site, open **Buildings**, **Space and occupiers**, then **DM-S30 Exampleton Civic Centre** (an
invented building). Four departments, the library and an NHS clinic share three floors, with reception, meeting
rooms and a kitchen shared. Planning and Customer Services share the second-floor office 60% and 20%, leaving 100 m²
of it vacant. **Northfield Library** shows public use figures.
