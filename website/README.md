# PHAEMA sales website

A single static page (`index.html`) aimed at councils: features, a sourced comparison with other estates
systems, a five-year cost-benefit analysis with a calculator, compliance status and indicative pricing.

- Edit figures, prices and text in `build.py` (the `CONTRACTS` and `TIERS` lists hold every number), then run
  `python3 website/build.py` to regenerate `index.html`.
- Host it anywhere that serves static files, for example GitHub Pages (Settings, Pages, deploy from the
  `/website` folder via an Action) or the council-facing domain.
- Screenshots in `img/` show the fictional demonstration data.
- Competitor facts are as at the date in `AS_OF`. Re-check them, and the sources linked on the page, before
  each publication.
- Fonts load from Google Fonts. For a site that sets no third-party requests, download Atkinson Hyperlegible
  and Bricolage Grotesque (both under the SIL Open Font License) into `website/fonts/` and replace the link.
