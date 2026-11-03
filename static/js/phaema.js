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
