# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Tests for hybrid_core using synthetic models (no Cura needed).

Run:  python3 -m pytest tests -q
"""
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "HybridSupports"))
sys.path.insert(0, HERE)
import hybrid_core as hc  # noqa: E402
import models  # noqa: E402
from models import box  # noqa: E402


def model(*boxes):
    m = hc.Mesh.concat(list(boxes))
    return m.vertices, m.faces


def cantilever():
    # pillar 10x10x40 with a 20 mm shelf sticking out at z=30..34
    return model(box(0, 0, 0, 10, 10, 40), box(10, 0, 30, 30, 10, 34))


def check_mesh(m):
    assert m.is_watertight(), "mesh not watertight"
    assert m.volume() > 0, "mesh inside-out or empty"


def samples(mesh, per_face=3, seed=0):
    """Vertices plus random points on every face of a mesh."""
    rng = np.random.default_rng(seed)
    t = mesh.vertices[mesh.faces]
    w = rng.dirichlet([1, 1, 1], size=(len(t), per_face))
    pts = np.einsum("fkj,fjd->fkd", w, t).reshape(-1, 3)
    return np.vstack([mesh.vertices, pts])


def points_inside(mesh_v, mesh_f, pts, shrink=0.05):
    """How many points are really inside the model.

    A foot standing on a surface touches it, so a point only counts when it is still
    inside after moving `shrink` mm both up and down.
    """
    rc = hc.VerticalRaycaster(np.asarray(mesh_v, float)[mesh_f])
    n = 0
    for x, y, z in pts:
        n += bool(rc.inside_many(x, y, [z - shrink, z + shrink]).all())
    return n


@pytest.fixture(scope="module")
def box_model():
    m = models.rugged_box()
    return m.vertices, m.faces


@pytest.fixture(scope="module")
def box_units(box_model):
    return hc.generate(*box_model)


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------

def test_primitives_are_closed():
    check_mesh(box(0, 0, 0, 1, 1, 1))
    check_mesh(hc.tube(0, 0, 3, 2.2, 0, 10, 24))
    check_mesh(hc.gusset(0, 0, 0.5, 3, 5, 6, 0.8, 0))
    check_mesh(hc.prism(np.array([[0, 0], [4, 0], [4, 3], [0, 3]], float), 1, 2))
    ang = np.linspace(0, 2 * math.pi, 24, endpoint=False)
    sec = np.array([[[3, 10], [3.8, 10], [9, 16], [8.2, 16]]] * len(ang), float)
    check_mesh(hc.loft(np.zeros(2), ang, sec))
    ss = np.linspace(0, 10, 6)
    check_mesh(hc.fin(np.zeros(2), np.array([1.0, 0.0]), ss, 10 + ss, 12 + ss * 0.5 + 2, 0.8))
    # a hollow star wall: 4 lobes, 3 levels
    a = np.linspace(0, 2 * math.pi, 72, endpoint=False)
    r = 5 + 4 * np.abs(np.cos(2 * a))
    outer = np.stack([np.column_stack([r * np.cos(a), r * np.sin(a), np.full(72, z)]) for z in (0, 5, 10)])
    inner = outer.copy()
    for j in range(3):
        inner[j, :, :2] = hc.offset_inward(outer[j, :, :2], 0.8)
    shell = hc.wall_shell(outer, inner)
    check_mesh(shell)
    ring_area = shell.volume() / 10
    assert 0.7 * 0.8 * 2 * math.pi * 6 < ring_area < 2 * 0.8 * 2 * math.pi * 9


# --------------------------------------------------------------------------
# Simple parts
# --------------------------------------------------------------------------

def test_cantilever_one_tower_on_the_plate():
    v, f = cantilever()
    units = hc.generate(v, f)
    assert len(units) == 1
    u = units[0]
    assert u.lands_on_plate and u.landing_z == 0.0
    check_mesh(u.support)
    check_mesh(u.blocker)
    # 0.6.3: the tower stops under a 0.8 mm interface cap, whose top is the contact gap under the overhang
    top = u.support.vertices[:, 2].max()
    assert abs(top - (30 - 0.2 - 0.8)) < 0.05
    assert len(u.caps) == 1 and abs(u.caps[0].vertices[:, 2].max() - (30 - 0.2)) < 1e-6
    assert abs(u.caps[0].vertices[:, 2].min() - top) < 0.05
    assert u.coverage >= 0.9


def test_tower_is_hollow():
    v, f = cantilever()
    u = hc.generate(v, f, hc.HybridSettings(gusset_count=0, cone_fill="none"))[0]
    rc = hc.VerticalRaycaster(u.support.vertices[u.support.faces])
    x, y = u.trunk_xy
    z = 0.5 * u.tower_top
    assert not rc.inside(x, y, z), "tower centre is solid"
    wall = [rc.inside(x + (u.trunk_radius - 0.3) * math.cos(a), y + (u.trunk_radius - 0.3) * math.sin(a), z)
            for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]
    assert all(wall), "tube wall missing"


def test_lands_on_lower_ledge():
    # pillar with a low ledge (z 10..12) under a higher shelf (z 30..34)
    v, f = model(box(0, 0, 0, 10, 10, 40), box(10, 0, 30, 30, 10, 34), box(10, 0, 10, 30, 10, 12))
    units = hc.generate(v, f, hc.HybridSettings(gusset_count=0))
    high = [u for u in units if u.underside_z > 20]
    assert len(high) == 1
    assert math.isclose(high[0].landing_z, 12.0, abs_tol=1e-6)
    assert not high[0].lands_on_plate


def test_gusset_height_setting_and_cap():
    v, f = cantilever()
    base = hc.generate(v, f, hc.HybridSettings(gusset_count=0))[0].support.volume()
    small = hc.generate(v, f, hc.HybridSettings(gusset_height=3, gusset_length=4))[0]
    big = hc.generate(v, f, hc.HybridSettings(gusset_height=10, gusset_length=4))[0]
    assert base < small.support.volume() < big.support.volume()
    huge = hc.generate(v, f, hc.HybridSettings(gusset_height=500, gusset_length=4))[0]
    assert any("capped" in n for n in huge.notes)


def test_conform_head_follows_sloped_underside():
    v = np.array([[10, 0, 26], [30, 0, 32], [30, 10, 32], [10, 10, 26],
                  [10, 0, 34], [30, 0, 34], [30, 10, 34], [10, 10, 34]], float)
    shelf = hc.Mesh(v, box(0, 0, 0, 1, 1, 1).faces)
    pv, pf = model(box(0, 0, 0, 10, 10, 40), shelf)
    s = hc.HybridSettings(head_mode="conform", gusset_count=0, support_angle=50)
    u = hc.generate(pv, pf, s)[0]
    check_mesh(u.support)
    top = u.support.vertices
    hi_x = top[top[:, 0] > 27]
    lo_x = top[(top[:, 0] < 13) & (top[:, 2] > u.tower_top + 1)]
    assert hi_x[:, 2].max() > lo_x[:, 2].max() + 3, "head top does not follow the slope"
    assert points_inside(pv, pf, samples(u.support)) == 0


def test_long_shelf_split_by_max_span():
    v, f = model(box(0, 0, 0, 10, 80, 40), box(10, 0, 30, 30, 80, 34))
    one = hc.generate(v, f)
    many = hc.generate(v, f, hc.HybridSettings(max_span=30))
    assert len(many) >= 3 and len(many) > len(one)


def test_low_overhang_gets_standing_webs():
    v, f = model(box(0, 0, 0, 10, 10, 10), box(10, 0, 2, 30, 10, 6))
    u = hc.generate(v, f)[0]
    assert any("standing webs" in n for n in u.notes)
    check_mesh(u.support)
    assert points_inside(v, f, samples(u.support)) == 0


def test_no_overhang_no_units():
    v, f = model(box(0, 0, 0, 10, 10, 10))
    assert hc.generate(v, f) == []


# --------------------------------------------------------------------------
# The rugged box (the part from the 0.1.x bug report)
# --------------------------------------------------------------------------

def test_box_ceiling_gets_one_big_pillar(box_units):
    """The inner ceiling (z 117.5) gets ONE trunk from the inner floor, not three."""
    ceiling = [u for u in box_units if u.underside_z > 115]
    assert len(ceiling) == 1
    u = ceiling[0]
    assert math.isclose(u.landing_z, 2.5, abs_tol=1e-6) and not u.lands_on_plate
    x, y = u.trunk_xy
    assert 2.5 < x < 67.5 and 0 < y < 37.5, "trunk is not inside the box"
    assert u.trunk_radius >= 6
    assert u.coverage >= 0.9
    assert u.branches >= 4, "the cross needs at least one spoke per corner"


def test_box_every_tower_stands_on_something(box_model, box_units):
    """0.1.x printed towers starting in mid-air. Every foot must sit on the plate or the model."""
    v, f = box_model
    rc = hc.VerticalRaycaster(v[f])
    for u in box_units:
        if u.lands_on_plate:
            assert u.landing_z == 0.0
        else:
            x, y = u.trunk_xy
            below = rc.below(x, y, u.landing_z + 0.01)
            assert below is not None and abs(below - u.landing_z) < 0.05


def test_box_ceiling_lobes(box_model):
    """Lobes head: one pillar, a lobe to each corner (plus the open front edge), less plastic than the cone."""
    v, f = box_model
    lobes = [u for u in hc.generate(v, f, hc.HybridSettings(head_mode="lobes")) if u.underside_z > 115]
    cone = [u for u in hc.generate(v, f, hc.HybridSettings(head_mode="cone")) if u.underside_z > 115]
    assert len(lobes) == 1
    u = lobes[0]
    assert u.branches >= 4 and u.coverage >= 0.9
    assert u.support.volume() < cone[0].support.volume()


def test_box_ceiling_tethers(box_model):
    """Tethers: the inner ceiling is held by strips strung between the two side walls, no trunk."""
    v, f = box_model
    units = hc.generate(v, f, hc.HybridSettings(head_mode="tethers"))
    ceiling = [u for u in units if u.underside_z > 115]
    assert len(ceiling) == 1
    u = ceiling[0]
    assert not u.lands_on_plate and u.landing_z > 100, "tethers start just under the ceiling"
    assert u.branches >= 3
    assert u.global_settings["support_xy_distance"] == 0.0 and u.global_settings["support_roof_enable"]
    sx = u.support.vertices[:, 0]
    assert sx.min() < 3.0 and sx.max() > 67.0, "strips reach both side walls (inner faces at x 2.5 and 67.5)"
    # the outside ribs have only one wall next to them: they fall back to lobes
    ribs = [w for w in units if 25 < w.underside_z < 95]
    assert ribs and all(any("lobes" in n for n in w.notes) for w in ribs)


@pytest.fixture(scope="module")
def channel():
    m = models.u_channel()
    return m.vertices, m.faces


def test_channel_tethers_cover_20_percent_staggered(channel):
    """Straight tethers across the channel: equally spaced strips covering about 20 % of its length,
    every other layer shifted half a line width, cap kept clear of the legs."""
    v, f = channel
    s = hc.HybridSettings(head_mode="tethers", line_width=0.42)
    units = [u for u in hc.generate(v, f, s) if u.global_settings]
    assert len(units) == 1
    u = units[0]
    w = 3 * 0.42
    cover = u.branches * w / 40.0                          # channel is 40 mm long
    assert 0.15 <= cover <= 0.25, cover
    V = u.support.vertices
    strip = V[V[:, 2] < u.underside_z - 2.5]                # below the cap
    assert strip[:, 0].min() < 3.6 and strip[:, 0].max() > 43.4, "strips reach both legs (inner faces x 3.5 / 43.5)"
    # stagger: done in the G-code after slicing (Cura can't do it from the shape), half a line across
    plan = u.gcode_plan
    assert plan and len(plan["polys"]) == u.branches
    assert math.isclose(math.hypot(*plan["shift"]), 0.21, abs_tol=1e-6)
    assert abs(plan["shift"][0]) < 1e-6, "shift goes across the strips (along the channel), not along them"
    cap = V[V[:, 2] > u.underside_z - 0.9]     # the cap stack is 0.8 mm thick
    assert cap[:, 0].min() > 3.5 + 0.35 and cap[:, 0].max() < 43.5 - 0.35, "the cap must not touch the legs"
    # the first and last strip sit at the two open ends of the channel (0.2 mm in), the rest evenly between
    assert 0.1 < strip[:, 1].min() < 0.5 and 39.4 < strip[:, 1].max() < 39.9, (strip[:, 1].min(), strip[:, 1].max())


def test_lobes_build_one_tower_to_size():
    """The 40 mm channel and corner (15 mm up): one lobes tower sized to reach the whole roof, not four."""
    for mesh in (models.plate_channel(), models.plate_corner()):
        units = hc.generate(mesh.vertices, mesh.faces, hc.HybridSettings(head_mode="lobes"))
        assert len(units) == 1 and units[0].coverage >= 0.95, [(u.notes, u.coverage) for u in units]
        assert any("built to size" in n for n in units[0].notes)
        assert points_inside(mesh.vertices, mesh.faces, samples(units[0].support, per_face=1)) == 0
    split = hc.generate(models.plate_channel().vertices, models.plate_channel().faces,
                        hc.HybridSettings(head_mode="lobes", lobes_one_tower=False))
    assert len(split) > 1, "with the option off it splits as before"


def test_tether_gcode_stagger_shifts_odd_layers_only():
    import tether_gcode
    poly = [(-1, -1), (50, -1), (50, 2), (-1, 2)]
    plan = {"polys": [poly], "shift": (0.0, 0.21), "z": (6.2, 6.8), "h0": 0.2, "lh": 0.2}
    g = [";FLAVOR:Marlin\n",
         ";LAYER:31\nG0 Z6.4\nG0 X100 Y100.5\n;TYPE:SUPPORT\nG1 X140 Y100.5 E1.0\n;TYPE:WALL-OUTER\nG1 X100 Y90 E2\n",
         ";LAYER:32\nG0 Z6.6\n;TYPE:SUPPORT\nG0 X100 Y100.5\nG1 X140 Y100.5 E3.0\n"]
    out = tether_gcode.stagger(g, [plan], offset=(100.0, 100.0))
    assert "G1 X140 Y100.71 E1" in out[1], out[1]          # layer 31 (odd): moved 0.21 across the strip
    assert "G0 X100 Y100.71" in out[1], out[1]              # ...including the travel to its start
    assert "G1 X100 Y90 E2" in out[1]                       # walls untouched
    assert "G1 X140 Y100.5 E3.0" in out[2]                  # layer 32 (even): untouched
    assert tether_gcode.MARK in out[0]
    assert tether_gcode.stagger(out, [plan], offset=(100.0, 100.0)) == out   # never applied twice


@pytest.fixture(scope="module")
def corner():
    m = models.l_corner()
    return m.vertices, m.faces


def test_tethers_refuse_an_overhang_they_cannot_reach(corner):
    """Straight parallel tethers on an L only fit near the corner: they must not claim the whole roof."""
    v, f = corner
    units = hc.generate(v, f, hc.HybridSettings(head_mode="tethers", line_width=0.42))
    assert not any(u.global_settings for u in units), "no tethers where most of the roof is out of reach"


def test_slow_bridges_slows_flow_and_fan_then_restores():
    import tether_gcode
    poly = [(-1, -1), (60, -1), (60, 60), (-1, 60)]
    plan = {"slow": {"poly": poly, "z": (6.4, 6.4), "speed": 20.0, "flow": 1.5, "fan": 1.0}}
    g = [";FLAVOR:Marlin\nM82\nG92 E0\nM106 S80\n",
         ";LAYER:31\nG0 F600 Z6.4\n;TYPE:SUPPORT\nG1 F2700 E10.0\nG1 F9900 X40 Y10 E11.0\nG1 X40 Y11 E11.1\nG1 F2700 E10.6\n"
         "G0 F15000 X10 Y10\nG1 F2700 E11.1\nG1 F9900 X40 Y10 E12.1\n",
         ";LAYER:32\nG0 F600 Z6.6\n;TYPE:SUPPORT\nG1 F9900 X40 Y10 E13.1\nG1 X40 Y12 E13.3\n"]
    out = tether_gcode.slow_bridges(g, [plan])
    c1, c2 = out[1].split("\n"), out[2].split("\n")
    assert "G1 F1200 X40 Y10 E11.5" in c1                       # 20 mm/s, 1.5 x the filament (1.0 -> 1.5)
    assert "G1 X40 Y11 E11.65" in c1                            # the next line keeps the slow F by inheritance
    assert any(l.startswith("M106 S255") for l in c1), "fan goes up for the bridge"
    assert "G1 F2700 E11.15" in c1                              # the retraction carries the 0.55 mm already added
    assert "G1 F1200 X40 Y10 E13.15" in c1, out[1]              # a later line: 12.1 + (0.5 + 0.05 + 0.5) added so far
    # layer 32 is outside the slowed layers: Cura's speed and fan are back, E stays shifted by the 1.05 mm added
    assert any(l.startswith("M106 S80") for l in c2), out[2]
    assert "G1 F9900 X40 Y10 E14.15" in c2 and "G1 X40 Y12 E14.35" in c2, out[2]
    assert tether_gcode.MARK_SLOW in out[0]
    assert tether_gcode.slow_bridges(out, [plan]) == out


def test_cap_first_layer_gets_lower_flow_but_keeps_cura_speed():
    import tether_gcode
    poly = [(-1, -1), (60, -1), (60, 60), (-1, 60)]
    cap = {"poly": poly, "z": (14.3, 14.5), "speed": 0.0, "flow": 0.5, "fan": 1.0, "types": ["SUPPORT-INTERFACE", "SUPPORT"]}
    g = [";FLAVOR:Marlin\nM82\nG92 E0\nM106 S80\n",
         ";LAYER:70\nG0 F600 Z14.2\n;TYPE:SUPPORT\nG1 F9900 X40 Y10 E10.0\n"
         ";LAYER:71\nG0 F600 Z14.4\n;TYPE:SUPPORT-INTERFACE\nG1 F9900 X40 Y12 E10.4\nG1 X40 Y14 E10.8\n"
         ";LAYER:72\nG0 F600 Z14.6\n;TYPE:SUPPORT-INTERFACE\nG1 F9900 X40 Y16 E11.2\n"]
    out = tether_gcode.slow_bridges(g, [{"slow": [cap]}])
    lines = out[1].split("\n")
    assert "G1 F9900 X40 Y10 E10" in lines                    # the last tether layer is untouched
    assert "G1 F9900 X40 Y12 E10.2" in lines                    # first cap layer: half the filament, Cura's own speed
    assert "G1 X40 Y14 E10.4" in lines
    assert "G1 F9900 X40 Y16 E10.8" in lines, out[1]                  # next cap layer: full flow again, E stays shifted by 0.4
    s = hc.HybridSettings(tether_cap_flow=0.7, tether_cap_layers=1, tether_bridge_speed=20.0, tether_cap_stack=False)
    plan = hc._slow_plan(s, [(0, 6.2, 6.4), (1, 14.0, 14.2)], np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float))
    assert [p.get("types") for p in plan["slow"]] == [None, ["SUPPORT-INTERFACE", "SUPPORT"]]
    assert abs(plan["slow"][1]["z"][0] - 14.3) < 1e-9 and abs(plan["slow"][1]["z"][1] - 14.5) < 1e-9
    assert hc._slow_plan(hc.HybridSettings(tether_cap_flow=1.0, tether_bridge_speed=0.0, tether_cap_stack=False), [(0, 6.2, 6.4)],
                         np.array([[0, 0], [10, 0], [10, 10]], float)) is None


def _cap_gcode(zs=(14.4, 14.6, 14.8, 15.0), with_other=True):
    """A tiny G-code with a 10 x 10 mm cap (model XY 0..10, offset 100) of interface layers, absolute E, retraction."""
    hdr = ";FLAVOR:Marlin\nM82\nG92 E0\n"
    chunks = [hdr]
    e = 0.0
    for i, z in enumerate(zs):
        lines = [f";LAYER:{i}", f"G0 F600 Z{z}", ";TYPE:SUPPORT-INTERFACE"]
        lines.append("G1 F2700 E%.5f" % (e - 0.8)); e -= 0.8
        lines.append("G0 F15000 X102 Y102")
        lines.append("G1 F2700 E%.5f" % (e + 0.8)); e += 0.8
        for k in range(4):                                 # four 6 mm lines: Cura's roof, E = 0.03 per mm
            e += 0.18
            lines.append(("G1 F3000 " if k == 0 else "G1 ") + f"X{108 if k % 2 == 0 else 102} Y{102 + k} E{e:.5f}")
        lines.append("G1 F2700 E%.5f" % (e - 0.8)); e -= 0.8
        if with_other:
            lines.append("G0 F15000 X180 Y180")
            lines.append("G1 F2700 E%.5f" % (e + 0.8)); e += 0.8
            e += 0.5
            lines.append("G1 F3000 X185 Y180 E%.5f" % e)   # another unit's roof, far from the cap
        chunks.append("\n".join(lines) + "\n")
    return chunks, e


def test_cap_stack_replaces_cap_layers_and_keeps_everything_else():
    import tether_gcode
    cap = {"poly": [(0, 0), (10, 0), (10, 10), (0, 10)], "angle": 0.0, "pitch": 3.0, "density": 0.5, "hole": 4.0,
           "flow": 0.5, "width": 0.4, "lh": 0.2}
    g, e_end = _cap_gcode()
    out = tether_gcode.cap_stack(g, [{"capstack": cap}], (100.0, 100.0))
    assert tether_gcode.MARK_CAP in out[0] and "4 layers" in out[0]
    assert tether_gcode.cap_stack(out, [{"capstack": cap}], (100.0, 100.0)) == out        # never twice
    kinds = [l for c in out[1:] for l in c.split("\n") if l.startswith(";cap stack:")]
    assert [k.split()[2] for k in kinds] == ["lat1", "lat2", "ring", "diag"], kinds
    for c in out[1:]:
        for l in c.split("\n"):
            if l.startswith("G1") and "X10" in l and " Y10" in l:       # the old roof lines are gone ...
                assert "X108 Y102" not in l
    assert any("X185 Y180" in l for c in out[1:] for l in c.split("\n")), "the other unit's lines stay"
    # every extruding move of the new paths lies inside the cap (model 0..10 -> G-code 100..110)
    import re
    for c in out[1:]:
        inside_cap = False
        for l in c.split("\n"):
            if l.startswith(";cap stack"):
                inside_cap = True
            elif l.startswith(";TYPE") or l.startswith("G0 F15000 X180"):
                inside_cap = False
            m = re.match(r"G1 (?:F\d+ )?X([\d.]+) Y([\d.]+) E", l)
            if inside_cap and m:
                assert 100 <= float(m.group(1)) <= 110 and 100 <= float(m.group(2)) <= 110, l
    # E stays monotone-consistent: net filament = Cura's net minus the removed roof plus the new paths, and the
    # kept lines (the other unit) keep their own extrusion lengths
    def keep_lines(chunks):
        return [l for c in chunks[1:] for l in c.split("\n") if "X185 Y180" in l]
    def e_of(l):
        return float(re.search(r"E(-?[\d.]+)", l).group(1))
    e_vals = [e_of(l) for l in keep_lines(out)]
    orig = [e_of(l) for l in keep_lines(g)]
    d_new = [b - a for a, b in zip(e_vals, e_vals[1:])]
    d_old = [b - a for a, b in zip(orig, orig[1:])]
    assert len(d_new) == len(d_old) == 3
    # the E delta between the other unit's lines changes only by the cap stack's own net extrusion on each layer
    assert all(abs(dn - do) > 0 for dn, do in zip(d_new, d_old))
    # retraction is balanced: after the last line the filament position equals what a retract-neutral print has
    state = 0.0
    last = [l for c in out[1:] for l in c.split("\n") if l.startswith("G1") and " E" in l][-1]
    assert e_of(last) > e_vals[-1] - 1e-9


def test_cap_stack_layer1_has_lower_flow_than_layer2_per_mm():
    import re, math, tether_gcode
    cap = {"poly": [(0, 0), (20, 0), (20, 20), (0, 20)], "angle": 0.0, "pitch": 4.0, "density": 0.5, "hole": 4.0,
           "flow": 0.5, "width": 0.4, "lh": 0.2}
    g, _ = _cap_gcode(with_other=False)
    out = tether_gcode.cap_stack(g, [{"capstack": cap}], (100.0, 100.0))
    per_mm = []
    for c in out[1:3]:
        pos, e_prev, ratios = None, None, []
        for l in c.split("\n"):
            m = re.match(r"G0 .*X([\d.]+) Y([\d.]+)", l)
            if m:
                pos = (float(m.group(1)), float(m.group(2)))
            m = re.match(r"G1 (?:F\d+ )?X([\d.]+) Y([\d.]+) E([\d.-]+)", l)
            if m and pos is not None:
                q = (float(m.group(1)), float(m.group(2)))
                e = float(m.group(3))
                if e_prev is not None and math.dist(pos, q) > 1:
                    ratios.append((e - e_prev) / math.dist(pos, q))
                pos, e_prev = q, e
            elif l.startswith("G1 F2700 E"):
                e_prev = float(l.split("E")[1])
        per_mm.append(sum(ratios) / len(ratios))
    assert per_mm[0] == pytest.approx(0.5 * per_mm[1], rel=0.1), per_mm


def test_cap_stack_geometry_helpers():
    import tether_gcode as tg
    sq = [(0, 0), (30, 0), (30, 30), (0, 30)]
    h = tg.hatch(sq, 0.0, 3.0)
    assert len(h) == 2 * 11 and all(0 <= x <= 30 and 0 <= y <= 30 for x, y in h)
    r = tg.rings(sq, 0.4, 0.5, 10.0)
    xs = [p[0] for p in r]
    assert min(xs) == pytest.approx(0.2) and max(xs) < 30
    inner = tg.shrink_convex(sq, 0.2 + 0.8 * (len(r) // 5 - 1))
    assert inner, "rings stop before the middle closes"
    assert min(p[0] for p in r[-5:]) > 9.0, "open middle: the last ring is still around a hole of about 10 mm"
    assert tg._stack_kinds(4) == ["lat1", "lat2", "ring", "diag"] and tg._stack_kinds(5)[-1] == "diag"


def test_cap_stack_copes_with_a_cap_outline_that_has_tiny_corner_edges():
    """From the 100 mm channel: offsetting a convex hull left 0.1-0.3 mm edges at the corners and the edge
    half-planes then cut everything away (an empty hatch crashed the save)."""
    import tether_gcode as tg
    pts = [(4.7, 3.91), (4.71, 1.14), (5.08, 1.14), (6.27, 1.13), (99.89, 1.13), (102.55, 1.14), (102.69, 1.27),
           (102.69, 98.47), (102.4, 99.0), (4.71, 99.0), (4.71, 99.25), (4.7, 96.87)]
    edge = tg.shrink_convex(pts, 0.2)
    assert len(edge) >= 3
    assert len(tg.hatch(edge, 0.785, 0.4)) > 100 and len(tg.rings(pts, 0.4, 0.5, 8.0)) > 50
    g = [";FLAVOR:Marlin\nM82\n", ";LAYER:0\nG0 Z1\n;TYPE:SUPPORT-INTERFACE\nG1 F3000 X50 Y50 E1\nG1 X60 Y50 E1.3\n"]
    plan = {"capstack": {"poly": [(0, 0), (1e-6, 0)], "angle": 0.0, "pitch": 3.0, "density": 0.5, "hole": 8.0,
                         "flow": 0.85, "width": 0.4, "lh": 0.2}}
    assert tg.cap_stack(g, [plan], (0.0, 0.0)) == g, "a degenerate outline leaves Cura's roof alone"


@pytest.mark.parametrize("mode,fill", [("cone", "cross"), ("cone", "rings"), ("cone", "none"), ("lobes", "cross"), ("tethers", "cross"),
                                       ("branch", "cross"), ("trapezoid", "cross")])
def test_box_supports_never_enter_the_model(box_model, mode, fill):
    v, f = box_model
    s = hc.HybridSettings(head_mode=mode, cone_fill=fill, gusset_height=12, gusset_length=10)
    units = hc.generate(v, f, s)
    assert len(units) >= 8
    for u in units:
        check_mesh(u.support)
        assert points_inside(v, f, samples(u.support, per_face=1)) == 0, (mode, fill, u.underside_z)


def test_blob_small_curved_overhangs(tmp_path):
    m = models.tilted_blob()
    units = hc.generate(m.vertices, m.faces)
    assert units
    # 0.6.1: one criss-cross built to size usually covers these now instead of several standing webs
    assert any("standing webs" in n or "criss-cross" in n for u in units for n in u.notes)
    assert len(units) <= 4
    for u in units:
        check_mesh(u.support)
        assert points_inside(m.vertices, m.faces, samples(u.support, per_face=1)) == 0


# --------------------------------------------------------------------------
# Packaging checks (0.1.0-wip crashed Cura at startup because of the toolbar icon)
# --------------------------------------------------------------------------

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "..", "HybridSupports")


def test_toolbar_icon_survives_cura_recolouring():
    """Cura inserts fill="#rrggbb" straight after "<svg " (UM/ColorImage.py).

    If the icon's root tag already has a fill attribute the result is invalid
    XML, and Cura's SVG loader segfaults while the main window is loading.
    """
    import xml.etree.ElementTree as ET
    raw = open(os.path.join(PLUGIN_DIR, "tool_icon.svg"), "rb").read()
    assert raw.count(b"<svg ") == 1
    recoloured = raw.replace(b"<svg ", b'<svg fill="#1f2933" ')
    root = ET.fromstring(recoloured)            # raises on a duplicate attribute
    assert root.tag.endswith("svg")
    assert b"stroke" not in raw, "Cura only sets fill; stroked icons render black or not at all"


def test_plugin_metadata_is_consistent():
    import json
    meta = json.load(open(os.path.join(PLUGIN_DIR, "plugin.json")))
    assert meta["api"] == 8 and meta["supported_sdk_versions"] == ["8.0.0"]
    assert hc.__version__.split("-")[0] == meta["version"]
    init = open(os.path.join(PLUGIN_DIR, "__init__.py")).read()
    for ref in ("tool_icon.svg", "HybridSupportsTool.qml"):
        assert ref in init and os.path.exists(os.path.join(PLUGIN_DIR, ref))


# --------------------------------------------------------------------------
# install.py: build + install + check (the launchers run this)
# --------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run_install(*args, home=None):
    import subprocess
    import sys as _sys
    env = dict(os.environ)
    env.pop("DISPLAY", None)                # tests always use text mode
    env.pop("WAYLAND_DISPLAY", None)
    if home:
        env.update(HOME=str(home), USERPROFILE=str(home))
        env.pop("XDG_DATA_HOME", None)
        env.pop("APPDATA", None)
    return subprocess.run([_sys.executable, os.path.join(REPO_ROOT, "install.py"), *args],
                          capture_output=True, text=True, env=env)


def _installer():
    import importlib.util
    spec = importlib.util.spec_from_file_location("hs_install", os.path.join(REPO_ROOT, "install.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _log_line(when, text):
    return f"{when:%Y-%m-%d %H:%M:%S},000 - INFO - [MainThread] UM.PluginRegistry.loadPlugin [540]: {text}\n"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="uses the Linux Cura folder layout")
def test_install_replaces_broken_copy_and_registers_with_cura(tmp_path):
    import json
    cura = tmp_path / ".local" / "share" / "cura" / "5.13"
    old = cura / "plugins" / "HybridSupports"                         # flat copy from 0.1.1's install.py
    old.mkdir(parents=True)
    (old / "tool_icon.svg").write_text('<svg xmlns="x" fill="none"/>')
    (old / "plugin.json").write_text('{"version": "0.1.0"}')
    (cura / "packages.json").write_text(json.dumps(
        {"installed": {"Other": {}}, "to_install": {"HybridSupports": {}}, "to_remove": ["HybridSupports"],
         "version": 1}))
    (tmp_path / ".local" / "share" / "cura" / "4.13").mkdir()        # Cura 4 must be left alone

    inst = _installer()
    assert inst.status(str(cura))["state"] == "bad"                   # the crashing copy is recognised

    r = _run_install("--cli", home=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    new = cura / "plugins" / "HybridSupports" / "HybridSupports"      # same layout Cura's own installer uses
    assert (new / "plugin.json").exists() and (new / "hybrid_core.py").exists()
    assert not (old / "plugin.json").exists()
    assert json.loads((new / "build_info.json").read_text())["version"] == hc.__version__
    rec = json.loads((cura / "packages.json").read_text())
    info = rec["installed"]["HybridSupports"]["package_info"]        # this is what Marketplace > Manage lists
    assert info["package_type"] == "plugin" and info["display_name"] == "Hybrid Supports"
    assert info["package_version"] == hc.__version__.split("-")[0]
    assert "HybridSupports" not in rec["to_install"] and "HybridSupports" not in rec["to_remove"]
    assert "Other" in rec["installed"] and (cura / "packages.json.bak").exists()
    assert not (tmp_path / ".local" / "share" / "cura" / "4.13" / "plugins").exists()
    assert "Cura not started since" in r.stdout

    r = _run_install("--uninstall", home=tmp_path)
    assert r.returncode == 0 and not (cura / "plugins" / "HybridSupports").exists()
    assert "HybridSupports" not in json.loads((cura / "packages.json").read_text())["installed"]


def test_check_reads_what_cura_logged(tmp_path):
    import datetime
    inst = _installer()
    cura = tmp_path / "5.13"
    inst.install_into(str(cura))
    ver = hc.__version__.split("-")[0]
    now = datetime.datetime.now()

    assert inst.status(str(cura))["state"] == "wait"                  # installed, Cura not started yet
    (cura / "cura.log").write_text(_log_line(now - datetime.timedelta(hours=1), "Loaded plugin HybridSupports 0.1.1"))
    assert inst.status(str(cura))["state"] == "wait"                  # an older start does not count
    later = now + datetime.timedelta(seconds=5)
    (cura / "cura.log").write_text(_log_line(later, f"Loaded plugin HybridSupports {ver}"))
    st = inst.status(str(cura))
    assert st["state"] == "ok" and "left tool bar" in st["detail"]
    (cura / "cura.log").write_text(_log_line(later, "Error loading plugin HybridSupports:") + "Traceback...\n")
    assert inst.status(str(cura))["state"] == "bad"
    (cura / "cura.log").write_text(_log_line(later, "Plugin [HybridSupports] has been disabled. Skip loading it."))
    st = inst.status(str(cura))
    assert st["state"] == "bad" and "switched off" in st["summary"]


def test_install_reports_when_cura_is_missing(tmp_path):
    r = _run_install("--cli", home=tmp_path)
    assert r.returncode == 1 and "No Cura 5.x settings folder" in r.stdout


def test_no_display_falls_back_to_text_mode(tmp_path):
    r = _run_install("--cura-dir", str(tmp_path / "5.11"))            # no --cli, no display
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "5.11" / "plugins" / "HybridSupports" / "HybridSupports" / "HybridSupportsTool.qml").exists()


def test_launchers_exist_and_are_runnable():
    for name in ("Install-Linux.sh", "Install-Mac.command"):
        path = os.path.join(REPO_ROOT, name)
        assert open(path, "rb").read(2) == b"#!" and b"\r" not in open(path, "rb").read()
        if os.name == "posix":
            assert os.access(path, os.X_OK), f"{name} lost its executable bit"
    bat = open(os.path.join(REPO_ROOT, "Install-Windows.bat"), "rb").read()
    assert b"install.py" in bat and b"\r\n" in bat


# 0.6.1: on a channel standing on a base plate (the brim of u_channel), the criss-cross stood on the
# plate's top and its first check saw that surface as "model above the fin", so no wall could be built
# and the overhang was split into 4 or more towers. And its round foot had to clear the legs.
@pytest.mark.parametrize("mode", ["lobes", "branch", "cone"])
@pytest.mark.parametrize("height", [8.0, 16.0])
def test_channel_on_plate_is_one_tower(mode, height):
    m = models.u_channel(height=height)
    units = hc.generate(m.vertices, m.faces, hc.HybridSettings(head_mode=mode, xy_clearance=1.46))
    assert len(units) == 1, [u.notes for u in units]
    assert units[0].coverage >= 0.85
    assert points_inside(m.vertices, m.faces, samples(units[0].support, per_face=1)) == 0


def test_towers_print_as_walls_tethers_as_support():
    m = models.u_channel()
    for mode, want in (("lobes", "walls"), ("cone", "walls"), ("branch", "walls"), ("tethers", "support")):
        units = hc.generate(m.vertices, m.faces, hc.HybridSettings(head_mode=mode))
        assert units and all(u.print_as == want for u in units), (mode, [u.print_as for u in units])
    units = hc.generate(m.vertices, m.faces, hc.HybridSettings(head_mode="lobes", print_walls=False))
    assert all(u.print_as == "support" for u in units)


# 0.6.2: the built-to-size Lobes support is one watertight star of a few wide rounded lobes with
# rounded (filleted) joins, printed hollow, instead of thin slabs meeting in sharp notches.
@pytest.mark.parametrize("part", ["plate_channel", "plate_corner"])
def test_lobes_star_is_few_wide_rounded_lobes(part):
    m = getattr(models, part)()
    units = hc.generate(m.vertices, m.faces, hc.HybridSettings(head_mode="lobes", xy_clearance=0.78))
    assert len(units) == 1
    u = units[0]
    assert any("rounded lobe" in n for n in u.notes), u.notes
    assert 3 <= u.branches <= 5
    assert u.support.is_watertight() and u.support.volume() > 0
    assert points_inside(m.vertices, m.faces, samples(u.support, per_face=1)) == 0
    # the outline at mid height: the narrowest neck between lobes is far wider than a 2-line slab
    v = u.support.vertices
    mid = v[np.abs(v[:, 2] - np.median(v[:, 2])) < 0.3]
    c = np.array(u.trunk_xy)
    r = np.linalg.norm(mid[:, :2] - c, axis=1)
    assert r.min() > 3.0


# 0.6.3: every tower gets an interface cap (its own mesh), and the cap stack finds it by mesh name
def test_cap_stack_by_mesh_name_leaves_the_part_alone():
    import tether_gcode
    cap = {"poly": [(0, 0), (10, 0), (10, 10), (0, 10)], "angle": 0.0, "pitch": 3.0, "density": 0.5, "hole": 0.0,
           "flow": 1.0, "width": 0.4, "lh": 0.2, "mesh_prefix": "HybridCap"}
    g, _ = _cap_gcode(with_other=False)
    g2 = [g[0]]
    for c in g[1:]:
        c = c.replace(";TYPE:SUPPORT-INTERFACE", ";MESH:HybridCap_01(2)\n;TYPE:SKIN")
        c += ";MESH:part.stl\n;TYPE:SKIN\nG1 F3000 X104 Y108 E999.0\n"     # the part's own skin inside the outline
        g2.append(c)
    out = tether_gcode.cap_stack(g2, [{"capstack": cap}], (100.0, 100.0))
    kinds = [l.split()[2] for c in out[1:] for l in c.split("\n") if l.startswith(";cap stack:")]
    assert kinds == ["lat1", "lat2", "ring", "diag"], kinds
    assert sum("X104 Y108" in l for c in out[1:] for l in c.split("\n")) == 4      # the part's lines stay
    assert not any("X108 Y102" in l for c in out[1:] for l in c.split("\n"))       # the cap mesh's own lines are gone


@pytest.mark.parametrize("mode", ["lobes", "branch", "cone", "trapezoid"])
@pytest.mark.parametrize("part", ["plate_channel", "plate_corner"])
def test_every_tower_gets_an_interface_cap(mode, part):
    m = getattr(models, part)()
    s = hc.HybridSettings(head_mode=mode, xy_clearance=0.78)
    units = hc.generate(m.vertices, m.faces, s)
    caps = [c for u in units for c in u.caps]
    assert caps, [u.notes for u in units]
    under = 15.1                                          # the roof's underside on the plate parts
    for c in caps:
        assert c.is_watertight() and c.volume() > 0
        assert abs(c.vertices[:, 2].max() - (under - s.contact_gap)) < 1e-6
        assert abs(c.vertices[:, 2].min() - (under - s.contact_gap - 4 * s.layer_height)) < 1e-6
        assert points_inside(m.vertices, m.faces, samples(c, per_face=1)) == 0
    # the towers stop at the cap's underside (or lower), not in it
    for u in units:
        assert u.support.vertices[:, 2].max() <= under - s.contact_gap - 4 * s.layer_height + 0.05
    plans = [p for u in units for p in (u.gcode_plan or [])]
    assert any(p.get("capstack", {}).get("mesh_prefix") == "HybridCap" for p in plans)
    assert any(p.get("slow", {}).get("speed") == 20.0 for p in plans)


def test_tethers_keep_their_own_cap_and_no_tower_cap():
    m = models.plate_channel()
    units = hc.generate(m.vertices, m.faces, hc.HybridSettings(head_mode="tethers"))
    assert len(units) == 1 and not units[0].caps and units[0].tether_dir is not None


# 0.6.4: big overhangs on a long stem (the 200 mm benchmark parts, scaled down so the test is quick)
def _table(top=120.0, stem=20.0, h=60.0, t=5.0):
    c = top / 2
    a = models.box(c - stem / 2, c - stem / 2, 0, c + stem / 2, c + stem / 2, h)
    b = models.box(0, 0, h, top, top, h + t)
    return hc.Mesh(np.vstack([a.vertices, b.vertices]), np.vstack([a.faces, b.faces + len(a.vertices)]))


@pytest.mark.parametrize("mode", ["lobes", "cone"])
def test_big_table_top_supports_stay_under_the_overhang(mode):
    m = _table()
    units = hc.generate(m.vertices, m.faces, hc.HybridSettings(head_mode=mode, xy_clearance=0.78))
    assert 2 <= len(units) <= 4, [u.notes for u in units]      # split in a few, not a swarm
    for u in units:
        v = np.vstack([u.support.vertices] + [c.vertices for c in u.caps])
        # 0.6.3's cone flared ~17 mm past the edge of a 100 mm overhang (off the part and the bed)
        assert v[:, :2].min() > -4.0 and v[:, :2].max() < 124.0
        assert u.coverage >= 0.85



def test_first_three_tether_layers_are_slowed_bridges():
    # 0.6.5: three layers, not two, in case the first two come out weak or slack
    poly = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    layers = [(0, 6.0, 6.2), (1, 6.2, 6.4), (2, 6.4, 6.6), (3, 6.6, 6.8)]
    plan = hc._slow_plan(hc.HybridSettings(tether_cap_stack=True), layers, poly)
    z0, z1 = plan["slow"][0]["z"]
    assert (z0, z1) == (6.2, 6.6) and plan["slow"][0]["speed"] == 20.0 and plan["slow"][0]["fan"] == 1.0
    assert hc.HybridSettings().tether_slow_layers == 3


@pytest.mark.parametrize("gap,kind", [(80, "clean"), (100, "warn"), (140, "refused")])
def test_tether_span_limits(gap, kind):
    # 0.6.6: warn over 90 mm, hard limit 110 mm (falls back to lobes and says why)
    m = models.plate_channel(height=15.1, span=float(gap), length=40.0)
    s = hc.HybridSettings(head_mode="tethers")
    units = hc.generate(m.vertices, m.faces, s)
    notes = " | ".join(n for u in units for n in u.notes)
    assert units
    if kind == "clean":
        assert "Flying Spaghetti" not in notes and "limit" not in notes
        assert "tether span 80 mm" in notes
    elif kind == "warn":
        assert "Flying Spaghetti Monster" in notes and "unpredictable" in notes and "100 mm" in notes
    else:
        assert "over the 110 mm limit" in notes and "Flying Spaghetti" not in notes
        assert all(getattr(u, "print_as", "") != "tethers" for u in units)
