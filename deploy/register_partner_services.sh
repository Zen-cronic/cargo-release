#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${GOOGLE_CLOUD_LOCATION:=us-central1}"
: "${INSURER_URL:?Set INSURER_URL}"
: "${ADJUSTER_URL:?Set ADJUSTER_URL}"
: "${CARRIER_URL:?Set CARRIER_URL}"

gcloud agent-registry services create cargo-release-insurer \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --location="${GOOGLE_CLOUD_LOCATION}" \
  --display-name="Cargo Release Insurer Fixture" \
  --agent-spec-type=no-spec \
  --interfaces="url=${INSURER_URL},protocolBinding=http-json"

gcloud agent-registry services create cargo-release-adjuster \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --location="${GOOGLE_CLOUD_LOCATION}" \
  --display-name="Cargo Release Adjuster Fixture" \
  --agent-spec-type=no-spec \
  --interfaces="url=${ADJUSTER_URL},protocolBinding=http-json"

gcloud agent-registry services create cargo-release-carrier \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --location="${GOOGLE_CLOUD_LOCATION}" \
  --display-name="Cargo Release Carrier Fixture" \
  --agent-spec-type=no-spec \
  --interfaces="url=${CARRIER_URL},protocolBinding=http-json"

gcloud agent-registry agents list \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --location="${GOOGLE_CLOUD_LOCATION}" \
  --filter="displayName:Cargo Release"
