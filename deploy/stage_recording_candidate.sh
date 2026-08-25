#!/usr/bin/env bash
set -euo pipefail

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-ata-2026-cargo}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-cargo-release}"
CONTROLLER_SERVICE="${CONTROLLER_SERVICE:-cargo-release-controller}"
WEB_SERVICE="${WEB_SERVICE:-cargo-release-web}"
APP_SOURCE_COMMIT="${CARGO_RELEASE_APP_SOURCE_COMMIT:-11a2f1e4ede7a12c489b9c5a4e1f96d03414bb47}"
SOURCE_LABEL="${CARGO_RELEASE_SOURCE_LABEL:-11a2f1e}"
DEPLOY_TAG="${CARGO_RELEASE_DEPLOY_TAG:-recording-${SOURCE_LABEL}}"
CONTROLLER_AUDIENCE="${CARGO_RELEASE_CONTROLLER_AUDIENCE:-https://cargo-release-controller-1015646664425.us-central1.run.app}"
WEB_OPERATOR_ACTOR="${CARGO_RELEASE_WEB_OPERATOR_ACTOR:-demo-operator-via:cargo-web@ata-2026-cargo.iam.gserviceaccount.com}"
APPROVAL="${CARGO_RELEASE_RECORDING_STAGE_APPROVED:-}"
APPROVAL_PHRASE="I_APPROVE_RECORDING_CANDIDATE_BUILD_AND_ZERO_TRAFFIC_STAGE"
IMAGE_ROOT="${GOOGLE_CLOUD_LOCATION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${ARTIFACT_REPOSITORY}"
BACKEND_TAG="${IMAGE_ROOT}/backend:recording-${SOURCE_LABEL}"
WEB_TAG="${IMAGE_ROOT}/web:recording-${SOURCE_LABEL}"

if [[ "${GOOGLE_CLOUD_PROJECT}" != "ata-2026-cargo" ]] || \
  [[ "${GOOGLE_CLOUD_LOCATION}" != "us-central1" ]]; then
  printf '%s\n' "This helper is pinned to ata-2026-cargo/us-central1." >&2
  exit 2
fi

if [[ "${CONTROLLER_AUDIENCE}" != "https://cargo-release-controller-1015646664425.us-central1.run.app" ]] || \
  [[ "${WEB_OPERATOR_ACTOR}" != "demo-operator-via:cargo-web@ata-2026-cargo.iam.gserviceaccount.com" ]]; then
  printf '%s\n' "Refusing an override of the controller audience or server-bound operator actor." >&2
  exit 2
fi

for command in gcloud git jq curl; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "${command}" >&2
    exit 2
  fi
done

if ! git merge-base --is-ancestor "${APP_SOURCE_COMMIT}" HEAD; then
  printf 'Accepted application source %s is not an ancestor of HEAD.\n' "${APP_SOURCE_COMMIT}" >&2
  exit 2
fi

application_changes="$({
  git diff --name-only "${APP_SOURCE_COMMIT}..HEAD" -- \
    .dockerignore Dockerfile README.md pyproject.toml poetry.lock src web
  git diff --name-only -- \
    .dockerignore Dockerfile README.md pyproject.toml poetry.lock src web
  git diff --cached --name-only -- \
    .dockerignore Dockerfile README.md pyproject.toml poetry.lock src web
} | sort -u)"
if [[ -n "${application_changes}" ]]; then
  printf '%s\n%s\n' \
    "Refusing application inputs beyond the accepted source commit:" \
    "${application_changes}" >&2
  exit 2
fi

active_account="$(gcloud config get-value account 2>/dev/null)"
active_project="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "${active_account}" ]] || [[ "${active_project}" != "${GOOGLE_CLOUD_PROJECT}" ]]; then
  printf 'Expected an active account in %s; found account=%s project=%s.\n' \
    "${GOOGLE_CLOUD_PROJECT}" "${active_account:-none}" "${active_project:-none}" >&2
  exit 2
fi

controller_before="$(gcloud run services describe "${CONTROLLER_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --format=json)"
web_before="$(gcloud run services describe "${WEB_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --format=json)"
controller_serving_before="$(jq -er '.status.traffic[] | select(.percent == 100) | .revisionName' <<<"${controller_before}")"
web_serving_before="$(jq -er '.status.traffic[] | select(.percent == 100) | .revisionName' <<<"${web_before}")"

if [[ "${APPROVAL}" != "${APPROVAL_PHRASE}" ]]; then
  printf '%s\n' \
    "Preflight passed; no mutation performed." \
    "Active account: ${active_account}" \
    "Application source: ${APP_SOURCE_COMMIT}" \
    "Controller rollback: ${controller_serving_before}" \
    "Web rollback: ${web_serving_before}" \
    "Backend tag: ${BACKEND_TAG}" \
    "Web tag: ${WEB_TAG}" \
    "To authorize immutable builds and zero-traffic staging, set:" \
    "CARGO_RELEASE_RECORDING_STAGE_APPROVED=${APPROVAL_PHRASE}" >&2
  exit 3
fi

backend_build="$(gcloud builds submit . \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --tag="${BACKEND_TAG}" \
  --format='value(id)' \
  --quiet)"
web_build="$(gcloud builds submit web \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --tag="${WEB_TAG}" \
  --format='value(id)' \
  --quiet)"

backend_digest="$(gcloud artifacts docker images describe "${BACKEND_TAG}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --format='value(image_summary.digest)')"
web_digest="$(gcloud artifacts docker images describe "${WEB_TAG}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --format='value(image_summary.digest)')"
backend_image="${IMAGE_ROOT}/backend@${backend_digest}"
web_image="${IMAGE_ROOT}/web@${web_digest}"

gcloud run deploy "${CONTROLLER_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --image="${backend_image}" \
  --no-traffic \
  --tag="${DEPLOY_TAG}" \
  --quiet

controller_after="$(gcloud run services describe "${CONTROLLER_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --format=json)"
controller_revision="$(jq -er '.status.latestCreatedRevisionName' <<<"${controller_after}")"
controller_tag_url="$(jq -er --arg tag "${DEPLOY_TAG}" '.status.traffic[] | select(.tag == $tag) | .url' <<<"${controller_after}")"
controller_serving_after="$(jq -er '.status.traffic[] | select(.percent == 100) | .revisionName' <<<"${controller_after}")"
if [[ "${controller_serving_after}" != "${controller_serving_before}" ]]; then
  printf 'Controller traffic changed unexpectedly: before=%s after=%s.\n' \
    "${controller_serving_before}" "${controller_serving_after}" >&2
  exit 1
fi

gcloud run deploy "${WEB_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --image="${web_image}" \
  --no-traffic \
  --tag="${DEPLOY_TAG}" \
  --update-env-vars="CARGO_RELEASE_CONTROLLER_URL=${controller_tag_url},CARGO_RELEASE_CONTROLLER_AUDIENCE=${CONTROLLER_AUDIENCE},CARGO_RELEASE_WEB_OPERATOR_ACTOR=${WEB_OPERATOR_ACTOR}" \
  --quiet

web_after="$(gcloud run services describe "${WEB_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --format=json)"
web_revision="$(jq -er '.status.latestCreatedRevisionName' <<<"${web_after}")"
web_tag_url="$(jq -er --arg tag "${DEPLOY_TAG}" '.status.traffic[] | select(.tag == $tag) | .url' <<<"${web_after}")"
web_serving_after="$(jq -er '.status.traffic[] | select(.percent == 100) | .revisionName' <<<"${web_after}")"
if [[ "${web_serving_after}" != "${web_serving_before}" ]]; then
  printf 'Web traffic changed unexpectedly: before=%s after=%s.\n' \
    "${web_serving_before}" "${web_serving_after}" >&2
  exit 1
fi

health_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "${web_tag_url}/api/cargo/health")"
forbidden_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "${web_tag_url}/api/cargo/v1/notifications")"
query_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "${web_tag_url}/api/cargo/health?debug=1")"
if [[ "${health_status}" != "200" ]] || [[ "${forbidden_status}" != "404" ]] || \
  [[ "${query_status}" != "400" ]]; then
  printf 'Staged relay proof failed: health=%s forbidden=%s query=%s.\n' \
    "${health_status}" "${forbidden_status}" "${query_status}" >&2
  exit 1
fi

printf '%s\n' \
  "Recording candidate staged with zero percent default traffic." \
  "APPLICATION_SOURCE=${APP_SOURCE_COMMIT}" \
  "BACKEND_BUILD=${backend_build}" \
  "BACKEND_IMAGE=${backend_image}" \
  "CONTROLLER_REVISION=${controller_revision}" \
  "CONTROLLER_TAG_URL=${controller_tag_url}" \
  "CONTROLLER_ROLLBACK=${controller_serving_before}" \
  "WEB_BUILD=${web_build}" \
  "WEB_IMAGE=${web_image}" \
  "WEB_REVISION=${web_revision}" \
  "WEB_TAG_URL=${web_tag_url}" \
  "WEB_ROLLBACK=${web_serving_before}" \
  "RELAY_PROOF=health:200,forbidden:404,query:400"
