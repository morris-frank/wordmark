#!/usr/bin/env python3
"""wordmarks — type a word, browse it in 1,342 TAAG fonts, recoloured from a config.

Usage:
  wordmarks.py [WORD] [--font NAME] [--theme NAME] [--max-height N] [--config PATH]
  python3 <(curl -fsSL https://raw.githubusercontent.com/morris-frank/wordmark/main/wordmarks.py)

Keys: ↑/↓ font  PgUp/PgDn ±20  TAB/⇧TAB section  ←/→ style  ^T theme
      - + max height  0 any height  a–z A–Z space type  ⌫ delete
      ^Y copy text  ^A copy with colour  ESC quit

The dataset is data/taag-glyphs.json.gz next to this file, or else downloaded once
into the cache. The config is created on first run with the Soilytix palette.
Needs Python 3.11+ (tomllib) and a truecolour terminal; macOS or Linux.
"""

import argparse, colorsys, gzip, json, os, re, select, shutil, signal, subprocess, sys, termios, time, tomllib, tty
import urllib.request
from base64 import b64encode
from pathlib import Path

DATA_URL = "https://raw.githubusercontent.com/morris-frank/wordmark/main/data/taag-glyphs.json.gz"
APP = "wordmark"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / APP / "config.toml"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / APP / "taag-glyphs.json.gz"

DEFAULT_CONFIG = """\
# wordmark config. ←/→ cycles [[styles]] in order; TAB cycles [themes] in order.
# A colour is "#RRGGBB" or a table with one value per theme. Styles name colours
# from [colors] or give a hex directly. Delete this file to get the defaults back.
# Defaults: the Soilytix design system (Obsidian ink, Lime accent).

word = "maurice"
theme = "dark"
# max_height = 6        # only fonts at most this many lines tall; - and + change it live

# The Favourites section, first in the list (Tab gets back to it). Names match TAAG's,
# ignoring case; a name shared by several fonts (Elite, Nightmare) brings all of them.
favourites = [
  "Neurosis 1", "Nice", "NeurosisSim", "Nightmare", "News", "Neon", "LINE!Limpy",
  "KeWl", "Inertia", "Hobbes", "HgSierraT", "Fungi", "Friendship", "Font 64",
  "Font 34", "FocusPop", "File", "FBR", "FB-Gothic", "FB-CheapLine", "EMS", "Elusive",
  "Elite", "effekt", "DRG", "Donnow", "DC Font", "Darknesses", "Darklands", "Cfh 3",
  "Boxfight", "Bow Font", "Bone", "BoldMedium", "Blunder Smal", "BIG!Limpy",
  "BigOutline", "Ansiltr5", "Ansiltr4", "Ansiltr3", "Red Phoenix", "DOS Rebel",
  "Cybermedium", "Small Mono 999", "Small Braille", "Small Block", "Rebel", "Pagga",
  "Mono 9", "Coder Mini", "ANSI Shadow", "ANSI Regular", "ANSI Compact", "RubiFont",
  "miniwi", "BlurVision ASCII",
]

[themes.dark]
page = "#171916"
muted = "#CED0CF"

[themes.light]
page = "#F5F6F6"
muted = "#6D7471"

[colors]
lime = { dark = "#8EDE3D", light = "#384C10" }  # Lime is never text on light: green text there
ink = { dark = "#F0EEE1", light = "#29332E" }   # Obsidian on light, text-on-dark on dark
soil = "#423C2D"                                # dark anchor of the Lime ramp
gold = "#CA8407"                                # chart peers: gold, azure, rose
azure = "#2998ED"
rose = "#D76EB9"

# kind = "solid"          every glyph character in `color`
# kind = "vgrad"          rows blend `from` (top) -> `to` (bottom)
# kind = "ansi-hue"       colour fonts only: each ANSI colour takes the family nearest in hue;
#                         greys take `neutral`; shade is kept by blending from the page
# kind = "ansi-ramp"      colour fonts only: every ANSI colour on one ramp by lightness
# kind = "ansi-original"  colour fonts only: the font's own 16 colours (VGA RGB)
# Colour fonts cycle only the ansi-* styles; plain fonts only the others.

[[styles]]
name = "solid lime"
kind = "solid"
color = "lime"

[[styles]]
name = "solid ink"
kind = "solid"
color = "ink"

[[styles]]
name = "vgrad lime"
kind = "vgrad"
from = "soil"
to = "lime"

[[styles]]
name = "ansi hue"
kind = "ansi-hue"
families = ["lime", "gold", "azure", "rose"]
neutral = "ink"

[[styles]]
name = "ansi lime"
kind = "ansi-ramp"
color = "lime"

[[styles]]
name = "ansi original"
kind = "ansi-original"
"""

VGA = [
    (0, 0, 0),
    (170, 0, 0),
    (0, 170, 0),
    (170, 85, 0),
    (0, 0, 170),
    (170, 0, 170),
    (0, 170, 170),
    (170, 170, 170),
    (85, 85, 85),
    (255, 85, 85),
    (85, 255, 85),
    (255, 255, 85),
    (85, 85, 255),
    (255, 85, 255),
    (85, 255, 255),
    (255, 255, 255),
]
SGR = re.compile(r"\x1b\[([0-9;]*)m")
KEY = re.compile(r"\x1b\[[0-9;]*[A-Za-z~]|\x1bO.|\x1b|.", re.S)


# ---- data & config -----------------------------------------------------------
def load_fonts():
    local = Path(__file__).resolve().parent / "data" / "taag-glyphs.json.gz"
    path = local if local.is_file() else CACHE
    if not path.is_file():
        print(f"downloading the glyph dataset (2.7 MB) to {CACHE} …", file=sys.stderr)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(DATA_URL) as r:
            CACHE.write_bytes(r.read())
    return json.loads(gzip.decompress(path.read_bytes()))["fonts"]


def load_config(path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG)
    return tomllib.loads(path.read_text())


def hex_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))


def colour(cfg, ref, theme):
    """A [colors] name or a hex, resolved for the theme."""
    v = cfg.get("colors", {}).get(ref, ref)
    if isinstance(v, dict):
        v = v[theme]
    return hex_rgb(v)


# ---- composition -------------------------------------------------------------
def glyph_cells(g, ansi):
    """-> rows of (char, fg, bg); fg/bg are ANSI indices, or fg True for plain ink."""
    rows = []
    ansi = ansi and "ansi" in g  # a colour font's space glyph can be plain
    src = g["ansi"] if ansi else g["text"]
    for line in src[:-1].split("\n") if src.endswith("\n") else src.split("\n"):
        if not ansi:
            rows.append([(c, True if c != " " else None, None) for c in line])
            continue
        fg = bg = None
        cells, pos = [], 0
        for m in SGR.finditer(line):
            cells += [(c, fg, bg) for c in line[pos : m.start()]]
            pos = m.end()
            for p in (int(x) for x in (m.group(1) or "0").split(";") if x):
                if p == 0:
                    fg = bg = None
                elif 30 <= p <= 37:
                    fg = p - 30
                elif 90 <= p <= 97:
                    fg = p - 82
                elif 40 <= p <= 47:
                    bg = p - 40
                elif 100 <= p <= 107:
                    bg = p - 92
        cells += [(c, fg, bg) for c in line[pos:]]
        rows.append(cells)
    return rows


def compose(font, word, ansi):
    """TAAG "Full" layout: glyph cells side by side, top-aligned, per-font gap and direction."""
    rule = font["compose"] or {"sep": 0, "rtl": False}
    chars = [c for c in word if c in font["glyphs"]]
    if rule["rtl"]:
        chars.reverse()
    glyphs = [glyph_cells(font["glyphs"][c], ansi) for c in chars]
    if not glyphs:
        return []
    blank = (" ", None, None)
    h = max(len(g) for g in glyphs)
    widths = [max((len(r) for r in g), default=0) for g in glyphs]
    rows = []
    for r in range(h):
        row = []
        for k, g in enumerate(glyphs):
            cells = list(g[r]) if r < len(g) else []
            row += cells + [blank] * (widths[k] - len(cells))
            if k < len(glyphs) - 1:
                row += [blank] * rule["sep"]
        rows.append(row)
    while rows and all(c[0] == " " and c[2] is None for c in rows[-1]):
        rows.pop()  # drop blank bottom rows (text glyphs are padded to the font height)
    return rows


# ---- styles ------------------------------------------------------------------
def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def hue_dist(a, b):
    ha = colorsys.rgb_to_hsv(*(c / 255 for c in a))[0] * 360
    hb = colorsys.rgb_to_hsv(*(c / 255 for c in b))[0] * 360
    d = abs(ha - hb)
    return min(d, 360 - d)


def ansi_mapper(style, cfg, theme, page):
    kind = style["kind"]
    if kind == "ansi-original":
        return lambda i: VGA[i]
    if kind == "ansi-ramp":
        targets = [colour(cfg, style["color"], theme)] * 16
    else:
        fams = [colour(cfg, f, theme) for f in style["families"]]
        neutral = colour(cfg, style["neutral"], theme)
        targets = [
            neutral
            if colorsys.rgb_to_hsv(*(c / 255 for c in rgb))[1] < 0.2
            else min(fams, key=lambda f: hue_dist(f, rgb))
            for rgb in VGA
        ]
    out = []
    for i, rgb in enumerate(VGA):
        _, light, _ = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
        s = (light + max(rgb) / 255) / 2  # 0 black … 1 white; normal < bright, dark grey < light grey
        out.append(page if s == 0 else mix(page, targets[i], 0.25 + 0.75 * s))  # floor keeps faint shades visible
    return out.__getitem__


def paint(rows, style, cfg, theme):
    """-> rows of (char, fg_rgb|None, bg_rgb|None)."""
    page = hex_rgb(cfg["themes"][theme]["page"])
    kind = style["kind"]
    if kind.startswith("ansi"):
        f = ansi_mapper(style, cfg, theme, page)
        return [[(c, None if a is None else f(a), None if b is None else f(b)) for c, a, b in r] for r in rows]
    n = len(rows)
    out = []
    for i, r in enumerate(rows):
        if kind == "solid":
            fg = colour(cfg, style["color"], theme)
        else:
            fg = mix(colour(cfg, style["from"], theme), colour(cfg, style["to"], theme), i / (n - 1) if n > 1 else 1)
        out.append([(c, fg if a else None, None) for c, a, b in r])
    return out


def sgr(fg, bg):
    return f"\x1b[38;2;{fg[0]};{fg[1]};{fg[2]};48;2;{bg[0]};{bg[1]};{bg[2]}m"


def to_ansi(rows, page=None, width=None):
    """Truecolour escapes; page=None leaves uncoloured cells on the terminal default (for copying)."""
    lines = []
    for r in rows:
        s, prev = "", None
        for ch, fg, bg in r[:width]:
            if page is None:
                code = (
                    "\x1b[0m"
                    + (f"\x1b[38;2;{fg[0]};{fg[1]};{fg[2]}m" if fg and ch != " " else "")
                    + (f"\x1b[48;2;{bg[0]};{bg[1]};{bg[2]}m" if bg else "")
                )
            else:
                code = sgr(fg if fg and ch != " " else page, bg or page)
            if code != prev:
                s += code
                prev = code
            s += ch
        lines.append(s + ("\x1b[0m" if page is None else ""))
    return lines


# ---- clipboard ---------------------------------------------------------------
def copy(text):
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"], ["clip.exe"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text.encode(), check=False)
            return cmd[0]
    sys.stdout.write(f"\x1b]52;c;{b64encode(text.encode()).decode()}\x07")  # OSC 52: terminal clipboard, works over ssh
    return "OSC 52"


# ---- TUI ---------------------------------------------------------------------
def font_height(font):
    """Tallest glyph in lines, ignoring blank padding rows at the bottom."""
    h = 0
    for g in font["glyphs"].values():
        rows = g["text"].rstrip("\n").split("\n")
        while rows and not rows[-1].strip():
            rows.pop()
        h = max(h, len(rows))
    return h


class App:
    def __init__(self, fonts, cfg, word, font, theme, max_height=None):
        self.cfg, self.word = cfg, word
        by_name = {}
        for f in fonts:
            by_name.setdefault(f["name"].lower(), []).append(f)
        favs = cfg.get("favourites", [])
        missing = [n for n in favs if n.lower() not in by_name]
        seen = set()
        fav_fonts = [
            {**f, "section": "Favourites"}
            for n in favs
            for f in by_name.get(n.lower(), [])
            if id(f) not in seen and not seen.add(id(f))
        ]
        fonts = fav_fonts + fonts
        for f in fonts:
            f["height"] = font_height(f)
        self.all = fonts
        self.heights = sorted({f["height"] for f in fonts})
        self.max_height = None
        start = next((k for k, f in enumerate(fonts) if f["name"].lower() == font.lower()), 0) if font else 0
        self.set_filter(max_height, start)
        self.themes = list(cfg["themes"])
        self.theme = theme if theme in self.themes else self.themes[0]
        self.style = 0
        self.flash, self.flash_until = "", 0.0
        if missing:
            self.flash, self.flash_until = f"unknown favourite: {', '.join(missing)}", time.monotonic() + 4

    def set_filter(self, max_height, keep):
        """Show only fonts at most max_height lines tall; stay on font `keep` or the nearest one after it."""
        if max_height is not None and max_height < self.heights[0]:
            max_height = self.heights[0]  # never filter down to nothing
        self.max_height = max_height
        self.view = [k for k, f in enumerate(self.all) if max_height is None or f["height"] <= max_height]
        self.i = next((p for p, k in enumerate(self.view) if k >= keep), 0)

    def step_height(self, step):
        hs = self.heights
        cur = self.max_height if self.max_height is not None else hs[-1]
        if step < 0:
            nxt = next((h for h in reversed(hs) if h < cur), hs[0])
        else:
            nxt = next((h for h in hs if h > cur), None)
            nxt = None if nxt is None or nxt == hs[-1] else nxt  # the tallest step means no filter
        self.set_filter(nxt, self.view[self.i])

    @property
    def fonts(self):
        return [self.all[k] for k in self.view]

    @property
    def font(self):
        return self.all[self.view[self.i]]

    def styles(self):
        # Colour fonts get only the ANSI recolourings; plain fonts only the character styles.
        return [s for s in self.cfg["styles"] if s["kind"].startswith("ansi") == bool(self.font["colored"])]

    def current(self):
        ss = self.styles()
        st = ss[self.style % len(ss)]
        rows = compose(self.font, self.word, st["kind"].startswith("ansi"))
        return st, rows, paint(rows, st, self.cfg, self.theme)

    def draw(self):
        th = self.cfg["themes"][self.theme]
        page, muted = hex_rgb(th["page"]), hex_rgb(th["muted"])
        st, _, painted = self.current()
        cols, lines = shutil.get_terminal_size()
        avail = max(0, lines - 6)  # index + name lines, gaps, shortcut bar
        w = max((len(r) for r in painted), default=0)
        shown = painted[:avail]
        top = max(3, (lines - len(shown)) // 2)
        left = max(1, (cols - w) // 2 + 1)
        dim = f"\x1b[38;2;{muted[0]};{muted[1]};{muted[2]};48;2;{page[0]};{page[1]};{page[2]}m"

        def centre(row, text):
            text = text[:cols]
            return f"\x1b[{row};{max(1, (cols - len(text)) // 2 + 1)}H{dim}{text}"

        buf = [f"\x1b[0;48;2;{page[0]};{page[1]};{page[2]}m\x1b[2J"]
        for k, s in enumerate(to_ansi(shown, page, cols)):
            buf.append(f"\x1b[{top + k};{left}H{s}")
        if not shown:
            buf.append(centre(top, "type a word" if not self.word else f"no glyphs for {self.word!r} in this font"))
        cap = f" · ≤ {self.max_height} lines" if self.max_height is not None else ""
        index = self.flash if time.monotonic() < self.flash_until else f"{self.i + 1} / {len(self.view)}{cap}"
        crop = " · cropped" if w > cols or len(painted) > avail else ""
        buf.append(centre(top - 2, index))
        buf.append(
            centre(top + max(len(shown), 1) + 1, f"{self.font['name']} · {self.font['section']} · {st['name']}{crop}")
        )
        buf.append(
            centre(
                lines,
                "↑↓ font  ←→ style  tab section  ^T theme  - + height  0 any  "
                "a–z type  ⌫ delete  ^Y copy  ^A colour  esc quit",
            )
        )
        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    def jump_section(self, step):
        fonts = self.fonts
        n, sec, j = len(fonts), self.font["section"], self.i
        while fonts[j]["section"] == sec:
            j = (j + step) % n
            if j == self.i:
                return
        if step < 0:  # land on the first font of the previous section
            while fonts[(j - 1) % n]["section"] == fonts[j]["section"] and (j - 1) % n != self.i:
                j = (j - 1) % n
        self.i = j

    def key(self, k):
        n = len(self.view)
        moves = {"\x1b[A": -1, "\x1bOA": -1, "\x1b[B": 1, "\x1bOB": 1, "\x1b[5~": -20, "\x1b[6~": 20}
        if k in ("\x1b", "\x03"):
            return False
        if k in moves:
            self.i = (self.i + moves[k]) % n
        elif k in ("\x1b[C", "\x1bOC"):
            self.style += 1
        elif k in ("\x1b[D", "\x1bOD"):
            self.style -= 1
        elif k == "\x14":  # ^T
            self.theme = self.themes[(self.themes.index(self.theme) + 1) % len(self.themes)]
        elif k == "\t":
            self.jump_section(1)
        elif k == "\x1b[Z":  # shift-tab
            self.jump_section(-1)
        elif k == "-":
            self.step_height(-1)
        elif k in ("+", "="):
            self.step_height(1)
        elif k == "0":
            self.set_filter(None, self.view[self.i])
        elif k in ("\x7f", "\x08"):
            self.word = self.word[:-1]
        elif k == " " or (len(k) == 1 and k.isascii() and k.isalpha()):
            self.word += k
        elif k in ("\x19", "\x01"):
            _, rows, painted = self.current()
            text = (
                "\n".join("".join(c for c, _, _ in r).rstrip() for r in rows) + "\n"
                if k == "\x19"
                else "\n".join(to_ansi(painted)) + "\n"
            )
            via = copy(text)
            self.flash, self.flash_until = (
                f"copied {'text' if k == chr(0x19) else 'colour'} via {via}",
                time.monotonic() + 1.5,
            )
        return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("word", nargs="?")
    ap.add_argument("--font", help="start on this font (exact name, case-insensitive)")
    ap.add_argument("--theme")
    ap.add_argument("--max-height", type=int, help="only fonts at most this many lines tall")
    ap.add_argument("--config", type=Path, default=CONFIG, help=f"default {CONFIG}")
    a = ap.parse_args()
    cfg = load_config(a.config)
    app = App(
        load_fonts(),
        cfg,
        a.word if a.word is not None else cfg.get("word", "maurice"),
        a.font,
        a.theme or cfg.get("theme", "dark"),
        a.max_height or cfg.get("max_height"),
    )

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    signal.signal(signal.SIGWINCH, lambda *_: None)
    sys.stdout.write("\x1b[?1049h\x1b[?25l")
    try:
        tty.setraw(fd)
        running = True
        while running:
            app.draw()
            try:
                if not select.select([fd], [], [], 0.5)[0]:
                    continue
            except InterruptedError:
                continue
            for k in KEY.findall(os.read(fd, 1024).decode(errors="ignore")):
                if not app.key(k):
                    running = False
                    break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
