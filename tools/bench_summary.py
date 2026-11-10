# Summarise a folder of benchmark runs (out/<model>__<mode>/hybrid.gcode, cura_support.gcode, cura_tree.gcode):
# Cura's time estimate and the filament (metres) spent on support moves. Edit B to point at your output folder.
import re, sys, glob, os
B='/tmp/claude-0/cura/bench/out/'
def stats(path):
    t=''; e_prev=0.0; sup=0.0; tm=None; fil=None; rel=False; z=0; zmax=0
    for l in open(path, errors='ignore'):
        if l.startswith(';TIME:') and tm is None: tm=int(l[6:])
        elif l.startswith(';Filament used:') and fil is None: fil=float(l.split(':')[1].strip().rstrip('m'))
        elif l.startswith(';TYPE:'): t=l[6:].strip()
        elif l.startswith('M83'): rel=True
        elif l.startswith('G92'):
            m=re.search(r'E(-?[\d.]+)',l)
            if m: e_prev=float(m.group(1))
        elif l.startswith(('G0','G1')):
            m=re.search(r' E(-?[\d.]+)',l)
            if m:
                e=float(m.group(1)); d=e if rel else e-e_prev
                if not rel: e_prev=e
                if d>0 and t.startswith('SUPPORT') and re.search(r' [XY]',l): sup+=d
    return tm,fil,sup
rows={}
for d in sorted(glob.glob(B+'*/')):
    name=os.path.basename(d.rstrip('/')); model,mode=name.split('__')
    for f,label in (('hybrid.gcode',mode),('cura_support.gcode','cura_sparse5' if mode=='ref' else None),('cura_tree.gcode','cura_tree' if mode=='ref' else None)):
        p=d+f
        if label and os.path.exists(p) and os.path.getsize(p):
            if mode=='ref' and f=='hybrid.gcode': continue
            rows.setdefault(model,{})[label]=stats(p)
for model,r in rows.items():
    print('\n==',model)
    print(f"{'support':14} {'time min':>9} {'support m':>10}")
    for k,(tm,fil,sup) in sorted(r.items(), key=lambda kv: kv[1][2]):
        print(f"{k:14} {tm/60 if tm else 0:9.1f} {sup/1000:10.2f}")
