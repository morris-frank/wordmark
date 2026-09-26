#!/usr/bin/env python3
"""Pack a TAAG glyph capture (the unzipped taag-glyphs folder) into data/taag-glyphs.json.gz.

Usage: scripts/build-dataset.py PATH/TO/taag-glyphs-soilytix

One gzip JSON file, so the TUI can fetch the whole dataset in a single request.
Drops the per-font words.* check renders and the heights/widths tables (both
derivable from the glyphs) and keeps everything else from fonts.json.
"""

import gzip, json, sys
from pathlib import Path

src = Path(sys.argv[1])
index = json.loads((src / "fonts.json").read_text(encoding="utf-8"))
keep = ("name", "section", "colored", "compose", "upperOnly", "defaultLayoutJoins", "figletSource")
fonts, unrendered = [], []
for f in index["fonts"]:
    if not f["rendered"]:
        unrendered.append({"name": f["name"], "section": f["section"]})
        continue
    glyphs = json.loads((src / f["glyphs"]).read_text(encoding="utf-8"))["glyphs"]
    row = {k: f.get(k) for k in keep}
    if row["figletSource"]:
        row["figletSource"] = "data/" + row["figletSource"]
    row["glyphs"] = {
        c: ({"text": g["text"], "ansi": g["ansi"]} if g.get("ansi") else {"text": g["text"]}) for c, g in glyphs.items()
    }
    fonts.append(row)

out = {k: index[k] for k in ("source", "captured", "layout", "chars")}
out.update(fonts=fonts, unrendered=unrendered)
dest = Path(__file__).resolve().parent.parent / "data" / "taag-glyphs.json.gz"
raw = json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode()
dest.write_bytes(gzip.compress(raw, 9, mtime=0))  # mtime=0: rebuilds are byte-identical
print(f"{dest}: {len(fonts)} fonts, {len(unrendered)} unrendered, {dest.stat().st_size / 1e6:.1f} MB")
