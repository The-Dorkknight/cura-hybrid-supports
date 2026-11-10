# Tether sag simulation: Ender 3 vs Neptune 4 (PLA)

*cura-hybrid-supports research note. Matthew Armstrong, 2026-11-10. Simulator v0.3.*

## Why

No published data exists for how far an FDM strand can span when some droop is acceptable, as it is for tether supports where later layers catch up. This model estimates it from physics instead of guesswork, so the plug-in can use per-printer span limits and Z/flow schedules.

## Model in one paragraph

A PLA strand leaves the 0.4 mm orifice and is drawn down to the bridge-strand area (flow × line width × layer height). Mass conservation fixes its length to the travel length, so the nozzle pulls it taut with a **viscous drawing force**. Behind the nozzle the hot zone hangs like a string between the nozzle and the freeze point. Its droop is locked in as each 0.5 mm element passes Tg, because stiffness is "born" in the deformed shape. The frozen strand then sags as a tensioned beam under its own weight. Each element cools by forced convection from the local fan air speed (Hilpert cylinder correlation), plus natural convection and radiation. Fan drag also pushes the hot strand downward. The far wall clamps the strand on arrival, and the last hot section's shrinkage can then pull it taut. Layers 2+ are laid over the frozen strand below, which acts as a rigid obstacle; contact above 120 °C counts as fused.

## Calibration (be honest about this)

The drawing force carries the largest uncertainty (melt shear-thinning, length of the drawing zone). **One factor (`F_SCALE = 0.25`) was fitted** so that a stock Ender 3 at 25 mm/s reproduces published PLA bridge guidance: about 0.1 mm at 25 mm (Creality: ≤25 mm clean), 0.4 mm at 50 mm (Qidi: slight sag at 20–50 mm) and 0.85 mm at 80 mm (Qidi: visible sag at 50–80 mm). Everything else, including every Neptune 4 result, comes from the physics. Fan air speeds are **estimates**: Ender 3.5 m/s at the nozzle with a short one-sided jet; Neptune 6 m/s plus a 2.5 m/s rear auxiliary stream. A ±50% air-speed sweep is included.

## Results

### 1. Sag vs span (`sag_vs_span.png`)
- Up to about **60 mm** both printers stay under ~0.4 mm at any sensible speed.
- Beyond about **100 mm** the limit is no longer cooling. It is the solid 0.32 mm PLA strand bending under its own weight (sag ∝ L⁴/d²). That is a hard ceiling for a 0.4 nozzle and 0.2 layers on any printer. Thicker strands (0.6 nozzle) raise it.
- **Neptune 4 gets better the faster it goes** (taller drawing force, and the strong fan freezes it quickly). **The Ender doesn't**: at 30–40 mm/s its hot zone stretches past 20 mm.
- Ender: more air helps (+50% air → 68 mm instead of 61 mm at a 0.45 mm budget). Neptune: more air *hurts* slightly (64 mm vs 71 mm). The stock Neptune is already past the point where extra fan drag pushes hot strands down faster than it freezes them. Sensitive to the estimated downward-drag fraction, so verify on a print.
- Lower bridge flow (0.8) gives more tension and less sag, but thinner, weaker strands (snapping is not modelled).

### 2. Layer fusion (layers 2–3)
- At 0.2 mm layers the free strand is ~0.32 mm round, so **stacked strands overlap and mostly fuse even printed flat** (85–100%).
- A Z offset of **0.5 × predicted sag of the layer below** gave **100% fusion in every case**.
- The offset must **never exceed the predicted sag**. Beyond that the nozzle sits closer than one layer above the strand below and will plough it (nozzle contact is not modelled, so the sim can't flag it).

### 3. Catch-up (`catchup.png`), the real budget
Each tether layer recovers only about **0.45 × (d_below + d_this) − layer_h ≈ 0.09 mm** at flow 0.9. So the **sag budget for a 5-layer catch-up is only ~0.45 mm**, not 1 mm. Boosting flow on layers 2+ to 1.2–1.5 raises recovery to ~0.12–0.17 mm per layer, giving a **~0.6 mm budget** (80 mm span: back to nominal by layer 5 at flow 1.5, by layer 6 at flow 1.2).

### Max tether span (mm), PLA, conservative (soft walls, no shrink pull)

| Printer | Speed | 0.45 mm budget (flow 0.9 throughout) | 0.6 mm budget (flow 1.2–1.5 on layers 2+) |
|---|---|---|---|
| Ender 3 | 10–15 mm/s | **70** | **80** |
| Ender 3 | 20 mm/s | 61 | 75 |
| Ender 3 | 30–40 mm/s | 57–65 | 66–75 |
| Neptune 4 | 20 mm/s | 71 | 81 |
| Neptune 4 | 30 mm/s | 75 | 87 |
| Neptune 4 | 40 mm/s | **79** | **92** |

With rigid walls (shrinkage pulls the strand taut after anchoring) these rise to 85–130 mm, so treat them as the optimistic bound.

## Recommendations for the plug-in

1. **Span limit per printer profile**: Ender-class ~70 mm at 10–15 mm/s; Neptune-class ~80–90 mm at 30–40 mm/s. Split longer voids with a mid-span hub or pillar.
2. **Tether speed**: slow (10–15) for weak-fan printers, fast (30–40) for strong-fan printers. Expose it as a setting with these defaults.
3. **Layers 2–3**: nozzle Z follows `0.5 × predicted_sag(x)` of the layer below (non-planar G-code, tiny Z moves). Clamp it to ≤ the predicted sag.
4. **Layers 2–5**: flow 1.2–1.5 on tether and interface lines until the predicted deficit reaches zero, then the 50% concentric and 100% interface.
5. **Anchors**: anchor several mm into the walls. Rigid anchors let shrinkage pull strands taut, which is a large free gain.

## Not modelled / to verify by printing
Sideways fan push on long single strands (the Neptune rear fan especially), strand snapping, anchor pull-out, nozzle scraping, Bowden ooze at strand starts (Ender), PETG/ABS, non-round strands. **Validation print**: single-strand ladder at 20–120 mm in 10 mm steps on both printers, midspan sag measured with calipers, then re-fit `F_SCALE` and the air speeds.

## Files
- `tether_sim.py`: the model (v0.3). `calibrate.py`: drawing-force fit.
- `sweep.py` → `results.json`: speed, fan, flow and air-sensitivity sweeps.
- `layers.py` → `layers.json`: layer 2–3 fusion vs Z-offset schedule.
- `catchup.py` → `catchup.json`: height recovery per layer vs flow.
- `plots.py`: charts. `tether_sim_v01.py`, `tether_sim_v02_creep_rejected.py`: earlier versions kept for the log. v0.2 treated all hot material as free-creeping and predicted slack strands, which contradicts real bridges. Rejected in favour of the drawing (fibre-spinning) picture.

All runs take under a minute in total, with a heartbeat line per run.
