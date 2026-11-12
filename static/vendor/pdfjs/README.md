# PDF.js

Mozilla's PDF viewer library, version 6.5.438, from the `pdfjs-dist` package on npm. Licence: Apache-2.0 (see LICENSE).

PHAEMA uses it to show PDFs inside its own page (`templates/core/pdf_view.html`, `static/js/pdf-view.mjs`).

Kept here: `build/pdf.min.mjs`, `build/pdf.worker.min.mjs`, `web/pdf_viewer.mjs`, `web/pdf_viewer.css`, `web/images/`,
`cmaps/`, `standard_fonts/` and `wasm/`. To update, download the new `pdfjs-dist` package, replace those files and
folders with the same ones from it, change the version above, and try the viewer on a text PDF and a scanned PDF.
