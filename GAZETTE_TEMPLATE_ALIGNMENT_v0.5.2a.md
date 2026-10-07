# v0.5.2a — Original Gazette Template Alignment

This hotfix aligns the renderer to the supplied canonical Blacktop Gazette artwork.

## Canonical artwork

The supported original template is:

- file: `assets/newspaper/newspaper_template.png`
- canonical size: **1103 × 1426**
- the renderer automatically normalises a scaled copy to this size before drawing

The artwork already contains:

- section headers
- standings rank numbers
- race-award labels/icons
- track-record labels
- Winner's Quote metadata labels
- rivalry stars
- achievement ticks
- sponsor decoration/ruled lines
- Prediction Results labels
- Big Move decoration

The renderer now fills those printed slots rather than repainting whole panels.

## Standings

- Championship races keep the original **FINAL STANDINGS** header.
- Exhibitions replace only the central title text with **RACE ORDER**, leaving the stars, border and surrounding artwork intact.
- Results are written beside the original printed **1–5** markers.
- The unused **6–10** markers are hidden with a texture sample from the same standings body, preserving the newspaper grain.
- No flat cream rectangle is painted over the panel.

## Exact row alignment

The template-specific row anchors are now explicit constants and regression-tested:

- standings: 5 rows
- race awards: 8 rows
- track records: 5 rows

Winner quote metadata and Prediction Results values are also shifted onto the original printed baselines.

## Lower-panel alignment

- Rivalry Watch uses the vertical spacing of the printed star rows.
- New Achievements follows the printed tick rows.
- Sponsor Offers uses the ruled-line spacing rather than bunching copy at the top.

## Scope

This is a visual/template hotfix only. Race simulation, progression, sponsors, championship scoring, parts and driver balance are unchanged.

The binary artwork is intentionally not bundled by this hotfix if the repository copy is omitted for asset-size reasons. Keep the supplied original PNG at the path above in the running installation.
