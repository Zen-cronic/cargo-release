#!/usr/bin/env bash
set -euo pipefail

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-ata-2026-cargo}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
CONTROLLER_SERVICE="cargo-release-controller"
WEB_SERVICE="cargo-release-web"
CONTROLLER_CANDIDATE="cargo-release-controller-00021-tac"
WEB_CANDIDATE="cargo-release-web-00016-nol"
CONTROLLER_ROLLBACK="cargo-release-controller-00019-ton"
WEB_ROLLBACK="cargo-release-web-00014-pag"
CONTROLLER_IMAGE="us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/backend@sha256:19e842e379fed15c4692b699fb903508eaff5de59dc1f7edc4555a6c165fe4aa"
WEB_IMAGE="us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/web@sha256:76d2b0ef3e23c3a7307c8ad3f6ef91980b6bde842dcfba509440ab709f2b9b8b"
WEB_URL="https://cargo-release-web-1015646664425.us-central1.run.app"
CANDIDATE_WEB_URL="https://recording-59b2aed---cargo-release-web-zy35vzmm6a-uc.a.run.app"
APPROVAL_PHRASE="I_APPROVE_PROMOTE_RECORDING_59B2AED_CONTROLLER_00021_WEB_00016_KEEP_00019_00014_ROLLBACK"
APPROVAL="${CARGO_RELEASE_RECORDING_PROMOTION_APPROVED:-}"

if [[ "${GOOGLE_CLOUD_PROJECT}" != "ata-2026-cargo" ]] || \
  [[ "${GOOGLE_CLOUD_LOCATION}" != "us-central1" ]]; then
  printf '%s\n' "This helper is pinned to ata-2026-cargo/us-central1." >&2
  exit 2
fi

for command in gcloud jq curl; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "${command}" >&2
    exit 2
  fi
done

active_account="$(gcloud config get-value account 2>/dev/null)"
active_project="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "${active_account}" ]] || [[ "${active_project}" != "${GOOGLE_CLOUD_PROJECT}" ]]; then
  printf 'Expected an active account in %s; found account=%s project=%s.\n' \
    "${GOOGLE_CLOUD_PROJECT}" "${active_account:-none}" "${active_project:-none}" >&2
  exit 2
fi

service_json() {
  gcloud run services describe "$1" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --region="${GOOGLE_CLOUD_LOCATION}" \
    --format=json
}

revision_json() {
  gcloud run revisions describe "$1" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --region="${GOOGLE_CLOUD_LOCATION}" \
    --format=json
}

serving_revision() {
  jq -er '.status.traffic[] | select(.percent == 100) | .revisionName'
}

assert_ready_image() {
  local revision="$1"
  local expected_image="$2"
  local payload ready actual_image
  payload="$(revision_json "${revision}")"
  ready="$(jq -er '.status.conditions[] | select(.type == "Ready") | .status' <<<"${payload}")"
  actual_image="$(jq -er '.spec.containers[0].image' <<<"${payload}")"
  if [[ "${ready}" != "True" ]] || [[ "${actual_image}" != "${expected_image}" ]]; then
    printf 'Revision preflight failed: revision=%s ready=%s image=%s expected=%s.\n' \
      "${revision}" "${ready}" "${actual_image}" "${expected_image}" >&2
    return 1
  fi
}

assert_ready() {
  local revision="$1"
  local payload ready
  payload="$(revision_json "${revision}")"
  ready="$(jq -er '.status.conditions[] | select(.type == "Ready") | .status' <<<"${payload}")"
  if [[ "${ready}" != "True" ]]; then
    printf 'Rollback revision is not Ready: revision=%s status=%s.\n' "${revision}" "${ready}" >&2
    return 1
  fi
}

controller_before="$(service_json "${CONTROLLER_SERVICE}")"
web_before="$(service_json "${WEB_SERVICE}")"
controller_serving_before="$(serving_revision <<<"${controller_before}")"
web_serving_before="$(serving_revision <<<"${web_before}")"

if [[ "${controller_serving_before}" != "${CONTROLLER_ROLLBACK}" ]] || \
  [[ "${web_serving_before}" != "${WEB_ROLLBACK}" ]]; then
  printf 'Production drifted from the pinned rollback pair: controller=%s web=%s.\n' \
    "${controller_serving_before}" "${web_serving_before}" >&2
  exit 2
fi

assert_ready_image "${CONTROLLER_CANDIDATE}" "${CONTROLLER_IMAGE}"
assert_ready_image "${WEB_CANDIDATE}" "${WEB_IMAGE}"
assert_ready "${CONTROLLER_ROLLBACK}"
assert_ready "${WEB_ROLLBACK}"

if [[ "${APPROVAL}" != "${APPROVAL_PHRASE}" ]]; then
  printf '%s\n' \
    "Promotion preflight passed; no traffic changed." \
    "Active account: ${active_account}" \
    "Controller candidate: ${CONTROLLER_CANDIDATE}" \
    "Controller rollback: ${CONTROLLER_ROLLBACK}" \
    "Web candidate: ${WEB_CANDIDATE}" \
    "Web rollback: ${WEB_ROLLBACK}" \
    "To authorize controller-first promotion with automatic pair rollback on failure, set:" \
    "CARGO_RELEASE_RECORDING_PROMOTION_APPROVED=${APPROVAL_PHRASE}" >&2
  exit 3
fi

controller_promoted=0
web_promoted=0

rollback_on_error() {
  local exit_code="$?"
  trap - ERR
  set +e
  printf '%s\n' "Promotion verification failed; restoring the pinned pair." >&2
  if [[ "${web_promoted}" == "1" ]]; then
    gcloud run services update-traffic "${WEB_SERVICE}" \
      --project="${GOOGLE_CLOUD_PROJECT}" \
      --region="${GOOGLE_CLOUD_LOCATION}" \
      --to-revisions="${WEB_ROLLBACK}=100" \
      --quiet >&2
  fi
  if [[ "${controller_promoted}" == "1" ]]; then
    gcloud run services update-traffic "${CONTROLLER_SERVICE}" \
      --project="${GOOGLE_CLOUD_PROJECT}" \
      --region="${GOOGLE_CLOUD_LOCATION}" \
      --to-revisions="${CONTROLLER_ROLLBACK}=100" \
      --quiet >&2
  fi
  exit "${exit_code}"
}
trap rollback_on_error ERR

controller_promoted=1
gcloud run services update-traffic "${CONTROLLER_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --to-revisions="${CONTROLLER_CANDIDATE}=100" \
  --quiet

controller_after="$(service_json "${CONTROLLER_SERVICE}")"
controller_serving_after="$(serving_revision <<<"${controller_after}")"
[[ "${controller_serving_after}" == "${CONTROLLER_CANDIDATE}" ]]
assert_ready_image "${CONTROLLER_CANDIDATE}" "${CONTROLLER_IMAGE}"
assert_ready "${CONTROLLER_ROLLBACK}"

controller_health="$(curl --silent --show-error --fail \
  "${CANDIDATE_WEB_URL}/api/cargo/health")"
jq -e '.status == "ok" and .database == "postgresql"' <<<"${controller_health}" >/dev/null

web_promoted=1
gcloud run services update-traffic "${WEB_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --to-revisions="${WEB_CANDIDATE}=100" \
  --quiet

web_after="$(service_json "${WEB_SERVICE}")"
web_serving_after="$(serving_revision <<<"${web_after}")"
[[ "${web_serving_after}" == "${WEB_CANDIDATE}" ]]
assert_ready_image "${WEB_CANDIDATE}" "${WEB_IMAGE}"
assert_ready "${WEB_ROLLBACK}"

relay_tmp="$(mktemp -d)"
trap 'rm -r "${relay_tmp}"' EXIT
health_status="$(curl --silent --show-error --output "${relay_tmp}/health.json" \
  --write-out '%{http_code}' "${WEB_URL}/api/cargo/health")"
forbidden_status="$(curl --silent --show-error --output "${relay_tmp}/forbidden.txt" \
  --write-out '%{http_code}' "${WEB_URL}/api/cargo/v1/notifications")"
query_status="$(curl --silent --show-error --output "${relay_tmp}/query.txt" \
  --write-out '%{http_code}' "${WEB_URL}/api/cargo/health?debug=1")"
jq -e '.status == "ok" and .database == "postgresql"' "${relay_tmp}/health.json" >/dev/null
[[ "${health_status}" == "200" ]]
[[ "${forbidden_status}" == "404" ]]
[[ "${query_status}" == "400" ]]

trap - ERR
printf '%s\n' \
  "Recording repair promoted and verified." \
  "CONTROLLER_REVISION=${CONTROLLER_CANDIDATE}" \
  "CONTROLLER_ROLLBACK=${CONTROLLER_ROLLBACK}" \
  "WEB_REVISION=${WEB_CANDIDATE}" \
  "WEB_ROLLBACK=${WEB_ROLLBACK}" \
  "RELAY_PROOF=health:200,forbidden:404,query:400" \
  "PUBLIC_URL=${WEB_URL}"
