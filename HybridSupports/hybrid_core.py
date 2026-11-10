# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""Hybrid tower support geometry core.

Pure numpy, no Cura imports, so it can be tested and profiled on its own.
Coordinates are Z-up millimetres with the build plate at Z = 0. The Cura
adapter (HybridSupportsTool.py) converts from Cura's Y-up scene.

Pipeline per model (0.2):
  1. Overhang faces (flatter than the support angle) are cut into small pieces and
     sampled on an XY grid.
  2. Every sample casts a ray down to the surface it would stand on. Samples that are
     inside the model, or barely above a surface, are dropped.
  3. Samples are grouped into support regions by XY neighbourhood AND height, so a
     ceiling, a rib and a hinge at different heights stay separate even where they
     touch in plan view.
  4. Each region gets ONE trunk (a hollow tube) where the column below is clear and the
     reach to the far edge of the region is smallest. The trunk gets fatter as the
     reach grows.
  5. Branch head: thin wedge-shaped fins rise from the trunk at no more than 45 degrees
     and fan out until every part of the overhang is within half a bridge gap of a fin.
     (The older solid heads, "trapezoid" and "conform", are still available.)
  6. Trunk, gussets and fins are tested against the model and shortened where they
     would run into it, keeping Cura's support X/Y distance.
  7. A region too wide for its height to reach at 45 degrees is split in two, and so on.
  8. A thin anti-overhang blocker over each region keeps Cura's own automatic support
     from filling the same space.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

__version__ = "0.6.6-wip"  # WORK IN PROGRESS: many features may be broken


# --------------------------------------------------------------------------
# Settings and results
# --------------------------------------------------------------------------

@dataclass
class HybridSettings:
    support_angle: float = 50.0      # deg from vertical, same meaning as Cura's
    head_mode: str = "lobes"         # "cone" (hollow cone), "lobes" (hollow star), "tethers", "branch" (slats), "trapezoid"/"conform" (solid)
    head_fraction: float = 0.20      # solid heads: the head takes at least this share of the gap
    max_flare_angle: float = 45.0    # deg from vertical for branches and head sides
    contact_gap: float = 0.2         # mm Z gap between the support top and the model
    line_width: float = 0.4          # support line width (mm)
    layer_height: float = 0.2
    wall_lines: int = 2              # trunk wall thickness in lines
    branch_lines: int = 3            # branch (fin) thickness in lines
    min_branch_thickness: float = 0.0  # raised by the Cura side when support walls are off (only used when print_walls is off)
    tower_cap: bool = True           # every non-tether support gets an interface cap under the overhang: the cap stack
                                     # (lattice, lattice, 50 % rings, 100 % top) printed as its own mesh on the tower tops
    tower_cap_bridge_speed: float = 20.0   # mm/s for the cap's first (lattice) layer, a bridge between the walls (0 = off)
    print_walls: bool = True         # towers, fins, lobes and cones print as hollow walls (a normal mesh: walls only, no infill,
                                     # no top/bottom), not as Cura support filled with the support pattern (zig-zag)
    tower_scale: float = 0.25        # trunk radius as a share of its reach
    min_tower_radius: float = 2.0    # mm (outer)
    max_tower_radius: float = 8.0    # mm (outer)
    lobes_one_tower: bool = True     # "lobes"/"branch": when one normal tower can't reach the whole overhang, build one hub-less criss-cross to size before splitting
    max_fit_radius: float = 30.0     # mm: the biggest trunk/foot that "built to size" may use
    min_fit_coverage: float = 0.85   # "built to size" is kept if it reaches at least this share of the overhang; else split
    tether_end_inset: float = 0.2    # tethers: the first and last strip sit this far in from the ends of the overhang
    cone_fill: str = "cross"         # inside the cone: "cross" (spokes), "rings" or "none"
    cone_wall_lines: int = 2         # the cone built to size: its wall, in lines (1 or 2)
    lobe_width: float = 0.0          # "lobes" head: lobe width in mm (0 = auto, from the trunk size)
    max_lobes: int = 8
    lobe_fillet: float = 3.0         # built-to-size star: inner corners between lobes are rounded at least this much (mm)
    tether_height: float = 10.0      # tethers/web: how far below the overhang they start
    tether_coverage: float = 0.20    # share of the void covered by tether strips (equally spaced)
    tether_width: float = 0.0        # width of each tether strip (0 = auto: 3 support line widths)
    tether_cap: float = 2.0          # cap under the overhang, on top of the tethers (printed as support roof)
    tether_xy: float = 0.0           # Cura Support X/Y Distance while tethers are used (0 = touch the walls)
    tether_max_span: float = 110.0   # longest wall-to-wall tether: HARD limit (0.6.6; was 120), longer falls back to lobes
    tether_warn_span: float = 90.0   # over this (up to the hard limit) it still builds, with a warning
    tether_dir: Optional[float] = None   # set by generate(): the direction the first tethered overhang used
    tether_slow_layers: int = 3      # tether-type heads: the first 3 layers are printed as slow, cooled bridges (G-code step; 0.6.5: was 2)
    tether_bridge_speed: float = 20.0   # mm/s for those layers (0 = leave the profile's support speed)
    tether_bridge_flow: float = 1.0     # flow multiplier for those layers
    tether_bridge_fan: float = 1.0      # part-cooling fan for those layers, 0..1
    tether_cap_stack: bool = True       # the cap is a 4-layer stack written in the G-code (see tether_gcode.cap_stack): lattice x2, open rings, diagonal
    tether_lattice_pitch: float = 3.0   # mm between lines of the two lattice layers
    tether_ring_density: float = 0.5    # fill of the ring layer (0.5 = line gap equal to the line width)
    tether_cap_hole: float = 0.0        # mm: leave an open middle this wide in the ring layer (0 = rings all the way in, a full 50 % layer)
    tether_cap_layers: int = 1          # tether-type heads: the first cap (roof) layers lie across the tethers ...
    tether_cap_flow: float = 0.85       # ... and are printed with this flow multiplier, so the bead fuses with the tether instead of squashing it (0 or 1 = off)
    tether_cap_speed: float = 0.0       # mm/s for those cap layers (0 = leave the profile's support speed)
    layer_height_0: float = 0.2      # Cura initial layer height (tether layers are built layer by layer)
    bridge_gap: float = 20.0         # longest bridge left for the printer (cross: spoke gaps, rings: spacing)
    low_gap: float = 6.0             # overhangs lower than this get standing webs, no trunk
    max_branches: int = 24
    max_span: float = 250.0          # regions wider than this are split; normally 1 pillar per region
    min_island_area: float = 1.0     # mm^2; smaller overhangs are ignored
    bed_tolerance: float = 0.3       # mm; surfaces this close to Z=0 count as the plate
    xy_clearance: float = 0.8        # sideways gap kept from the model (Cura's support X/Y distance)
    gusset_count: int = 4            # 0 disables gussets
    gusset_height: float = 6.0       # mm; capped at half the trunk height
    gusset_length: float = 5.0       # mm outward from the tube wall
    blocker: bool = True
    blocker_margin: float = 1.0      # mm XY margin around the region outline
    segments: int = 24               # tube / head resolution around the axis
    head_rings: int = 6              # conform head: radial sample rings


@dataclass
class Mesh:
    vertices: np.ndarray  # (N, 3) float
    faces: np.ndarray     # (M, 3) int

    @staticmethod
    def empty() -> "Mesh":
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))

    @staticmethod
    def concat(meshes: List["Mesh"]) -> "Mesh":
        meshes = [m for m in meshes if len(m.faces)]
        if not meshes:
            return Mesh.empty()
        verts, faces, off = [], [], 0
        for m in meshes:
            verts.append(m.vertices)
            faces.append(m.faces + off)
            off += len(m.vertices)
        return Mesh(np.vstack(verts), np.vstack(faces))

    def volume(self) -> float:
        v = self.vertices[self.faces]
        return float(np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0)

    def is_watertight(self) -> bool:
        """Every edge used exactly twice, once in each direction."""
        e = np.concatenate([self.faces[:, [0, 1]], self.faces[:, [1, 2]], self.faces[:, [2, 0]]])
        fwd = {tuple(x) for x in e.tolist()}
        if len(fwd) != len(e):
            return False
        return all((b, a) in fwd for a, b in fwd)


@dataclass
class SupportUnit:
    island_id: int
    support: Mesh             # printed as a Cura support mesh
    blocker: Optional[Mesh]   # used as a Cura anti-overhang mesh
    landing_z: float
    tower_top: float          # where the trunk ends and the head starts
    underside_z: float        # lowest point of the overhang it holds up
    lands_on_plate: bool
    notes: List[str] = field(default_factory=list)
    trunk_xy: Tuple[float, float] = (0.0, 0.0)
    trunk_radius: float = 0.0
    branches: int = 0
    coverage: float = 1.0     # share of the overhang within reach of the head
    region: Optional[np.ndarray] = None   # (N, 3) overhang sample points this unit holds up
    mesh_settings: Dict[str, object] = field(default_factory=dict)   # extra per-mesh Cura settings
    global_settings: Dict[str, object] = field(default_factory=dict)  # Cura settings this unit needs changed
    tether_dir: Optional[float] = None
    gcode_plan: Optional[object] = None   # a dict, or a list of dicts: what the Cura side changes in the G-code
    print_as: str = "support"            # "walls": a normal mesh printed as hollow walls; "support": a Cura support mesh
    caps: List[Mesh] = field(default_factory=list)   # interface cap pieces under the overhang (normal meshes, see _plan_caps)


# --------------------------------------------------------------------------
# Vertical ray casting with an XY bin grid
# --------------------------------------------------------------------------

class VerticalRaycaster:
    """Answers "surface below", "surface above" and "inside the model?" for vertical lines."""

    def __init__(self, tris: np.ndarray, target_cells: int = 160):
        self.tris = tris.astype(np.float64)
        xy = self.tris[:, :, :2]
        a, b, c = xy[:, 0], xy[:, 1], xy[:, 2]
        self.det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
        ok = np.abs(self.det) > 1e-12          # vertical (edge-on) triangles never hit a vertical ray
        idx = np.nonzero(ok)[0]
        lo, hi = xy.min(axis=1), xy.max(axis=1)
        self.origin = lo.min(axis=0) if len(lo) else np.zeros(2)
        extent = (hi.max(axis=0) - self.origin) if len(hi) else np.ones(2)
        self.cell = max(float(extent.max()) / target_cells, 1e-3)
        lo_c = np.floor((lo - self.origin) / self.cell).astype(int)
        hi_c = np.floor((hi - self.origin) / self.cell).astype(int)
        tmp: Dict[Tuple[int, int], List[int]] = {}
        for t in idx:
            for i in range(lo_c[t, 0], hi_c[t, 0] + 1):
                for j in range(lo_c[t, 1], hi_c[t, 1] + 1):
                    tmp.setdefault((i, j), []).append(t)
        self.bins = {k: np.asarray(v) for k, v in tmp.items()}

    def hits(self, x: float, y: float) -> Tuple[np.ndarray, np.ndarray]:
        """All crossings of the vertical line through (x, y): heights and up-facing flags."""
        key = (int(math.floor((x - self.origin[0]) / self.cell)),
               int(math.floor((y - self.origin[1]) / self.cell)))
        cand = self.bins.get(key)
        if cand is None:
            return np.zeros(0), np.zeros(0, dtype=bool)
        t = self.tris[cand]
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        det = self.det[cand]
        l1 = ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / det
        l2 = ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / det
        l3 = 1.0 - l1 - l2
        eps = -1e-9
        inside = (l1 >= eps) & (l2 >= eps) & (l3 >= eps)
        z = l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2]
        return z[inside], det[inside] > 0

    def below(self, x: float, y: float, z: float, eps: float = 1e-3) -> Optional[float]:
        zh, _ = self.hits(x, y)
        zh = zh[zh < z - eps]
        return float(zh.max()) if len(zh) else None

    def below_hit(self, x: float, y: float, z: float, eps: float = 1e-3):
        """(height, up_facing) of the first surface below, or (None, None)."""
        zh, up = self.hits(x, y)
        m = zh < z - eps
        if not m.any():
            return None, None
        k = np.argmax(np.where(m, zh, -np.inf))
        return float(zh[k]), bool(up[k])

    def above(self, x: float, y: float, z: float, eps: float = 1e-3) -> Optional[float]:
        zh, _ = self.hits(x, y)
        zh = zh[zh > z + eps]
        return float(zh.min()) if len(zh) else None

    def inside_many(self, x: float, y: float, zs) -> np.ndarray:
        """Winding test along +Z: works for closed meshes, including overlapping shells."""
        zh, up = self.hits(x + 1.37e-4, y + 0.71e-4)        # nudge off shared edges
        zs = np.atleast_1d(np.asarray(zs, float))
        if not len(zh):
            return np.zeros(len(zs), dtype=bool)
        sign = np.where(up, 1, -1)
        w = (sign[None, :] * (zh[None, :] > zs[:, None])).sum(axis=1)
        return w > 0

    def inside(self, x: float, y: float, z: float) -> bool:
        return bool(self.inside_many(x, y, [z])[0])


# --------------------------------------------------------------------------
# Small geometry helpers
# --------------------------------------------------------------------------

def convex_hull_2d(points: np.ndarray) -> np.ndarray:
    """Monotone chain; returns counter-clockwise hull without repeated end point."""
    pts = np.unique(np.round(points, 6), axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def polygon_area_centroid(poly: np.ndarray) -> Tuple[float, np.ndarray]:
    x, y = poly[:, 0], poly[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cr = x * yn - xn * y
    area = cr.sum() / 2.0
    if abs(area) < 1e-12:
        return 0.0, poly.mean(axis=0)
    cx = ((x + xn) * cr).sum() / (6 * area)
    cy = ((y + yn) * cr).sum() / (6 * area)
    return abs(area), np.array([cx, cy])


def offset_convex(poly: np.ndarray, d: float) -> np.ndarray:
    """Push a CCW convex polygon outwards by d (mitre joins)."""
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        e1, e2 = p1 - p0, p2 - p1
        n1 = np.array([e1[1], -e1[0]]) / (np.linalg.norm(e1) + 1e-12)
        n2 = np.array([e2[1], -e2[0]]) / (np.linalg.norm(e2) + 1e-12)
        bis = n1 + n2
        nb = np.linalg.norm(bis)
        if nb < 1e-9:
            out.append(p1 + n1 * d)
            continue
        bis /= nb
        cosh = max(float(np.dot(bis, n1)), 0.25)  # limit mitre spikes
        out.append(p1 + bis * d / cosh)
    return np.array(out)


def radial_profile(poly: np.ndarray, centre: np.ndarray, angles: np.ndarray) -> np.ndarray:
    """Distance from centre to a convex polygon's edge along each angle."""
    res = np.zeros(len(angles))
    n = len(poly)
    for k, th in enumerate(angles):
        d = np.array([math.cos(th), math.sin(th)])
        best = 0.0
        for i in range(n):
            a, b = poly[i] - centre, poly[(i + 1) % n] - centre
            e = b - a
            den = d[0] * e[1] - d[1] * e[0]
            if abs(den) < 1e-12:
                continue
            t = (a[0] * e[1] - a[1] * e[0]) / den
            s = (a[0] * d[1] - a[1] * d[0]) / den
            if t > 0 and -1e-9 <= s <= 1 + 1e-9:
                best = max(best, t)
        res[k] = best
    return res


def prism(poly: np.ndarray, z0: float, z1: float) -> Mesh:
    """Closed extrusion of a CCW polygon between z0 and z1."""
    n = len(poly)
    v = np.vstack([np.column_stack([poly, np.full(n, z0)]),
                   np.column_stack([poly, np.full(n, z1)]),
                   [[*poly.mean(axis=0), z0]], [[*poly.mean(axis=0), z1]]])
    cb, ct = 2 * n, 2 * n + 1
    f = []
    for i in range(n):
        j = (i + 1) % n
        f += [[i, j, n + j], [i, n + j, n + i]]   # side
        f += [[cb, j, i]]                         # bottom (faces down)
        f += [[ct, n + i, n + j]]                 # top (faces up)
    return Mesh(v, np.array(f))


def tube(cx: float, cy: float, r_out: float, r_in: float, z0: float, z1: float, seg: int) -> Mesh:
    """Closed hollow cylinder (annulus extruded)."""
    th = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    c, s = np.cos(th), np.sin(th)
    rings = []
    for r, z in ((r_out, z0), (r_out, z1), (r_in, z0), (r_in, z1)):
        rings.append(np.column_stack([cx + r * c, cy + r * s, np.full(seg, z)]))
    v = np.vstack(rings)
    ob, ot, ib, it = 0, seg, 2 * seg, 3 * seg
    f = []
    for i in range(seg):
        j = (i + 1) % seg
        f += [[ob + i, ob + j, ot + j], [ob + i, ot + j, ot + i]]   # outer wall
        f += [[ib + i, it + j, ib + j], [ib + i, it + i, it + j]]   # inner wall (faces in)
        f += [[ot + i, ot + j, it + j], [ot + i, it + j, it + i]]   # top ring
        f += [[ob + i, ib + j, ob + j], [ob + i, ib + i, ib + j]]   # bottom ring
    return Mesh(v, np.array(f))


def gusset(cx: float, cy: float, angle: float, r_start: float, length: float,
           height: float, thickness: float, z0: float) -> Mesh:
    """Triangular fin standing on z0, leaning on the tower wall."""
    d = np.array([math.cos(angle), math.sin(angle)])
    nrm = np.array([-d[1], d[0]]) * thickness / 2
    base = np.array([cx, cy]) + d * r_start
    p_in_bot = base
    p_out_bot = base + d * length
    p_in_top = base
    profile = [(p_in_bot, z0), (p_out_bot, z0), (p_in_top, z0 + height)]
    v = []
    for side in (-1, 1):
        for p, z in profile:
            q = p + side * nrm
            v.append([q[0], q[1], z])
    v = np.array(v)
    # 0,1,2 = side -1 ; 3,4,5 = side +1
    f = [[0, 2, 1], [3, 4, 5],                 # triangle faces
         [0, 1, 4], [0, 4, 3],                 # bottom
         [1, 2, 5], [1, 5, 4],                 # slope
         [2, 0, 3], [2, 3, 5]]                 # inner (against tube)
    m = Mesh(v, np.array(f))
    if m.volume() < 0:
        m.faces = m.faces[:, ::-1]
    return m


def loft(p, angles, sections) -> Mesh:
    """Sweep a cross-section around a vertical axis at p.

    sections: (K, M, 2) array of (radius, z) per angle, the same M-gon for every angle,
    listed counter-clockwise in the (r, z) plane. The result is a closed ring-shaped solid.
    """
    sec = np.asarray(sections, float)
    k_, m_ = sec.shape[0], sec.shape[1]
    v = np.empty((k_ * m_, 3))
    for k, a in enumerate(angles):
        d = np.array([math.cos(a), math.sin(a)])
        v[k * m_:(k + 1) * m_, :2] = p + sec[k, :, :1] * d
        v[k * m_:(k + 1) * m_, 2] = sec[k, :, 1]
    f = []
    for k in range(k_):
        k2 = (k + 1) % k_
        for i in range(m_):
            i2 = (i + 1) % m_
            a, b = k * m_ + i, k * m_ + i2
            c, d_ = k2 * m_ + i2, k2 * m_ + i
            f += [[a, b, c], [a, c, d_]]
    m = Mesh(v, np.array(f))
    if m.volume() < 0:
        m.faces = m.faces[:, ::-1]
    return m


def fin(p, u, ss, zb, zt, thickness: float) -> Mesh:
    """A vertical wedge-shaped web from p along unit vector u.

    ss: distances along u; zb/zt: bottom and top height at each distance.
    """
    n = np.array([-u[1], u[0]]) * thickness / 2
    v = []
    for s_, b_, t_ in zip(ss, zb, zt):
        c = p + u * s_
        for side in (n, -n):
            q = c + side
            v.append([q[0], q[1], b_])
            v.append([q[0], q[1], t_])
    v = np.array(v)
    k_ = len(ss)
    f = []
    for k in range(k_ - 1):
        lb, lt, rb, rt = 4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3
        lb2, lt2, rb2, rt2 = lb + 4, lt + 4, rb + 4, rt + 4
        f += [[lb, lb2, lt2], [lb, lt2, lt]]          # left face
        f += [[rb, rt2, rb2], [rb, rt, rt2]]          # right face
        f += [[lt, lt2, rt2], [lt, rt2, rt]]          # top
        f += [[lb, rb2, lb2], [lb, rb, rb2]]          # bottom
    e = 4 * (k_ - 1)
    f += [[0, 1, 3], [0, 3, 2]]                       # start cap
    f += [[e, e + 2, e + 3], [e, e + 3, e + 1]]       # end cap
    m = Mesh(v, np.array(f))
    if m.volume() < 0:
        m.faces = m.faces[:, ::-1]
    return m


# --------------------------------------------------------------------------
# Overhang sampling and support regions
# --------------------------------------------------------------------------

def overhang_triangles(tris: np.ndarray, s: HybridSettings) -> np.ndarray:
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    n = np.cross(e1, e2)
    area2 = np.linalg.norm(n, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        nz = np.where(area2 > 0, n[:, 2] / area2, 0.0)
    over = (-nz > math.cos(math.radians(s.support_angle))) & (tris[:, :, 2].min(axis=1) > s.bed_tolerance)
    return tris[over]


def _subdivide(tris: np.ndarray, max_edge: float, limit: int = 600000) -> np.ndarray:
    """Split triangles along their longest edge until every edge is <= max_edge."""
    done, todo = [], tris
    total = 0
    while len(todo):
        e = np.stack([np.linalg.norm(todo[:, 1] - todo[:, 0], axis=1),
                      np.linalg.norm(todo[:, 2] - todo[:, 1], axis=1),
                      np.linalg.norm(todo[:, 0] - todo[:, 2], axis=1)], axis=1)
        long_ = e.max(axis=1) > max_edge
        done.append(todo[~long_])
        total += int((~long_).sum())
        t = todo[long_]
        if total + 2 * len(t) > limit:
            done.append(t)
            break
        k = np.argmax(e[long_], axis=1)
        r = np.arange(len(t))
        a, b, c = t[r, k], t[r, (k + 1) % 3], t[r, (k + 2) % 3]
        m = (a + b) / 2
        todo = np.concatenate([np.stack([a, m, c], 1), np.stack([m, b, c], 1)])
    return np.concatenate(done) if done else tris[:0]


def island_xy_area(t: np.ndarray) -> float:
    a = t[:, 1, :2] - t[:, 0, :2]
    b = t[:, 2, :2] - t[:, 0, :2]
    return float(0.5 * np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum())


@dataclass
class Region:
    pts: np.ndarray       # (N, 3) x, y, underside z
    land: np.ndarray      # (N,) surface below each point
    cell: float


def find_regions(tris: np.ndarray, rc: VerticalRaycaster, s: HybridSettings) -> List[Region]:
    over = overhang_triangles(tris, s)
    if not len(over):
        return []
    xy = over[:, :, :2].reshape(-1, 2)
    ext = xy.max(axis=0) - xy.min(axis=0)
    area = island_xy_area(over)
    c = float(np.clip(math.sqrt(max(area, 1.0) / 40000.0), 0.6, 2.0))
    pieces = _subdivide(over, c * 0.7)
    cen = pieces.mean(axis=1)
    origin = xy.min(axis=0) - c
    ij = np.floor((cen[:, :2] - origin) / c).astype(np.int64)
    order = np.lexsort((cen[:, 2], ij[:, 1], ij[:, 0]))
    ij, cen = ij[order], cen[order]

    # nodes: per grid cell, one node per separate height
    nodes_xy, nodes_z, nodes_ij = [], [], []
    start = 0
    n = len(cen)
    z_split = c + 1.0
    while start < n:
        end = start + 1
        while end < n and ij[end, 0] == ij[start, 0] and ij[end, 1] == ij[start, 1]:
            end += 1
        g0 = start
        for k in range(start + 1, end + 1):
            if k == end or cen[k, 2] - cen[k - 1, 2] > z_split:
                grp = cen[g0:k]
                nodes_xy.append(grp[:, :2].mean(axis=0))
                nodes_z.append(grp[:, 2].min())
                nodes_ij.append(ij[start])
                g0 = k
        start = end
    nodes_xy = np.array(nodes_xy)
    nodes_z = np.array(nodes_z)
    nodes_ij = np.array(nodes_ij)

    # keep nodes with open space below them, record where they would stand
    min_gap = max(3 * s.layer_height, 0.8)
    keep, land = [], []
    for k in range(len(nodes_z)):
        x, y, z = nodes_xy[k, 0], nodes_xy[k, 1], nodes_z[k]
        hz, up = rc.below_hit(x, y, z - 0.01)
        if hz is not None and not up:          # the space under this face is inside the model
            continue
        lz = hz if hz is not None else 0.0
        if lz <= s.bed_tolerance:
            lz = 0.0
        if z - lz < min_gap or rc.inside(x, y, z - 0.05):
            continue
        keep.append(k)
        land.append(lz)
    if not keep:
        return []
    keep = np.array(keep)
    pts = np.column_stack([nodes_xy[keep], nodes_z[keep]])
    land = np.array(land)
    cij = nodes_ij[keep]

    # connect neighbouring nodes at a similar height
    parent = list(range(len(pts)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    cells: Dict[Tuple[int, int], List[int]] = {}
    for k, (i, j) in enumerate(cij.tolist()):
        cells.setdefault((i, j), []).append(k)
    dz_link = 1.2 * c + 0.4
    for (i, j), ks in cells.items():
        for di in (0, 1):
            for dj in (-1, 0, 1):
                if di == 0 and dj <= 0:
                    continue
                other = cells.get((i + di, j + dj))
                if not other:
                    continue
                for a in ks:
                    for b in other:
                        if abs(pts[a, 2] - pts[b, 2]) <= dz_link:
                            ra, rb = find(a), find(b)
                            if ra != rb:
                                parent[ra] = rb
    groups: Dict[int, List[int]] = {}
    for k in range(len(pts)):
        groups.setdefault(find(k), []).append(k)
    out = []
    for g in groups.values():
        g = np.array(g)
        if len(g) * c * c >= s.min_island_area:
            out.append(Region(pts[g], land[g], c))
    return out


def split_region(r: Region) -> List[Region]:
    """Cut a region in two across its longest direction."""
    xy = r.pts[:, :2] - r.pts[:, :2].mean(axis=0)
    if len(xy) < 4:
        return [r]
    _, _, vt = np.linalg.svd(xy, full_matrices=False)
    proj = xy @ vt[0]
    m = proj <= np.median(proj)
    if m.all() or (~m).all():
        return [r]
    parts = [Region(r.pts[m], r.land[m], r.cell), Region(r.pts[~m], r.land[~m], r.cell)]
    for q in parts:
        q.capped = getattr(r, "capped", False)
    return parts


# --------------------------------------------------------------------------
# One support unit: trunk + head
# --------------------------------------------------------------------------

class _TopLookup:
    """Underside height (minus the contact gap) near an XY point, from the region samples."""

    def __init__(self, r: Region, gap: float):
        self.c = r.cell
        self.o = r.pts[:, :2].min(axis=0) - 2 * r.cell
        self.d: Dict[Tuple[int, int], float] = {}
        for x, y, z in r.pts:
            key = (int((x - self.o[0]) // self.c), int((y - self.o[1]) // self.c))
            self.d[key] = min(self.d.get(key, 1e9), z - gap)

    def __call__(self, x: float, y: float) -> Optional[float]:
        i, j = int((x - self.o[0]) // self.c), int((y - self.o[1]) // self.c)
        best = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                v = self.d.get((i + di, j + dj))
                if v is not None and (best is None or v < best):
                    best = v
        return best


def _place_trunk(r: Region, rc: VerticalRaycaster, s: HybridSettings, tan_f: float, tip_h: float, fit: bool = False):
    """Best trunk position: clear column, lowest reach. Returns a dict or None, plus the best miss.

    fit: size the trunk to the overhang instead of from tower_scale: as wide as it must be for the head
    to reach every point within the flare angle (up to max_fit_radius), so one tower covers it."""
    xy, z = r.pts[:, :2], r.pts[:, 2]
    cen = xy.mean(axis=0)
    step = max(1, len(xy) // 60)
    cands = [cen[None], xy[::step]]
    hull = convex_hull_2d(xy)
    if len(hull) >= 3:                     # also just outside the overhang (e.g. a rib on a wall)
        mids = (hull + np.roll(hull, -1, axis=0)) / 2
        for off in (s.min_tower_radius + s.xy_clearance + 0.3,
                    0.5 * (s.min_tower_radius + s.max_tower_radius) + s.xy_clearance,
                    s.max_tower_radius + s.xy_clearance):
            cands += [offset_convex(hull, off), offset_convex(mids if len(mids) >= 3 else hull, off)]
    cands = np.vstack(cands)
    dist = np.linalg.norm(xy[None, :, :] - cands[:, None, :], axis=2)
    reach = dist.max(axis=1)
    zmin = float(z.min())
    gap = s.contact_gap
    best_miss = None
    ring = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    tried = 0
    probe = zmin - 0.02
    for k in np.argsort(reach):
        p = cands[k]
        if fit:
            # Built to size: each wall of the criss-cross stands on the floor along its own line as far
            # out as it must, so only a small foot round the centre has to be clear. (0.6.0 asked for a
            # whole circle as wide as the reach, which hit the legs of a channel and split the overhang
            # into 2, 4 ... towers.)
            hz, up = rc.below_hit(p[0], p[1], probe)
            if hz is not None and not up:
                continue
            z_c = 0.0 if hz is None or hz <= s.bed_tolerance else hz
            rt0 = max(s.min_tower_radius, (s.wall_lines + 1) * s.line_width)
            need = float(np.clip(reach[k] - tan_f * (zmin - gap - tip_h - z_c), rt0, s.max_fit_radius))
            r_ok = _clear_foot(rc, p, z_c, probe, need, rt0, s)
            tried += 1
            if r_ok is not None and _sees(rc, p, xy, zmin - gap - 0.3, s.xy_clearance):
                return {"p": p, "rt": r_ok, "rt_need": need, "z_land": z_c, "z_h0": z_c, "dist": dist[k]}, None
            if tried >= 40:
                break
            continue
        rt = float(np.clip(s.tower_scale * reach[k], s.min_tower_radius, s.max_tower_radius))
        rt = max(rt, (s.wall_lines + 1) * s.line_width)
        pts = [p] + [p + (rt + s.xy_clearance) * np.array([math.cos(a), math.sin(a)]) for a in ring]
        lands = []
        bad = False
        for q in pts:
            hz, up = rc.below_hit(q[0], q[1], probe)
            if hz is not None and not up:      # inside the model here
                bad = True
                break
            lands.append(hz if hz is not None else 0.0)
        tried += 1
        if not bad:
            bad = not _sees(rc, p, xy, zmin - gap - 0.3, s.xy_clearance)
        if not bad and max(lands) - min(lands) <= 1.0:
            z_land = max(lands)
            if z_land <= s.bed_tolerance:
                z_land = 0.0
            need = z - gap - tip_h - np.maximum(0.0, dist[k] - rt) / tan_f
            z_h0 = float(need.min())
            if z_h0 >= z_land:
                return {"p": p, "rt": rt, "z_land": z_land, "z_h0": z_h0, "dist": dist[k]}, None
            miss = {"p": p, "rt": rt, "z_land": z_land, "need": need, "dist": dist[k]}
            if best_miss is None or z_h0 - z_land > best_miss["score"]:
                miss["score"] = z_h0 - z_land
                best_miss = miss
        if tried >= 40:
            break
    return None, best_miss


def _clear_foot(rc: VerticalRaycaster, p, z_c: float, probe: float, r_max: float, r_min: float,
                s: HybridSettings) -> Optional[float]:
    """Widest round foot (r_min .. r_max) centred on p whose edge, plus the X/Y clearance, stands on the
    same flat floor as the centre and nowhere inside the model. None when even r_min doesn't fit."""
    ring = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    dirs = np.column_stack([np.cos(ring), np.sin(ring)])
    zs = [z_c + 0.6, 0.5 * (z_c + probe), probe - 0.3]

    def ok(r):
        for d in dirs:
            for rr in (0.5 * r, r + s.xy_clearance):
                q = p + d * rr
                hz, up = rc.below_hit(q[0], q[1], probe)
                if hz is not None and not up:
                    return False
                if abs((0.0 if hz is None or hz <= s.bed_tolerance else hz) - z_c) > 1.0:
                    return False
                if rc.inside_many(q[0], q[1], zs).any():
                    return False
        return True

    if not ok(r_min):
        return None
    if ok(r_max):
        return float(r_max)
    lo, hi = r_min, r_max
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return float(lo)


def _arm_foot(rc: VerticalRaycaster, p, u, z_c: float, probe: float, want: float, s: HybridSettings, half: float) -> float:
    """How far a wall of the criss-cross can stand on the floor along direction u (up to `want`): the floor
    under it, and beside it by half its thickness plus the X/Y clearance, is flat at the landing height."""
    n = np.array([-u[1], u[0]])
    last = 0.0
    for d in np.arange(0.0, want + 1e-9, 0.5):
        q = p + u * d
        for o in (q, q + n * (half + s.xy_clearance), q - n * (half + s.xy_clearance), q + u * s.xy_clearance):
            hz, up = rc.below_hit(o[0], o[1], probe)
            if (hz is not None and not up) or abs((0.0 if hz is None or hz <= s.bed_tolerance else hz) - z_c) > 0.3 \
                    or rc.inside_many(o[0], o[1], [z_c + 0.6, 0.5 * (z_c + probe), probe - 0.3]).any():
                return max(0.0, last)
        last = d
    return float(want)


def _sees(rc: VerticalRaycaster, p, xy, z: float, clear: float) -> bool:
    """Is there a clear straight path at height z from p to the nearest overhang point?"""
    d = np.linalg.norm(xy - p, axis=1)
    q = xy[d.argmin()]
    L = float(d.min())
    if L < 1e-6:
        return not rc.inside(p[0], p[1], z)
    u = (q - p) / L
    for t in np.arange(0.0, L + 1e-9, 0.5):
        a = p + u * t
        if rc.inside(a[0], a[1], z):
            return False
    return True


def _clear(rc: VerticalRaycaster, x: float, y: float, zs, u, half: float, side_zs=None) -> bool:
    """True when the points (x, y, zs) and their sideways neighbours are outside the model.

    The sideways test uses side_zs (default: zs) so a sloped or curved underside right above
    the branch top does not count as a collision.
    """
    if rc.inside_many(x, y, zs).any():
        return False
    n = np.array([-u[1], u[0]])
    for off in (half, -half):
        q = np.array([x, y]) + n * off
        if rc.inside_many(q[0], q[1], zs if side_zs is None else side_zs).any():
            return False
    return True


def _build_fin(p, u, length, rt, z_h0, top: _TopLookup, rc: VerticalRaycaster, s: HybridSettings,
               tan_f: float, tip_h: float, thick: float, standing: bool = False, min_len: Optional[float] = None):
    """Profile of one branch towards direction u; shortened where it would hit the model."""
    step = max(0.5, top.c / 2)
    ss = np.unique(np.append(np.arange(0.0, length, step), length))
    zt = []
    nrm = np.array([-u[1], u[0]]) * (thick / 2)
    for s_ in ss:
        q = p + u * s_
        vals = [v for v in (top(q[0], q[1]), top(*(q + nrm)), top(*(q - nrm))) if v is not None]
        zt.append(min(vals) if vals else np.nan)     # both faces of the web stay under the model
    zt = np.array(zt)
    if np.isnan(zt).all():
        return None
    good = ~np.isnan(zt)
    zt = np.interp(ss, ss[good], zt[good])
    for k, s_ in enumerate(ss):      # exact check: the model surface right above each face of the web
        q = p + u * s_
        for o in (q, q + nrm, q - nrm):
            # from just above the fin's foot (a fin standing on a surface must not see that surface)
            a = rc.above(o[0], o[1], (zt[k] - 0.5) if standing else min(zt[k] - 0.5, z_h0 + 0.05))
            if a is not None and a - s.contact_gap < zt[k]:
                zt[k] = a - s.contact_gap
    if standing:                     # a web standing on whatever is below it
        zb = []
        for s_, t_ in zip(ss, zt):
            q = p + u * s_
            g = rc.below(q[0], q[1], t_)
            zb.append(0.0 if g is None or g <= s.bed_tolerance else g)
        zb = np.array(zb)
        tip_h = 0.4
    else:
        zb = z_h0 + np.maximum(0.0, ss - rt) / tan_f
    half = thick / 2 + s.xy_clearance
    keep = len(ss)
    for k, s_ in enumerate(ss):
        if zt[k] - zb[k] < tip_h * 0.5:
            keep = k
            break
        q = p + u * s_
        zs = [zb[k] + 0.05, (zb[k] + zt[k]) / 2, zt[k] - 0.05]
        side = [zb[k] + 0.05, (zb[k] + zt[k]) / 2]
        if not _clear(rc, q[0], q[1], zs, u, half if s_ > rt else thick / 2, side):
            keep = k
            break
    if keep < len(ss):
        # back off by the clearance so Cura's X/Y distance does not eat the tip
        cut = ss[keep] - s.xy_clearance - step
        m = ss <= cut
        if m.sum() < 2:
            return None
        ss, zb, zt = ss[m], zb[m], zt[m]
    if ss[-1] <= (rt * 0.5 if min_len is None else min_len) and not standing:
        return None
    if standing and ss[-1] < 0.5:
        return None
    zt = np.maximum(zt, zb + 0.2)
    return ss, zb, zt


def _gussets(p, rt, wall, z_land, trunk_h, rc: VerticalRaycaster, s: HybridSettings, notes) -> List[Mesh]:
    if s.gusset_count <= 0 or s.gusset_height <= 0 or s.gusset_length <= 0 or trunk_h < 2.0:
        return []
    g_h = min(s.gusset_height, 0.5 * trunk_h)
    if g_h < s.gusset_height:
        notes.append(f"gusset height capped to {g_h:.1f} mm")
    thick = max(1, s.wall_lines) * s.line_width
    out, trimmed = [], 0
    for k in range(s.gusset_count):
        a = 2 * np.pi * k / s.gusset_count + np.pi / 4
        u = np.array([math.cos(a), math.sin(a)])
        r0 = rt - 0.5 * wall
        length = s.gusset_length + 0.5 * wall
        ok_len = 0.0
        for d in np.unique(np.append(np.arange(0.5, length, 0.5), length)):
            q = p + u * (r0 + d)
            h = g_h * (1 - d / length)
            zs = [z_land + 0.05, z_land + max(0.1, h - 0.05)]
            if not _clear(rc, q[0], q[1], zs, u, thick / 2 + s.xy_clearance):
                break
            if z_land > 0:          # standing on the model: the foot needs ground under it
                below = rc.below(q[0], q[1], z_land + 0.3)
                if below is None or below < z_land - 0.3:
                    break
            ok_len = d
        if ok_len < length - 1e-6:
            trimmed += 1
            ok_len = max(0.0, ok_len - s.xy_clearance)
        if ok_len < 1.0:
            continue
        h_eff = g_h * ok_len / length if ok_len < length else g_h
        out.append(gusset(p[0], p[1], a, r0, ok_len, max(h_eff, 0.5), thick, z_land))
    if trimmed:
        notes.append(f"{trimmed} gusset(s) shortened to keep clear of the model")
    return out


def _branches(p, rt, z_h0, pts, top, rc, s, tan_f, tip_h, thick, standing, covered=None, limit=None):
    """Greedy fan of fins until every overhang point is near one. Returns meshes and the covered mask."""
    d = np.linalg.norm(pts[:, :2] - p, axis=1)
    cover = s.bridge_gap / 2
    covered = (np.zeros(len(pts), dtype=bool) if covered is None else covered.copy()) | (d <= rt)
    dead = np.zeros(len(pts), dtype=bool)
    meshes = []
    limit = s.max_branches if limit is None else limit
    fails = 0
    while not (covered | dead).all() and len(meshes) < limit and fails < 150:   # don't grind through every point
        far = np.where(covered | dead, -1, d).argmax()
        if d[far] < 1e-6:
            covered[far] = True
            continue
        u = (pts[far, :2] - p) / d[far]
        prof = _build_fin(p, u, d[far], rt, z_h0, top, rc, s, tan_f, tip_h, thick, standing)
        if prof is None:
            dead[far] = True
            # points just beside a failed direction would fail too
            dead |= (np.abs(np.remainder(np.arctan2(pts[:, 1] - p[1], pts[:, 0] - p[0]) - math.atan2(u[1], u[0]) + np.pi,
                                         2 * np.pi) - np.pi) < 0.03) & (d >= d[far] - 1.0)
            fails += 1
            continue
        ss, zb, zt = prof
        meshes.append(fin(p, u, ss, zb, zt, thick))
        seg = u * ss[-1]
        t = np.clip(((pts[:, :2] - p) @ seg) / max(seg @ seg, 1e-9), 0, 1)
        near = np.linalg.norm(pts[:, :2] - (p + t[:, None] * seg), axis=1)
        covered |= near <= cover
        if ss[-1] < d[far] - 1e-6:
            dead[far] = True
    return meshes, covered


def _flare_reach(p, rt, z_h0, pts, top: _TopLookup, rc: VerticalRaycaster, s: HybridSettings, tan_f: float, K: int):
    """How far a 45-degree flare from the trunk top can go in each of K directions.

    Per direction it rises at the flare angle until it reaches the edge of the overhang,
    the underside, or the model. Returns a dict of per-direction and per-point arrays.
    """
    angles = np.linspace(0, 2 * np.pi, K, endpoint=False)
    rel = pts[:, :2] - p
    rho = np.linalg.norm(rel, axis=1)
    phi = np.mod(np.arctan2(rel[:, 1], rel[:, 0]), 2 * np.pi)
    bins = np.round(phi / (2 * np.pi / K)).astype(int) % K
    reach = np.full(K, rt)
    for k in range(K):                       # far edge of the overhang along each direction
        d = np.array([math.cos(angles[k]), math.sin(angles[k])])
        along = rel @ d
        perp = np.abs(rel @ np.array([-d[1], d[0]]))
        # points close to this ray (not a whole angular sector: on a big overhang a sector's far
        # points lie well off the ray, and 0.6.3 pushed the cone out past the overhang's edge, off
        # the 200 mm part and the bed)
        m = (along > 0) & (perp <= max(top.c, 1.0))
        if not m.any():
            m = (bins == k) | (bins == (k + 1) % K) | (bins == (k - 1) % K)
        if m.any():
            reach[k] = max(rt, float((along[m] if (perp[m] <= max(top.c, 1.0)).all() else rho[m]).max()) + top.c / 2)

    def ceiling(x, y, z_from):
        v = top(x, y)
        a = rc.above(x, y, z_from)
        if a is not None:
            v = a - s.contact_gap if v is None else min(v, a - s.contact_gap)
        return v

    step = 0.5
    r1 = np.full(K, rt)
    z1 = np.full(K, z_h0)
    for k, a in enumerate(angles):
        d = np.array([math.cos(a), math.sin(a)])
        r = rt
        while r < reach[k] - 1e-9:
            rn = min(r + step, reach[k])
            zc = z_h0 + (rn - rt) / tan_f
            q = p + d * rn
            cz = ceiling(q[0], q[1], zc - 1.0)
            if cz is not None and zc >= cz:        # the cone meets the underside
                break
            qq = p + d * (rn + s.xy_clearance)
            if rc.inside_many(q[0], q[1], [zc, zc + 0.3]).any() or rc.inside(qq[0], qq[1], zc):
                rn = max(rt, r - s.xy_clearance)    # keep clear of the model
                r = rn
                break
            r = rn
        r1[k] = r
        z1[k] = z_h0 + (r - rt) / tan_f
    return {"angles": angles, "rel": rel, "rho": rho, "phi": phi, "bins": bins, "reach": reach,
            "r1": r1, "z1": z1, "ceiling": ceiling}


def _cone_head(p, rt, wall, z_h0, pts, top: _TopLookup, rc: VerticalRaycaster, s: HybridSettings, tan_f: float):
    """Hollow inverted cone from the trunk top, with a cross of spokes, rings or nothing inside.

    Per direction the cone wall rises at the flare angle until it reaches the edge of the
    overhang (or the model, or the underside), then goes straight up to the underside.
    Returns (meshes, covered mask).
    """
    K = max(24, 2 * s.segments)
    fr = _flare_reach(p, rt, z_h0, pts, top, rc, s, tan_f, K)
    angles, rel, rho, phi, bins = fr["angles"], fr["rel"], fr["rho"], fr["phi"], fr["bins"]
    r1, z1, ceiling = fr["r1"], fr["z1"], fr["ceiling"]
    w = wall

    def tops(radii, z_from):
        """Underside height over both faces of a wall at these radii, smoothed over neighbours."""
        raw = np.full(K, np.inf)
        for k, a in enumerate(angles):
            d = np.array([math.cos(a), math.sin(a)])
            for rr in (radii[k], max(radii[k] - w, 0.0)):
                q = p + d * rr
                cz = ceiling(q[0], q[1], z_from[k])
                if cz is not None:
                    raw[k] = min(raw[k], cz)
        return np.minimum(raw, np.minimum(np.roll(raw, 1), np.roll(raw, -1)))

    t1 = tops(r1, z1)
    zt1 = np.where(np.isfinite(t1) & (r1 > rt + 1e-6), np.maximum(z1, t1), z1)
    sec = []
    for k in range(K):
        sec.append([(rt, z_h0), (r1[k], z1[k]), (r1[k], zt1[k]),
                    (r1[k] - w, zt1[k]), (r1[k] - w, z1[k]), (rt - w, z_h0)])
    meshes = [loft(p, angles, np.array(sec))]

    gap = s.bridge_gap
    fill = s.cone_fill if gap > 0 else "none"
    cell = top.c
    rim_d = np.maximum(r1[bins] - rho, 0.0)          # distance from each point out to the cone rim
    if fill == "rings":
        radii = [r1.copy()]
        n = 1
        while True:
            rk = r1 - n * gap
            if rk.max() < rt + 0.5 * gap or n > 40:
                break
            rk = np.maximum(rk, rt + w)
            zb = z_h0 + (rk - rt) / tan_f
            tk = tops(rk, zb + 0.05)
            zt = np.where(np.isfinite(tk), tk, zb)
            zt = np.maximum(zt, zb + 0.2)
            ring = [[(rk[k], zb[k] - 0.05), (rk[k], zt[k]), (rk[k] - w, zt[k]), (rk[k] - w, zb[k] - 0.05)]
                    for k in range(K)]
            meshes.append(loft(p, angles, np.array(ring)))
            radii.append(rk)
            n += 1
        dist = np.min([np.abs(rho - rk[bins]) for rk in radii], axis=0)
        covered = (rho <= rt) | ((2 * dist <= gap + cell) & (rho <= r1[bins] + cell))
    elif fill == "cross":
        # spokes from the trunk to the corners of the overhang, then wherever the longest bridge is
        thick = max(w, _min_thick(s))
        hull = convex_hull_2d(pts[:, :2])
        dirs = []
        if len(hull) >= 3:
            for i in range(len(hull)):
                a_, b_, c_ = hull[i - 1], hull[i], hull[(i + 1) % len(hull)]
                v1, v2 = a_ - b_, c_ - b_
                cosang = float(v1 @ v2 / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-12))
                if cosang > math.cos(math.radians(150)):      # a real corner
                    dirs.append(math.atan2(b_[1] - p[1], b_[0] - p[0]))
        if len(dirs) < 2:
            dirs = [k * np.pi / 2 for k in range(4)]
        spoke_len = {}

        def add_spoke(a):
            k = int(round(np.mod(a, 2 * np.pi) / (2 * np.pi / K))) % K
            if r1[k] <= rt + 0.5:
                return None
            u = np.array([math.cos(a), math.sin(a)])
            prof = _build_fin(p, u, r1[k], rt, z_h0, top, rc, s, tan_f, 0.5, thick)
            if prof is None:
                return None
            ss, zb, zt = prof
            meshes.append(fin(p, u, ss, zb, zt, thick))
            return u * ss[-1]

        segs = []
        for a in dirs:
            sg = add_spoke(a)
            if sg is not None:
                segs.append(sg)
        tried = set()
        while len(segs) < 16:
            if segs:
                d_sp = np.min([np.linalg.norm(rel - np.clip((rel @ sg) / (sg @ sg), 0, 1)[:, None] * sg, axis=1)
                               for sg in segs], axis=0)
            else:
                d_sp = np.full(len(pts), np.inf)
            span = 2 * np.minimum(d_sp, rim_d)
            span[rho <= rt] = 0
            worst = int(span.argmax())
            if span[worst] <= gap + cell or round(phi[worst], 2) in tried:
                break
            tried.add(round(phi[worst], 2))
            sg = add_spoke(phi[worst])
            if sg is not None:
                segs.append(sg)
        if segs:
            d_sp = np.min([np.linalg.norm(rel - np.clip((rel @ sg) / (sg @ sg), 0, 1)[:, None] * sg, axis=1)
                           for sg in segs], axis=0)
        else:
            d_sp = np.full(len(pts), np.inf)
        covered = (rho <= rt) | ((2 * np.minimum(d_sp, rim_d) <= gap + cell) & (rho <= r1[bins] + cell))
    else:
        covered = (rho <= rt) | (rho <= r1[bins] + cell)
    return meshes, covered


def offset_inward(poly: np.ndarray, w: float) -> np.ndarray:
    """Miter offset of a counter-clockwise polygon by w towards its inside (same vertex count)."""
    e = np.roll(poly, -1, axis=0) - poly
    L = np.linalg.norm(e, axis=1, keepdims=True)
    e = e / np.maximum(L, 1e-12)
    n = np.column_stack([-e[:, 1], e[:, 0]])          # left normal = inside for CCW
    n_prev = np.roll(n, 1, axis=0)
    m = n + n_prev
    denom = 1.0 + np.sum(n * n_prev, axis=1, keepdims=True)
    off = w * m / np.maximum(denom, 1e-3)
    mag = np.linalg.norm(off, axis=1, keepdims=True)
    off = np.where(mag > 3 * w, off * (3 * w) / np.maximum(mag, 1e-12), off)
    return poly + off


def wall_shell(outer: np.ndarray, inner: np.ndarray) -> Mesh:
    """Closed hollow wall between stacked outlines.

    outer, inner: (J+1, K, 3) rings of points, level 0 at the bottom. Each level's outer ring
    is counter-clockwise seen from above; inner is the same ring moved inwards.
    """
    J1, K = outer.shape[0], outer.shape[1]
    v = np.vstack([outer.reshape(-1, 3), inner.reshape(-1, 3)])
    oi = lambda j, k: j * K + k % K                  # noqa: E731
    ii = lambda j, k: J1 * K + j * K + k % K         # noqa: E731
    f = []
    for j in range(J1 - 1):
        for k in range(K):
            a, b, c, d = oi(j, k), oi(j, k + 1), oi(j + 1, k + 1), oi(j + 1, k)
            f += [[a, b, c], [a, c, d]]               # outer face, normal outwards
            a, b, c, d = ii(j, k), ii(j, k + 1), ii(j + 1, k + 1), ii(j + 1, k)
            f += [[a, c, b], [a, d, c]]               # inner face, normal inwards
    jt = J1 - 1
    for k in range(K):
        f += [[oi(jt, k), oi(jt, k + 1), ii(jt, k + 1)], [oi(jt, k), ii(jt, k + 1), ii(jt, k)]]   # top
        f += [[oi(0, k), ii(0, k + 1), oi(0, k + 1)], [oi(0, k), ii(0, k), ii(0, k + 1)]]       # bottom
    m = Mesh(v, np.array(f))
    if m.volume() < 0:
        m.faces = m.faces[:, ::-1]
    return m


def _lobe_head(p, rt, wall, z_h0, pts, top: _TopLookup, rc: VerticalRaycaster, s: HybridSettings, tan_f: float):
    """A star-shaped "pseudo cone": hollow lobes flaring out from the trunk towards the corners.

    Each horizontal slice is one closed outline: the trunk circle with straight-sided lobes
    sticking out of it. A lobe grows outwards at the flare angle as it rises, so its tip is
    the only overhanging part. Lobes go to the corners of the overhang first, then more are
    added wherever a bridge (to a lobe, or to a wall of the model) would be longer than
    Max bridge span. Returns (meshes, covered mask, number of lobes).
    """
    K = 180
    fr = _flare_reach(p, rt, z_h0, pts, top, rc, s, tan_f, K)
    angles, rel, rho, phi, bins = fr["angles"], fr["rel"], fr["rho"], fr["phi"], fr["bins"]
    r1, reach, ceiling = fr["r1"], fr["reach"], fr["ceiling"]
    w = wall
    half = 0.5 * (s.lobe_width if s.lobe_width > 0 else float(np.clip(rt, 4.0, 10.0)))
    half = max(half, w + 0.6)                         # keep a hollow inside every lobe
    gap = s.bridge_gap if s.bridge_gap > 0 else 1e9
    cell = top.c
    zmin = float(pts[:, 2].min())

    # overhang edges that sit against a wall of the model count as support for bridges
    backed = np.zeros(K, dtype=bool)
    for k, a in enumerate(angles):
        d = np.array([math.cos(a), math.sin(a)])
        for extra in (s.xy_clearance + 0.5, s.xy_clearance + 1.5):
            q = p + d * (reach[k] + extra)
            if rc.inside_many(q[0], q[1], [zmin - 0.5, zmin + 0.5]).any():
                backed[k] = True
                break
    wall_d = np.where(backed[bins], np.maximum(reach[bins] - rho, 0.0), np.inf)

    def lobe_dist(lobes):
        d = np.maximum(rho - rt, 0.0)
        for a, L in lobes:
            u = np.array([math.cos(a), math.sin(a)])
            t = np.clip(rel @ u, 0.0, L)
            d = np.minimum(d, np.maximum(np.linalg.norm(rel - t[:, None] * u, axis=1) - half, 0.0))
        return d

    def r1_at(a):
        return r1[int(round(np.mod(a, 2 * np.pi) / (2 * np.pi / K))) % K]

    hull = convex_hull_2d(pts[:, :2])
    dirs = []
    if len(hull) >= 3:
        for i in range(len(hull)):
            a_, b_, c_ = hull[i - 1], hull[i], hull[(i + 1) % len(hull)]
            v1, v2 = a_ - b_, c_ - b_
            cosang = float(v1 @ v2 / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-12))
            if cosang > math.cos(math.radians(150)):
                dirs.append(math.atan2(b_[1] - p[1], b_[0] - p[0]))
    if len(dirs) < 2:
        dirs = [k * np.pi / 2 for k in range(4)]
    lobes = []
    for a in dirs:
        if r1_at(a) > rt + half and all(abs(math.remainder(a - b, 2 * np.pi)) > 0.35 for b, _ in lobes):
            lobes.append((a, r1_at(a)))
    tried = set()
    while len(lobes) < s.max_lobes:
        span = 2 * np.minimum(lobe_dist(lobes), wall_d)
        span[rho <= rt] = 0
        worst = int(span.argmax())
        key = round(phi[worst], 2)
        if span[worst] <= gap + cell or key in tried:
            break
        tried.add(key)
        a = phi[worst]
        if r1_at(a) > rt + 0.5 and all(abs(math.remainder(a - b, 2 * np.pi)) > 0.2 for b, _ in lobes):
            lobes.append((a, min(r1_at(a), rho[worst] + cell)))

    # outline radius per direction: trunk circle, or the lobe's straight sides / end
    R = np.full(K, rt)
    for a, L in lobes:
        dl = np.abs(np.array([math.remainder(t - a, 2 * np.pi) for t in angles]))
        ok = dl < np.pi / 2 - 1e-6
        side = np.where(dl > 1e-9, half / np.maximum(np.sin(dl), 1e-9), np.inf)
        end = L / np.maximum(np.cos(dl), 1e-9)
        R = np.where(ok, np.maximum(R, np.minimum(side, end)), R)
    R = np.maximum(rt, np.minimum(R, np.maximum(r1, rt)))

    # top height at each direction: the underside over both wall faces, smoothed over neighbours
    dvec = np.column_stack([np.cos(angles), np.sin(angles)])
    raw = np.full(K, np.inf)
    zf = z_h0 + (R - rt) / tan_f
    outer_xy = p + dvec * R[:, None]
    inner_xy = offset_inward(outer_xy, w)
    for k in range(K):
        for q in (outer_xy[k], inner_xy[k], 0.5 * (outer_xy[k] + inner_xy[k])):
            cz = ceiling(q[0], q[1], zf[k] - 0.5)
            if cz is not None:
                raw[k] = min(raw[k], cz)
    zt = np.minimum(raw, np.minimum(np.roll(raw, 1), np.roll(raw, -1)))
    zt = np.where(np.isfinite(zt), zt, zf + 0.2)
    zt = np.maximum(zt, z_h0 + 0.4)

    J = int(np.clip(math.ceil((zt.max() - z_h0) / 0.8), 4, 80))
    outer = np.empty((J + 1, K, 3))
    inner = np.empty((J + 1, K, 3))
    for j in range(J + 1):
        z = z_h0 + (zt - z_h0) * j / J
        rr = np.minimum(rt + np.maximum(z - z_h0, 0.0) * tan_f, R)
        o = p + dvec * rr[:, None]
        outer[j, :, :2], outer[j, :, 2] = o, z
        inner[j, :, :2], inner[j, :, 2] = offset_inward(o, w), z
    meshes = [wall_shell(outer, inner)]

    d_l = lobe_dist(lobes)
    covered = (rho <= rt) | ((2 * np.minimum(d_l, wall_d) <= gap + cell) & (rho <= r1[bins] + cell))
    return meshes, covered, len(lobes)


def _min_thick(s: HybridSettings) -> float:
    """Cura support with no support walls only prints thin areas where its infill crosses them, so fins were
    made fat (and came out as a zig-zag). Printed as walls they don't need that."""
    return 0.0 if s.print_walls else s.min_branch_thickness


def _reachable(pts, rc: VerticalRaycaster, clear: float) -> np.ndarray:
    """Points Cura would let support reach: not within the X/Y distance of the model sideways."""
    ok = np.ones(len(pts), dtype=bool)
    for k, (x, y, z) in enumerate(pts):
        for dx, dy in ((clear, 0), (-clear, 0), (0, clear), (0, -clear)):
            if rc.inside(x + dx, y + dy, z - 0.3):
                ok[k] = False
                break
    return ok


def _blocker(pts, s):
    if not s.blocker:
        return None
    hull = convex_hull_2d(pts[:, :2])
    if len(hull) < 3:
        return None
    z_lo = max(float(pts[:, 2].min()) - 0.5, 0.0)
    z_hi = float(pts[:, 2].max()) + 0.5
    return prism(offset_convex(hull, s.blocker_margin), z_lo, z_hi)


def _low_unit(r: Region, rc: VerticalRaycaster, s: HybridSettings, uid: int, notes) -> List[SupportUnit]:
    """Low overhangs: thin webs standing on the surface below, fanned out from a few points."""
    pts = r.pts
    thick = max(s.branch_lines * s.line_width, _min_thick(s))
    top = _TopLookup(r, s.contact_gap)
    covered = np.zeros(len(pts), dtype=bool)
    tried = np.zeros(len(pts), dtype=bool)
    meshes, hubs = [], []
    empty = 0
    if s.bridge_gap <= 0:
        s = HybridSettings(**{**s.__dict__, "bridge_gap": 10.0})
    while len(hubs) < 8 and len(meshes) < s.max_branches and not (covered | tried).all():
        open_ = ~(covered | tried)
        cen = pts[open_, :2].mean(axis=0)
        order = np.where(open_)[0][np.argsort(np.linalg.norm(pts[open_, :2] - cen, axis=1))]
        p = None
        for k in order[:30]:
            tried[k] = True
            q = pts[k]
            if not rc.inside(q[0], q[1], (q[2] + r.land[k]) / 2):
                p = q[:2]
                break
        if p is None:
            continue
        new, covered = _branches(p, 0.0, 0.0, pts, top, rc, s, 1.0, 0.4, thick, True, covered,
                                 limit=s.max_branches - len(meshes))
        if new:
            meshes += new
            hubs.append(p)
        else:
            empty += 1
            if empty >= 8:          # the rest can't be reached by standing webs; stop looking
                break
    if not meshes:
        return []
    coverage = float((covered | ~_reachable(pts, rc, s.xy_clearance)).mean())
    notes.append("low overhang: standing webs")
    if coverage < 0.98:
        notes.append(f"webs reach {100 * coverage:.0f}% of this overhang")
    land = float(r.land.min())
    p = hubs[0]
    return [SupportUnit(uid, Mesh.concat(meshes), _blocker(pts, s), land, land, float(pts[:, 2].min()),
                        land == 0.0, notes, (float(p[0]), float(p[1])), 0.0, len(meshes), coverage, pts)]


def _wall_hit(rc: VerticalRaycaster, q, u, z: float, max_d: float) -> Optional[float]:
    """Distance from q along u to the first wall of the model at height z (to 0.05 mm), or None."""
    d, step = 0.0, 0.5
    while d < max_d:
        nd = d + step
        a = q + u * nd
        if rc.inside(a[0], a[1], z):
            lo, hi = d, nd
            while hi - lo > 0.05:
                mid = 0.5 * (lo + hi)
                b = q + u * mid
                if rc.inside(b[0], b[1], z):
                    hi = mid
                else:
                    lo = mid
            return lo
        d = nd
    return None


def _hexahedron(lo_q: np.ndarray, hi_q: np.ndarray, z0: float, z1: float) -> Mesh:
    """Closed solid between a bottom quad at z0 and a top quad at z1 (same corner order)."""
    v = np.vstack([np.column_stack([lo_q, np.full(4, z0)]), np.column_stack([hi_q, np.full(4, z1)])])
    f = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    m = Mesh(v, f)
    if m.volume() < 0:
        m.faces = m.faces[:, ::-1]
    return m


def _layer_bounds(s: HybridSettings, z0: float, z1: float):
    """Cura's layers between z0 and z1, as (index, bottom, top). Layer 1 sits on the initial layer."""
    h0, lh = s.layer_height_0, max(s.layer_height, 0.05)
    k = max(1, int(math.ceil((z0 - h0) / lh - 1e-6)) + 1)
    out = []
    while True:
        b = h0 + (k - 1) * lh
        t = b + lh
        if t > z1 + 1e-6:
            break
        out.append((k, b, t))
        k += 1
    return out


SPAGHETTI_WARNING = ("tethers: {span:.0f} mm span is over {warn:.0f} mm, so it is unpredictable (the hard limit is {hard:.0f} mm): "
                     "the vengeful Flying Spaghetti Monster may appear suddenly for trying to violate the laws of physics")


def _strip_ends(rc, q, u, n_half, zz, max_span):
    """Wall-to-wall ends of a strip centred on q along u, width 2*|n_half|, at height zz (or None)."""
    ends = []
    for sign in (1.0, -1.0):
        hits = [_wall_hit(rc, q + n_half * e, u * sign, zz, max_span) for e in (-1.0, 0.0, 1.0)]
        if any(h is None for h in hits):
            return None
        ends.append(min(hits))
    if ends[0] + ends[1] > max_span:
        return None
    return q - u * ends[1], q + u * ends[0]


def _tether_unit(r: Region, rc: VerticalRaycaster, s: HybridSettings, uid: int, notes) -> Optional[SupportUnit]:
    """Tethered support: strips strung between two facing walls just under the overhang, then a cap.

    Straight-up strips, every other layer shifted half a line width (so the layers only half overlap
    and snap apart easily). The first and last strip sit at the two ends of the overhang (tether_end_inset
    in from the edge) and the rest are spaced evenly between, covering about tether_coverage of the void.
    The cap is kept clear of the walls. Returns None when there are no walls to tie to.
    """
    pts = r.pts
    xy = pts[:, :2]
    top = float(pts[:, 2].min()) - s.contact_gap
    z0 = max(float(r.land.max()) + 0.5, top - s.tether_height)
    layers = _layer_bounds(s, z0, top - _cap_height(s))
    if len(layers) < 3:
        return None
    z_first = 0.5 * (layers[0][1] + layers[0][2])
    z_last = 0.5 * (layers[-1][1] + layers[-1][2])
    hull = convex_hull_2d(xy)
    if len(hull) < 3:
        return None
    c = xy.mean(axis=0)

    def under(q):                                       # inside the overhang's outline (with a little slack)
        e = np.roll(hull, -1, axis=0) - hull
        w_ = q - hull
        return bool(np.all(e[:, 0] * w_[:, 1] - e[:, 1] * w_[:, 0] >= -0.5))

    lw = s.line_width
    width = s.tether_width if s.tether_width > 0 else 3 * lw
    half = width / 2
    pitch = width / max(0.02, min(1.0, s.tether_coverage))
    lean = 0.0
    wobble = 0.5 * lw                                   # every other layer shifted by half a line

    def strips_for(a, offs):
        """Valid strips at angle a for these offsets: (offset, bottom ends, top ends)."""
        u = np.array([math.cos(a), math.sin(a)])
        n = np.array([-u[1], u[0]])
        found = []
        for o in offs:
            q0, q1 = c + n * o, c + n * (o + lean + wobble)
            if not (under(q0) and under(q1)) or rc.inside(q0[0], q0[1], z_first) or rc.inside(q1[0], q1[1], z_last):
                continue
            e0 = _strip_ends(rc, q0, u, n * half, z_first, s.tether_max_span)
            e1 = _strip_ends(rc, q1, u, n * half, z_last, s.tether_max_span) if e0 is not None else None
            if e0 is None or e1 is None:
                continue
            found.append((o, e0, e1))
        return found

    def even_offsets(a, extra=0.0):
        """Strip centres across the overhang: the first and last at its two ends (the overhang's edge,
        tether_end_inset in, half a strip in), the others evenly between about one pitch apart."""
        n = np.array([-math.sin(a), math.cos(a)])
        proj = (xy - c) @ n
        edge = 0.5 * r.cell                             # samples sit half a cell inside the real edge
        lo = proj.min() - edge + s.tether_end_inset + half
        hi = proj.max() + edge - s.tether_end_inset - half - extra
        if hi - lo < pitch * 0.5:
            return np.array([0.5 * (lo + hi)])
        k = max(2, int(round((hi - lo) / pitch)) + 1)
        return np.linspace(lo, hi, k)

    dirs = [np.pi * k / 12 for k in range(12)] if s.tether_dir is None else [s.tether_dir]
    best = None
    for a in dirs:                                      # shortest wall-to-wall span with walls for most strips
        offs = even_offsets(a, lean + wobble)
        found = strips_for(a, offs)
        if len(found) < max(1, int(0.6 * len(offs))):
            continue
        span = max(float(np.linalg.norm(e0[1] - e0[0])) for _, e0, _ in found)
        if best is None or span < best[0]:
            best = (span, a, found)
    if best is None:                                    # no facing walls (in the shared direction)
        return None
    span, ang, found = best
    notes.append(f"tether span {span:.0f} mm")          # read back by build_unit (probe + warning)
    # the cap can only bridge so far between strips: when the strips leave much of the overhang out of
    # reach (an L corner: chords only fit near the corner), tethers are the wrong tool here
    reach = max(1.5 * pitch, 8.0)
    d_min = np.full(len(xy), np.inf)
    for _, e0, _ in found:
        a_, b_ = e0
        ab = b_ - a_
        tt = np.clip(((xy - a_) @ ab) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
        d_min = np.minimum(d_min, np.linalg.norm(xy - (a_ + tt[:, None] * ab), axis=1))
    if float(np.mean(d_min <= reach)) < 0.9:
        notes.append(f"tethers would leave {100 * float(np.mean(d_min > reach)):.0f}% of the overhang more than {reach:.0f} mm from a strip")
        return None
    u = np.array([math.cos(ang), math.sin(ang)])
    nn = np.array([-u[1], u[0]])
    parts: List[Mesh] = []
    nl = len(layers)

    plan = None
    z_lo, z_hi = layers[0][1], layers[-1][2]
    polys = []
    for o, e0, e1 in found:                             # straight up; the G-code step adds the stagger
        q0 = np.array([e0[0] - nn * half, e0[1] - nn * half, e0[1] + nn * half, e0[0] + nn * half])
        parts.append(_hexahedron(q0, q0, z_lo, z_hi + 0.05))
        grow = np.array([e0[0] - nn * (half + 0.6) - u * 1.0, e0[1] - nn * (half + 0.6) + u * 1.0,
                         e0[1] + nn * (half + 0.6) + u * 1.0, e0[0] + nn * (half + 0.6) - u * 1.0])
        polys.append([tuple(map(float, q)) for q in grow])
    # Cura can't stagger from the shape (see tether_gcode.py), so the Cura side shifts every other
    # layer's tether lines by half a line width after slicing
    plan = {"polys": polys, "shift": tuple(map(float, nn * wobble)), "z": (float(z_lo), float(z_hi)),
            "h0": float(s.layer_height_0), "lh": float(s.layer_height)}
    what = f"{len(found)} tether(s) across {span:.0f} mm, every other layer shifted half a line"
    n_br = len(found)

    # the cap: printed as support roof, kept clear of the walls by the usual X/Y distance
    cap = offset_convex(hull, -max(s.xy_clearance, 0.4))
    if len(cap) >= 3:
        parts.append(prism(cap, layers[-1][2] - 0.05, top))
    notes.append(f"{what}, from {top - z0:.1f} mm below the overhang")
    if span > s.tether_warn_span:
        notes.append(SPAGHETTI_WARNING.format(span=span, warn=s.tether_warn_span, hard=s.tether_max_span))
    unit = SupportUnit(uid, Mesh.concat(parts), _blocker(pts, s), z0, z0, float(pts[:, 2].min()), False, notes,
                       (float(c[0]), float(c[1])), 0.0, n_br, 1.0, pts)
    # CuraEngine cuts every support back from the model by Support X/Y Distance, a support-extruder
    # setting that can't be set per mesh or per object, so the strips only reach the walls when it
    # is 0. The plugin's other supports (and the cap) keep their clearance in their own shape.
    # Cura's support line angle: 0 draws lines along Y, 90 along X (measured in Cura 5.13 G-code),
    # so lines along direction ang need 90 - ang: each tether is then a straight line wall to wall.
    g = {"support_xy_distance": s.tether_xy, "support_xy_distance_overhang": s.tether_xy,
         "support_roof_enable": True, "support_roof_height": _cap_height(s)}
    # Concentric outlines each strip exactly, so the half-line stagger follows the
    # geometry (zigzag lines sit on a fixed grid and ignore a 0.2 mm shift); the line angle is set
    # too in case a profile overrides the pattern.
    g["support_pattern"] = "concentric"
    g["support_infill_angles"] = f"[{int(round(90 - math.degrees(ang))) % 180}]"
    unit.global_settings = g
    unit.tether_dir = float(ang)
    slow = _slow_plan(s, layers, hull)
    if slow is not None:
        plan = dict(plan or {}, **slow)
    stack = _stack_plan(s, cap, ang)
    if stack is not None:
        plan = dict(plan or {}, **stack)
    unit.gcode_plan = plan
    return unit


def _cap_height(s: HybridSettings) -> float:
    """Thickness of the cap under the overhang: the 4-layer stack, or the old roof height."""
    return 4.0 * float(s.layer_height) if s.tether_cap_stack else float(s.tether_cap)


def _stack_plan(s: HybridSettings, cap, ang: float) -> Optional[dict]:
    """G-code step plan for the cap stack: lattice (across the tethers), lattice (along), open rings, diagonal.
    cap is the convex cap outline in model XY; ang the direction of the tethers (radians)."""
    if not s.tether_cap_stack or cap is None or len(cap) < 3:
        return None
    return {"capstack": {"poly": [tuple(map(float, q)) for q in cap], "angle": float(ang),
                         "pitch": float(s.tether_lattice_pitch), "density": float(s.tether_ring_density),
                         "hole": float(s.tether_cap_hole), "flow": float(s.tether_cap_flow if s.tether_cap_flow > 0 else 1.0),
                         "width": float(s.line_width), "lh": float(s.layer_height)}}


def _clip_halfplane(poly: np.ndarray, n: np.ndarray, c: float) -> np.ndarray:
    """Keep the part of a convex polygon with n . p <= c."""
    out = []
    m = len(poly)
    for i in range(m):
        a, b = poly[i], poly[(i + 1) % m]
        da, db = float(a @ n) - c, float(b @ n) - c
        if da <= 0:
            out.append(a)
        if (da <= 0) != (db <= 0):
            out.append(a + (b - a) * (da / (da - db)))
    return np.array(out) if len(out) >= 3 else np.zeros((0, 2))


def _cap_piece(xy: np.ndarray, z0: float, top: float, rc: VerticalRaycaster, s: HybridSettings) -> Optional[np.ndarray]:
    """Convex outline of the points xy, cut back (nearest offender first, staying convex) wherever the slab
    z0..top would be in the model or within the X/Y clearance of it. None when too little is left."""
    poly = convex_hull_2d(xy)
    if len(poly) < 3:
        return None
    zs = [z0 + 0.05, 0.5 * (z0 + top), top - 0.05, top + s.contact_gap * 0.5]
    offs = [np.zeros(2)] + [np.array([math.cos(a), math.sin(a)]) * s.xy_clearance
                            for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
    lo, hi = poly.min(axis=0), poly.max(axis=0)
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0] + 1e-9, 1.0), np.arange(lo[1], hi[1] + 1e-9, 1.0))
    cand = np.vstack([np.column_stack([gx.ravel(), gy.ravel()]), poly])
    cand = cand[[_point_in_convex(poly, q) for q in cand]]
    hit_at = {}
    bad_pts, bad_dir = [], []
    for q in cand:
        hits = []
        for o in offs:
            key = (round(float(q[0] + o[0]), 2), round(float(q[1] + o[1]), 2))
            if key not in hit_at:
                hit_at[key] = bool(rc.inside_many(key[0], key[1], zs).any())
            if hit_at[key]:
                hits.append(o)
        if hits:
            bad_pts.append(q)
            # which way the model is from here: the cut goes across that, so a wall beside the cap trims
            # a strip along the wall instead of a big corner (0.6.3 cut across the line to the centre)
            d = np.sum(hits, axis=0)
            bad_dir.append(d / np.linalg.norm(d) if np.linalg.norm(d) > 1e-9 else None)
    bad_pts = np.array(bad_pts).reshape(-1, 2)
    for _ in range(80):
        if len(poly) < 3 or not len(bad_pts):
            break
        keep = [_point_in_convex(poly, q) for q in bad_pts]
        bad_pts = bad_pts[keep]
        bad_dir = [d for d, k in zip(bad_dir, keep) if k]
        if not len(bad_pts):
            break
        c = poly.mean(axis=0)
        i = int(np.argmin(np.linalg.norm(bad_pts - c, axis=1)))
        bad = bad_pts[i]
        n = bad_dir[i]
        if n is None or float(n @ (bad - c)) <= 0:      # inside the model, or the model is towards the middle
            d = bad - c
            L = float(np.linalg.norm(d))
            if L < 0.5:
                return None
            n = d / L
        poly = _clip_halfplane(poly, n, float(n @ bad) - 0.5)
    if len(poly) < 3 or polygon_area_centroid(poly)[0] < 4.0:
        return None
    return poly


def _plan_caps(r: "Region", rc: VerticalRaycaster, s: HybridSettings):
    """Interface caps under an overhang, planned before its tower.

    Each cap is a flat slab of _cap_height (4 layers) whose top is the contact gap under the overhang. It is
    added as a normal mesh printed as solid skin, and on save the cap stack replaces its lines with
    lattice (bridging between the tower's walls, printed slowly), lattice the other way, 50 % rings and a
    100 % top layer, the same stack as the tethers' cap. A sloped or curved underside gets one flat piece
    per cap thickness of height (a staircase); a band that is a ring round a dome is split into sectors so
    each piece stays convex without covering the model. Each piece is cut back wherever it would come
    within the X/Y clearance of the model; where no cap fits (too low, too steep, boxed in) there is none.

    Returns (region with the capped points lowered to the caps' undersides, so the tower is built up to
    them, [(outline, z0, top)])."""
    pts = r.pts
    cap_h = _cap_height(s)
    z = pts[:, 2]
    zmin = float(z.min())
    band = np.floor((z - zmin) / cap_h + 1e-6).astype(int)
    centre = pts[:, :2].mean(axis=0)
    new_z = z.copy()
    pieces = []
    land = float(np.min(r.land)) if len(r.land) else 0.0
    for b in np.unique(band)[:24]:
        in_band = band == b
        sel = pts[in_band]
        if len(sel) < 3:
            continue
        top = zmin + b * cap_h - s.contact_gap
        z0 = top - cap_h
        if z0 <= float(np.max(r.land[in_band])) + 0.6:      # too low for a cap and something under it
            continue
        whole = convex_hull_2d(sel[:, :2])
        area = polygon_area_centroid(whole)[0] if len(whole) >= 3 else 0.0
        poly = _cap_piece(sel[:, :2], z0, top, rc, s)
        found = [poly] if poly is not None else []
        if poly is None or polygon_area_centroid(poly)[0] < 0.6 * area:
            ang = np.arctan2(sel[:, 1] - centre[1], sel[:, 0] - centre[0])
            sec = np.floor((ang + np.pi) / (2 * np.pi / 8)).astype(int) % 8
            parts = [_cap_piece(sel[sec == k, :2], z0, top, rc, s) for k in range(8) if (sec == k).sum() >= 3]
            parts = [q for q in parts if q is not None]
            if sum(polygon_area_centroid(q)[0] for q in parts) > (polygon_area_centroid(poly)[0] if poly is not None else 0):
                found = parts
        for poly in found:
            under = in_band & np.array([_point_in_convex(poly, q) for q in pts[:, :2]])
            new_z[under] = z0 + s.contact_gap         # the tower's top (z - contact gap) is the cap's underside
            pieces.append((poly, float(z0), float(top)))
    del land
    low = Region(np.column_stack([pts[:, :2], new_z]), r.land, r.cell)
    low.capped = True
    return low, pieces


def _attach_caps(u: "SupportUnit", pieces, s: HybridSettings) -> None:
    """The cap meshes and their G-code plans (cap stack, slow first lattice layer) for one unit."""
    lh = float(s.layer_height)
    plans = []
    for poly, z0, top in pieces:
        u.caps.append(prism(poly, z0, top))
        xy = poly - poly.mean(axis=0)
        ang = math.atan2(*np.linalg.svd(xy, full_matrices=False)[2][0][::-1])
        st = _stack_plan(s, poly, ang)
        if st is None:
            continue
        st["capstack"]["mesh_prefix"] = "HybridCap"
        st["capstack"]["flow"] = 1.0              # the first lattice bridges between walls, not onto thin tethers
        plan = dict(st)
        if s.tower_cap_bridge_speed > 0:
            plan["slow"] = {"poly": [tuple(map(float, q)) for q in offset_convex(poly, 1.0)],
                            "z": (float(z0 + 0.5 * lh), float(z0 + 1.5 * lh)), "speed": float(s.tower_cap_bridge_speed),
                            "flow": 1.0, "fan": float(s.tether_bridge_fan), "types": ["SUPPORT-INTERFACE"]}
        plans.append(plan)
    if u.caps:
        u.notes.append(f"interface cap: {len(u.caps)} piece(s), lattice x2, 50 % rings, 100 % top")
        prev = u.gcode_plan if isinstance(u.gcode_plan, list) else ([u.gcode_plan] if u.gcode_plan else [])
        u.gcode_plan = prev + plans


def _point_in_convex(poly: np.ndarray, q) -> bool:
    n = len(poly)
    sgn = 0
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        cr = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
        if abs(cr) < 1e-9:
            continue
        if sgn == 0:
            sgn = 1 if cr > 0 else -1
        elif (cr > 0) != (sgn > 0):
            return False
    return True


def _slow_plan(s: HybridSettings, layers, hull) -> Optional[dict]:
    """G-code step: the first tether layers are bridges in mid-air, so they get slowed and cooled; the
    first cap layers lie across the tethers and get a lower flow (and optionally a speed) so the hot bead
    fuses with the thin tether instead of squashing or melting through it."""
    if not layers:
        return None
    plans = []
    big = [tuple(map(float, q)) for q in offset_convex(hull, 1.0)]
    if s.tether_bridge_speed > 0 and s.tether_slow_layers > 0:
        n = min(s.tether_slow_layers, len(layers))
        plans.append({"poly": big, "z": (float(layers[0][2]), float(layers[n - 1][2])),
                      "speed": float(s.tether_bridge_speed), "flow": float(s.tether_bridge_flow),
                      "fan": float(s.tether_bridge_fan)})
    if not s.tether_cap_stack and s.tether_cap_layers > 0 and (0 < s.tether_cap_flow < 0.999 or s.tether_cap_speed > 0):
        lh, top = float(s.layer_height), float(layers[-1][2])
        plans.append({"poly": big, "z": (top + 0.5 * lh, top + (s.tether_cap_layers + 0.5) * lh),
                      "speed": float(s.tether_cap_speed), "flow": float(s.tether_cap_flow if s.tether_cap_flow > 0 else 1.0),
                      "fan": float(s.tether_bridge_fan), "types": ["SUPPORT-INTERFACE", "SUPPORT"]})
    return {"slow": plans} if plans else None


def _cone_shell(p, base: float, z_land: float, pts: np.ndarray, top: "_TopLookup", rc: VerticalRaycaster,
                s: HybridSettings, tan_f: float, w: float):
    """A thin hollow cone built to size, no trunk: radius `base` on the landing, flaring at the flare angle
    until it reaches the edge of the overhang (or the model) in each direction, then straight up to the
    underside. Wall thickness w. Returns (mesh, per-point reach mask)."""
    K = 64                                    # 64 sides: smooth enough, far fewer moves than 180
    fr = _flare_reach(p, base, z_land, pts, top, rc, s, tan_f, K)
    angles, rho, bins, r1, ceiling = fr["angles"], fr["rho"], fr["bins"], fr["r1"], fr["ceiling"]
    R = np.maximum(r1, base)
    dvec = np.column_stack([np.cos(angles), np.sin(angles)])
    raw = np.full(K, np.inf)
    zf = z_land + (R - base) / tan_f
    outer_xy = p + dvec * R[:, None]
    inner_xy = offset_inward(outer_xy, w)
    for k in range(K):
        for q in (outer_xy[k], inner_xy[k], 0.5 * (outer_xy[k] + inner_xy[k])):
            cz = ceiling(q[0], q[1], zf[k] - 0.5)
            if cz is not None:
                raw[k] = min(raw[k], cz)
    zt = np.minimum(raw, np.minimum(np.roll(raw, 1), np.roll(raw, -1)))
    zt = np.where(np.isfinite(zt), zt, zf + 0.2)
    zt = np.maximum(zt, z_land + 0.4)
    J = int(np.clip(math.ceil((zt.max() - z_land) / 0.8), 4, 80))
    outer = np.empty((J + 1, K, 3))
    inner = np.empty((J + 1, K, 3))
    for j in range(J + 1):
        z = z_land + (zt - z_land) * j / J
        rr = np.minimum(base + np.maximum(z - z_land, 0.0) * tan_f, R)
        o = p + dvec * rr[:, None]
        outer[j, :, :2], outer[j, :, 2] = o, z
        inner[j, :, :2], inner[j, :, 2] = offset_inward(o, w), z
    return wall_shell(outer, inner), rho <= R[bins] + top.c


def _criss_cross(p, base: float, z_land: float, pts: np.ndarray, top: "_TopLookup", rc: VerticalRaycaster,
                 s: HybridSettings, tan_f: float, tip_h: float, thick: float, corners_only: bool = False):
    """One support built to size, with no hub: thin walls (fins) from one centre point, standing on the
    landing out to `base` and then rising at the flare angle to the edge of the overhang, their tops under
    the underside. The first go to the corners of the overhang (a criss-cross); more are added only where a
    bridge to the nearest fin, or to an edge that rests on a wall of the model, would be longer than Max
    bridge span. Returns (meshes, covered mask)."""
    K = 180
    fr = _flare_reach(p, base, z_land, pts, top, rc, s, tan_f, K)
    angles, rel, rho, phi, bins, reach = fr["angles"], fr["rel"], fr["rho"], fr["phi"], fr["bins"], fr["reach"]
    gap = s.bridge_gap if s.bridge_gap > 0 else 1e9
    cell = top.c
    zmin = float(pts[:, 2].min())
    backed = np.zeros(K, dtype=bool)
    for k, a in enumerate(angles):
        d = np.array([math.cos(a), math.sin(a)])
        for extra in (s.xy_clearance + 0.5, s.xy_clearance + 1.5):
            q = p + d * (reach[k] + extra)
            if rc.inside_many(q[0], q[1], [zmin - 0.5, zmin + 0.5]).any():
                backed[k] = True
                break
    wall_d = np.where(backed[bins], np.maximum(reach[bins] - rho, 0.0), np.inf)
    half = thick / 2

    def fin_dist(arms):
        d = np.full(len(rel), np.inf)
        for a, L in arms:
            u = np.array([math.cos(a), math.sin(a)])
            tt = np.clip(rel @ u, 0.0, L)
            d = np.minimum(d, np.maximum(np.linalg.norm(rel - tt[:, None] * u, axis=1) - half, 0.0))
        return d

    def reach_at(a):
        return reach[int(round(np.mod(a, 2 * np.pi) / (2 * np.pi / K))) % K]

    hull = convex_hull_2d(pts[:, :2])
    dirs = []
    if len(hull) >= 3:
        for i in range(len(hull)):
            a_, b_, c_ = hull[i - 1], hull[i], hull[(i + 1) % len(hull)]
            v1, v2 = a_ - b_, c_ - b_
            cosang = float(v1 @ v2 / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-12))
            if cosang > math.cos(math.radians(150)):
                dirs.append(math.atan2(b_[1] - p[1], b_[0] - p[0]))
    if len(dirs) < 2:
        dirs = [k * np.pi / 2 for k in range(4)]
    arms = []
    for a in dirs:
        if all(abs(math.remainder(a - b, 2 * np.pi)) > 0.35 for b, _ in arms):
            arms.append((a, reach_at(a)))
    tried = set()
    while len(arms) < s.max_lobes and not corners_only:
        span = 2 * np.minimum(fin_dist(arms), wall_d)
        worst = int(span.argmax())
        key = round(phi[worst], 2)
        if span[worst] <= gap + cell or key in tried:
            break
        tried.add(key)
        if all(abs(math.remainder(phi[worst] - b, 2 * np.pi)) > 0.2 for b, _ in arms):
            arms.append((phi[worst], reach_at(phi[worst])))
    meshes, built = [], []
    probe = zmin - 0.02
    for a, L in arms:
        u = np.array([math.cos(a), math.sin(a)])
        # each wall stands on the floor along its own line as far out as it must to reach its end at the
        # flare angle (or as far as the floor is clear), then rises at the flare angle
        q_end = p + u * L
        h_end = top(q_end[0], q_end[1])
        h_end = (zmin - s.contact_gap) if h_end is None else h_end
        want = float(np.clip(L - tan_f * (h_end - z_land - tip_h), base, L))
        foot = max(base, _arm_foot(rc, p, u, z_land, probe, want, s, half)) if want > base else base
        prof = _build_fin(p, u, L, foot, z_land, top, rc, s, tan_f, tip_h, thick, False, min_len=1.0)
        if prof is None:
            continue
        ss, zb, zt = prof
        built.append((a, float(ss[-1]), float(foot)))
        if half < 1.0:                                  # thin ribs: straight webs, plus a filleted hub below
            meshes.append(fin(p, u, ss, zb, zt, thick))
    covered = (2 * np.minimum(fin_dist([(a, L) for a, L, _ in built]), wall_d) <= gap + cell) if built \
        else np.zeros(len(pts), bool)
    if built:
        # wide lobes: the whole star; thin ribs: only its middle, to round the corners where they meet
        hub = None if half >= 1.0 else half + 2.5 * max(s.lobe_fillet, half)
        star = _petal_star(p, built, z_land, half, top, rc, s, tan_f, max_r=hub)
        if star is not None:
            meshes.append(star)
    return meshes, covered, len(built)


def _smax(a, b, k):
    """Smooth maximum: max(a, b) with the corner where they meet rounded over a width k."""
    if k <= 0:
        return np.maximum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.maximum(a, b) + h * h * k / 4.0


def _petal_star(p, arms, z_land: float, w: float, top: "_TopLookup", rc: VerticalRaycaster, s: HybridSettings,
                tan_f: float, max_r: Optional[float] = None) -> Optional[Mesh]:
    """One solid star of rounded lobes (petals) round p, printed hollow by Cura (walls only).

    arms: (angle, length, foot) per petal. Each petal is a capsule of half-width w from p along its angle;
    at height z it reaches out to foot + (z - z_land) * tan(flare), never beyond its length, so its end
    rises at the flare angle. The petals are joined with a smooth maximum of their outline radius, so the
    inner corners where they meet are rounded (filleted) instead of sharp notches. Each column of the
    outline stops under the overhang (or the model), and the outline is pulled in wherever it would come
    within the X/Y clearance of the model."""
    K = 96 if max_r is not None else 128            # about 1 mm steps at the lobe tips: fewer, longer moves
    th = np.linspace(0, 2 * np.pi, K, endpoint=False)
    dirs = np.column_stack([np.cos(th), np.sin(th)])
    fil = max(s.lobe_fillet, w)

    def radii(z):
        z = np.broadcast_to(np.asarray(z, dtype=float), (K,))
        R = np.full(K, w)
        for a, L, foot in arms:
            Lz = np.minimum(L, foot + np.maximum(z - z_land, 0.0) * tan_f)
            seg = np.maximum(Lz - w, 0.0)
            phi = np.remainder(th - a + np.pi, 2 * np.pi) - np.pi
            c, sn = np.cos(phi), np.abs(np.sin(phi))
            # where a ray from p leaves the capsule: through its round end, or through its side
            disc = w * w - (seg * sn) ** 2
            t_end = np.where(disc >= 0, seg * c + np.sqrt(np.maximum(disc, 0.0)), 0.0)
            with np.errstate(divide="ignore"):
                t_side = np.where(sn > 1e-9, w / sn, np.inf)
            side_ok = (t_side * c <= seg) & (t_side * c >= 0)
            Ri = np.maximum(np.where(side_ok, t_side, 0.0), np.maximum(t_end, w * (c < 0) + 0.0))
            Ri = np.minimum(Ri, np.maximum(Lz, w))
            R = _smax(R, Ri, fil)
        return R if max_r is None else np.minimum(R, max_r)

    def ceiling(x, y, z_from):
        v = top(x, y)
        a = rc.above(x, y, z_from)
        if a is not None:
            v = a - s.contact_gap if v is None else min(v, a - s.contact_gap)
        return v

    R_full = radii(1e6)
    zmin_top = min(float(top.d[k]) for k in top.d)
    zt = np.full(K, np.inf)
    for k in range(K):
        for r in np.append(np.arange(0.0, R_full[k], 1.0), R_full[k]):
            q = p + dirs[k] * r
            cz = ceiling(q[0], q[1], z_land + 0.3)
            if cz is not None:
                zt[k] = min(zt[k], cz)
    zt = np.where(np.isfinite(zt), zt, zmin_top)
    zt = np.minimum(zt, np.minimum(np.roll(zt, 1), np.roll(zt, -1)))
    zt = np.maximum(zt, z_land + 0.4)
    J = int(np.clip(math.ceil((zt.max() - z_land) / 0.4), 4, 150))
    Z = np.array([z_land + (zt - z_land) * j / J for j in range(J + 1)])          # (J+1, K)
    R = np.array([radii(Z[j]) for j in range(J + 1)])
    # keep the X/Y clearance from the model
    for j in range(J + 1):
        for k in range(K):
            zs = [Z[j, k] + 0.05, min(Z[j, k] + 0.2, zt[k] - 0.05)]
            while R[j, k] > w * 0.5:
                q = p + dirs[k] * (R[j, k] + s.xy_clearance)
                q2 = p + dirs[k] * R[j, k]
                if not (rc.inside_many(q[0], q[1], zs).any() or rc.inside_many(q2[0], q2[1], zs).any()):
                    break
                R[j, k] -= 0.5
    for j in range(1, J + 1):                       # never wider than the flare allows over the layer below
        R[j] = np.minimum(R[j], R[j - 1] + (Z[j] - Z[j - 1]) * tan_f + 1e-6)
    R = np.maximum(R, 0.3)
    verts = [[p[0], p[1], z_land], [p[0], p[1], float(zt.max())]]
    for j in range(J + 1):
        for k in range(K):
            verts.append([p[0] + dirs[k, 0] * R[j, k], p[1] + dirs[k, 1] * R[j, k], Z[j, k]])
    verts = np.array(verts)

    def vid(j, k):
        return 2 + j * K + (k % K)
    faces = []
    for k in range(K):
        faces.append([0, vid(0, k + 1), vid(0, k)])
        faces.append([1, vid(J, k), vid(J, k + 1)])
        for j in range(J):
            a, b, c, d = vid(j, k), vid(j, k + 1), vid(j + 1, k + 1), vid(j + 1, k)
            faces += [[a, b, c], [a, c, d]]
    m = Mesh(verts, np.array(faces, dtype=np.int64))
    if m.volume() < 0:
        m.faces = m.faces[:, ::-1]
    return m


def build_unit(r: Region, rc: VerticalRaycaster, s: HybridSettings, uid: int, depth: int = 0) -> List[SupportUnit]:
    tan_f = math.tan(math.radians(s.max_flare_angle))
    tip_h = 1.5
    notes: List[str] = []
    pts = r.pts
    span = float(np.ptp(pts[:, :2], axis=0).max()) if len(pts) > 1 else 0.0
    if span > s.max_span and depth < 6:
        return [u for part in split_region(r) for u in build_unit(part, rc, s, uid, depth + 1)]
    if float((pts[:, 2] - r.land).max()) <= s.low_gap:
        return _low_unit(r, rc, s, uid, notes)
    if s.head_mode == "tethers":
        tn: List[str] = []
        t = _tether_unit(r, rc, s, uid, tn)
        if t is not None:
            return [t]
        # why not: walls too far apart (probe with a longer search) or really nothing to tie to
        why = "no walls to tether to: lobes"
        probe: List[str] = []
        try:
            if _tether_unit(r, rc, dataclasses.replace(s, tether_max_span=max(400.0, 3 * s.tether_max_span)), uid, probe) is not None:
                for n_ in probe:
                    if n_.startswith("tether span ") and float(n_.split()[2]) > s.tether_max_span:
                        why = (f"tethers: the walls are {n_.split()[2]} mm apart, over the {s.tether_max_span:.0f} mm limit "
                               f"(unpredictable past {s.tether_warn_span:.0f}): lobes instead")
        except Exception:
            pass
        why = "; ".join([n_ for n_ in tn if "tethers would leave" in n_] + [why]) if any("tethers would leave" in n_ for n_ in tn) else why
        s = dataclasses.replace(s, head_mode="lobes")   # nothing to tie to: use lobes here
        if s.tower_cap and not getattr(r, "capped", False):     # with an interface cap, like every tower
            low, pieces = _plan_caps(r, rc, s)
            out = build_unit(low, rc, s, uid, depth)
            if out:
                out[0].notes.insert(0, why)
                _attach_caps(out[0], pieces, s)
            return out
        notes.append(why)

    place, miss = _place_trunk(r, rc, s, tan_f, tip_h)
    if place is None and s.head_mode in ("lobes", "branch", "cone") and s.lobes_one_tower:
        fit, _ = _place_trunk(r, rc, s, tan_f, tip_h, fit=True)    # one support built to size: a criss-cross
        if fit is not None:
            thick = (max(2, s.branch_lines) if s.head_mode == "branch" else 2) * s.line_width
            thick = max(thick, _min_thick(s))
            if s.head_mode == "lobes" and s.print_walls:
                # wide rounded lobes, printed hollow: two walls far apart are much stiffer against the
                # nozzle than a 2-line slab, so fewer are needed
                thick = s.lobe_width if s.lobe_width > 0 else 8.0
            top = _TopLookup(r, s.contact_gap)
            cone = s.head_mode == "cone"
            fins, cov_mask, n_arms = _criss_cross(fit["p"], fit["rt"], fit["z_land"], pts, top, rc, s, tan_f, tip_h, thick,
                                          corners_only=cone)
            if fins and cone:                          # one thin cone round the ribs: they only need to reach the corners
                w = max(1, s.cone_wall_lines) * s.line_width
                shell, reach_mask = _cone_shell(fit["p"], fit["rt"], fit["z_land"], pts, top, rc, s, tan_f, w)
                fins = [shell] + fins
                cov_mask = cov_mask | reach_mask
            coverage = float((cov_mask | ~_reachable(pts, rc, s.xy_clearance)).mean()) if fins else 0.0
            if fins and (coverage >= s.min_fit_coverage or depth >= 5):   # else split, as before
                if cone:
                    notes.append(f"one cone built to size: {max(1, s.cone_wall_lines)}-line wall, {n_arms} rib(s) "
                                 f"{thick / s.line_width:.0f} lines thick inside, no hub")
                else:
                    notes.append(f"one criss-cross built to size: {n_arms} " + (f"rounded lobe(s) {thick:.0f} mm wide, filleted, " if thick >= 2.0 else f"wall(s) {thick / s.line_width:.0f} lines thick, ") +
                                 "no hub")
                if coverage < 0.98:
                    notes.append(f"reaches {100 * coverage:.0f}% of this overhang")
                return [SupportUnit(uid, Mesh.concat(fins), _blocker(pts, s), fit["z_land"], fit["z_land"],
                                    float(pts[:, 2].min()), fit["z_land"] == 0.0, notes,
                                    (float(fit["p"][0]), float(fit["p"][1])), 0.0, n_arms, coverage, pts)]
    if place is None:
        if depth < 5 and len(pts) >= 8:
            parts = split_region(r)
            if len(parts) > 1:
                return [u for part in parts for u in build_unit(part, rc, s, uid, depth + 1)]
        if s.head_mode == "branch":
            return _low_unit(r, rc, s, uid, notes)
        if miss is None:
            return []
        keep = miss["need"] >= miss["z_land"]
        if keep.sum() < 2:
            return []
        notes.append(f"{100 * (1 - keep.mean()):.0f}% of this overhang is too wide for its height")
        r = Region(pts[keep], r.land[keep], r.cell)
        pts = r.pts
        place = {"p": miss["p"], "rt": miss["rt"], "z_land": miss["z_land"],
                 "z_h0": float(miss["need"][keep].min()), "dist": miss["dist"][keep]}

    p, rt, z_land, z_h0 = place["p"], place["rt"], place["z_land"], place["z_h0"]
    wall = max(1, s.wall_lines) * s.line_width
    top = _TopLookup(r, s.contact_gap)
    parts: List[Mesh] = []
    trunk_h = z_h0 - z_land
    hub_top = top(p[0], p[1])
    if hub_top is None:
        hub_top = float(pts[:, 2].min()) - s.contact_gap
    hub_top = max(hub_top, z_h0 + 0.5)
    has_trunk = trunk_h >= 1.0
    if not has_trunk:
        z_h0 = z_land
    coverage, n_br = 1.0, 0

    if s.head_mode == "lobes":
        if has_trunk:
            parts.append(tube(p[0], p[1], rt, rt - wall, z_land, hub_top, s.segments))
        lobe_meshes, cov_mask, n_br = _lobe_head(p, rt, wall, z_h0, pts, top, rc, s, tan_f)
        parts += lobe_meshes
        coverage = float((cov_mask | ~_reachable(pts, rc, s.xy_clearance)).mean())
        if coverage < s.min_fit_coverage and depth < 5 and len(pts) >= 8:
            more = split_region(r)                      # too big for one: two (or more) towers reach further
            if len(more) > 1:
                return [u for part in more for u in build_unit(part, rc, s, uid, depth + 1)]
        if coverage < 0.98:
            notes.append(f"lobes reach {100 * coverage:.0f}% of this overhang")
    elif s.head_mode == "cone":
        if has_trunk:
            parts.append(tube(p[0], p[1], rt, rt - wall, z_land, hub_top, s.segments))
        cone_meshes, cov_mask = _cone_head(p, rt, wall, z_h0, pts, top, rc, s, tan_f)
        parts += cone_meshes
        n_br = len(cone_meshes) - 1
        reach_ok = _reachable(pts, rc, s.xy_clearance)
        coverage = float((cov_mask | ~reach_ok).mean())
        if coverage < s.min_fit_coverage and depth < 5 and len(pts) >= 8:
            more = split_region(r)                      # too big for one: two (or more) towers reach further
            if len(more) > 1:
                return [u for part in more for u in build_unit(part, rc, s, uid, depth + 1)]
        if coverage < 0.98:
            notes.append(f"cone reaches {100 * coverage:.0f}% of this overhang")
    elif s.head_mode == "branch":
        thick = max(s.branch_lines * s.line_width, _min_thick(s))
        if has_trunk:
            parts.append(tube(p[0], p[1], rt, rt - wall, z_land, hub_top, s.segments))
        fins, cov_mask = _branches(p, rt, z_h0, pts, top, rc, s, tan_f, tip_h, thick, standing=False)
        coverage = float((cov_mask | ~_reachable(pts, rc, s.xy_clearance)).mean())
        parts += fins
        n_br = len(fins)
        if coverage < s.min_fit_coverage and depth < 5 and len(pts) >= 8:
            more = split_region(r)                      # too big for one: two (or more) towers reach further
            if len(more) > 1:
                return [u for part in more for u in build_unit(part, rc, s, uid, depth + 1)]
        if coverage < 0.98:
            notes.append(f"branches reach {100 * coverage:.0f}% of this overhang")
        if not parts:
            return []
    else:
        hull = convex_hull_2d(pts[:, :2])
        if len(hull) < 3:
            return []
        min_head = s.head_fraction * (float(pts[:, 2].min()) - z_land)
        z_h0 = min(z_h0, float(pts[:, 2].min()) - s.contact_gap - min_head)
        z_h0 = max(z_h0, z_land)
        has_trunk = z_h0 - z_land >= 1.0
        if has_trunk:
            parts.append(tube(p[0], p[1], rt, rt - wall, z_land, z_h0, s.segments))
        zmin_gap = float(pts[:, 2].min()) - s.contact_gap
        z_base = z_h0

        def ray_cap(x, y, v):        # never let the head top poke into the model
            a = rc.above(x, y, z_base + 0.05)
            return v if a is None else min(v, a - s.contact_gap)

        if s.head_mode == "conform":
            def top_fn(x, y):
                v = top(x, y)
                return ray_cap(x, y, zmin_gap if v is None else v)
        else:
            def top_fn(x, y):
                return ray_cap(x, y, zmin_gap)
        parts.append(_head(p, rt, z_h0 - 0.05 if has_trunk else z_h0, hull, top_fn, s))

    if has_trunk:
        parts += _gussets(p, rt, wall, z_land, z_h0 - z_land, rc, s, notes)
    return [SupportUnit(uid, Mesh.concat(parts), _blocker(pts, s), z_land, z_h0 if has_trunk else z_land,
                        float(pts[:, 2].min()), z_land == 0.0, notes, (float(p[0]), float(p[1])), rt,
                        n_br, coverage, pts)]


def generate(vertices: np.ndarray, faces: np.ndarray, s: Optional[HybridSettings] = None) -> List[SupportUnit]:
    """Main entry point. vertices (N,3) Z-up mm, faces (M,3) int."""
    s = s or HybridSettings()
    tris = np.asarray(vertices, dtype=np.float64)[np.asarray(faces)]
    rc = VerticalRaycaster(tris)
    units: List[SupportUnit] = []
    regions = find_regions(tris, rc, s)
    if s.head_mode == "tethers":  # the biggest overhang picks the shared line direction
        regions = sorted(regions, key=lambda r: -len(r.pts))
        s = dataclasses.replace(s, tether_dir=None)
    for region in regions:
        pieces = []
        if s.tower_cap and s.head_mode != "tethers":
            # interface caps first: the tower is then built up to the caps' undersides (where a cap fits)
            region, pieces = _plan_caps(region, rc, s)
        built = build_unit(region, rc, s, len(units))
        for k, u in enumerate(built):
            if len(u.support.faces):
                u.island_id = len(units)
                # tethers need Cura's support roof and pattern; the solid heads are meant to be filled
                solid = s.head_mode in ("trapezoid", "conform") and not any("standing webs" in n for n in u.notes)
                u.print_as = "walls" if (s.print_walls and u.tether_dir is None and not solid) else "support"
                if pieces:
                    _attach_caps(u, pieces, s)
                    pieces = []
                units.append(u)
                if u.tether_dir is not None and s.tether_dir is None:
                    s = dataclasses.replace(s, tether_dir=u.tether_dir)
    return units


# --------------------------------------------------------------------------
# Solid heads (trapezoid / conform) and debug export
# --------------------------------------------------------------------------

def _head(centre, r_base, z_base, hull, top_z_fn, s: HybridSettings) -> Mesh:
    """Star-shaped closed head: circle at z_base flaring to the hull at the top.

    Top surface is a polar grid; each sample's height comes from top_z_fn.
    """
    seg, rings = s.segments, max(1, s.head_rings)
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    rad = radial_profile(hull, centre, ang)
    rad = np.maximum(rad, r_base)   # never narrower than the tube
    v = [[centre[0], centre[1], z_base]]                       # 0 bottom centre
    for k in range(seg):                                       # 1..seg bottom circle
        v.append([centre[0] + r_base * math.cos(ang[k]), centre[1] + r_base * math.sin(ang[k]), z_base])
    top_c = len(v)
    v.append([centre[0], centre[1], top_z_fn(centre[0], centre[1])])
    ring_start = len(v)
    for r_i in range(1, rings + 1):                            # top polar grid
        t = r_i / rings
        for k in range(seg):
            x = centre[0] + rad[k] * t * math.cos(ang[k])
            y = centre[1] + rad[k] * t * math.sin(ang[k])
            v.append([x, y, top_z_fn(x, y)])
    v = np.array(v)
    v[top_c + 1:, 2] = np.maximum(v[top_c + 1:, 2], z_base + 0.2)
    v[top_c, 2] = max(v[top_c, 2], z_base + 0.2)

    def ring(r_i, k):
        return ring_start + (r_i - 1) * seg + (k % seg)

    f = []
    for k in range(seg):
        j = (k + 1) % seg
        f.append([0, 1 + j, 1 + k])                           # bottom disc (down)
        f.append([top_c, ring(1, k), ring(1, j)])             # top centre fan (up)
        for r_i in range(1, rings):
            a, b = ring(r_i, k), ring(r_i, j)
            c, d = ring(r_i + 1, k), ring(r_i + 1, j)
            f += [[a, c, d], [a, d, b]]
        o_k, o_j = ring(rings, k), ring(rings, j)              # side skirt
        f += [[1 + k, 1 + j, o_j], [1 + k, o_j, o_k]]
    m = Mesh(v, np.array(f))
    if m.volume() < 0:
        m.faces = m.faces[:, ::-1]
    return m


def write_stl(path: str, mesh: Mesh) -> None:
    import struct
    with open(path, "wb") as fh:
        fh.write(b"hybrid_core".ljust(80, b" "))
        fh.write(struct.pack("<I", len(mesh.faces)))
        for f in mesh.faces:
            a, b, c = mesh.vertices[f]
            n = np.cross(b - a, c - a)
            ln = np.linalg.norm(n)
            n = n / ln if ln > 0 else n
            fh.write(struct.pack("<12fH", *n, *a, *b, *c, 0))
