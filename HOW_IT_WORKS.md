# How Hybrid Supports works

## What it reads and changes

- **Reads:** the selected model's triangles in world coordinates, plus a few Cura settings: *Support Overhang Angle* (unless you set your own), *Support Line Width*, *Layer Height*, *Support X/Y Distance*, *Support Wall Line Count* and *Support Line Distance*.
- **Changes:** it adds child meshes to the selected model, named `HybridTower_NN` (support meshes, with `minimum_support_area` set to 0 on that mesh only) and `HybridBlocker_NN` (support blockers). Generating again, or pressing Remove, deletes only meshes with those names. Every change goes through Cura's undo stack.
- **The installer** (`install.py`) writes only inside Cura's settings folder: the `plugins/HybridSupports` folder and one entry in `packages.json` (the previous file is kept as `packages.json.bak`). To check, it reads `cura.log`. The plugin itself stores one Cura preference, to remember that its one-time note was shown.
- **Tethers heads only:** it sets some of Cura's settings: *Support X/Y Distance* = 0, *Support Roof* = on, *Support Pattern* = concentric and *Support Infill Line Directions* = along the tethers. For straight tethers it also shifts every other layer's tether lines in the G-code when Cura saves it (user changes on the global stack, shown in Cura's settings panel). **Remove** or generating with another head puts back what was there.
- **Never:** it does not edit your model or your profiles, it changes no other Cura settings, and it makes no network connections.

## Pipeline

The geometry lives in `HybridSupports/hybrid_core.py` (numpy only, Z-up, millimetres). The Cura side (`HybridSupportsTool.py`) converts from Cura's Y-up scene, reads a few Cura settings, runs the core and turns the results into scene nodes.

1. **Overhang faces.** A face needs support when its downward normal is steeper than the support angle (`-n_z > cos(angle)`), the same meaning as Cura's setting. Faces resting on the plate are ignored.
2. **Sample and group.** Overhang faces are subdivided and sampled on a grid. Samples are grouped into **regions** by touching and by height, so a ceiling and a rib just below it don't merge.
3. **One trunk per region.** Candidate trunk positions (region centre, hull offsets, grid points) are scored. A position is accepted only if:
   - the column below it is clear down to a flat landing (the plate, or a model surface flat within 1 mm across the tube),
   - it can "see" the overhang (no wall between them),
   - a cone flaring at no more than 45° from the trunk top reaches the region.
   The lowest landing that works wins. Radius is `clip(0.25 × reach, 2, Max tower radius)`.
   If no position works, the region is split in two and each half tries again. Regions longer than *Split spans over* are split first.
4. **Low overhangs** (6 mm or less above what's below) are too short for a trunk. They get **standing webs**: thin vertical walls from the surface below up to the overhang.
5. **Trunk.** A hollow tube from the landing to the cone, `Tube walls × support line width` thick. Because Cura fills support meshes with support infill, a thin ring cross-section is what keeps it hollow.
6. **Head.**
   - **Lobes (default):** a star-shaped "pseudo cone". Each horizontal slice is one closed outline: the trunk circle with straight-sided lobes (width = trunk radius, 4–10 mm) sticking out of it. A lobe grows outwards at 45° as it rises, so only its tip overhangs, then stops at the edge of the overhang or the model and goes straight up to the underside. The wall is offset inwards by the tube wall thickness, so every lobe is hollow.
     - Lobes go to the corners of the overhang first.
     - Then, for every point of the overhang, the bridge it needs is twice its distance to the nearest lobe or to an edge that rests on a wall of the model. While the worst bridge is longer than *Max bridge span*, a lobe is added towards that point (up to 8).
     - On the test box that gives four lobes to the corners and a shorter fifth one towards the open front edge.
     - *Built to size (Lobes and Branch):* if no normal trunk can reach every point within the flare angle, `_place_trunk(fit=True)` finds where one support could stand and how far out it must start: radius = farthest reach − tan(flare) × the height available, up to *max_fit_radius* (30 mm). `_criss_cross` then builds thin walls from that centre with no hub: each stands on the landing out to that radius and rises at the flare angle beyond it (`_build_fin`), tops under the underside. Walls go to the corners of the overhang first, then towards wherever a bridge to the nearest wall, or to an edge resting on a wall of the model, would exceed *Max bridge span*. Only if no centre works is the overhang split.
   - **Tethers (experimental):** no trunk. Strips 3 support lines wide are laid between two facing walls of the model. The plugin tries 12 directions and keeps the shortest span where most strips have a wall at both ends, at the first layer and at the top; every tethered overhang on the part shares that direction. The strips start *Tethers start* (10 mm) below the overhang. The first and last sit at the two ends of the overhang, *tether_end_inset* (0.2 mm) in from its edge, and the rest are evenly spaced between, about one pitch apart (strip width ÷ *tether coverage*, 20 %). Above them a cap of support roof is inset from the walls by the usual X/Y distance.
     - *Tethers* are straight blocks. After slicing, `tether_gcode.py` shifts the support lines inside each strip by half a line width on every odd layer. It hooks Cura's output, like the Post Processing plugin does, and also moves the travel that leads into each strip.
     - Cura's support pattern is set to concentric, so each strip prints as its own outline.
     - *Tethers refuse what they can't reach:* if more than 10 % of the overhang is more than 1.5 strip pitches from every strip (an L corner, where parallel strips only fit near the corner), they are not used there and lobes take over.
     - *Cap stack:* the cap is the top four layers under the overhang (Support Roof, 0.8 mm). Cura can't change pattern or density from layer to layer, so after slicing `tether_gcode.cap_stack` removes Cura's roof moves inside the cap outline (and the travels into them), layer by layer, and writes its own paths: layer 1 a zigzag lattice across the tethers, layer 2 a lattice along them, then concentric rings (spacing line width ÷ fill, stopping when the middle is narrower than *tether_cap_hole*), then a solid 45° hatch. Extrusion per mm is copied from Cura's own roof lines (layer 1 times *Cap flow*), retraction and the absolute E values follow the file, and the nozzle is left retracted or primed to suit the lines that follow. The paths are in model XY plus the bed offset.
     - *Slow first layers:* the first *tether_slow_layers* (2) layers are mid-air bridges. After slicing, `tether_gcode.slow_bridges` sets *Bridge speed* on every SUPPORT move inside the tether footprint on those layers, scales the extrusion by the bridge flow (1.0 by default) and carries any extra filament through the later absolute E values, raises the part fan while it lasts and puts speed and fan back after.
   - **Cone:** a hollow inverted cone. For each direction around the trunk it rises at 45° until it is under the overhang or would hit the model, then goes straight up to the contact gap below the underside. Tops are smoothed over neighbouring directions so no edge pokes into the model. Inside it:
     - **Cross:** spokes from the trunk to the corners of the region outline, then extra spokes wherever a bridge would be longer than *Max bridge span* (up to 16). Spoke tops follow the underside.
     - **Rings:** concentric bands spaced *Max bridge span* apart.
     - **None:** just the cone wall.
   - **Branch:** separate slat fins fanned across the overhang (0.2 style).
   - **Solid / Conform:** the 0.1 star-shaped head, flat-topped or following the underside.
7. **Gussets.** Triangular fins at the trunk foot. Each one is shortened step by step until it is clear of the model and still stands on something; the status line says when gussets were shortened or capped (max half the trunk height).
8. **Blocker.** A prism over the region outline (plus a 1 mm margin). CuraEngine only removes overhang detection inside anti-overhang meshes at the overhang's own layers (`support.cpp`), so the blocker sits over the overhang, not around the tower.
9. **Per-mesh settings.** Each support mesh gets `minimum_support_area = 0`, so profiles that drop small support areas (Elegoo's sets 3 mm²) don't delete thin tube and spoke layers.

Every test model is checked for support points inside the model in every head mode (see `tests/test_core.py`). The background research is in [docs/RESEARCH.md](docs/RESEARCH.md).

## What Cura does with the meshes

Checked by slicing in Cura 5.13.0 with the Elegoo Neptune 4 profile (and 0.1.x on the Ender-3 profile): the trunk becomes one hollow ring per layer, the cone wall a closed loop, spokes thin straight lines and the top layers support interface. With **Support Wall Line Count 0** (the zigzag default) thin spokes and rings can print dashed; **1 wall** prints them as clean outlines at the cost of more filament. Other patterns have not been checked.

## Why support meshes, not a CuraEngine fork

Cura plugins are Python and can't change how CuraEngine generates support, but they can add meshes the engine treats as support. Support meshes print even with *Generate Support* off, and use your support line width, speed and interface settings. That keeps the plugin installable on any Cura 5.x with no custom engine build.

## Why there is no paint tool

Research for this project (October 2026) found that Cura's paint tool has carried a hidden support-painting mode since 5.11, and that CuraEngine only started consuming painted support data in 5.14.0-beta. Re-implementing it would duplicate a feature that is shipping natively.
