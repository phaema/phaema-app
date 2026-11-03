// SPDX-License-Identifier: AGPL-3.0-or-later
// PHAEMA maps, built on OpenLayers (vendored, BSD licence).
// Background mapping: Ordnance Survey (if the council has set an OS Maps API key) or OpenStreetMap.
/* global ol */
(function () {
  "use strict";

  const COLOURS = {
    let: "#00703c", part_let: "#1d70b8", vacant: "#d4351c", council: "#1d3557",
    na: "#505a5f", "": "#505a5f",
  };

  function colourFor(props) {
    if (props.role === "inspire") return "#f47738";
    if (props.role === "parent") return "#505a5f";
    return COLOURS[props.occupation] || "#505a5f";
  }

  function style(feature, selected) {
    const p = feature.getProperties();
    const colour = colourFor(p);
    const isInspire = p.role === "inspire";
    const isSelected = selected && selected.has(p.inspireId);
    const stroke = new ol.style.Stroke({
      color: isSelected ? "#0b0c0c" : colour,
      width: p.role === "self" || isSelected ? 3 : 2,
      lineDash: p.role === "parent" || (isInspire && !isSelected) ? [6, 4] : undefined,
    });
    const fillAlpha = p.role === "parent" ? "00" : isSelected ? "88" : isInspire ? "11" : "40";
    return new ol.style.Style({
      stroke,
      fill: new ol.style.Fill({ color: (isSelected ? "#ffdd00" : colour) + fillAlpha }),
      image: new ol.style.Circle({
        radius: p.role === "self" ? 8 : 6,
        fill: new ol.style.Fill({ color: colour }),
        stroke: new ol.style.Stroke({ color: "#ffffff", width: 2 }),
      }),
    });
  }

  function baseLayers(config) {
    const layers = [];
    if (config.osKey) {
      layers.push({
        id: "os", label: "Ordnance Survey",
        layer: new ol.layer.Tile({
          source: new ol.source.XYZ({
            url: `https://api.os.uk/maps/raster/v1/zxy/${config.osStyle}/{z}/{x}/{y}.png?key=${encodeURIComponent(config.osKey)}`,
            attributions: `Contains OS data © Crown copyright and database rights ${config.year}`,
            maxZoom: 20,
          }),
        }),
      });
    }
    layers.push({
      id: "osm", label: "OpenStreetMap",
      layer: new ol.layer.Tile({ source: new ol.source.OSM() }),
    });
    layers.forEach((b, i) => b.layer.setVisible(i === 0));
    return layers;
  }

  function init(el) {
    const config = JSON.parse(document.getElementById(el.dataset.config).textContent);
    const bases = baseLayers(config);
    const features = new ol.source.Vector({ url: el.dataset.featuresUrl, format: new ol.format.GeoJSON() });
    const featureLayer = new ol.layer.Vector({ source: features, style: (f) => style(f) });

    // INSPIRE parcels, loaded for the visible area once zoomed in.
    const selectForm = el.dataset.selectForm ? document.getElementById(el.dataset.selectForm) : null;
    const selected = new Set();
    const inspireSource = new ol.source.Vector({
      format: new ol.format.GeoJSON(),
      strategy: ol.loadingstrategy.bbox,
      attributions: config.inspireAttribution,
      url: (extent) => {
        const bbox = ol.proj.transformExtent(extent, "EPSG:3857", "EPSG:4326");
        return `${config.inspireUrl}?bbox=${bbox.join(",")}`;
      },
    });
    const inspireLayer = new ol.layer.Vector({
      source: inspireSource, minZoom: 15, visible: !!selectForm || el.dataset.inspire === "on",
      style: (f) => style(f, selected),
    });

    const map = new ol.Map({
      target: el,
      layers: bases.map((b) => b.layer).concat([inspireLayer, featureLayer]),
      view: new ol.View({ center: ol.proj.fromLonLat([-1.5, 52.6]), zoom: 6 }),
      controls: ol.control.defaults.defaults({ attributionOptions: { collapsible: false } })
        .extend([new ol.control.ScaleLine({ units: "metric" })]),
    });

    features.once("featuresloadend", () => {
      const extent = features.getExtent();
      if (features.getFeatures().length && isFinite(extent[0])) {
        map.getView().fit(extent, { padding: [40, 40, 40, 40], maxZoom: 18 });
      } else if (el.dataset.empty) {
        document.getElementById(el.dataset.empty).hidden = false;
      }
    });

    // Controls below the map: background map choice and INSPIRE toggle.
    const controls = document.getElementById(el.dataset.controls);
    if (controls) {
      if (bases.length > 1) {
        const label = document.createElement("label");
        label.className = "govuk-label govuk-!-display-inline-block govuk-!-margin-right-2";
        label.textContent = "Background map";
        label.htmlFor = el.id + "-base";
        const select = document.createElement("select");
        select.className = "govuk-select govuk-!-margin-right-4";
        select.id = el.id + "-base";
        bases.forEach((b) => select.add(new Option(b.label, b.id)));
        select.addEventListener("change", () => bases.forEach((b) => b.layer.setVisible(b.id === select.value)));
        controls.append(label, select);
      }
      if (!selectForm) {
        const wrap = document.createElement("div");
        wrap.className = "govuk-checkboxes govuk-checkboxes--small govuk-!-display-inline-block";
        wrap.innerHTML = `<div class="govuk-checkboxes__item"><input class="govuk-checkboxes__input" id="${el.id}-inspire" type="checkbox"${inspireLayer.getVisible() ? " checked" : ""}>
          <label class="govuk-label govuk-checkboxes__label" for="${el.id}-inspire">Land Registry INSPIRE parcels (zoom in to see)</label></div>`;
        wrap.querySelector("input").addEventListener("change", (e) => inspireLayer.setVisible(e.target.checked));
        controls.append(wrap);
      }
    }

    // Clicking a property shows its name and a link; on the boundary page, clicking a parcel selects it.
    const info = el.dataset.info ? document.getElementById(el.dataset.info) : null;
    map.on("singleclick", (evt) => {
      const hits = map.getFeaturesAtPixel(evt.pixel);
      if (selectForm) {
        const parcel = hits.find((f) => f.get("role") === "inspire");
        if (!parcel) return;
        const box = selectForm.querySelector(`input[value="${CSS.escape(parcel.get("inspireId"))}"]`);
        if (box) { box.checked = !box.checked; box.dispatchEvent(new Event("change")); }
        return;
      }
      const hit = hits.find((f) => f.get("url"));
      if (info) {
        if (hit) {
          info.innerHTML = "";
          const a = document.createElement("a");
          a.className = "govuk-link"; a.href = hit.get("url");
          a.textContent = `${hit.get("reference")} ${hit.get("name")}`;
          info.append(a, ` – ${hit.get("type")}${hit.get("occupationLabel") ? ", " + hit.get("occupationLabel").toLowerCase() : ""}`);
        } else {
          info.textContent = info.dataset.default || "";
        }
      }
    });
    map.on("pointermove", (evt) => {
      map.getTargetElement().style.cursor = map.hasFeatureAtPixel(evt.pixel) ? "pointer" : "";
    });

    if (selectForm) {
      selectForm.querySelectorAll("input[name=parcel]").forEach((box) => {
        box.addEventListener("change", () => {
          if (box.checked) selected.add(box.value); else selected.delete(box.value);
          inspireLayer.changed();
        });
        if (box.checked) selected.add(box.value);
      });
    }
  }

  document.querySelectorAll("[data-phaema-map]").forEach(init);
})();
