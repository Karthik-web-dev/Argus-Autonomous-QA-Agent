# Argus landing page visual spec

## Reference inventory (1316 px wide screenshots)

- **Global frame:** near-black green-tinted background (`#0d100e`), content spans approximately x=40–1275 (1236 px); 40 px desktop gutters, 20–24 px on small screens. Main text is warm white, body copy muted gray, inactive text darker gray. Thin white borders at roughly 8% opacity.
- **Navigation:** top aligned at y≈8–40, wordmark on left, compact 13–14 px links on right. Primary button is pale cream (`#fdf6c0`), about 38 px tall, 5 px radius.
- **Hero:** starts around y≈215, heading 56–60 px with ~1.02 line height and -0.03em tracking; copy 17 px/26 px and max width ~600 px. Hero image panel begins around y≈500, spans 1236 px and ~760 px high, 14–16 px radius. Centered desktop mock is ~608 px wide. Logo row sits below with five even text marks.
- **Task grid:** centered ~54–56 px heading; small dark cards around 180×105 px, 8–10 px gutters. Six columns on first row and four left-aligned on second. Fade the outer columns with a horizontal mask.
- **Trust section:** two-column heading/intro, then a 1236×~525 px green-black gradient panel with two inner cards split evenly and ~12 px radius. Three caption cards below, ~405 px wide with 10 px gaps. Section headings 54–56 px.
- **Roles section:** two-column intro followed by a pair of ~612 px cards, 10 px gap; table on left and compact 4-column workers grid on right. Captions use 18 px titles and 14 px/22 px body.
- **Use cases:** 594×594 px illustration card on left; right heading around 56 px and ~28 px use-case list. Two-column layout reverses in the console band.
- **Console / MCP:** image mockups around 594×530 px and 14 px radius; opposite column heading 54–56 px. Section gaps 120–160 px.
- **Final CTA and footer:** centered CTA with 54–56 px heading; dotted halftone fade band above a bordered footer. Footer has six columns and a huge full-width wordmark. Bottom metadata is small and muted.
- **Responsive:** preserve semantic hierarchy and visual mockups; stack paired sections, scale type to 38–44 px tablet / 34–38 px mobile, maintain ~24 px outer gutters on tablet and 20 px on mobile. Grid tiles wrap or horizontally scroll.

## Implementation notes

Reference imagery is original procedural artwork (see `scripts/generate_backgrounds.py`); no external photo assets or third-party logos are used. All benchmark values are explicitly labeled as sample data. The recreation uses the dark palette, tight grotesque typography, cream CTA, thin cards, image-led section rhythm, and halftone footer band while replacing Deck-specific branding and content with Argus.
