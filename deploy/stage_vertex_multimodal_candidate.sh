#!/usr/bin/env bash
set -euo pipefail

PROJECT="ata-2026-cargo"
REGION="us-central1"
CONTROLLER_SERVICE="cargo-release-controller"
WEB_SERVICE="cargo-release-web"
CONTROLLER_IMAGE="us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/backend@sha256:f9a81fd68d766f0b4e9779813728af25bcda2c61e58e6c32f370bfa95fe21f5b"
WEB_IMAGE="us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/web@sha256:2295573b113a16e66a556b8cfed59b96c2bba60b81a971ae1b5f89e2c897e664"
CONTROLLER_ROLLBACK="cargo-release-controller-00023-hay"
WEB_ROLLBACK="cargo-release-web-00018-jam"
DEPLOY_TAG="vertex-mm-c6ccfad"
CONTROLLER_AUDIENCE="https://cargo-release-controller-1015646664425.us-central1.run.app"
WEB_OPERATOR_ACTOR="demo-operator-via:cargo-web@ata-2026-cargo.iam.gserviceaccount.com"
APPROVAL_PHRASE="I_APPROVE_VERTEX_MULTIMODAL_ZERO_TRAFFIC_STAGE"
APPROVAL="${CARGO_RELEASE_VERTEX_STAGE_APPROVED:-}"

service_json() {
  gcloud run services describe "$1" --project="${PROJECT}" --region="${REGION}" --format=json
}

serving_revision() {
  jq -er '.status.traffic[] | select(.percent == 100) | .revisionName'
}

controller_before="$(service_json "${CONTROLLER_SERVICE}")"
web_before="$(service_json "${WEB_SERVICE}")"
[[ "$(serving_revision <<<"${controller_before}")" == "${CONTROLLER_ROLLBACK}" ]]
[[ "$(serving_revision <<<"${web_before}")" == "${WEB_ROLLBACK}" ]]

if [[ "${APPROVAL}" != "${APPROVAL_PHRASE}" ]]; then
  printf '%s\n' \
    "Vertex multimodal stage preflight passed; no mutation performed." \
    "Controller rollback: ${CONTROLLER_ROLLBACK}" \
    "Web rollback: ${WEB_ROLLBACK}" \
    "Set CARGO_RELEASE_VERTEX_STAGE_APPROVED=${APPROVAL_PHRASE} to stage at zero traffic." >&2
  exit 3
fi

gcloud run deploy "${CONTROLLER_SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${CONTROLLER_IMAGE}" \
  --no-traffic \
  --tag="${DEPLOY_TAG}" \
  --update-env-vars="CARGO_RELEASE_MULTIMODAL_MODE=VERTEX,CARGO_RELEASE_MULTIMODAL_LOCATION=global,CARGO_RELEASE_MULTIMODAL_MODEL=gemini-3.5-flash" \
  --quiet

controller_after="$(service_json "${CONTROLLER_SERVICE}")"
controller_revision="$(jq -er '.status.latestCreatedRevisionName' <<<"${controller_after}")"
controller_tag_url="$(jq -er --arg tag "${DEPLOY_TAG}" '.status.traffic[] | select(.tag == $tag) | .url' <<<"${controller_after}")"
[[ "$(serving_revision <<<"${controller_after}")" == "${CONTROLLER_ROLLBACK}" ]]

gcloud run deploy "${WEB_SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${WEB_IMAGE}" \
  --no-traffic \
  --tag="${DEPLOY_TAG}" \
  --update-env-vars="CARGO_RELEASE_CONTROLLER_URL=${controller_tag_url},CARGO_RELEASE_CONTROLLER_AUDIENCE=${CONTROLLER_AUDIENCE},CARGO_RELEASE_WEB_OPERATOR_ACTOR=${WEB_OPERATOR_ACTOR}" \
  --quiet

web_after="$(service_json "${WEB_SERVICE}")"
web_revision="$(jq -er '.status.latestCreatedRevisionName' <<<"${web_after}")"
web_tag_url="$(jq -er --arg tag "${DEPLOY_TAG}" '.status.traffic[] | select(.tag == $tag) | .url' <<<"${web_after}")"
[[ "$(serving_revision <<<"${web_after}")" == "${WEB_ROLLBACK}" ]]

health_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "${web_tag_url}/api/cargo/health")"
forbidden_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "${web_tag_url}/api/cargo/v1/notifications")"
query_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "${web_tag_url}/api/cargo/health?debug=1")"
[[ "${health_status}" == "200" ]]
[[ "${forbidden_status}" == "404" ]]
[[ "${query_status}" == "400" ]]

printf '%s\n' \
  "Vertex multimodal candidate staged at zero default traffic." \
  "CONTROLLER_REVISION=${controller_revision}" \
  "CONTROLLER_TAG_URL=${controller_tag_url}" \
  "CONTROLLER_ROLLBACK=${CONTROLLER_ROLLBACK}" \
  "WEB_REVISION=${web_revision}" \
  "WEB_TAG_URL=${web_tag_url}" \
  "WEB_ROLLBACK=${WEB_ROLLBACK}" \
  "RELAY_PROOF=health:200,forbidden:404,query:400"
