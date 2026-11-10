# Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
# Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.
"""G-code step for straight tethers: shift every other layer's tether lines by half a line width.

Cura can't do this from mesh shapes: it slices support meshes at both the bottom and the top of
each layer and keeps what the two slices share, so a strip that moves 0.2 mm every other layer
comes out as one constant strip. After slicing, this moves the support lines that lie inside a
tether strip on every odd layer sideways (across the strip), so consecutive layers only half
overlap and the tether snaps apart easily. Pure Python, no Cura imports.
"""
import math
import re
from typing import Dict, List, Sequence

MARK = ";HYBRID_SUPPORTS_STAGGER"
_NUM = re.compile(r"([XYZEF])(-?\d+\.?\d*)")


def _inside(poly, x: float, y: float) -> bool:
    n = len(poly)
    c = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            c = not c
        j = i
    return c


def _fmt(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def stagger(gcode_list: Sequence[str], plans: List[Dict], offset=(0.0, 0.0)) -> List[str]:
    """Return a new G-code list with tether lines shifted on odd layers.

    plans: dicts with "polys" (strip outlines in model XY, slightly enlarged), "shift" (dx, dy),
    "z" (lowest, highest tether layer top), "h0" and "lh" (initial and normal layer height).
    offset: added to model XY to get G-code XY (Cura puts the bed centre at the model origin).
    """
    out = list(gcode_list)
    plans = [p for p in (plans or []) if p.get("shift") is not None and p.get("polys")]
    if not plans or not out or MARK in out[0]:
        return out
    ox, oy = offset
    # work on all lines at once: the travel into a layer's first tether line is often written at the
    # end of the previous layer's chunk
    chunks = [c.split("\n") for c in out]
    lines = [ln for c in chunks for ln in c]
    types, cur = [], ""
    for line in lines:                           # feature type in force at each line
        if line.startswith(";TYPE:"):
            cur = line[6:].strip()
        types.append(cur)
    next_type, nt = [""] * len(lines), ""
    for li in range(len(lines) - 1, -1, -1):     # type of the next extruding move after each line
        line = lines[li]
        if line.startswith(("G0", "G1")) and " E" in line.split(";")[0]:
            nt = types[li]
        next_type[li] = nt
    shifted = 0
    z = 0.0
    x = y = 0.0
    for li, line in enumerate(lines):
        if not line.startswith(("G0", "G1")):
            continue
        body, sep, comment = line.partition(";")
        found = _NUM.findall(body)
        vals = dict((k, float(v)) for k, v in found)
        if "Z" in vals:
            z = vals["Z"]
        nx, ny = vals.get("X", x), vals.get("Y", y)
        travel = "E" not in vals
        wanted = (types[li] == "SUPPORT") if not travel else (next_type[li] == "SUPPORT")
        if ("X" in vals or "Y" in vals) and wanted:
            for p in plans:
                lo, hi = p["z"]
                if not (lo - 1e-3 <= z <= hi + 1e-3):
                    continue
                if int(round((z - p["h0"]) / p["lh"])) % 2 == 0:
                    continue
                if not any(_inside(poly, nx - ox, ny - oy) for poly in p["polys"]):
                    continue
                dx, dy = p["shift"]
                vals["X"], vals["Y"] = nx + dx, ny + dy
                present = set(k for k, _ in found) | {"X", "Y"}
                parts = [body.split()[0]] + [k + _fmt(vals[k]) for k in ("F", "X", "Y", "Z", "E") if k in present]
                lines[li] = " ".join(parts) + (sep + comment if sep else "")
                shifted += 1
                break
        x, y = nx, ny
    pos = 0
    for ci, c in enumerate(chunks):
        out[ci] = "\n".join(lines[pos:pos + len(c)])
        pos += len(c)
    out[0] = out[0] + MARK + f" {shifted} moves\n"
    return out


MARK_SLOW = ";HYBRID_SUPPORTS_SLOW_BRIDGE"
_FAN = re.compile(r"^M106(?:\s+P\d+)?\s+S(\d+\.?\d*)")


def slow_bridges(gcode_list: Sequence[str], plans: List[Dict], offset=(0.0, 0.0)) -> List[str]:
    """Slow down (and cool) the first tether layers, which are bridges in mid-air.

    Cura prints support at the support speed (165 mm/s on the Neptune 4 profile) and its bridge
    settings don't apply to support, so a 40 mm tether bridge would be flung out at that speed.
    plans: dicts with "slow": {"poly", "z": (first layer top, last layer top), "speed" mm/s,
    "flow" multiplier, "fan" 0..1, optional "types" (default SUPPORT only); speed 0 keeps Cura's}; "slow" may also be a list of those. Every extruding SUPPORT move inside the polygon on those layers
    gets that speed and flow; the fan is turned up while it lasts and put back after. Extrusion is
    absolute (M82) in Cura's Marlin output, so the extra filament is carried through the later E
    values; with relative extrusion (M83) each move is just scaled. Never applied twice.
    """
    out = list(gcode_list)
    flat = []
    for p in plans or []:
        sl = p.get("slow")
        flat += sl if isinstance(sl, list) else ([sl] if sl else [])
    plans = flat
    if not plans or not out or MARK_SLOW in out[0]:
        return out
    ox, oy = offset
    chunks = [c.split("\n") for c in out]
    lines = [ln for c in chunks for ln in c]
    types, cur = [], ""
    for line in lines:
        if line.startswith(";TYPE:"):
            cur = line[6:].strip()
        types.append(cur)
    relative = any(ln.startswith("M83") for ln in lines[:400])
    z = x = y = 0.0
    e_prev = 0.0         # E as Cura wrote it (absolute mode)
    extra = 0.0          # filament added so far by flow > 1
    f_orig = f_sent = None   # feed rate Cura believes is in force / the one the printer really has
    fan = 0.0            # fan value Cura believes is in force
    fan_up = None        # the value we hold the fan at, or None
    moved = 0
    new: List[str] = []
    marks: List[int] = []   # where each original line starts in `new` (lines get inserted)
    for li, line in enumerate(lines):
        marks.append(len(new))
        if line.startswith("G92"):
            m = re.search(r"E(-?\d+\.?\d*)", line)
            if m:
                e_prev, extra = float(m.group(1)), 0.0
            new.append(line)
            continue
        fm = _FAN.match(line)
        if fm or line.startswith("M107"):
            fan = float(fm.group(1)) if fm else 0.0
            new.append(f"M106 S{fan_up} ; (fan held up by Hybrid Supports)" if fan_up is not None else line)
            continue
        if not line.startswith(("G0", "G1")):
            new.append(line)
            continue
        body, sep, comment = line.partition(";")
        found = _NUM.findall(body)
        vals = dict((k, float(v)) for k, v in found)
        if "Z" in vals:
            z = vals["Z"]
        nx, ny = vals.get("X", x), vals.get("Y", y)
        x, y = nx, ny
        has_xy = "X" in vals or "Y" in vals
        slow = None
        if "E" in vals and has_xy and types[li].startswith("SUPPORT"):
            for sp in plans:
                lo, hi = sp["z"]
                if types[li] in sp.get("types", ("SUPPORT",)) and lo - 1e-3 <= z <= hi + 1e-3 and _inside(sp["poly"], nx - ox, ny - oy):
                    slow = sp
                    break
        if "F" in vals:
            f_orig = vals["F"]
        pre = []
        if slow:
            want = int(round(slow.get("fan", 0.0) * 255))
            if fan_up is None and want > fan:
                pre.append(f"M106 S{want} ; (bridge: fan up, Hybrid Supports)")
                fan_up = want
        elif fan_up is not None and "E" in vals and has_xy:
            pre.append(f"M106 S{int(round(fan))} ; (bridge over: fan back)")
            fan_up = None
        e_new = None
        if "E" in vals:
            if relative:
                e_new = vals["E"] * (slow["flow"] if slow else 1.0)
            else:
                d = vals["E"] - e_prev
                if slow and d > 0:
                    extra += d * (slow["flow"] - 1.0)
                e_prev = vals["E"]
                e_new = vals["E"] + extra
        want_f = slow["speed"] * 60.0 if slow and slow.get("speed", 0) > 0 else f_orig
        move = has_xy or "E" in vals
        set_f = move and want_f is not None and (f_sent is None or abs(want_f - f_sent) > 1e-6)
        edit_e = e_new is not None and abs(e_new - vals["E"]) > 1e-9
        if set_f or edit_e:
            present = set(k for k, _ in found)
            if set_f:
                vals["F"] = want_f
                present.add("F")
            if edit_e:
                vals["E"] = e_new
            line = " ".join([body.split()[0]] + [k + _fmt(vals[k]) for k in ("F", "X", "Y", "Z", "E") if k in present]) \
                + (sep + comment if sep else "")
            if slow:
                moved += 1
        elif slow:
            moved += 1
        if move and want_f is not None:
            f_sent = want_f
        elif "F" in vals:
            f_sent = vals["F"]
        new.extend(pre)
        new.append(line)
    marks.append(len(new))
    pos = 0
    for ci, c in enumerate(chunks):
        out[ci] = "\n".join(new[marks[pos]:marks[pos + len(c)]])
        pos += len(c)
    out[0] = out[0] + MARK_SLOW + f" {moved} moves\n"
    return out


# ---------------------------------------------------------------------------------------------
# The cap stack: what lies across the tethers, written here because Cura can't change pattern or
# density from layer to layer: lattice (across the tethers), lattice (along them), rings with an
# open middle (50 % fill), then a solid diagonal layer that closes the middle.
# ---------------------------------------------------------------------------------------------
MARK_CAP = ";HYBRID_SUPPORTS_CAP_STACK"
_FIL_AREA = math.pi * (1.75 / 2.0) ** 2


def _hull(points):
    pts = sorted(set((round(float(x), 4), round(float(y), 4)) for x, y in points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _ccw(poly):
    """A clean convex counter-clockwise outline: the hull of the points, without the tiny edges that
    offsetting leaves at corners (they make the edge half-planes cut the wrong way)."""
    hull = _hull(poly)
    if len(hull) < 4:
        return hull
    out = [hull[0]]
    for p in hull[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= 0.5:
            out.append(p)
    if len(out) > 3 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 0.5:
        out.pop()
    return out if len(out) >= 3 else hull


def _clip_keep(poly, nx, ny, c):
    """Keep the part of a polygon with n . p >= c."""
    res = []
    m = len(poly)
    for i in range(m):
        a, b = poly[i], poly[(i + 1) % m]
        da, db = a[0] * nx + a[1] * ny - c, b[0] * nx + b[1] * ny - c
        if da >= 0:
            res.append(a)
        if (da >= 0) != (db >= 0):
            tt = da / (da - db)
            res.append((a[0] + tt * (b[0] - a[0]), a[1] + tt * (b[1] - a[1])))
    return res


def shrink_convex(poly, d):
    """A convex polygon moved inwards by d (empty list when nothing is left)."""
    pts = _ccw(poly)
    out = pts
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        ln = math.hypot(ex, ey)
        if ln < 1e-9:
            continue
        nx, ny = -ey / ln, ex / ln                     # inward for a counter-clockwise polygon
        out = _clip_keep(out, nx, ny, x0 * nx + y0 * ny + d)
        if len(out) < 3:
            return []
    return out


def _min_width(poly):
    best = float("inf")
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        ln = math.hypot(x1 - x0, y1 - y0)
        if ln < 1e-9:
            continue
        nx, ny = -(y1 - y0) / ln, (x1 - x0) / ln
        proj = [px * nx + py * ny for px, py in poly]
        best = min(best, max(proj) - min(proj))
    return best


def _chord(poly, px, py, ux, uy):
    """Where the line p + t u lies inside a convex counter-clockwise polygon: (t0, t1) or None."""
    t0, t1 = -1e9, 1e9
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        ln = math.hypot(x1 - x0, y1 - y0)
        if ln < 1e-9:
            continue
        nx, ny = -(y1 - y0) / ln, (x1 - x0) / ln
        den = ux * nx + uy * ny
        num = (x0 - px) * nx + (y0 - py) * ny          # need t * den >= num
        if abs(den) < 1e-12:
            if num > 1e-9:
                return None
            continue
        if den > 0:
            t0 = max(t0, num / den)
        else:
            t1 = min(t1, num / den)
    return (t0, t1) if t1 - t0 > 1e-6 else None


def hatch(poly, angle, pitch):
    """Parallel lines across a convex polygon at the given angle (radians) and spacing, joined into one
    zigzag path (the joins run inside the polygon). Returns a list of points."""
    poly = _ccw(poly)
    ux, uy = math.cos(angle), math.sin(angle)
    vx, vy = -uy, ux
    proj = [px * vx + py * vy for px, py in poly]
    lo, hi = min(proj), max(proj)
    count = int((hi - lo) / pitch + 1e-9) + 1
    start = 0.5 * (lo + hi) - 0.5 * (count - 1) * pitch
    path = []
    flip = False
    for k in range(count):
        v = start + k * pitch
        ch = _chord(poly, vx * v, vy * v, ux, uy)
        if ch is None or ch[1] - ch[0] < 0.4:
            continue
        a = (vx * v + ux * ch[0], vy * v + uy * ch[0])
        b = (vx * v + ux * ch[1], vy * v + uy * ch[1])
        path += [b, a] if flip else [a, b]
        flip = not flip
    return path


def rings(poly, width, density, hole):
    """Concentric outlines of a convex polygon, spaced width / density apart, continuing inwards until the
    middle is narrower than hole; one path (each loop closes, then steps in to the next)."""
    step = width / max(density, 0.05)
    path = []
    k = 0
    while True:
        r = shrink_convex(poly, 0.5 * width + k * step)
        if len(r) < 3 or _min_width(r) < hole:
            break
        path += r + [r[0]]
        k += 1
    return path


def _stack_kinds(n):
    if n <= 1:
        return ["diag"] * n
    if n == 2:
        return ["lat1", "diag"]
    if n == 3:
        return ["lat1", "ring", "diag"]
    return ["lat1", "lat2"] + ["ring"] * (n - 3) + ["diag"]


def cap_stack(gcode_list: Sequence[str], plans: List[Dict], offset=(0.0, 0.0)) -> List[str]:
    """Replace the cap's support-roof layers under the tethers with the cap stack.

    plans: dicts with "capstack": {"poly" (convex cap outline, model XY), "angle" (tether direction, rad),
    "pitch" (lattice spacing), "density" (ring fill), "hole" (open middle width), "flow" (first lattice
    layer's flow multiplier), "width", "lh"}. The moves Cura wrote for the cap (SUPPORT-INTERFACE inside the
    outline, and the travels into them) are removed layer by layer and the plugin's own paths are written in
    their place: layer 1 lattice across the tethers, layer 2 lattice along them, then rings, then the
    diagonal layer. Extrusion per mm follows what Cura used for its own roof lines. Retraction and the
    absolute-E bookkeeping follow the file. Never applied twice.
    """
    out = list(gcode_list)
    caps = [p["capstack"] for p in (plans or []) if p.get("capstack")]
    if not caps or not out or MARK_CAP in out[0]:
        return out
    ox, oy = offset
    caps = [cp for cp in caps if len(shrink_convex(cp["poly"], 0.5 * cp["width"])) >= 3
            and len(hatch(shrink_convex(cp["poly"], 0.5 * cp["width"]), 0.0, cp["width"])) >= 2]
    if not caps:
        return out
    chunks = [c.split("\n") for c in out]
    lines = [ln for c in chunks for ln in c]
    n = len(lines)
    types, cur = [], ""
    meshes, cur_mesh = [], ""
    for line in lines:
        if line.startswith(";TYPE:"):
            cur = line[6:].strip()
        elif line.startswith(";MESH:"):
            cur_mesh = line[6:].strip()
        types.append(cur)
        meshes.append(cur_mesh)
    relative = any(ln.startswith("M83") for ln in lines[:400])
    f_at = [None] * n
    de = [0.0] * n
    seg = [0.0] * n
    xy_at = [None] * n
    has_e = [False] * n
    extr = [False] * n
    e_only = [None] * n
    layer_at = [0] * n
    x = y = 0.0
    f = None
    e_prev = 0.0
    layer = 0
    retract, retract_f = 0.0, None
    for li, line in enumerate(lines):
        if line.startswith(";LAYER:"):
            layer += 1
        layer_at[li] = layer
        if line.startswith("G92"):
            m = re.search(r"E(-?\d+\.?\d*)", line)
            if m:
                e_prev = float(m.group(1))
        elif line.startswith(("G0", "G1")):
            vals = dict((k, float(v)) for k, v in _NUM.findall(line.partition(";")[0]))
            if "F" in vals:
                f = vals["F"]
            nx, ny = vals.get("X", x), vals.get("Y", y)
            has_xy = "X" in vals or "Y" in vals
            if "E" in vals:
                d = vals["E"] if relative else vals["E"] - e_prev
                if not relative:
                    e_prev = vals["E"]
                de[li], has_e[li] = d, True
                if has_xy and d > 0:
                    extr[li] = True
                if not has_xy:
                    e_only[li] = d
                    if d < -0.2 and retract == 0.0:
                        retract, retract_f = -d, f
            seg[li] = math.hypot(nx - x, ny - y)
            if has_xy:
                xy_at[li] = (nx, ny)
            x, y = nx, ny
        f_at[li] = f
    nxt_layer, nxt_type, nxt_mesh = [0] * n, [""] * n, [""] * n
    nl, nt, nm = 0, "", ""
    for li in range(n - 1, -1, -1):
        if extr[li]:
            nl, nt, nm = layer_at[li], types[li], meshes[li]
        nxt_layer[li], nxt_type[li], nxt_mesh[li] = nl, nt, nm

    drop = {}                                   # line index -> (plan, layer)
    groups = []                                 # per plan: {layer: [line indexes]}
    for pi, cp in enumerate(caps):
        poly = _ccw(cp["poly"])
        grown = _ccw(_grow(poly, 0.3))
        prefix = cp.get("mesh_prefix")      # a cap printed as its own mesh (towers): every line of that mesh
        g = {}

        def ours(i, nxt=False):
            if prefix:
                return (nxt_mesh[i] if nxt else meshes[i]).startswith(prefix)
            return (nxt_type[i] if nxt else types[i]) == "SUPPORT-INTERFACE"
        for li in range(n):
            if xy_at[li] is None or li in drop:
                continue
            if extr[li]:
                if not ours(li):
                    continue
                key = layer_at[li]
            elif not has_e[li] and ours(li, True):
                key = nxt_layer[li]
            else:
                continue
            if _inside(grown, xy_at[li][0] - ox, xy_at[li][1] - oy):
                g.setdefault(key, []).append(li)
                drop[li] = (pi, key)
        g = {k: v for k, v in g.items() if any(extr[i] for i in v)}
        for k in list(drop):
            if drop[k][0] == pi and drop[k][1] not in g:
                del drop[k]
        groups.append(g)
    if not drop:
        out[0] = out[0] + MARK_CAP + " 0 layers\n"
        return out

    paths = {}                                  # (plan, kind) -> points in G-code XY
    insert_at, info = {}, {}
    done = 0
    for pi, cp in enumerate(caps):
        g = groups[pi]
        ks = _stack_kinds(len(g))
        poly = _ccw(cp["poly"])
        ang = cp["angle"]
        edge = shrink_convex(poly, 0.5 * cp["width"])
        for kind in set(ks):
            if kind == "lat1":
                pts = hatch(edge, ang + math.pi / 2, cp["pitch"])
            elif kind == "lat2":
                pts = hatch(edge, ang, cp["pitch"])
            elif kind == "ring":
                pts = rings(poly, cp["width"], cp["density"], cp["hole"])
            else:
                pts = hatch(edge, ang + math.pi / 4, cp["width"])
            paths[(pi, kind)] = [(px + ox, py + oy) for px, py in pts]
        for layer_key, kind in zip(sorted(g), ks):
            idx = g[layer_key]
            insert_at[max(idx)] = (pi, layer_key)
            first_e = next(i for i in idx if extr[i])
            kref = next((de[i] / seg[i] for i in idx if extr[i] and seg[i] > 1.0), cp["width"] * cp["lh"] / _FIL_AREA)
            tf = next((f_at[i] for i in idx if not has_e[i] and f_at[i]), None) or 12000.0
            info[(pi, layer_key)] = {"kind": kind, "f": f_at[first_e] or 3000.0, "k": kref * (cp["flow"] if kind == "lat1" else 1.0),
                                     "tf": tf}
            done += 1

    new: List[str] = []
    marks: List[int] = []
    e_orig = 0.0
    extra = 0.0
    retracted = False
    for li, line in enumerate(lines):
        marks.append(len(new))
        if line.startswith("G92"):
            m = re.search(r"E(-?\d+\.?\d*)", line)
            if m:
                e_orig, extra = float(m.group(1)), 0.0
            new.append(line)
            continue
        is_move = line.startswith(("G0", "G1"))
        body, sep, comment = line.partition(";")
        vals = dict((k, float(v)) for k, v in _NUM.findall(body)) if is_move else {}
        if is_move and has_e[li]:
            d = de[li]
            if not relative:
                e_orig = vals["E"]
        else:
            d = 0.0
        if li in drop:
            if not relative and has_e[li]:
                extra -= d
            if "Z" in vals:
                new.append(f"G0 Z{_fmt(vals['Z'])}")
            retracted = False if extr[li] else retracted
        else:
            if is_move and has_e[li]:
                if e_only[li] is not None:
                    retracted = e_only[li] < -0.05 if abs(e_only[li]) > 0.05 else retracted
                else:
                    retracted = False
                if not relative and abs(extra) > 1e-9:
                    vals["E"] = e_orig + extra
                    present = set(k for k, _ in _NUM.findall(body))
                    line = " ".join([body.split()[0]] + [k + _fmt(vals[k]) for k in ("F", "X", "Y", "Z", "E") if k in present]) \
                        + (sep + comment if sep else "")
            new.append(line)
        if li in insert_at:
            pi, layer_key = insert_at[li]
            inf = info[(pi, layer_key)]
            pts = paths[(pi, inf["kind"])]
            lines_out = [f";cap stack: {inf['kind']}  (Hybrid Supports)"]
            if types[li] != "SUPPORT-INTERFACE":
                lines_out.append(";TYPE:SUPPORT-INTERFACE")
            e = 0.0 if relative else e_orig + extra
            if pts:
                if retract > 0 and not retracted:
                    lines_out.append(f"G1 F{_fmt(retract_f or 2700)} E{_fmt(-retract if relative else e - retract)}")
                    e -= 0 if relative else retract
                lines_out.append(f"G0 F{_fmt(inf['tf'])} X{_fmt(pts[0][0])} Y{_fmt(pts[0][1])}")
                if retract > 0:
                    lines_out.append(f"G1 F{_fmt(retract_f or 2700)} E{_fmt(retract if relative else e + retract)}")
                    e += 0 if relative else retract
                first = True
                px, py = pts[0]
                for qx, qy in pts[1:]:
                    dist = math.hypot(qx - px, qy - py)
                    if dist < 1e-4:
                        continue
                    de_ = dist * inf["k"]
                    e = de_ if relative else e + de_
                    lines_out.append(f"G1 {'F' + _fmt(inf['f']) + ' ' if first else ''}X{_fmt(qx)} Y{_fmt(qy)} E{_fmt(e) if not relative else _fmt(de_)}")
                    first = False
                    px, py = qx, qy
                # leave the nozzle the way the lines that follow expect it: if the next E-only line is a prime, be retracted
                j = li + 1
                need_retract = False
                while j < n:
                    if j in drop:
                        j += 1
                        continue
                    if e_only[j] is not None:
                        need_retract = e_only[j] > 0.05
                        break
                    if xy_at[j] is not None:
                        break
                    j += 1
                if need_retract and retract > 0:
                    lines_out.append(f"G1 F{_fmt(retract_f or 2700)} E{_fmt(-retract if relative else e - retract)}")
                    e -= 0 if relative else retract
                    retracted = True
                else:
                    retracted = False
                if f_at[li]:
                    lines_out.append(f"G1 F{_fmt(f_at[li])}")
            if types[li] != "SUPPORT-INTERFACE":
                lines_out.append(f";TYPE:{types[li]}")
            if not relative:
                extra = e - e_orig
            new.extend(lines_out)
    marks.append(len(new))
    pos = 0
    for ci, c in enumerate(chunks):
        out[ci] = "\n".join(new[marks[pos]:marks[pos + len(c)]])
        pos += len(c)
    out[0] = out[0] + MARK_CAP + f" {done} layers\n"
    return out


def _grow(poly, d):
    """A convex counter-clockwise polygon pushed outwards by d (mitre joins)."""
    pts = _ccw(poly)
    m = len(pts)
    res = []
    for i in range(m):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % m]
        e1, e2 = (p1[0] - p0[0], p1[1] - p0[1]), (p2[0] - p1[0], p2[1] - p1[1])
        l1, l2 = math.hypot(*e1) + 1e-12, math.hypot(*e2) + 1e-12
        n1, n2 = (e1[1] / l1, -e1[0] / l1), (e2[1] / l2, -e2[0] / l2)
        bx, by = n1[0] + n2[0], n1[1] + n2[1]
        bl = math.hypot(bx, by)
        if bl < 1e-9:
            res.append((p1[0] + n1[0] * d, p1[1] + n1[1] * d))
            continue
        bx, by = bx / bl, by / bl
        cosh = max(bx * n1[0] + by * n1[1], 0.25)
        res.append((p1[0] + bx * d / cosh, p1[1] + by * d / cosh))
    return res
