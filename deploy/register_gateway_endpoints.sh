#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${GOOGLE_CLOUD_PROJECT_NUMBER:=1015646664425}"
: "${GOOGLE_CLOUD_LOCATION:=us-central1}"
: "${CARGO_RELEASE_CONTROLLER_URL:?Set CARGO_RELEASE_CONTROLLER_URL}"
: "${CARGO_RELEASE_CALLER_SERVICE_ACCOUNT:=cargo-coordinator@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com}"
: "${CARGO_RELEASE_AGENT_SOURCE_SERVICE_ACCOUNT:=ka84a0ee6a752dfefp-tp@appspot.gserviceaccount.com}"

AGENT_PRINCIPAL="${CARGO_RELEASE_AGENT_PRINCIPAL:-principal://agents.global.proj-1015646664425.system.id.goog/resources/aiplatform/projects/1015646664425/locations/us-central1/reasoningEngines/6735983714976661504}"

register_and_allow() {
  local service_id="$1"
  local display_name="$2"
  local endpoint_url="$3"
  local protocol_binding="${4:-http-json}"
  local registry_resource
  local endpoint_id

  if ! gcloud agent-registry services describe "${service_id}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --location="${GOOGLE_CLOUD_LOCATION}" >/dev/null 2>&1; then
    gcloud agent-registry services create "${service_id}" \
      --project="${GOOGLE_CLOUD_PROJECT}" \
      --location="${GOOGLE_CLOUD_LOCATION}" \
      --display-name="${display_name}" \
      --endpoint-spec-type=no-spec \
      --interfaces="url=${endpoint_url},protocolBinding=${protocol_binding}"
  else
    gcloud agent-registry services update "${service_id}" \
      --project="${GOOGLE_CLOUD_PROJECT}" \
      --location="${GOOGLE_CLOUD_LOCATION}" \
      --display-name="${display_name}" \
      --interfaces="url=${endpoint_url},protocolBinding=${protocol_binding}"
  fi

  registry_resource="$(gcloud agent-registry services describe "${service_id}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --location="${GOOGLE_CLOUD_LOCATION}" \
    --format='value(registryResource)')"
  endpoint_id="${registry_resource##*/}"
  gcloud iap web add-iam-policy-binding \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --resource-type=agent-registry \
    --endpoint="${endpoint_id}" \
    --region="${GOOGLE_CLOUD_LOCATION}" \
    --member="${AGENT_PRINCIPAL}" \
    --role=roles/iap.egressor \
    --quiet
}

register_and_allow \
  cargo-release-controller-endpoint \
  "Cargo Release private controller" \
  "${CARGO_RELEASE_CONTROLLER_URL}"
register_and_allow \
  cargo-release-iam-credentials-endpoint \
  "Cargo Release coordinator identity-token exchange" \
  "https://iamcredentials.mtls.googleapis.com/v1/projects/-/serviceAccounts/${CARGO_RELEASE_CALLER_SERVICE_ACCOUNT}:generateIdToken"
register_and_allow \
  cargo-release-agent-trust-boundary-endpoint \
  "Cargo Release Agent Identity allowed-locations lookup" \
  "https://iamcredentials.mtls.googleapis.com/v1/projects/-/serviceAccounts/${CARGO_RELEASE_AGENT_SOURCE_SERVICE_ACCOUNT}/allowedLocations"
register_and_allow \
  cargo-release-gemini-35-endpoint \
  "Cargo Release Gemini 3.5 inference" \
  "https://aiplatform.mtls.googleapis.com/v1beta1/projects/${GOOGLE_CLOUD_PROJECT}/locations/global/publishers/google/models/gemini-3.5-flash:generateContent" \
  jsonrpc
register_and_allow \
  cargo-release-runtime-sessions-endpoint \
  "Cargo Release managed runtime self endpoint" \
  "https://${GOOGLE_CLOUD_LOCATION}-aiplatform.mtls.googleapis.com/v1beta1/projects/${GOOGLE_CLOUD_PROJECT_NUMBER}/locations/${GOOGLE_CLOUD_LOCATION}/reasoningEngines/6735983714976661504" \
  jsonrpc
register_and_allow \
  cargo-release-telemetry-endpoint \
  "Cargo Release managed telemetry" \
  "https://telemetry.mtls.googleapis.com/"
register_and_allow \
  cargo-release-logging-endpoint \
  "Cargo Release managed logging" \
  "https://logging.mtls.googleapis.com/"
