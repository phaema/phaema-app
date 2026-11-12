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

  let resizing;
  window.addEventListener("resize", () => {
    clearTimeout(resizing);
    resizing = setTimeout(() => {
      const value = viewer.currentScaleValue;
      if (value === "page-width" || value === "page-fit") viewer.currentScaleValue = value;
    }, 150);
  });
}
