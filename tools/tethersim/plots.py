import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
R = json.load(open("results.json"))["results"]; C = json.load(open("catchup.json"))
RAMP = {0: "#86b6ef", 1: "#3987e5", 2: "#184f95"}
INK, MUTED, GRID = "#1f1f1e", "#6b6a64", "#e4e3dd"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False})
fig, axs = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
for ax, p in zip(axs, ("Ender 3", "Neptune 4")):
    for i, v in enumerate(("10", "20", "40")):
        c = R["speed"][p][v]
        xs = [q["span"] for q in c]; ys = [q["noshrink"] for q in c]
        ax.plot(xs, ys, color=RAMP[i], lw=2, marker="o", ms=4, label=f"{v} mm/s")
    for b, lab in ((0.45, "5-layer catch-up, flow 0.9"), (0.6, "5-layer catch-up, flow 1.2-1.5")):
        ax.axhline(b, color=MUTED, lw=1, ls="--"); ax.text(22, b+0.04, lab, color=MUTED, fontsize=8)
    ax.set_title(f"{p} (stock cooling)", color=INK, loc="left", fontsize=11)
    ax.set_xlabel("Unsupported tether span (mm)"); ax.set_ylim(0, 2.6); ax.set_xlim(15, 125)
    ax.grid(axis="y", color=GRID, lw=0.8)
axs[0].set_ylabel("Mid-span sag while printing (mm)")
axs[1].legend(frameon=False, loc="upper left", title="Tether speed")
fig.suptitle("Simulated PLA tether sag, 0.4 mm nozzle, 0.2 mm layers, bridge flow 0.9",
             color=INK, x=0.01, ha="left", fontsize=12)
fig.tight_layout(); fig.savefig("sag_vs_span.png", dpi=130)

fig, axs = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
for ax, p in zip(axs, ("Ender 3", "Neptune 4")):
    for i, fu in enumerate(("0.9", "1.2", "1.5")):
        ys = C[f"{p}|80|{fu}"]; xs = list(range(1, len(ys)+1))
        ax.plot(xs, ys, color=RAMP[i], lw=2, marker="o", ms=4, label=f"flow {fu}")
    ax.set_title(f"{p}: 80 mm span", color=INK, loc="left", fontsize=11)
    ax.set_xlabel("Tether layer"); ax.grid(axis="y", color=GRID, lw=0.8)
axs[0].set_ylabel("Height deficit vs nominal Z (mm)")
axs[1].legend(frameon=False, title="Flow on layers 2+")
fig.suptitle("Catch-up: how fast the stack gets back to nominal height", color=INK, x=0.01, ha="left", fontsize=12)
fig.tight_layout(); fig.savefig("catchup.png", dpi=130)
print("ok")
