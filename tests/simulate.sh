#!/usr/bin/env bash
# Simule deux etapes completes, sans reseau. Visuels dans out/, etat dans state.json.
set -euo pipefail
cd "$(dirname "$0")/.."
export TDP_IBU_FIXTURES=tests/fixtures TDP_DRY_RUN=1 TDP_WATERMARK=1 TDP_STATE=tests/sim_state.json TDP_OUT=tests/out
rm -rf tests/out tests/sim_state.json tests/fixtures
python tests/make_fixtures.py tests/fixtures
for t in 2026-11-29T11:05 2026-11-29T14:30 2026-12-16T09:05 2026-12-16T12:05 2026-12-16T15:05 2026-12-17T11:30 2026-12-17T12:20 2026-12-17T13:16 2026-12-17T15:00 2026-12-19T12:30 2026-12-19T13:05 2026-12-19T16:00; do
  echo "=== $t"; python -m tdp.tick --now "$t"
done
python tests/make_fixtures.py tests/fixtures --after
for t in 2026-12-21T09:05 2026-12-22T09:05 2026-12-22T13:05; do
  echo "=== $t"; python -m tdp.tick --now "$t"
done
python - <<'PY'
import json; s=json.load(open("tests/sim_state.json"))
for k,v in s["posts"].items(): print(f"{k:45s} {v['status']:10s} {len(v.get('files',[]))} visuel(s)")
PY
