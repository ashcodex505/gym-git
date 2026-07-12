"""Sprite generator: valid GIF/PNG output, tier progression."""

import struct

from irongraph.sprites import (
    CYCLE,
    H_ROWS,
    W,
    _grid,
    generate_hero,
    generate_hero_still,
    tier_for_level,
)


def test_tier_ladder():
    assert tier_for_level(1) == "novice"
    assert tier_for_level(4) == "novice"
    assert tier_for_level(5) == "apprentice"
    assert tier_for_level(10) == "ironbound"
    assert tier_for_level(18) == "vanguard"
    assert tier_for_level(30) == "titan"
    assert tier_for_level(99) == "titan"


def test_frames_are_well_formed():
    for art in CYCLE:
        rows = _grid(art)
        assert len(rows) == H_ROWS
        assert all(len(r) == W for r in rows)
        # every frame must contain a bar and hands
        assert any("b" in r for r in rows)
        assert any("G" in r for r in rows)


def test_gif_output_is_valid_animated_gif(tmp_path):
    out = tmp_path / "hero.gif"
    generate_hero(12, out, scale=4)
    data = out.read_bytes()
    assert data[:6] == b"GIF89a"
    w, h = struct.unpack("<HH", data[6:10])
    assert (w, h) == (W * 4, H_ROWS * 4)
    assert data[-1:] == b"\x3b"                    # trailer
    assert b"NETSCAPE2.0" in data                  # loops forever
    assert data.count(b"\x21\xf9\x04") == len(CYCLE)  # one GCE per frame


def test_gif_differs_by_tier(tmp_path):
    a, b = tmp_path / "a.gif", tmp_path / "b.gif"
    generate_hero(1, a, scale=2)
    generate_hero(30, b, scale=2)
    assert a.read_bytes() != b.read_bytes()


def test_png_still(tmp_path):
    out = tmp_path / "hero.png"
    generate_hero_still(30, out, scale=2)
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (W * 2, H_ROWS * 2)
