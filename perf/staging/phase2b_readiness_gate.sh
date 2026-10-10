#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVIDENCE_DIR="${FINACC_PHASE2B_EVIDENCE_DIR:-$ROOT_DIR/docs/qa/performance/evidence/phase2b}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$EVIDENCE_DIR"
cd "$ROOT_DIR"

echo "Running redacted performance-staging safety audit..."
python manage.py audit_performance_staging --json --strict \
  > "$EVIDENCE_DIR/staging_safety_audit_$STAMP.json"

echo "Capturing Django release-environment audit..."
python manage.py audit_release_environment --json \
  > "$EVIDENCE_DIR/release_environment_audit_$STAMP.json"

echo "Capturing PostgreSQL/runtime telemetry snapshot..."
python perf/baseline/phase1d_resource_monitor.py \
  --output "$EVIDENCE_DIR/telemetry_snapshot_$STAMP.csv" \
  --duration "${FINACC_PHASE2B_TELEMETRY_SECONDS:-10}" \
  --interval 2

echo "Phase 2B readiness evidence captured under $EVIDENCE_DIR"
