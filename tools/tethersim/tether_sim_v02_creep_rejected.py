#!/usr/bin/env python3
"""
tether_sim.py  v0.2  (2026-11-10)
Single-strand bridge / tether sag model for FDM PLA - research tool for
cura-hybrid-supports (tether head) and the "Putting plastic on a pedestal" paper.

Cheap by design: a full sweep runs in a few minutes on a 7th-gen i3, and
prints a heartbeat line per run.

PHYSICS
  Thermal   : lumped cooling per 0.5 mm element; h = Hilpert cross-flow cylinder
              correlation from local fan air speed + natural convection + radiation.
              Air speed decays exponentially behind the nozzle (duct jet), plus an
              optional uniform auxiliary-fan stream (Neptune 4 rear fan).
  Viscosity : VFT fit, eta(200 C)=800 Pa.s, eta(Tg)=1e12 Pa.s, T_inf = Tg-51.6.
  Stiffness : E(T) log-sigmoid glass (3.3 GPa) -> rubber (3 MPa) -> melt.
              Stiffness is born in the deformed shape (incremental freezing), so
              droop that happens while hot is locked in.
  Loads     : gravity + vertical component of fan drag on the strand.
  Tension   : uniform horizontal tension F, found every step by LENGTH
              COMPATIBILITY: geometric excess length of the strand = viscous creep
              (Trouton, eps_dot = F / 3 eta A) + rubbery elastic stretch - thermal
              shrink below Tg. The first 1 mm behind the nozzle is the drawing zone
              (accounted for by bridge flow) and is excluded from creep.
  Mechanics : quasi-static tensioned Euler-Bernoulli beam, finite differences,
              clamped at the start wall, pinned at the nozzle (held at nozzle Z),
              clamped at the far wall once reached, then 3 s of cooling.
  Layers    : strand n+1 can be laid over frozen strand n (rigid obstacle) with an
              optional Z-offset curve; contact while hotter than T_fuse = fused.

LIMITS (read before trusting numbers): no lateral fan push, no strand necking/
snapping, no anchor pull-out, no nozzle contact with previous strand, round strand.
All air speeds are ESTIMATES - see the sensitivity sweep.
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

PLA = dict(rho=1240.0, cp=1800.0, k=0.13, Tg=58.0, E_glass=3.3e9, E_rubber=3e6,
           E_melt=2e4, alpha=6.8e-5, vft_A=-0.41, vft_B=640.0)
AIR = dict(rho=1.18, nu=1.6e-5, k=0.026, Pr=0.71)

# EST: U0 = jet speed at the nozzle (m/s) at 100% fan, lam = decay length behind
# nozzle (m), fv = fraction of drag acting downward. U_aux = uniform rear-fan stream.
PRINTERS = {
    "Ender 3": dict(U0=3.5, lam=6e-3, fv=0.5, U_aux=0.0, fv_aux=0.0,
                    note="stock 4010 blower, one-sided duct"),
    "Neptune 4": dict(U0=6.0, lam=10e-3, fv=0.5, U_aux=2.5, fv_aux=0.1,
                      note="stock head blower + big rear auxiliary fan"),
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
    Tinf = p["Tg"] - 51.6
    return 10**(p["vft_A"] + p["vft_B"]/np.maximum(T - Tinf, 1.0))

_OPS = {}
def _ops(n, dx, far_clamped):
    key = (n, far_clamped)
    if key in _OPS: return _OPS[key]
    rows, cols, vals = [], [], []
    for i in range(n+1):
        if i == 0:
            rows += [0, 0]; cols += [1, 0]; vals += [2, -2]
        elif i == n:
            if far_clamped:
                rows += [n, n]; cols += [n-1, n]; vals += [2, -2]
        else:
            rows += [i, i, i]; cols += [i-1, i, i+1]; vals += [1, -2, 1]
    D = sp.csr_matrix((np.array(vals, float)/dx**2, (rows, cols)), shape=(n+1, n+1))
    r2, c2, v2 = [], [], []
    for i in range(1, n):
        r2 += [i, i, i]; c2 += [i-1, i, i+1]; v2 += [1, -2, 1]
    S = sp.csr_matrix((np.array(v2, float)/dx**2, (r2, c2)), shape=(n+1, n+1))
    _OPS[key] = (D, S)
    return D, S

def run_strand(span_mm, printer, v=20.0, fan=1.0, flow=0.9, T_noz=200.0, T_amb=25.0,
               line_w=0.44, layer_h=0.2, F_resid=1e-4, dx_mm=0.5,
               obstacle=None, z_offset=None, T_fuse=120.0, hold_s=3.0, air=None):
    """span_mm: unsupported length. Returns dict; w (mm) is +down from the nominal line."""
    _OPS.clear()
    pr = dict(PRINTERS[printer]);  pr.update(air or {})
    A = flow*line_w*layer_h*1e-6
    d = np.sqrt(4*A/np.pi); I = np.pi*d**4/64
    q_g = PLA["rho"]*9.81*A
    dx = dx_mm*1e-3; v_ms = v*1e-3; dt = dx/v_ms
    N = int(round(span_mm/dx_mm)); hold_steps = int(hold_s/dt)
    T_exit = T_noz - 10.0
    F_draw = F_resid + max(0.0, 3*eta_of_T(T_exit)*A*(1-flow)*v_ms/1e-3)
    drag_k = 0.5*AIR["rho"]*1.3*d
    h_extra = 25.0 + 9.0

    x = np.array([0.0]); T = np.array([T_amb+5]); w = np.zeros(1)
    K = np.zeros(1); kap = np.zeros(1); eps_c = np.zeros(1); frozen = np.array([True])
    fused = np.zeros(1, bool); F = F_draw
    out = {}

    def solve(Fv, EI, q, Kc, kc, far_clamped, nozzle_z, cmask, obst):
        n = len(EI)-1
        D, S = _ops(n, dx, far_clamped)
        EIv = EI.copy(); Kcv = Kc.copy()
        if not far_clamped: EIv[n] = 0.0; Kcv[n] = 0.0
        M = (S @ sp.diags(EIv) @ D - Fv*D).tocsr()
        rhs = q - S @ (Kcv - EIv*kc)
        fixed = np.zeros(n+1, bool); fixed[0] = True; fixed[n] = True
        val = np.zeros(n+1); val[n] = 0.0 if far_clamped else nozzle_z
        if cmask is not None:
            fixed |= cmask; val[cmask] = obst[cmask]
        free = ~fixed
        rows = np.where(free)[0]
        wv = val.copy()
        if rows.size:
            Mr = M[rows]
            b = rhs[rows] - Mr[:, fixed] @ val[fixed]
            wv[free] = spla.spsolve(Mr[:, free].tocsc(), b)
        return wv, D

    for step in range(N + hold_steps):
        laying = step < N
        if laying:
            x = np.append(x, x[-1]+dx); T = np.append(T, T_exit)
            w = np.append(w, z_offset[len(x)-1]*1e-3 if z_offset is not None else 0.0)
            K = np.append(K, 0.0); kap = np.append(kap, 0.0); eps_c = np.append(eps_c, 0.0)
            frozen = np.append(frozen, False); fused = np.append(fused, False)
        s = x[-1]
        fan_on = laying or (step-N)*dt < 0.5
        dist = np.clip(s - x, 0, None)
        Uh = fan*pr["U0"]*np.exp(-dist/pr["lam"]) if fan_on else 0*x
        Ua = fan*pr["U_aux"]*np.ones_like(x) if fan_on else 0*x
        h = hilpert_h(np.sqrt(Uh**2+Ua**2), d) + h_extra
        tau = PLA["rho"]*PLA["cp"]*d/(4*h) * (1 + h*(d/2)/(4*PLA["k"]))
        T = T_amb + (T - T_amb)*np.exp(-dt/tau); T[0] = T_amb + 5
        frozen |= T < PLA["Tg"]
        creeping = (dist > 1e-3) & (T > PLA["Tg"]+5); creeping[0] = False
        eps_c[creeping] += F/(3*eta_of_T(T[creeping])*A)*dt
        eps_th = np.where(frozen, -PLA["alpha"]*np.clip(PLA["Tg"]-T, 0, None), 0.0)
        q = q_g + (drag_k*(pr["fv"]*Uh**2 + pr["fv_aux"]*Ua**2) if fan_on else 0*x)
        EI = E_of_T(T)*I
        far = not laying
        nz = (z_offset[len(x)-1]*1e-3 if (z_offset is not None and laying) else 0.0)
        obst = obstacle[:len(x)]*1e-3 if obstacle is not None else None
        el = (T < 120); el[0] = False
        comp = np.sum(1/(E_of_T(T[el])*A))*dx
        base_excess = np.sum(eps_c + eps_th)*dx
        # chord excess due to nozzle Z offset is geometric, not material: subtract straight-line part
        def g(lF):
            Fv = np.exp(lF)
            cm = None if obst is None else np.zeros(len(x), bool)
            for _ in range(20):
                wv, D = solve(Fv, EI, q, K, kap, far, nz, cm, obst)
                if cm is None: break
                pen = wv > obst + 1e-9; pen[0] = False; pen[-1] = False
                if not (pen & ~cm).any(): break
                cm |= pen
            wl = wv - np.linspace(0, wv[-1], len(wv))
            arc = 0.5*np.sum(np.diff(wl)**2)/dx
            return arc - (base_excess + Fv*comp), (wv, D, cm)
        lo, hi = np.log(1e-6), np.log(5.0)
        res = None
        glo, rlo = g(lo)
        if glo <= 0:
            F = np.exp(lo); res = rlo
        else:
            for _ in range(18):
                mid = 0.5*(lo+hi); gm, rm = g(mid)
                if gm > 0: lo = mid
                else: hi = mid; res = rm
            F = np.exp(hi)
            if res is None: res = g(hi)[1]
        wv, D, cm = res
        newk = D @ wv
        K = K + EI*(newk - kap); kap = newk; w = wv
        if cm is not None: fused |= cm & (T > T_fuse)
        if step == N-1:
            out["sag_at_arrival"] = float(w.max()*1e3)
            out["hot_len_mm"] = float(((T > PLA["Tg"]+15).sum())*dx_mm)
            out["F_laying_mN"] = F*1e3
    out.update(x=x*1e3, w=w*1e3, sag=float(w.max()*1e3), F_final_mN=F*1e3,
               d_mm=d*1e3, F_draw_mN=F_draw*1e3,
               fused_frac=float(fused[2:-2].mean()) if obstacle is not None else None)
    return out

if __name__ == "__main__":
    import time
    for p in PRINTERS:
        t0 = time.time()
        r = run_strand(60, p)
        print(p, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k not in ("x", "w")},
              f"{time.time()-t0:.1f}s", flush=True)
