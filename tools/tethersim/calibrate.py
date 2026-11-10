import sys; sys.path.insert(0,'.')
from tether_sim import run_strand
print("F_scale | Ender3 v=25 sag(no-shrink) at 25/50/80/100 mm", flush=True)
for fs in (1.0, 0.5, 0.3, 0.2, 0.15, 0.1):
    r=[run_strand(L,"Ender 3",v=25,F_scale=fs)["sag_noshrink_mm"] for L in (25,50,80,100)]
    print(f"{fs:5.2f} | " + "  ".join(f"{x:.2f}" for x in r), flush=True)
