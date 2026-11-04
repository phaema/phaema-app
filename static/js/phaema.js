// SPDX-License-Identifier: AGPL-3.0-or-later
// Photo gallery: clicking a thumbnail shows it as the main photo.
// Without JavaScript the thumbnails simply open the full-size photo.
for (const gallery of document.querySelectorAll("[data-phaema-gallery]")) {
  const main = gallery.querySelector("[data-gallery-main]");
  const caption = gallery.querySelector("[data-gallery-caption]");
  const link = gallery.querySelector("[data-gallery-link]");
  const thumbs = gallery.querySelectorAll("[data-gallery-thumb]");
  thumbs.forEach((thumb, index) => {
    thumb.addEventListener("click", (event) => {
      event.preventDefault();
      main.src = thumb.href;
      main.alt = thumb.dataset.alt;
      link.href = thumb.href;
      caption.textContent = `Photo ${index + 1} of ${thumbs.length}` + (thumb.dataset.caption ? `: ${thumb.dataset.caption}` : "");
      thumbs.forEach((t) => t.removeAttribute("aria-current"));
      thumb.setAttribute("aria-current", "true");
    });
  });
}

// Header menus: one open at a time; close on Escape or a click elsewhere.
const menus = document.querySelectorAll(".phaema-menu");
menus.forEach((menu) => menu.addEventListener("toggle", () => {
  if (menu.open) menus.forEach((other) => { if (other !== menu) other.open = false; });
}));
document.addEventListener("click", (event) => {
  menus.forEach((menu) => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  menus.forEach((menu) => { if (menu.open) { menu.open = false; menu.querySelector("summary").focus(); } });
});

// Collapsible panels. Each <section class="phaema-panel" data-panel="key"> gets a show/hide button in its
// heading. Closed panels are remembered in this browser. Without JavaScript every panel stays open.
const PANEL_STORE = "phaema_closed_panels";
function closedPanels() {
  try { return new Set(JSON.parse(localStorage.getItem(PANEL_STORE) || "[]")); } catch (e) { return new Set(); }
}
function rememberPanels(set) {
  try { localStorage.setItem(PANEL_STORE, JSON.stringify([...set])); } catch (e) { /* private browsing */ }
}
const panels = [...document.querySelectorAll(".phaema-panel[data-panel]")];
function setPanel(panel, open, store) {
  const button = panel.querySelector(".phaema-panel__toggle");
  const body = panel.querySelector(".phaema-panel__body");
  button.setAttribute("aria-expanded", String(open));
  button.querySelector(".phaema-panel__state").textContent = open ? "Hide" : "Show";
  body.hidden = !open;
  panel.classList.toggle("phaema-panel--closed", !open);
  if (store) {
    const closed = closedPanels();
    if (open) closed.delete(panel.dataset.panel); else closed.add(panel.dataset.panel);
    rememberPanels(closed);
  }
}
const closedAtStart = closedPanels();
panels.forEach((panel, i) => {
  const title = panel.querySelector(".phaema-panel__title");
  const body = panel.querySelector(".phaema-panel__body");
  if (!title || !body) return;
  body.id = body.id || `panel-body-${i}`;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "phaema-panel__toggle";
  button.setAttribute("aria-controls", body.id);
  const label = document.createElement("span");
  label.className = "phaema-panel__label";
  while (title.firstChild) label.appendChild(title.firstChild);
  const state = document.createElement("span");
  state.className = "phaema-panel__state";
  state.setAttribute("aria-hidden", "true");
  button.append(label, state);
  title.appendChild(button);
  setPanel(panel, !closedAtStart.has(panel.dataset.panel), false);
  button.addEventListener("click", () => setPanel(panel, button.getAttribute("aria-expanded") !== "true", true));
});
const panelsControl = document.querySelector("[data-panels-control]");
if (panelsControl && panels.length > 1) {
  const all = document.createElement("button");
  all.type = "button";
  all.className = "phaema-link-button govuk-body-s govuk-!-margin-0";
  const refresh = () => {
    all.textContent = panels.every((p) => !p.classList.contains("phaema-panel--closed")) ? "Hide all" : "Show all";
  };
  all.addEventListener("click", () => {
    const open = all.textContent === "Show all";
    panels.forEach((p) => setPanel(p, open, true));
    refresh();
  });
  panels.forEach((p) => p.querySelector(".phaema-panel__toggle")?.addEventListener("click", refresh));
  refresh();
  panelsControl.appendChild(all);
}

// Wide tables scroll sideways inside their own box on small screens, instead of the whole page.
// A table that is wider than the screen becomes a labelled, focusable region so keyboard users can scroll it.
// Without JavaScript the page itself scrolls, as before.
function tableName(table) {
  const caption = table.querySelector("caption");
  if (caption && caption.textContent.trim()) return caption.textContent.trim();
  let el = table.closest(".phaema-table-scroll") || table;
  while (el && el !== document.body) {
    let prev = el.previousElementSibling;
    while (prev) {
      if (/^H[1-4]$/.test(prev.tagName)) return prev.textContent.trim();
      const inner = prev.querySelectorAll ? prev.querySelectorAll("h1, h2, h3, h4") : [];
      if (inner.length) return inner[inner.length - 1].textContent.trim();
      prev = prev.previousElementSibling;
    }
    el = el.parentElement;
  }
  return "Table";
}
const scrollBoxes = [];
document.querySelectorAll("main table.govuk-table").forEach((table) => {
  let box = table.parentElement;
  if (!box.classList.contains("phaema-table-scroll")) {
    box = document.createElement("div");
    box.className = "phaema-table-scroll";
    table.parentNode.insertBefore(box, table);
    box.appendChild(table);
  }
  scrollBoxes.push(box);
});
function markScrollable() {
  scrollBoxes.forEach((box) => {
    if (box.scrollWidth > box.clientWidth + 1) {
      box.setAttribute("tabindex", "0");
      box.setAttribute("role", "region");
      if (!box.hasAttribute("aria-label")) box.setAttribute("aria-label", tableName(box.querySelector("table")));
    } else if (!box.dataset.keep) {
      box.removeAttribute("tabindex");
      box.removeAttribute("role");
    }
  });
}
scrollBoxes.forEach((box) => { if (box.hasAttribute("tabindex")) box.dataset.keep = "1"; });
markScrollable();
window.addEventListener("resize", markScrollable);
