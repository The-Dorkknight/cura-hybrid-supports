import sys; sys.path[:0]=["/home/claude/src/cura-hybrid-supports/HybridSupports","/home/claude/src/cura-hybrid-supports/tests"]
import numpy as np, hybrid_core as hc, models as M
def cat(*ms):
    v=[];f=[];o=0
    for m in ms: v.append(m.vertices); f.append(m.faces+o); o+=len(m.vertices)
    return hc.Mesh(np.vstack(v),np.vstack(f))
W,L,T,R=200.0,200.0,10.0,5.0
def u(h):   # 200 x 200 U: two 10 mm legs, 5 mm roof whose underside is h above the bed
    return cat(M.box(0,0,0,T,L,h), M.box(W-T,0,0,W,L,h), M.box(0,0,h,W,L,h+R))
def mushroom(h, stem=30.0):   # 200 x 200 table top on one 30 x 30 stem
    c=W/2
    return cat(M.box(c-stem/2,c-stem/2,0,c+stem/2,c+stem/2,h), M.box(0,0,h,W,L,h+R))
for name,m in [("U200_h50",u(50.1)),("U200_h150",u(150.1)),("mushroom200_h150",mushroom(150.1))]:
    hc.write_stl(f"/home/claude/big/{name}.stl", m); print(name, m.vertices.min(0), m.vertices.max(0))
