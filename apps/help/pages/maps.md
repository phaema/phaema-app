title: Maps
section: Records
order: 2
summary: The property map, base maps, Land Registry INSPIRE boundaries and setting a property's boundary.
---
# Maps

## The property map

Select **Map** in the menu to see every property with a location. Colours show occupation (see the key). Select a
property for its details and a link to its page. Filters work as they do on the property list, and
**Show as a list** takes you back to the list with the same filters.

A property appears on the map if it has a **boundary** or an **easting and northing** (a British National Grid
reference).

## Base maps

- **OpenStreetMap** is always available.
- **Ordnance Survey** maps are available when an administrator has added the council's OS Maps API key in
  [settings](settings.md). Councils have free access through the Public Sector Geospatial Agreement.

## Land Registry INSPIRE boundaries

HM Land Registry publishes the boundaries of registered freehold titles as "INSPIRE Index Polygons", free for each
local authority area. Administrators can load them with **Import**, then **Land Registry boundaries**. Download the
GML file for your area from the Land Registry website first.

INSPIRE boundaries show the general extent of a title, not its legal boundary.

> Contains HM Land Registry data © Crown copyright and database right. This data is licensed under the Open
> Government Licence v3.0.

## Setting a property's boundary

On a property page, select **Set the boundary from Land Registry INSPIRE parcels**. Choose one or more parcels
near the property and save. The boundary source is recorded on the property.

## Using PHAEMA's boundaries in QGIS or ArcGIS

PHAEMA offers its property boundaries as map layers for desktop GIS, in the open **OGC API - Features** standard.
Your GIS team can show them beside the council's own layers without copying files, and always sees the latest
boundaries.

There are two layers:

- **Properties:** every property in the register, including blocks and units. A property with no boundary drawn
  is shown as a point at its grid reference.
- **Top-level holdings:** only properties that are not part of another (sites, estates and stand-alone buildings
  and land), so the shapes do not overlap. This suits colouring by holding purpose or occupation.

Each feature carries the reference, name, type, parent, holding purpose, tenure, occupation, use, address, UPRN,
portfolio, managing surveyor, areas and a link to the record in PHAEMA. The layers are read only.

**Connecting.** An administrator makes an [API token](users-and-roles.md#api-tokens): read only, acting as a
Viewer account such as "gis.service", with **Properties** ticked. Then:

- **QGIS:** in **Settings**, **Options**, **Authentication**, add a configuration of the **API Header** kind, with
  the header `Authorization` and the value `Bearer ` followed by the token. Then **Layer**, **Add Layer**, **Add
  WFS / OGC API - Features Layer**, make a new connection to `https://<your PHAEMA address>/api/ogc/` with that
  authentication, and choose a layer.
- **ArcGIS Pro:** **Insert**, **Connections**, **Server**, **New OGC API Server**, with the same address and the
  token as a custom request header where your version offers it.

Layers are served in longitude and latitude (WGS 84) unless the GIS asks for British National Grid (EPSG:27700),
which PHAEMA also offers. The token works only for the parts of PHAEMA it was made for, and the layers show only
what its account may see.
