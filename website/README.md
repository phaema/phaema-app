# PHAEMA project website

A single static page (`index.html`) about the project: what PHAEMA is and does, why it is open source, the
roadmap, links to the test site, training, manuals, technical information and code, and how to take part.

- Edit text and links in `build.py` (`LINKS`, `CAPABILITIES`, `OPEN_SOURCE`, `ROADMAP`, `RESOURCES`, `INVOLVE`),
  then run `python3 website/build.py` to regenerate `index.html`.
- `LINKS["test_site"]` and `LINKS["contact"]` are empty until the test site is running and a contact address is
  chosen; the page shows "Coming soon" or points people to GitHub until then.
- The user manual, technical manual, test programme and integrations review are hosted on the site, in `docs/`,
  each as a web page with contents and a PDF to download. They are written in claude.ai docs; to refresh them,
  export each doc as HTML and as an A4 PDF into `docs/source/` (`<slug>.html` and `<slug>.pdf`), then run
  `python3 website/build_docs.py`. It takes the diagrams and screenshots from the PDF and also copies the
  e-learning from `static/training` into `training/`.
- To publish, upload `index.html`, `tour.html` and the `img/`, `docs/` and `training/` folders (not
  `docs/source/`, which is only the input).
- Host it anywhere that serves static files, for example GitHub Pages (Settings, Pages, deploy the `/website`
  folder) or phaema.co.uk.
- `tour.html` is the self-running, clickable tour; it uses the screenshots in `img/` and links back to `index.html`.
- Screenshots in `img/` show the fictional demonstration data.
- Fonts load from Google Fonts. For a site that makes no third-party requests, download Atkinson Hyperlegible
  and Bricolage Grotesque (both under the SIL Open Font License) into `website/fonts/` and replace the link.
