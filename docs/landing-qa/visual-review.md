# Landing page visual review

## QA captures

- `desktop-full.png` — full page at 1316 × 900 viewport.
- `reference-slice-01.png` through `reference-slice-06.png` — crops following the six provided reference scroll positions.
- `desktop-slices-contact.png` — overview of the six crops.
- `mobile-full.png` — full page at 390 × 844 viewport.
- `mobile-first-viewport.png` — first mobile viewport.

## Review notes and corrections

- Matched the 1236 px desktop content width, 40 px outer gutters, hero start position, 760 px feature panel, paired section layouts, dark palette, cream buttons, card borders, and six-column/four-column task grid rhythm.
- The first generated wordmark paths rendered as the wrong letters. Replaced them with an original horizontally extended ARGUS SVG wordmark and verified it at nav and footer sizes.
- Added explicit “Sample data” labels next to demo scoreboard and reproduction metrics.
- Cropped the six QA captures at the same content transitions as the supplied scroll references.
- Checked the 390 px mobile layout: columns stack, the run mock scales within the viewport, cards wrap, and the footer switches to a two-column layout.

## Deliberate visual differences

- All landscapes are original procedural illustrations. They use layered silhouettes, noise, a reduced palette, dither, and flower flecks; they are flatter than the reference's painterly 3D terrain.
- Benchmark names are text labels only. The page makes no customer or partnership claim and contains no third-party logos.
- Product imagery is static HTML/CSS mock UI. The page has no backend, scan action, authentication, API calls, or live run behavior.

The screenshots are visual review artifacts, not a pixel-diff score. The original reference assets were not reused, so an exact pixel/SSIM comparison would not be meaningful for the image areas.
