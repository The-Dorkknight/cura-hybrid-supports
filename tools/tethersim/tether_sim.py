#!/usr/bin/env python3
"""
tether_sim.py  v0.3  (2026-11-10)
Single-strand bridge / tether sag model for FDM PLA.
Research tool for cura-hybrid-supports (tether head) and the paper
"Putting plastic on a pedestal: experimental methods of plastic waste reduction".

Cheap by design: one strand takes well under a second; full sweeps print a
heartbeat line per run so a slow machine never looks crashed.

PHYSICAL PICTURE (fibre-spinning analogy)
  The nozzle draws the melt from the orifice area (0.4 mm round) down to the bridge
  strand area (flow x line width x layer height). Mass conservation fixes the strand
  length to the travel length, so the strand is pulled taut with the DRAWING FORCE
      F = 3 * eta(T_exit) * A_mean * v * ln(DR) / L_draw
  (Trouton viscosity, DR = draw ratio). The hot zone behind the nozzle hangs like a
  string between the nozzle and the freeze point; whatever droop it has when an
  element freezes is locked in. Frozen strand then sags elastically as a tensioned
  beam under its own weight.

  Thermal   : lumped cooling per 0.5 mm element (Hilpert cross-flow cylinder) with
              local fan air speed (jet decays behind nozzle) + optional uniform aux
              fan stream + natural convection + radiation.
  Viscosity : VFT fit, eta(200 C)=800 Pa.s, eta(Tg)=1e12 Pa.s.
  Stiffness : E(T) glass 3.3 GPa -> rubber 3 MPa -> melt; born in deformed state.
  Loads     : gravity + downward component of fan drag.
  Far wall  : clamped on arrival; then post-anchor thermal shrink of the last hot
              section adds tension (scaled by anchor_eff; 0 = soft walls, 1 = rigid).
  Layers    : strand n+1 laid over frozen strand n (rigid obstacle) with optional
              nozzle Z-offset curve; contact while > T_fuse counts as fused.

NOT MODELLED: lateral fan push, necking/snapping, anchor pull-out, nozzle scraping
the strand below, non-round strands, PETG/ABS. Air speeds are ESTIMATES.
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

PLA = dict(rho=1240.0, cp=1800.0, k=0.13, Tg=58.0, E_glass=3.3e9, E_rubber=3e6,
           E_melt=2e4, alpha=6.8e-5, vft_A=-0.41, vft_B=640.0)
AIR = dict(rho=1.18, nu=1.6e-5, k=0.026, Pr=0.71)
NOZZLE_D = 0.4e-3
F_SCALE = 0.25  # calibrated vs Creality/Qidi PLA bridge guidance for Ender-class printers (calibrate.py)

# EST air: U0 = jet speed at nozzle (m/s, 100% fan), lam = jet decay length behind
# nozzle (m), fv = downward fraction of drag. U_aux = uniform rear-fan stream.
PRINTERS = {
    "Ender 3":   dict(U0=3.5, lam=6e-3,  fv=0.5, U_aux=0.0, fv_aux=0.0),
    "Neptune 4": dict(U0=6.0, lam=10e-3, fv=0.5, U_aux=2.5, fv_aux=0.1),
}

def hilpert_h(U, d):
    Re = np.maximum(U, 1e-6) * d / AIR["nu"]
    C = np.where(Re < 4, 0.989, np.where(Re < 40, 0.911, 0.683))
    m = np.where(Re < 4, 0.330, np.where(Re < 40, 0.385, 0.466))
    return C * Re**m * AIR["Pr"]**(1/3) * AIR["k"] / d

def E_of_T(T, p=PLA):
    lg, lr, lm = np.log10(p["E_glass"]), np.log10(p["E_rubber"]), np.log10(p["E_melt"])
    s1 = 1/(1+np.exp(-(T-(p["Tg"]+5))/3.0))
    s2 = 1/(1+np.exp(-(T-120)/12.0))
    return 10**(lg + (lr-lg)*s1 + (lm-lr)*s2)

def eta_of_T(T, p=PLA):
    return 10**(p["vft_A"] + p["vft_B"]/np.maximum(T - (p["Tg"]-51.6), 1.0))

_OPS = {}
def _ops(n, dx, far):
    key = (n, far, dx)
    if key not in _OPS:
        r, c, v = [0, 0], [1, 0], [2.0, -2.0]
        for i in range(1, n):
            r += [i]*3; c += [i-1, i, i+1]; v += [1.0, -2.0, 1.0]
        if far: r += [n, n]; c += [n-1, n]; v += [2.0, -2.0]
        D = sp.csr_matrix((np.array(v)/dx**2, (r, c)), shape=(n+1, n+1))
        r2, c2, v2 = [], [], []
        for i in range(1, n):
            r2 += [i]*3; c2 += [i-1, i, i+1]; v2 += [1.0, -2.0, 1.0]
        S = sp.csr_matrix((np.array(v2)/dx**2, (r2, c2)), shape=(n+1, n+1))
        _OPS[key] = (D, S)
    return _OPS[key]

def _solve(F, EI, q, K, kap, far, nozzle_z, cmask, obst, dx):
    n = len(EI)-1
    D, S = _ops(n, dx, far)
    EIv, Kv = EI.copy(), K.copy()
    if not far: EIv[n] = 0.0; Kv[n] = 0.0
    M = (S @ sp.diags(EIv) @ D - F*D).tocsr()
    rhs = q - S @ (Kv - EIv*kap)
    fixed = np.zeros(n+1, bool); fixed[[0, n]] = True
    val = np.zeros(n+1); val[n] = 0.0 if far else nozzle_z
    if cmask is not None: fixed |= cmask; val[cmask] = obst[cmask]
    free = np.where(~fixed)[0]
    wv = val.copy()
    if free.size:
        Mr = M[free]
        wv[free] = spla.spsolve(Mr[:, free].tocsc(), rhs[free] - Mr[:, fixed] @ val[fixed])
    return wv, D

def run_strand(span_mm, printer, v=20.0, fan=1.0, flow=0.9, T_noz=200.0, T_amb=25.0,
               line_w=0.44, layer_h=0.2, L_draw=1.5e-3, dx_mm=0.5, anchor_eff=0.5,
               obstacle=None, z_offset=None, T_fuse=120.0, hold_s=3.0, air=None, F_scale=F_SCALE):
    """Returns dict. w (mm) is + DOWN from the nominal (planar) strand centreline.
    obstacle: +down position (mm) above which this strand's centre cannot go
              (= lower strand centre - centre spacing needed to touch).
    z_offset: +down nozzle Z lowering (mm) along the path."""
    _OPS.clear()
    pr = dict(PRINTERS[printer]); pr.update(air or {})
    A = flow*line_w*layer_h*1e-6
    d = np.sqrt(4*A/np.pi); I = np.pi*d**4/64
    A_n = np.pi*NOZZLE_D**2/4
    DR = A_n/A
    q_g = PLA["rho"]*9.81*A
    dx = dx_mm*1e-3; v_ms = v*1e-3; dt = dx/v_ms
    N = int(round(span_mm/dx_mm)); hold = int(hold_s/dt)
    T_exit = T_noz - 10.0
    F = 3*eta_of_T(T_exit)*np.sqrt(A*A_n)*v_ms*max(np.log(DR), 0.0)/L_draw*F_scale + 2e-5
    drag_k = 0.5*AIR["rho"]*1.3*d

    x = np.array([0.0]); T = np.array([T_amb+5.0]); w = np.zeros(1)
    K = np.zeros(1); kap = np.zeros(1); fused = np.zeros(1, bool)
    out = dict(F_draw_mN=F*1e3, d_mm=d*1e3, draw_ratio=DR)
    T_at_anchor = None
    for step in range(N + hold):
        laying = step < N
        if laying:
            x = np.append(x, x[-1]+dx); T = np.append(T, T_exit)
            w = np.append(w, 0.0); K = np.append(K, 0.0); kap = np.append(kap, 0.0)
            fused = np.append(fused, False)
        elif T_at_anchor is None:
            T_at_anchor = T.copy()
        s = x[-1]
        fan_on = laying or (step-N)*dt < 0.5
        dist = s - x
        Uh = fan*pr["U0"]*np.exp(-dist/pr["lam"]) if fan_on else 0*x
        Ua = fan*pr["U_aux"]*np.ones_like(x) if fan_on else 0*x
        h = hilpert_h(np.hypot(Uh, Ua), d) + 34.0
        tau = PLA["rho"]*PLA["cp"]*d/(4*h)*(1 + h*(d/2)/(4*PLA["k"]))
        T = T_amb + (T - T_amb)*np.exp(-dt/tau); T[0] = T_amb + 5
        q = q_g + (drag_k*(pr["fv"]*Uh**2 + pr["fv_aux"]*Ua**2) if (fan_on and laying) else 0*x)
        EI = E_of_T(T)*I
        nz = z_offset[len(x)-1]*1e-3 if (z_offset is not None and laying) else 0.0
        obst = None if obstacle is None else obstacle[:len(x)]*1e-3
        cm = None if obst is None else np.zeros(len(x), bool)
        for _ in range(25):
            wv, D = _solve(F, EI, q, K, kap, not laying, nz, cm, obst, dx)
            if cm is None: break
            pen = wv > obst + 1e-9; pen[[0, -1]] = False
            if not (pen & ~cm).any(): break
            cm |= pen
        newk = D @ wv
        K = K + EI*(newk - kap); kap = newk; w = wv
        if cm is not None: fused |= cm & (T > T_fuse)
        if step == N-1:
            out["sag_laying_mm"] = float(w.max()*1e3)
            out["hot_len_mm"] = float((T > PLA["Tg"]+15).sum()*dx_mm)
    out["sag_noshrink_mm"] = float(w.max()*1e3)
    # post-anchor shrink tension (length compatibility, both ends held)
    if anchor_eff > 0 and T_at_anchor is not None and obstacle is None:
        dL = anchor_eff*float(np.sum(PLA["alpha"]*np.clip(np.minimum(T_at_anchor, PLA["Tg"]) - T, 0, None))*dx)
        EA = PLA["E_glass"]*A; L = x[-1]
        arc = lambda wv: 0.5*np.sum(np.diff(wv)**2)/dx
        a0 = arc(w); EI = E_of_T(T)*I
        def r(Ft):
            wv, _ = _solve(Ft, EI, q_g+0*x, K, kap, True, 0.0, None, None, dx)
            return arc(wv) - (a0 - dL + (Ft-F)*L/EA), wv
        lo, hi = F, F + EA*dL/L + 1e-7
        rh, wh = r(hi)
        if rh < 0:
            for _ in range(40):
                mid = 0.5*(lo+hi); rm, wm = r(mid)
                if rm > 0: lo = mid
                else: hi, wh = mid, wm
        w = wh; out["F_final_mN"] = hi*1e3
    out.update(x=x*1e3, w=w*1e3, sag_mm=float(w.max()*1e3),
               fused_frac=None if obstacle is None else float(fused[2:-2].mean()))
    return out

if __name__ == "__main__":
    import time
    for p in PRINTERS:
        for L in (40, 80, 120):
            t0 = time.time(); r = run_strand(L, p)
            print(f"{p:10s} L={L:3d}  laying {r['sag_laying_mm']:.2f}  no-shrink {r['sag_noshrink_mm']:.2f}"
                  f"  final {r['sag_mm']:.2f} mm  hot {r['hot_len_mm']:.0f} mm  F {r['F_draw_mN']:.2f} mN"
                  f"  ({time.time()-t0:.2f}s)", flush=True)
