# PHAEMA project website

A single static page (`index.html`) about the project: what PHAEMA is and does, why it is open source, the
roadmap, links to the test site, training, manuals, technical information and code, and how to take part.

- Edit text and links in `build.py` (`LINKS`, `CAPABILITIES`, `OPEN_SOURCE`, `ROADMAP`, `RESOURCES`, `INVOLVE`),
  then run `python3 website/build.py` to regenerate `index.html`.
- `LINKS["test_site"]` and `LINKS["contact"]` are empty until the test site is running and a contact address is
  chosen; the page shows "Coming soon" or points people to GitHub until then.
- The training, manuals, test programme and integrations review are shared documents. Make sure each is shared
  so that anyone with the link can view it, or replace the link with a public copy.
- Host it anywhere that serves static files, for example GitHub Pages (Settings, Pages, deploy the `/website`
  folder) or phaema.co.uk.
- Screenshots in `img/` show the fictional demonstration data.
- Fonts load from Google Fonts. For a site that makes no third-party requests, download Atkinson Hyperlegible
  and Bricolage Grotesque (both under the SIL Open Font License) into `website/fonts/` and replace the link.
