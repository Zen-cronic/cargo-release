#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="ata-2026-cargo"
TOPIC="cargo-casualties"
PUBLIC_BASE_URL="https://cargo-release-web-1015646664425.us-central1.run.app"
REQUIRED_APPROVAL="I_APPROVE_ONE_MARKED_SYNTHETIC_RECORDING_EVENT"

if [[ "${CARGO_RELEASE_RECORDING_EVENT_APPROVED:-}" != "${REQUIRED_APPROVAL}" ]]; then
  printf '%s\n' "Recording event not published."
  printf '%s\n' "To publish exactly one marked synthetic Pub/Sub event, run:"
  printf '%s\n' \
    "CARGO_RELEASE_RECORDING_EVENT_APPROVED=${REQUIRED_APPROVAL} ./scripts/publish_recording_event.sh"
  exit 3
fi

for command_name in gcloud sha256sum cut; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Required command is unavailable: %s\n' "${command_name}" >&2
    exit 2
  fi
done

payload='{"source_ref":"SYNTHETIC/ALL-THINGS-AGENTIC/CONTINUOUS-DEMO","vessel":"MV Northstar","container_ref":"TCLU-482019-7"}'

message_id="$({
  gcloud pubsub topics publish "${TOPIC}" \
    --project="${PROJECT_ID}" \
    --message="${payload}" \
    --attribute="schema=casualty-declared-v1,synthetic=true" \
    --format='value(messageIds[0])'
} 2>/dev/null)"

if [[ ! "${message_id}" =~ ^[0-9]+$ ]]; then
  printf '%s\n' "Pub/Sub did not return one numeric message ID; no mission URL can be derived." >&2
  exit 1
fi

mission_suffix="$(printf '%s' "${message_id}" | sha256sum | cut -c1-12)"
mission_id="mission-${mission_suffix}"

printf 'MARKED SYNTHETIC EVENT PUBLISHED — NO REAL CARGO ACTION\n'
printf 'Message ID: %s\n' "${message_id}"
printf 'Mission ID: %s\n' "${mission_id}"
printf 'Mission URL: %s/?mission=%s\n' "${PUBLIC_BASE_URL}" "${mission_id}"
printf 'Expected first stop: READY_FOR_SIGNATURE / owner-bond human gate\n'
