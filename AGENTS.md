# AGENTS.md

Working agreement for this repository. `CLAUDE.md` is a symlink to this file.

## Golden rules

1. **`wordmarks.py` stays one stdlib-only file.** It must run as
   `python3 <(curl -fsSL …/wordmarks.py)` with nothing installed, so no third-party
   imports and no sibling modules. Python 3.11 is the floor (`tomllib`).
2. **Colours live in the config, never in code.** `DEFAULT_CONFIG` in `wordmarks.py` is
   the only place the default palette (Soilytix) is written down. The code holds only
   the ANSI semantics: the VGA palette and the style kinds.
3. **The dataset is generated.** `data/taag-glyphs.json.gz` comes from
   `scripts/build-dataset.py`, not from hand edits, and `data/sources/` stays
   byte-exact as captured (the hygiene hooks skip it).
4. **The download URL points at `main`.** Changing the bundle's path or format breaks
   every one-off `curl` run until `DATA_URL` matches, so change both together.

## Layout

| Path | Holds |
|---|---|
| `wordmarks.py` | The TUI: data loading, config, composition, styles, key handling. |
| `scripts/build-dataset.py` | Capture folder → `data/taag-glyphs.json.gz`. |
| `data/` | The bundle and the raw FIGlet/TheDraw sources; `data/README.md` describes them. |
| `brand/icon/` | The repository icon (`.svg` source, 1024 px `.png`). |

## Workflow

- `mise run setup`: toolchain, hooks, verify.
- `mise run run`: the TUI from this clone.
- `mise run check`: everything CI runs (the prek hooks: ruff, hygiene, gitleaks).

## Definition of done

`mise run check` is green, and the TUI was started once in a real terminal and driven
through the keys the change touches.
