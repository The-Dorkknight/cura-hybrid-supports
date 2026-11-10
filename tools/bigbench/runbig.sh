#!/bin/bash
# usage: runbig.sh outdir mode model.stl quick(1/0) plain(1/0)
out=$1; mode=$2; model=$3; quick=$4; plain=$5
cd /home/claude/src/cura-hybrid-supports
for try in 1 2 3; do
  rm -rf $out /home/claude/home_big; cp -r /home/claude/warmhome /home/claude/home_big
  HS_HOME=/home/claude/home_big HS_HARNESS_PRINTER=elegoo_neptune_4 HS_HARNESS_QUICK=$quick HS_HARNESS_PLAIN=$plain HS_MODEL_FILE=$model HS_TIMEOUT=3000 \
    tests/cura_harness/run_in_cura.sh /home/claude/cura/squashfs-root/AppRun 5.13 $out $mode >/dev/null 2>&1
  if [ -f $out/hybrid.gcode ] || [ -f $out/plain.gcode ]; then echo "$(date +%H:%M) $out ok"; exit 0; fi
done
echo "$(date +%H:%M) $out FAILED"; python3 -c "import json;r=json.load(open('$out/results.json'));print(r.get('error','')[-300:])"
