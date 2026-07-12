"""Pixel-art hero sprites — pure Python, zero dependencies.

The IronGraph hero is a little lifter who performs an endless
clean-and-press. Gear evolves with your level tier:

    Novice     cloth        (gray)
    Apprentice leather      (brown)
    Ironbound  steel        (blue-silver)
    Vanguard   gilded steel (gold trim)
    Titan      ember-forged (glowing accent, aura)

Frames are ASCII pixel grids; the encoder writes a real animated GIF89a
(custom minimal LZW — the classic clear-code technique) so the sprite
works everywhere GitHub renders images. Also emitted as PNG frames for
crisp use in the dashboard if ever needed.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

# ---------------------------------------------------------------- art
# 22 columns × 24 rows. Characters:
# . transparent  H hair  S skin  E eye  M mouth
# T armor  t armor shade  C chest emblem  L legs  B boots
# b bar    P plate rim    p plate core   G hands/grip  A aura
W, H_ROWS = 22, 24

FRAME_DOWN = """
......................
......................
......HHHHHHHHH.......
.....HHHHHHHHHHH......
.....HSSSSSSSSSH......
.....SSESSSSSES.......
.....SSSSSSSSSS.......
......SSSSMMSS........
.......SSSSSS.........
......TTTTTTTT........
.....TTTTTTTTTT.......
....STtTCCCCtTTS......
....S.TTTTTTTT.S......
....S.TtTTTTtT.S......
....S.TTTTTTTT.S......
....G..LLLLLL..G......
PPbbGbbbbbbbbbbGbbPP..
Pp....LL...LLL...pP...
Pp....LL...LLL...pP...
PP....LL...LLL...PP...
......LL...LLL........
.....BBB...BBBB.......
....BBBB...BBBBB......
......................
"""

FRAME_CHEST = """
......................
......................
......HHHHHHHHH.......
.....HHHHHHHHHHH......
.....HSSSSSSSSSH......
.....SSESSSSSES.......
.....SSSSSSSSSS.......
......SSSSMMSS........
.......SSSSSS.........
PP....TTTTTTTT....PP..
Pp.G.TTTTTTTTTT.G.pP..
PPbbGbbbbbbbbbbGbbPP..
....SSTTCCCCTTSS......
.....STtTTTTtTS.......
......TTTTTTTT........
.......LLLLLL.........
......LL...LLL........
......LL...LLL........
......LL...LLL........
......LL...LLL........
......LL...LLL........
.....BBB...BBBB.......
....BBBB...BBBBB......
......................
"""

FRAME_OVERHEAD = """
PP.................PP.
PpbbGbbbbbbbbbbbGbbpP.
PP..G...........G..PP.
....S...........S.....
....S.HHHHHHHHH.S.....
....SHHHHHHHHHHHS.....
....SHSSSSSSSSSHS.....
.....SSESSSSSES.......
.....SSSSSSSSSS.......
......SSSSMMSS........
.......SSSSSS.........
......TTTTTTTT........
.....TTTTTTTTTT.......
.....TTTCCCCTTT.......
.....TtTTTTTTtT.......
......TTTTTTTT........
.......LLLLLL.........
......LL...LLL........
......LL...LLL........
......LL...LLL........
......LL...LLL........
.....BBB...BBBB.......
....BBBB...BBBBB......
......................
"""

# lift cycle: floor → chest → overhead → chest
CYCLE = [FRAME_DOWN, FRAME_CHEST, FRAME_OVERHEAD, FRAME_CHEST]
FRAME_DELAY_CS = 28  # centiseconds per frame

BASE_PALETTE = {
    "H": (61, 43, 31),      # hair
    "S": (235, 189, 155),   # skin
    "E": (20, 24, 30),      # eyes
    "M": (196, 132, 108),   # mouth shade
    "L": (43, 49, 60),      # pants
    "B": (28, 32, 40),      # boots
    "b": (150, 158, 170),   # bar
    "G": (235, 189, 155),   # hands = skin
    "P": (52, 58, 68),      # plate rim
    "p": (74, 82, 96),      # plate core
    "A": (247, 129, 102),   # aura (titan only)
}

# (min_level, tier_id, armor, armor_shade, emblem, plate_rim, plate_core, aura?)
TIERS = [
    (1,  "novice",     (108, 117, 125), (84, 92, 100),   (139, 148, 158), (52, 58, 68),   (74, 82, 96),   False),
    (5,  "apprentice", (146, 94, 58),   (110, 70, 44),   (196, 148, 90),  (72, 52, 40),   (110, 78, 56),  False),
    (10, "ironbound",  (142, 158, 178), (100, 114, 134), (88, 166, 255),  (60, 70, 84),   (96, 110, 128), False),
    (18, "vanguard",   (168, 178, 194), (118, 130, 148), (227, 179, 65),  (227, 179, 65), (150, 120, 50), False),
    (30, "titan",      (58, 50, 56),    (40, 34, 40),    (247, 129, 102), (247, 129, 102), (255, 177, 153), True),
]


def tier_for_level(level: int) -> str:
    tier = TIERS[0]
    for t in TIERS:
        if level >= t[0]:
            tier = t
    return tier[1]


def _palette_for(level: int) -> dict[str, tuple[int, int, int]]:
    tier = TIERS[0]
    for t in TIERS:
        if level >= t[0]:
            tier = t
    _, _, armor, shade, emblem, prim, pcore, _aura = tier
    pal = dict(BASE_PALETTE)
    pal["T"], pal["t"], pal["C"], pal["P"], pal["p"] = armor, shade, emblem, prim, pcore
    return pal


def _has_aura(level: int) -> bool:
    tier = TIERS[0]
    for t in TIERS:
        if level >= t[0]:
            tier = t
    return tier[7]


def _grid(art: str) -> list[str]:
    rows = [r for r in art.strip("\n").split("\n")]
    return [r.ljust(W, ".")[:W] for r in rows][:H_ROWS]


def _add_aura(rows: list[str]) -> list[str]:
    """Titan tier: one-pixel ember aura around every solid pixel."""
    out = [list(r) for r in rows]
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                continue
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < len(rows) and 0 <= xx < W and rows[yy][xx] not in ".A":
                    out[y][x] = "A"
                    break
    return ["".join(r) for r in out]


# ------------------------------------------------------------- GIF89a
def _lzw_encode(indices: list[int], min_code_size: int) -> bytes:
    """Minimal LZW: emit literals at (min+1) bits, clearing before the
    code table would force a width increase. Valid, dependency-free."""
    clear = 1 << min_code_size
    end = clear + 1
    width = min_code_size + 1
    max_literals_per_run = (1 << width) - clear - 2  # codes we may emit before width grows

    out = bytearray()
    acc = 0
    nbits = 0

    def emit(code: int) -> None:
        nonlocal acc, nbits
        acc |= code << nbits
        nbits += width
        while nbits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            nbits -= 8

    emit(clear)
    run = 0
    for idx in indices:
        if run >= max_literals_per_run:
            emit(clear)
            run = 0
        emit(idx)
        run += 1
    emit(end)
    if nbits:
        out.append(acc & 0xFF)
    return bytes(out)


def write_gif(path: Path, frames: list[list[int]], w: int, h: int,
              palette: list[tuple[int, int, int]], delay_cs: int) -> None:
    """frames = per-frame flat index lists; index 0 is transparent."""
    ncolors = max(4, 1 << (len(palette) - 1).bit_length())
    table = list(palette) + [(0, 0, 0)] * (ncolors - len(palette))
    depth = ncolors.bit_length() - 1

    buf = bytearray(b"GIF89a")
    buf += struct.pack("<HHBBB", w, h, 0x80 | (depth - 1) << 4 | (depth - 1), 0, 0)
    for r, g, b in table:
        buf += bytes((r, g, b))
    buf += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"  # loop forever
    min_code = max(2, depth)
    for fr in frames:
        buf += b"\x21\xf9\x04" + bytes((0x09,)) + struct.pack("<H", delay_cs) + b"\x00\x00"
        buf += b"\x2c" + struct.pack("<HHHH", 0, 0, w, h) + bytes((0,))
        data = _lzw_encode(fr, min_code)
        buf += bytes((min_code,))
        for i in range(0, len(data), 255):
            chunk = data[i:i + 255]
            buf += bytes((len(chunk),)) + chunk
        buf += b"\x00"
    buf += b"\x3b"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))


def write_png(path: Path, rgba_rows: list[list[tuple[int, int, int, int]]]) -> None:
    """Tiny PNG writer (for dashboard stills / debugging)."""
    h = len(rgba_rows)
    w = len(rgba_rows[0])
    raw = b"".join(b"\x00" + b"".join(bytes(px) for px in row) for row in rgba_rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data)))

    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(raw, 9)) +
           chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


# ------------------------------------------------------------ generate
def generate_hero(level: int, out_gif: Path, scale: int = 6) -> None:
    pal_map = _palette_for(level)
    chars = sorted(pal_map)
    palette = [(13, 17, 23)] + [pal_map[c] for c in chars]   # slot 0 = transparent
    index_of = {c: i + 1 for i, c in enumerate(chars)}

    frames = []
    for art in CYCLE:
        rows = _grid(art)
        if _has_aura(level):
            rows = _add_aura(rows)
        flat: list[int] = []
        for row in rows:
            line = [index_of.get(ch, 0) for ch in row]
            scaled = [i for i in line for _ in range(scale)]
            for _ in range(scale):
                flat.extend(scaled)
        frames.append(flat)
    write_gif(out_gif, frames, W * scale, H_ROWS * scale, palette, FRAME_DELAY_CS)


def generate_hero_still(level: int, out_png: Path, scale: int = 6) -> None:
    pal_map = _palette_for(level)
    rows = _grid(FRAME_OVERHEAD)
    if _has_aura(level):
        rows = _add_aura(rows)
    rgba = []
    for row in rows:
        line = [(*pal_map[ch], 255) if ch in pal_map else (0, 0, 0, 0) for ch in row]
        scaled = [px for px in line for _ in range(scale)]
        rgba.extend([scaled] * scale)
    write_png(out_png, rgba)


# ======================================================================
# Sprite library — the rest of the IronGraph pixel world.
# Each sprite: variable-size grid frames + its own palette. Same GIF
# pipeline as the hero.
# ======================================================================

GOLD = (227, 179, 65)
GOLD_D = (166, 124, 38)
WHITE = (240, 246, 252)
EMBER = (247, 129, 102)
EMBER_D = (196, 84, 60)
FLAME_Y = (255, 214, 102)
WOOD = (121, 82, 50)
PARCH = (222, 203, 164)
PARCH_D = (186, 163, 122)
INK = (74, 62, 46)
BROWN = (110, 74, 46)
BROWN_D = (78, 52, 33)
STEEL = (110, 122, 140)
STEEL_D = (74, 84, 100)
ROBE = (108, 92, 231)
ROBE_D = (76, 62, 176)
ORB = (121, 192, 255)

TROPHY_F1 = """
................
..*.............
.GGGGGGGGGGGGG..
.G.GGGGGGGGGG.G.
.G.GGGGGGGGGG.G.
.g.GGGGGGGGGG.g.
..g.GGGGGGGG.g..
....GGGGGGGG....
.....gGGGGg.....
.......GG.......
.......GG.......
......gGGg......
....GGGGGGGG....
....gggggggg....
................
................
"""
TROPHY_F2 = TROPHY_F1.replace("..*.", "....").replace(
    ".GGGGGGGGGGGGG..\n.G.GGGGGGGGGG.G.",
    ".GGGGGGGGGGGGG.*\n.G.GGGGGGGGGG.G.")

TROPHY = {"frames": [TROPHY_F1, TROPHY_F2], "delay": 45, "palette": {
    "G": GOLD, "g": GOLD_D, "*": WHITE}}

CHEST_CLOSED = """
..................
...BBBBBBBBBBBB...
..BbbbbbbbbbbbbB..
..BbbbbbGGbbbbbB..
..BBBBBBBBBBBBBB..
..BbbbbbGGbbbbbB..
..BbbbbbGgbbbbbB..
..BbbbbbbbbbbbbB..
..BBBBBBBBBBBBBB..
..................
"""
CHEST_OPEN = """
...BBBBBBBBBBBB...
..Bbbbbbbbbbbbb.B.
..BBBBBBBBBBBBBB..
..*..Y.YY.Y...*...
..BbbYYYYYYbbbbB..
..BbbbYGGYbbbbbB..
..BbbbbGGbbbbbbB..
..BbbbbbbbbbbbbB..
..BBBBBBBBBBBBBB..
..................
"""
CHEST_OPEN2 = CHEST_OPEN.replace("..*..Y.YY.Y...*...", ".....YY.Y.YY......")

CHEST = {"frames": [CHEST_CLOSED, CHEST_CLOSED, CHEST_OPEN, CHEST_OPEN2],
         "delay": 40, "palette": {
    "B": BROWN_D, "b": BROWN, "G": GOLD, "g": GOLD_D, "Y": FLAME_Y, "*": WHITE}}

SCROLL_F1 = """
................
.RRPPPPPPPPPPRR.
.RPPPPPPPPPPPPR.
.RPPllllPPPPPPR.
.RPPPPPPPPPPPPR.
.RPPllllllllPPR.
.RPPPPPPPPPPPPR.
.RPPllllllPPPPR.
.RPPPPPPPPPP*PR.
.RRPPPPPPPPPPRR.
................
"""
SCROLL_F2 = SCROLL_F1.replace("PP*P", "PPPP").replace(
    ".RPPllllPPPPPPR.", ".RPPllllPPP*PPR.")
SCROLL = {"frames": [SCROLL_F1, SCROLL_F2], "delay": 50, "palette": {
    "R": PARCH_D, "P": PARCH, "l": INK, "*": GOLD}}

COACH_F1 = """
................
......HHHH...O..
.....HHHHHH..W..
.....SSSSSS..W..
.....SESSES..W..
......SSSS...W..
.....RRRRRR..W..
....RRRRRRRRSW..
....RRRRRRRR.W..
....RrRRRRrR.W..
....RRRRRRRR.W..
.....RRRRRR..W..
.....RRRRRR..W..
....RRRRRRRR....
................
"""
COACH_F2 = COACH_F1.replace("...O..", "..OO..").replace("......HHHH...O..",
                                                        "......HHHH..OO..")
COACH = {"frames": [COACH_F1, COACH_F2], "delay": 45, "palette": {
    "H": (200, 205, 215), "S": (235, 189, 155), "E": (20, 24, 30),
    "R": ROBE, "r": ROBE_D, "W": WOOD, "O": ORB}}

FORGE_F1 = """
....................
.........f..........
........fff.........
.......ffFff........
......fFFFFf........
.......FFFF.........
........FF..........
...AAAAAAAAAAAAAA...
......AAAAAA........
......AAAAAA........
....AAAAAAAAAA......
...aaaaaaaaaaaa.....
....................
"""
FORGE_F2 = """
....................
..........f.........
.......f.fff........
......fffFFf........
.......fFFFFf.......
........FFFF........
........FF..........
...AAAAAAAAAAAAAA...
......AAAAAA........
......AAAAAA........
....AAAAAAAAAA......
...aaaaaaaaaaaa.....
....................
"""
FORGE_F3 = """
....................
........f...........
........ff.f........
......ffFFff........
......fFFFFf........
.......FFFF.........
........FF..........
...AAAAAAAAAAAAAA...
......AAAAAA........
......AAAAAA........
....AAAAAAAAAA......
...aaaaaaaaaaaa.....
....................
"""
FORGE = {"frames": [FORGE_F1, FORGE_F2, FORGE_F3], "delay": 22, "palette": {
    "f": FLAME_Y, "F": EMBER, "A": STEEL, "a": STEEL_D}}

SWORD_F1 = """
............
....*.......
.....B......
.....BB.....
......BB....
.......BB...
....G..BB...
.....GGgG...
......GG....
.....G.gG...
....G...G...
............
"""
SWORD_F2 = SWORD_F1.replace("....*.......", "............").replace(
    "......BB....", "...*..BB....")
SWORD = {"frames": [SWORD_F1, SWORD_F2], "delay": 50, "palette": {
    "B": (200, 210, 225), "G": GOLD, "g": GOLD_D, "*": WHITE}}

LIBRARY: dict[str, dict] = {"trophy": TROPHY, "chest": CHEST, "scroll": SCROLL,
                            "coach": COACH, "forge": FORGE, "sword": SWORD}


def _grid_free(art: str) -> list[str]:
    rows = art.strip("\n").split("\n")
    width = max(len(r) for r in rows)
    return [r.ljust(width, ".") for r in rows]


def generate_sprite(name: str, out_gif: Path, scale: int = 5) -> None:
    spec: dict = LIBRARY[name]
    pal_map = spec["palette"]
    chars = sorted(pal_map)
    palette = [(13, 17, 23)] + [pal_map[c] for c in chars]
    index_of = {c: i + 1 for i, c in enumerate(chars)}
    grids = [_grid_free(f) for f in spec["frames"]]
    w = max(len(g[0]) for g in grids)
    h = max(len(g) for g in grids)
    frames = []
    for rows in grids:
        rows = [r.ljust(w, ".") for r in rows] + ["." * w] * (h - len(rows))
        flat: list[int] = []
        for row in rows:
            line = [index_of.get(ch, 0) for ch in row]
            scaled = [i for i in line for _ in range(scale)]
            for _ in range(scale):
                flat.extend(scaled)
        frames.append(flat)
    write_gif(out_gif, frames, w * scale, h * scale, palette, spec["delay"])


def generate_all(level: int, outdir: Path) -> None:
    """Regenerate the hero (level-dependent) and the full sprite set."""
    generate_hero(level, outdir / "hero-sprite.gif")
    sprite_dir = outdir / "sprites"
    for name in LIBRARY:
        generate_sprite(name, sprite_dir / f"{name}.gif")
