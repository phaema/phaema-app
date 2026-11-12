// SPDX-License-Identifier: AGPL-3.0-or-later
// Shows a PDF inside PHAEMA with PDF.js (static/vendor/pdfjs). The page works without this file: it then offers
// the document to open in the browser or download.
const root = document.querySelector("[data-pdf-view]");
if (root) start(root).catch((err) => fail(root, err));

function part(root, name) { return root.querySelector(`[data-pdf="${name}"]`); }

function fail(root, err) {
  console.error(err);
  const name = err && err.name;
  let text = "PHAEMA could not read this file as a PDF.";
  if (err && err.tooOld) text = "PHAEMA's reader needs a newer web browser than this one.";
  else if (name === "PasswordException") text = "This document is protected with a password.";
  else if (name === "MissingPDFException" || name === "UnexpectedResponseException" || name === "ResponseException") {
    text = "The document could not be fetched. You may have been signed out: reload the page and try again.";
  }
  part(root, "status").hidden = true;
  part(root, "error-text").textContent = text;
  part(root, "error").hidden = false;
}

async function start(root) {
  const data = root.dataset;
  let pdfjsLib, pdfjsViewer;
  try {
    pdfjsLib = await import(data.lib);
    globalThis.pdfjsLib = pdfjsLib;                    // the viewer components look for the library here
    pdfjsViewer = await import(data.viewer);
  } catch (err) {
    err.tooOld = true;                                 // the library needs a browser from the last two years or so
    throw err;
  }
  pdfjsLib.GlobalWorkerOptions.workerSrc = data.worker;

  const container = part(root, "container");
  const eventBus = new pdfjsViewer.EventBus();
  const linkService = new pdfjsViewer.PDFLinkService({ eventBus, externalLinkTarget: 2, externalLinkRel: "noopener noreferrer nofollow" });
  const findController = new pdfjsViewer.PDFFindController({ eventBus, linkService });
  const viewer = new pdfjsViewer.PDFViewer({ container, viewer: part(root, "pages-holder"), eventBus, linkService, findController });
  linkService.setViewer(viewer);

  const page = part(root, "page");
  eventBus.on("pagesinit", () => { viewer.currentScaleValue = "page-width"; });
  eventBus.on("pagechanging", (evt) => { page.value = evt.pageNumber; });

  const doc = await pdfjsLib.getDocument({
    url: data.src, cMapUrl: data.assets + "cmaps/", cMapPacked: true,
    standardFontDataUrl: data.assets + "standard_fonts/", wasmUrl: data.assets + "wasm/",
    enableXfa: false, isEvalSupported: false,
  }).promise;
  viewer.setDocument(doc);
  linkService.setDocument(doc, null);
  part(root, "pages").textContent = doc.numPages;
  page.max = doc.numPages;
  part(root, "status").hidden = true;
  root.querySelector("[data-pdf-bar]").hidden = false;

  const go = (n) => { if (n >= 1 && n <= doc.numPages) viewer.currentPageNumber = n; };
  const on = (name, fn) => part(root, name).addEventListener("click", fn);
  on("prev", () => go(viewer.currentPageNumber - 1));
  on("next", () => go(viewer.currentPageNumber + 1));
  page.addEventListener("change", () => { go(parseInt(page.value, 10)); page.value = viewer.currentPageNumber; });
  on("zoom-in", () => { viewer.currentScale = Math.min(viewer.currentScale * 1.2, 6); });
  on("zoom-out", () => { viewer.currentScale = Math.max(viewer.currentScale / 1.2, 0.2); });
  on("fit-width", () => { viewer.currentScaleValue = "page-width"; });
  on("fit-page", () => { viewer.currentScaleValue = "page-fit"; });
  on("rotate", () => { viewer.pagesRotation = (viewer.pagesRotation + 90) % 360; });

  const find = part(root, "find");
  const count = part(root, "find-count");
  const search = (type, previous) => {
    if (!find.value.trim()) { count.textContent = ""; }
    eventBus.dispatch("find", { source: root, type, query: find.value, caseSensitive: false, entireWord: false,
                                highlightAll: true, findPrevious: previous, matchDiacritics: false });
  };
  part(root, "find-form").addEventListener("submit", (evt) => { evt.preventDefault(); search("", false); });
  on("find-next", () => search("again", false));
  on("find-prev", () => search("again", true));
  const showCount = (evt) => {
    const m = evt.matchesCount || {};
    if (!find.value.trim()) count.textContent = "";
    else if (m.total) count.textContent = `${m.current} of ${m.total}`;
    else if (evt.state === 1 || evt.state === undefined) count.textContent = "Not found";   // 1 = FindState.NOT_FOUND
  };
  eventBus.on("updatefindmatchescount", showCount);
  eventBus.on("updatefindcontrolstate", showCount);

  thumbnails(root, doc, viewer, eventBus);

  let resizing;
  window.addEventListener("resize", () => {
    clearTimeout(resizing);
    resizing = setTimeout(() => {
      const value = viewer.currentScaleValue;
      if (value === "page-width" || value === "page-fit") viewer.currentScaleValue = value;
    }, 150);
  });
}

// The strip of small pages down the side. Each is drawn only when it scrolls into view, one at a time.
function thumbnails(root, doc, viewer, eventBus) {
  const strip = part(root, "thumbs");
  const toggle = part(root, "thumbs-toggle");
  const word = strip.dataset.pageWord || "Page";
  const wide = window.matchMedia("(min-width: 48em)");
  const items = [];
  let built = false;
  let queue = Promise.resolve();

  const refit = () => {
    const value = viewer.currentScaleValue;
    if (value === "page-width" || value === "page-fit") viewer.currentScaleValue = value;
  };
  const mark = (number, follow) => {
    items.forEach((item) => item.button.removeAttribute("aria-current"));
    const item = items[number - 1];
    if (!item) return;
    item.button.setAttribute("aria-current", "page");
    if (follow && !strip.hidden) {                      // keep the current page in sight without moving the whole window
      const top = item.button.offsetTop, bottom = top + item.button.offsetHeight;
      if (top < strip.scrollTop) strip.scrollTop = top - 8;
      else if (bottom > strip.scrollTop + strip.clientHeight) strip.scrollTop = bottom - strip.clientHeight + 8;
    }
  };
  const draw = (item) => {
    if (item.drawn) return;
    item.drawn = true;
    queue = queue.then(async () => {
      const page = await doc.getPage(item.number);
      const turn = (page.rotate + viewer.pagesRotation) % 360;
      const base = page.getViewport({ scale: 1, rotation: turn });
      const width = item.holder.clientWidth || 110;
      const viewport = page.getViewport({ scale: (width / base.width) * Math.min(window.devicePixelRatio || 1, 2), rotation: turn });
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(viewport.width);
      canvas.height = Math.round(viewport.height);
      item.holder.style.height = Math.round(width * base.height / base.width) + "px";
      await page.render({ canvas, canvasContext: canvas.getContext("2d"), viewport }).promise;
      item.holder.replaceChildren(canvas);
    }).catch((err) => { console.error(err); });
  };
  const watcher = new IntersectionObserver((entries) => {
    entries.forEach((entry) => { if (entry.isIntersecting) draw(items[entry.target.dataset.page - 1]); });
  }, { root: strip, rootMargin: "300px 0px" });

  const build = async () => {
    built = true;
    const first = (await doc.getPage(1)).getViewport({ scale: 1 });
    for (let number = 1; number <= doc.numPages; number += 1) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "phaema-pdf__thumb";
      button.dataset.page = number;
      button.setAttribute("aria-label", `${word} ${number}`);
      const holder = document.createElement("span");
      holder.className = "phaema-pdf__thumb-page";
      const label = document.createElement("span");
      label.textContent = number;
      button.append(holder, label);
      strip.append(button);
      holder.style.height = Math.round(holder.clientWidth * first.height / first.width) + "px";
      button.addEventListener("click", () => { viewer.currentPageNumber = number; });
      items.push({ number, button, holder, drawn: false });
      watcher.observe(button);
    }
    mark(viewer.currentPageNumber, true);
  };
  const show = (open, remember) => {
    strip.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && !built) build();
    else if (open) mark(viewer.currentPageNumber, true);
    refit();
    if (remember) { try { localStorage.setItem("phaema-pdf-pages", open ? "open" : "closed"); } catch (err) { /* not remembered */ } }
  };

  toggle.addEventListener("click", () => show(strip.hidden, true));
  eventBus.on("pagechanging", (evt) => mark(evt.pageNumber, true));
  eventBus.on("rotationchanging", () => {
    items.forEach((item) => { item.drawn = false; watcher.unobserve(item.button); watcher.observe(item.button); });
  });

  let saved = null;
  try { saved = localStorage.getItem("phaema-pdf-pages"); } catch (err) { /* start from the default */ }
  if (doc.numPages > 1 && wide.matches && saved !== "closed") show(true, false);
}
