# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org).

## [0.6.6-wip] - 2026-11-10

From the user, after his tether sag simulation: "make 110 as hard limit for tethers where it notifies and switches to the next best. Anything above 90 it warns that unpredictable and 'the vengeful flying spaghetti monster may appear suddenly for trying to violate the laws of physics'."

### Added (paper)
- `docs/paper/putting-plastic-on-a-pedestal.pdf`: the research paper / defensive publication on these supports (version 1.0, its own repository `putting-plastic-on-a-pedestal`). The big-parts chart (`docs/images/big_parts_filament.png`) now shows tethers too, as hatched bars: they refused all three parts and fell back to lobes.

### Changed
- `tether_max_span` is 110 mm (was 120): a hard limit. A tether that would span more falls back to lobes, and the note says why ("the walls are 180 mm apart, over the 110 mm limit") instead of "no walls to tether to".
- New `tether_warn_span` (90 mm): spans between 90 and 110 mm still build, with a warning that includes the Flying Spaghetti Monster line.
- The tool shows a Cura warning message listing these cases and adds them to the status line.

### Added
- `tools/tethersim`: the user's sag simulation and its research note. Research section 18.

### Tests
- New: 80 mm gap builds clean, 100 mm builds with the warning, 140 mm is refused and falls back. 63 tests.

## [0.6.5-wip] - 2026-11-10

From the user: "make at least the first 3 z layers of the tethers printed as bridges in case 2 are weak or slack", and a request to research established bridging limits.

### Changed
- `tether_slow_layers` is 3 (was 2): the first three tether layers get the bridge speed (20 mm/s) and fan at 100 % in the saved G-code.

### Research
- Section 17 of docs/RESEARCH.md: published bridge limits (10 to 30 mm conservative, about 100 mm tuned, nothing for 180 mm), and where the 120 mm tether limit came from (no source: a search distance from 0.4.0). The limit is unchanged.

### Tests
- New: three slowed bridge layers by default. 60 passed.

## [0.6.4-wip] - 2026-11-10

From the user's request: "run the simulations on bigger parts, parts with a long stem, so we can get a better feel for potential savings. Perhaps a U which is 200x200."

### Fixed
- **Cone shells overshot big overhangs.** `_flare_reach` used the farthest point of each 5.6 degree direction sector, and on a 100 mm overhang that point lies far off the ray, so the 45 degree shell flared ~17 mm past the roof's edge (off the part, off the bed) and Cura truncated the slice to 4 layers. Reach is now measured along the ray from points near it. Footprints stay within ~3 mm of the part.
- A normal tower (lobes, cone, branch) that reaches under `min_fit_coverage` of its region now splits the region and builds again, instead of leaving corners to the cap.
- The interface cap cuts back across the direction of the model hits instead of along the line to the centre, so caps keep ~99 % of the hull.
- The Cura harness' slice wait is configurable (`HS_SLICE_WAIT`, default 180 s) for 200 mm parts.

### Added
- `tools/bigbench`: the three benchmark STLs, slicing script, filament/time tools, and results (`summary.json`); research section 16 with the table and chart.

### Measured (Cura 5.13 + Neptune 4)
- Lobes vs Cura normal support: 64 % (50 mm stem) to 84 % (150 mm) less support plastic. Vs Cura tree support: 24 to 26 % less on 150 mm parts, 29 % *more* on the 50 mm U. Whole job (move model): lobes 583 min on the 150 mm U against 666 tree and 1404 normal.

### Tests
- New: tall table-top supports stay under the overhang for lobes and cone (2 to 4 towers, reach 85 % or more). 59 passed (the two environment-dependent ones included).

## [0.6.3-wip] - 2026-11-02

From the user's review of 0.6.2 (sliced, not printed): "they don't have any support interface. Please make sure they all have at least 2 layers of lattice and one 100 % interface, else the part will droop."

### Added
- **Interface cap on every non-tether support** (`tower_cap`, on). Before a tower is built, `_plan_caps` plans flat 0.8 mm caps under the overhang: one per 0.8 mm height band of the underside (a staircase on slopes), each the convex outline of its part of the overhang, cut back (half-planes, nearest offender first) wherever the slab would come within the X/Y clearance of the model; a band that forms a ring round a dome is split into 8 sectors. The region's points under a cap are lowered to the cap's underside, so every head is built up to the cap. Each cap is a normal mesh `HybridCap_NN` (0 walls, 0 infill, solid skin, support speed); on save `tether_gcode.cap_stack` replaces that mesh's lines (found by its `;MESH:` name, so the part's own lines on those layers are never touched) with lattice, lattice, 50 % rings, 100 % top, and `slow_bridges` prints the first lattice at `tower_cap_bridge_speed` (20 mm/s) with the fan at 100 %. First-lattice flow is 100 % (the tethers' 85 % is for fusing onto thin strips).
- Tethers that fall back to lobes get the cap too.

### Fixed
- The standing-web search for low overhangs could try thousands of fins on a curved part (40 s on the tilted blob test part); it now gives up after repeated misses (under 4 s).

### Measured (Cura 5.13 + Neptune 4, six-part plate)
- Every part's G-code has the 4 cap layers (`;HYBRID_SUPPORTS_CAP_STACK 24 layers`: 5 tower caps + the tether cap). Towers end at 14.1 mm, lattice 14.3, lattice 14.5, rings 14.7, solid 14.9, part from 15.1 (with the 0.2 contact gap).
- Support plus cap between the legs: channel lobes 0.93 m, corner lobes 0.83 m, channel cone 1.44 m, channel branch 1.23 m (0.6.2 without caps: 0.73, 0.65, 1.26, 1.06). Plate: 2 h 21 min, 29.3 m (0.6.2: 2 h 14 min, 27.1 m); Cura's estimate doesn't include the slow first lattice layers.

### Tests
- New: caps for every head on the channel and corner (watertight, outside the model, top at underside minus contact gap, towers end at the cap's underside, plans carry the mesh name and slow layer), cap stack by mesh name leaves the part's lines alone, tethers keep their own cap. The cantilever test now expects the tower to stop under the cap. 57 passed.

## [0.6.2-wip] - 2026-10-23

From the user's review of the 0.6.1 top view (not yet printed): "that stress concentrator shape is pretty terrible for 3D printing, can we fillet it or even have a straight line; also hollow loops are very close, which will reduce its XY strength, making it flex during nozzle drag. Can we do fewer lobes which are rounded loops which take up far more space?"

### Changed
- **Lobes, built to size: one star of wide rounded lobes** (`_petal_star`). Each lobe is a capsule (8 mm wide by default, `lobe_width`) from the centre, reaching out at height z to its foot + (z - landing) x tan(flare), capped at its length; the lobes are joined with a smooth maximum of their outline radius so the inner corners are rounded over at least `lobe_fillet` (3 mm). It is one solid, watertight mesh that Cura prints hollow with *Tube walls* (2) walls. The arm count rule is unchanged (corners first, more only where a bridge would pass *Max bridge span*), but it now counts the lobe width, so the 40 mm channel and corner get 4 lobes instead of 6 walls. Each column stops under the overhang, and the outline is pulled in wherever it would come within the X/Y clearance of the model, then limited to the flare angle over the layer below.
- **Branch and Cone ribs** keep their straight thin webs, plus a rounded hub at the centre (the same star, cut to a radius of half-width + 2.5 x fillet) so they meet without a notch.
- Wall-printed towers now get *Tube walls* walls (was 1), so the solid lobes print with 2 walls; thin parts get as many as fit.

### Measured (Cura 5.13 + Neptune 4, six-part plate, between the legs)
- Channel lobes 0.73 m / 14,738 moves (0.6.1: 0.65 m / 3,638), corner lobes 0.65 m / 15,316 (0.57 m / 2,714), channel branch 1.06 m / 9,965 (0.64 m / 3,022: its 3-line webs were a loop with a gap, now solid), cones about the same. Whole plate: 2 h 14 min, 27.1 m (0.6.1: 2 h 6 min, 26.8 m).

### Tests
- New `test_lobes_star_is_few_wide_rounded_lobes` (channel and corner: one watertight star, 3 to 5 lobes, nothing inside the model, no neck narrower than 3 mm from the centre). 47 passed.

## [0.6.1-wip] - 2026-10-19

From the user's first look at 0.6.0 in Cura (Neptune 4): "the tethers are flawless, the others are bad: they generate zig-zag towers instead of hollow towers, and some generate 4 towers when 1 would do."

### Fixed
- **Zig-zag towers.** Cura fills a support mesh with the support pattern, and Support Wall Line Count / Support Pattern can't be set per mesh (checked in Cura 5.13's fdmprinter.def.json: `settable_per_mesh: false`). With the Neptune 4's 0 support walls, 0.6.0 also widened every thin wall to about 3 mm so it wouldn't vanish, which printed as one zig-zag line inside a 3 mm strip. Lobes, Cone and Branch supports (and standing webs) are now added as **normal printed meshes** with per-mesh settings: 1 wall, 0 % infill, 0 top/bottom/roofing/flooring layers, no horizontal expansion, Cura support off for them, wall speed and flow set to the support speed and flow. Each 2-line wall prints as one closed loop; tubes as two rings. `print_walls` (on by default) switches back to support meshes. Tethers and the Solid/Conform heads stay support meshes.
- **4 (up to 32) towers where 1 would do.** Two bugs in "built to size": (1) a fin standing on a surface above the bed (a base plate, a brim block, a floor in the model) cast its "is the model just above me?" ray from 0.5 mm *below* its own foot, saw the surface it stood on, and was dropped, so every criss-cross came out empty and the overhang was split, then split again; (2) the criss-cross needed a clear round foot as wide as its reach, which hit the legs of a channel. Now each wall stands on the floor along its own line as far as it must (`_arm_foot`), the round foot only has to be as wide as is clear (`_clear_foot`), and the landing height is included when working out how far the foot must reach. Built to size is kept when it reaches at least 85 % of the overhang (`min_fit_coverage`), otherwise the old split still applies.

### Measured
- Pure-Python sweep (channels 8 to 25 mm high, 30 to 60 mm wide, 40 to 80 mm long, and L corners, all on a 0.4 mm base plate, X/Y clearance 1.46 mm): every Lobes, Branch and Cone support is now 1 tower (0.6.0: 1 to 32).
- Cura 5.13 + Neptune 4, six-part plate, filament and extrusion moves between the legs: channel lobes 0.65 m / 3,638 (0.6.0: 0.78 m / 8,505), channel branch 0.64 m / 3,022 (0.77 m / 8,486), corner lobes 0.57 m / 2,714 (0.66 m / 7,895), channel cone 1.30 m / 21,668 (1.24 m / 21,040), corner cone 1.17 m / 18,737 (1.11 m / 19,908), tethers unchanged (1.28 m). Cura's estimate for the plate is unchanged (2 h 6 min).

### Tests
- New: `test_channel_on_plate_is_one_tower` (3 heads x 2 heights), `test_towers_print_as_walls_tethers_as_support`. `test_blob_small_curved_overhangs` now accepts one criss-cross instead of several standing webs (8 supports became 2). 45 passed.

## [0.6.0-wip] - 2026-10-16

Research round: other cheap supports, radial tethers, bridging speed and arc overhangs (docs/RESEARCH.md section 11).

### Added
- **Radial tethers** head (experimental), from the user's drawing: for an overhang with only two walls meeting at a corner, a short patch on one wall (20 % of its length) fans straight tethers out to points along the other wall, and a second fan goes the other way from the opposite wall, criss-crossing. The part of a square roof that no wall-to-wall strip can reach gets lobes. With no corner it falls back to straight tethers, then lobes.
- **Slow first layers** for all tether-type heads: the first two layers are mid-air bridges, so on save they are slowed to *Bridge speed* (20 mm/s; 0 = off), with the fan at 100 % and extra filament carried through the later E values (`tether_gcode.slow_bridges`). Speed and fan are put back after.
- Fixed: the panel's *Coverage* field clamped before converting % to a fraction, so 10 % printed 31 strips.
- **Cap stack** for the tether heads (on by default; untick *Cap stack* for the old plain roof). The cap is four layers (0.8 mm) written into the G-code on save (`tether_gcode.cap_stack`): a lattice across the tethers at 3 mm, a lattice along them, concentric rings at 50 % fill with an open middle about 8 mm wide (the nozzle never lingers over one spot on the thin strips), then a solid diagonal layer that bridges the middle. On the 40 mm channel the stack costs about 0.2 m of cap filament against 0.39 m for the old 2 mm roof, and the whole support 0.95 m against 1.04 m. Untested on a printer; Cura's preview shows plain roof lines.
- **Cap flow** (default 85 %, 100 = off): the first lattice layer lies across the thin tethers, so it is printed with less filament, the idea being that the bead fuses with the tether instead of squashing or melting through it. Untested; compare 100 / 85 / 70 on small parts. With the stack off, the first roof layer gets the flow instead; optional speed for it in the settings (`tether_cap_speed`).
- Panel: *Coverage* and *Bridge speed* fields for the tether heads.
- `u_channel`-style second test part, `l_corner` (two walls and a square roof), in `tests/models.py`; `tests/cura_harness/gcode_time.py` (rough print time, to add the slow-down Cura's estimate misses); `tools/arc_prototype.py` (arc-overhang estimator, research only).

### Changed (after the first look at the sliced test plate)
- **Tether cap: the 50 % concentric layer is now a full layer** (no open middle; `tether_cap_hole` 0 by default), so the stack is lattice, lattice, 50 % concentric, then a solid 100 % top layer that leaves the part a smooth, easy-to-remove underside.
- **Dropped stepped tethers, the spiderweb and radial tethers.** Stepped tethers gave no advantage over straight ones; the spiderweb left large regions unsupported; radial tethers needed a lobes tower for the far corner as well, the worst of both. Code, panel options and tests removed; the research notes stay.
- **Lobes and Branch: one criss-cross built to size.** Where a normal tower can't reach the whole overhang within the flare angle, they now build one hub-less criss-cross instead of several towers: thin walls (2 lines for Lobes) from one centre, standing on the bed out as far as needed and flaring at 45° to the edges, to the corners first and elsewhere only where a bridge would be too long. 40 mm test channel: 6 walls, 0.58 m of support (four lobes towers: 1.21 m). A first version with a wide hollow foot and spokes (1.09 m) was replaced after review: the hub cost too much. `lobes_one_tower` turns it off.
- **Cone: one cone built to size**, where a normal one can't reach: a thin wall (`cone_wall_lines`, 2) from a circle on the bed flaring at 45° to the overhang's edges, with an X of 2-line ribs inside to the corners, no hub or trunk. 40 mm channel: 0.92 m of support and about 20,400 extrusion moves, against 0.97 m for four cones, and 0.58 m / 8,100 moves for the criss-cross. Kept for the test print; the user's rule is to drop the cone if it costs too many moves or too much plastic.
- **Tethers: the first and last strip sit at the two ends of the overhang**, 0.2 mm in from the edge (`tether_end_inset`), and the rest evenly between. They used to start half a gap in, leaving the roof's ends hanging.
- `test-prints/` now holds the one-job plate only; the separate 0.5/0.6 files were for heads that are gone or changed.

### Changed
- **Models with different heads can share a plate.** Generate used to forget the G-code steps and Cura settings of the models generated before; they are now kept per model (select a model, pick its head, Generate; repeat). Cura's own settings (X/Y distance, roof, pattern) are still one set for the whole job, merged from every model's needs.
- Tethers now refuse an overhang they can't reach (more than 10 % of it farther than 1.5 strip pitches from any strip). On an L corner they used to cover only the half near the corner and leave the rest of the roof unsupported; they now fall back to lobes.
- **Radial tethers and the spiderweb set Cura's Support Join Distance to 0.2 mm** (put back on Remove). Cura merges support areas closer than 2 mm, which turned the first radial slice into one filled triangle and the spiderweb into linked loops. Now the radial tethers slice as a criss-cross lattice and the spiderweb as threads then rings.
- The spiderweb's rings are built as one strip per arc with shared edges, and arcs that end at a wall are lengthened until they touch it.

### Tried and dropped
- **Corner fan** (spokes from a corner plus arcs between the walls): prints round hubs and arcs in mid-air, not load bearing, and saved filament but not time on the L-corner (24 min / 0.88 m of support against Cura's normal support at 23 min / 1.42 m). Replaced by radial tethers.

### Tested
- One plate with nine parts (every head on the 40 mm channel and corner, 0.3 mm first layer, 4 walls, 8 mm brim): `test-prints/N4_PLATE_all_supports_one_job.gcode`. Because Cura's support settings are job-wide, lobes, cone and branch come out thicker on that plate than alone (lobes 1.2 m against 0.76 m); see test-prints/README.md.
- Cura 5.13, Neptune 4 profile (support filament): 40 mm test corner: lobes 20 min / 0.23 m, radial tethers + lobes 26 min / 1.06 m, Cura tree 26 min / 0.73 m, Cura normal 23 min / 1.42 m. 60 mm-tall corner: lobes 46 min / 1.03 m, radial 49 min / 1.41 m. Channel: tethers 25.5 min / 1.04 m, 10 % tethers 24 min / 0.72 m, tethers starting 4 mm below 24 min / 0.56 m, spiderweb 28 min / 1.18 m, Cura 5 % zigzag without roof 23 min / 0.75 m. Slow first layers add 0.4–0.7 min.
- 100 x 100 mm roofs, 100 and 150 mm tall (docs/RESEARCH.md section 11): on the channel, tethers, stepped tethers and the spiderweb are the cheapest (about 12 % less time than lobes, 5 to 20 % less filament, 3 to 5 times less than Cura's sparse support); on the corner, lobes win and radial tethers cost twice as much (they reach 54 % of the roof). `tools/bench_summary.py` makes the tables.
- **Not tested:** any of this on a real printer. In these numbers lobes are the cheapest support everywhere; the tether heads are for trying where pillars fail.

## [0.5.0-wip] - 2026-10-13

From the first real test print (stepped tethers on the old test box).

### Fixed
- **Tethers too sparse, leaving much of the cap unsupported:** strips now cover 20 % of the space under the overhang, equally spaced (on the test channel, 6 strips 5.4 mm apart).
- **The roof lattice touched the walls:** the cap is now kept clear of the walls by the usual X/Y distance. Only the strips touch the walls.

### Changed
- **Tethers** are straight again, with every other layer shifted half a line width so the layers only half overlap and snap apart. Cura can't do this from the shape: it slices support meshes at both the top and bottom of each layer and keeps what they share. So the plugin shifts those lines in the G-code when Cura saves it (`tether_gcode.py`, hooked like Cura's Post Processing plugin).
- Tethers use Cura's concentric support pattern, so each strip prints as its own outline.

### Added
- **Spiderweb** head (experimental): threads through the middle from wall to wall, then rings across them.
- New simple test bed: `u_channel.stl`, an upside-down U channel with 3.5 mm legs and roof on a big 0.4 mm brim plate. `test-prints/` has Neptune 4 G-code for classic lobes, staggered tethers and spiderweb, replacing the old test box.

### Tested
- Cura 5.13, Neptune 4 profile, test channel: the G-code shows every odd layer's tether lines shifted exactly 0.21 mm, with no crooked lines. Lobes 27 min / 0.78 m, tethers 26 min / 1.04 m, spiderweb 28 min / 1.05 m of support.
- **Not tested:** a successful real print of the new tethers or spiderweb.

## [0.4.2-wip] - 2026-10-10

### Changed
- Panel: **Tethers** (straight up) and **Stepped tethers** (leaning) are now separate head choices; *Step per layer* shows for stepped tethers only.

### Added
- `test-prints/`: a quick test part (`tether_test_box.stl`, 60 × 36 × 24 mm, open on one side, 55 × 33.5 mm ceiling) and G-code for the Elegoo Neptune 4 made with each of the three heads (lobes, tethers, stepped tethers), to compare on a real printer.

## [0.4.1-wip] - 2026-10-09

### Changed
- **Tethers lean** (the user's idea): each layer steps sideways by *Step per layer*, so a tether isn't a solid wall 10 mm high and one line thick and is easier to cut or snap off. The default is half a line width (about 45°), so each line still sits half on the one below. A step of a whole line width or more would land each layer beside the one below, making every layer a new bridge.
- Tether strips are now 3 support lines wide; Cura prints each as a pair of straight lines.
- Panel: *Step per layer* field for tethers.

### Measured
- Test box, Cura 5.13, Neptune 4 profile: Tethers 134 min / 3.9 m of support filament (standing straight up: 136 min / 4.3 m). The G-code shows each strip stepping about 0.2 mm per layer.

## [0.4.0-wip] - 2026-10-09

### Added
- **Tethers head (experimental)**, the user's idea: strips of support strung between two walls of the model a short way under the overhang (default 10 mm), then a cap of support roof. No pillar from the floor. Overhangs without two facing walls fall back to lobes.
- Tethers set Cura's *Support X/Y Distance* to 0, *Support Roof* on and *Support Infill Line Directions* along the strips (so each tether is a straight bridge, not a zigzag), because CuraEngine keeps all support that far from walls and the setting can't be made per mesh or per object (checked in Cura 5.13). Remove puts them back.
- Panel: *Tethers (test)* head and a *Tethers start* field.

### Measured
- Test box, Cura 5.13, Neptune 4 profile: Tethers 136 min / 4.3 m of support filament, against Lobes 149 min / 4.9 m. The strips are straight lines that touch both walls from the first mid-air layer (0.03 mm gap in the G-code).

### Tested
- Unit tests: tethers reach both side walls of the box, don't enter the model, and the outside ribs fall back to lobes.
- **Not tested:** a real print (the first mid-air layer is the big unknown), Windows, macOS.

## [0.3.0-wip] - 2026-10-09

### Added
- **Lobes head (new default)**, the user's idea: a hollow, star-shaped "pseudo cone" with thick hollow lobes to the corners of the overhang instead of a cone wall plus thin spokes. Every layer is one closed outline, so it prints cleanly even with 0 support walls. Lobes are added where a bridge would exceed *Max bridge span*; edges resting on a wall of the model count as support.
- Panel: **Lobes** head option. Cone, Branch, Solid and Conform remain.

### Measured
- Test box in Cura 5.13 (Neptune 4 profile): Lobes 149 min / 4.9 m support filament, Cone 151 min / 5.4 m, tree support 151 min / 6.5 m, normal support 190 min / 22.3 m. Every pillar printed on 100 % of its layers.

### Tested
- Unit tests: lobes never enter the model, the shell is watertight, less volume than the cone on the box.
- **Not tested:** a real print, Cura 5.11/5.14, Windows, macOS.

## [0.2.0-wip] - 2026-10-09

New support geometry, from feedback on an "EN4 Rugged Box" printed on an Elegoo Neptune 4.

### Fixed
- **Tubes printed only in places, "in mid-air".** Elegoo's Cura profiles set *Minimum Support Area* to 3 mm², and CuraEngine deleted thin tube layers smaller than that. Each generated support mesh now sets it to 0 for itself only. Pillars also check for a clear column down to a flat landing before they are placed.
- **Gussets stuck into the print.** Every gusset is now shortened until it is clear of the model and still stands on something.
- **No pillar in the middle of a box / three pillars across one gap.** Pillar positions are searched for a clear column that can see the overhang, with one pillar per overhang. Splitting only happens when the cone can't reach (default over 250 mm).
- Supports now respect Cura's *Support X/Y Distance*.

### Added
- **Cone head (new default):** a hollow inverted cone flaring at most 45° from the pillar.
- **Inside the cone:** *Cross* (default: spokes to the corners, plus extra spokes wherever a bridge would exceed *Max bridge span*), *Rings* or *None*.
- **Branch** head (separate slat fins) as an option.
- Standing webs for low overhangs (6 mm or less).
- Status line: how many supports were only partly reached, gusset shortening, and a tip about *Support Wall Line Count*.
- `docs/RESEARCH.md`: all research notes (paint-on supports, how CuraEngine treats support meshes, the bug root causes, the bridge-span maths).
- Test parts (`tests/models.py`), renders (`tools/preview_models.py`) and a per-pillar layer check for real Cura gcode (`tests/cura_harness/gcode_towers.py`).

### Changed
- Settings: *Max span per tower* (30 mm) became *Split spans over* (250 mm); *Max tower radius* default 6 → 8 mm; new *Max bridge span* (20 mm). *Head share of gap* is gone; the head size now follows from the 45° flare.
- `PUBLISHING.md` now lives inside the repo.

### Tested
- Cura 5.13.0 Linux AppImage, Elegoo Neptune 4 profile: the test box (10 supports, every pillar printed on 100 % of its layers) and a tilted blob (standing webs), plus Cura normal and tree support for comparison.
- Unit tests check that no support point is inside the model in every head mode.
- **Not tested:** a real print, Cura 5.11/5.14, Windows, macOS.

## [0.1.2-wip] - 2026-10-06

### Fixed
- **"Installed, but I can't see it."** 0.1.1-wip's `install.py` copied the files but removed the plugin from Cura's package record, so Cura did not list it under Marketplace > Manage; and Cura hides its tool bar until a model is loaded, so an empty Cura showed nothing. The installer now installs the way Cura's own package installer does (same folder layout, same record in `packages.json`).

### Added
- Installer window (`install.py`, tkinter): Install / Update, Check, Start Cura, Open plugin folder, Add Cura folder, Uninstall. It reads the files back after installing and reads Cura's log to confirm Cura loaded the plugin, or to show Cura's error.
- Click-to-run launchers: `Install-Linux.sh`, `Install-Windows.bat`, `Install-Mac.command`. Text mode when there is no tkinter or display (`--cli`, `--check`).
- In Cura: an **Extensions > Hybrid Supports** menu (How to use, About) and a one-time note after installing.

### Tested
- Cura 5.11.0 and 5.13.0 Linux AppImages: listed under Installed Plugins, Extensions menu present, note shown, then click, generate and slice.
- Installer window on Linux (Tk 8.6, Xvfb), including pressing Install then Start Cura against a real Cura 5.13 and seeing the check pass. `Install-Linux.sh` in window and text mode.
- **Not tested:** `Install-Windows.bat`, `Install-Mac.command`, anything on Windows or macOS. Still not test-printed.

## [0.1.1-wip] - 2026-10-03

**Installs but is hard to find in Cura (see 0.1.2-wip).**

### Fixed
- **Cura crashed (segfault) at startup with 0.1.0-wip installed.** The toolbar icon's `<svg>` tag had a `fill` attribute; Cura inserts its own `fill` there to recolour tool icons, which made invalid XML and crashed Cura's SVG loader. The icon is now plain filled shapes, and a test checks it.

### Changed
- Tool panel is a compact two-column layout.
- The build date shown in the panel is stamped when the package is built, not when it is installed.

### Added
- `install.py`: one script that builds the plugin and installs it straight into every Cura 5.x found, replacing older copies (replaces `tools/build_package.py`; `--package` still writes the `.curapackage` and zip).
- `tests/cura_harness`: drives a real Cura AppImage (toolbar click, Generate click, slice, Remove, undo) and compares against Cura's normal and tree support.
- Real Cura screenshots, sliced-layer plot and comparison numbers in the README.

### Tested
- Cura 5.11.0 and 5.13.0 Linux AppImages under Xvfb with software rendering, Creality Ender-3 profile, one synthetic model, including install from the `.curapackage`. Still not test-printed.

## [0.1.0-wip] - 2026-10-03

**Do not use: crashes Cura at startup (see 0.1.1-wip).**

Work in progress, proof of concept.

### Added
- Geometry core: overhang islands, auto-splitting, down/up ray-casting, hollow tube towers, gussets, trapezoid and conforming heads, support blockers.
- Adjustable gusset count, height (capped at half the tower height) and length.
- Cura tool plugin (shortcut **H**) with a settings panel, Generate and Remove.
- `.curapackage` and plugin-zip builder.
- Unit tests, Cura-adapter smoke test, preview renders and a benchmark.

### Not done
- Not yet run inside the Cura GUI or test-printed.
