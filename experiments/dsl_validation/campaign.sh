#!/bin/bash
# Launch every cell for one writer model in parallel. Usage: campaign.sh <tag> <openrouter-id>
TAG=$1; MODEL=$2
cd "$(dirname "$0")/../.."
R="venv/bin/python experiments/dsl_validation/run_cell.py --model $MODEL"
mkdir -p work/dsl/logs
for F in alcyone orehauler; do
  $R --name e1-$TAG-$F-off --foundation $F --ticks 8 > work/dsl/logs/e1-$TAG-$F-off.log 2>&1 &
  $R --name e1-$TAG-$F-on  --foundation $F --ticks 8 --set generation.enable_scene_skeleton=true > work/dsl/logs/e1-$TAG-$F-on.log 2>&1 &
  $R --name e2-$TAG-$F-single --foundation $F --ticks 6 --set generation.enable_scene_skeleton=true --set generation.scene_length_preset=masters > work/dsl/logs/e2-$TAG-$F-single.log 2>&1 &
  $R --name e2-$TAG-$F-sect   --foundation $F --ticks 6 --set generation.enable_scene_skeleton=true --set generation.scene_length_preset=masters --set generation.subblock_generation=true > work/dsl/logs/e2-$TAG-$F-sect.log 2>&1 &
  if [ "$3" != "noe3" ]; then
  $R --name e3-$TAG-$F-off --foundation $F --ticks 15 --set generation.use_plot_first=true > work/dsl/logs/e3-$TAG-$F-off.log 2>&1 &
  $R --name e3-$TAG-$F-on  --foundation $F --ticks 15 --set generation.use_plot_first=true --set generation.use_contracts=true > work/dsl/logs/e3-$TAG-$F-on.log 2>&1 &
  fi
done
wait
