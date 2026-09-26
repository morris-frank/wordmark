# The dataset

Every TAAG font's glyphs for A–Z, a–z and space, captured from
[patorjk.com/software/taag](https://patorjk.com/software/taag) ("Test all" view) on
2026-09-26. Each glyph was rendered on its own with Horizontal kerning = **Full**: the
raw glyph cell, with no kerning or smushing.

| Path | Holds |
|---|---|
| `taag-glyphs.json.gz` | One gzip JSON bundle, which the TUI loads. `fonts[]` has one row per rendered font: `name`, `section`, `colored`, `compose`, `upperOnly`, `defaultLayoutJoins`, `figletSource`, and `glyphs[char] = {text, ansi?}`. `unrendered[]` lists the 37 fonts that produced no output. |
| `sources/figlet/` | 363 raw FIGlet/TOIlet font files (`.flf`/`.tlf`) as embedded in TAAG. Use them with any figlet implementation for kerned or smushed layout and for any character, not only letters. |
| `sources/thedraw/` | The 36 TheDraw (`.tdf`) bundles TAAG loads, plus `font-registry.json` (font name → bundle). |

`text` is the characters only. `ansi` is 16-colour SGR escapes, present only on colour
fonts. `scripts/build-dataset.py` rebuilds the bundle from the unzipped capture
(`mise run dataset <folder>`).

## Coverage

- 1,342 fonts rendered glyphs; 37 produce no output.
- 1,013 are colour fonts (they carry `ansi`).
- 1,066 fonts have no distinct lowercase: their a–z are copies of A–Z (`upperOnly`).

## Composing

None of these formats has ligatures or context-dependent glyphs. Every letter is one
fixed block; only the join between neighbours varies.

- **Full width**, which the TUI does: glyph cells side by side, top-aligned, with the
  per-font gap `compose.sep` (0 for FIGlet, usually 1 column for TheDraw) and
  right-to-left order where `compose.rtl` is set (5 fonts). The composed `SOILYTIX` and
  `soilytix` match TAAG's own Full-width render exactly for 1,340 of 1,342 fonts, in
  text and ANSI. Unverified: Diet Cola, Filter. 39 fonts have no verified rule
  (`compose` is null) and are joined with no gap.
- **Default layout**: for 148 FIGlet/TOIlet fonts (`defaultLayoutJoins`), TAAG's default
  kerns or smushes neighbouring glyphs by rules in the font header. Those rules cannot
  be recovered from rendered glyphs, so for these fonts run a real figlet on the file in
  `sources/figlet/`.

## Licence

The fonts belong to their authors and are redistributed here as TAAG serves them.
Check an individual font's header before commercial use. The capture's structure and
the code in this repository are MIT.
