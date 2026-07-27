"""Sprite generator: valid GIF/PNG output, tier progression."""

import struct

from irongraph.sprites import (
    CYCLE,
    FRAME_CHEST,
    H_ROWS,
    W,
    _grid,
    apply_muscle_bulge,
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


def test_muscle_bulge_never_moves_or_erases_base_pixels():
    """Bulge overlays must only fill currently-blank (".") cells, with one
    deliberate exception: `core` may relabel an armor "T" pixel to the
    already-present shading tone "t" to draw ab definition. Nothing else
    in the base silhouette (armor shape, skin, bar, hands) ever moves."""
    rows = _grid(FRAME_CHEST)
    bulged = apply_muscle_bulge(rows, {r: 4 for r in
                                 ("shoulders", "chest", "back", "arms", "legs", "core")})
    for y, (base, new) in enumerate(zip(rows, bulged)):
        for x, ch in enumerate(base):
            if ch == "." or (ch == "T" and new[x] == "t"):
                continue
            assert new[x] == ch, f"row {y} col {x}: {ch!r} overwritten by {new[x]!r}"


def test_muscle_bulge_is_untrained_at_zero_tiers():
    rows = _grid(FRAME_CHEST)
    assert apply_muscle_bulge(rows, {}) == rows
    assert apply_muscle_bulge(rows, {"chest": 0, "arms": 0}) == rows


def test_muscle_bulge_grows_monotonically_with_tier():
    rows = _grid(FRAME_CHEST)

    def mass(tier: int) -> int:
        bulged = apply_muscle_bulge(rows, {r: tier for r in
                                    ("shoulders", "chest", "back", "arms", "legs", "core")})
        return sum(1 for row in bulged for ch in row if ch in "mq")

    masses = [mass(t) for t in range(5)]
    assert masses[0] == 0
    assert all(b > a for a, b in zip(masses, masses[1:]))


def test_muscle_bulge_regions_are_independent():
    """Training only legs must never add shoulder/chest/arm mass, and
    vice versa — each region's overlay is driven only by its own tier."""
    rows = _grid(FRAME_CHEST)
    legs_only = apply_muscle_bulge(rows, {"legs": 4})
    assert any("q" in row for row in legs_only)
    assert not any("m" in row for row in legs_only)

    arms_only = apply_muscle_bulge(rows, {"arms": 4})
    assert any("m" in row for row in arms_only)
    assert not any("q" in row for row in arms_only)


def test_generate_hero_with_muscle_tiers_differs_from_untrained(tmp_path):
    a, b = tmp_path / "untrained.gif", tmp_path / "jacked.gif"
    generate_hero(5, a, scale=3)
    generate_hero(5, b, scale=3, muscle_tiers={"chest": 4, "shoulders": 4, "arms": 4,
                                                "back": 4, "legs": 4, "core": 4})
    assert a.read_bytes() != b.read_bytes()


def test_png_still(tmp_path):
    out = tmp_path / "hero.png"
    generate_hero_still(30, out, scale=2)
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (W * 2, H_ROWS * 2)
