#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${GOOGLE_CLOUD_LOCATION:=us-central1}"
: "${CARGO_RELEASE_GATEWAY_AUTHZ_MODE:=enforce}"

case "${CARGO_RELEASE_GATEWAY_AUTHZ_MODE}" in
  dry-run)
    extension_source="deploy/agent-gateway-iap-extension-dry-run.yaml"
    ;;
  enforce)
    extension_source="deploy/agent-gateway-iap-extension.yaml"
    ;;
  *)
    echo "CARGO_RELEASE_GATEWAY_AUTHZ_MODE must be dry-run or enforce." >&2
    exit 2
    ;;
esac

gcloud beta service-extensions authz-extensions import \
  cargo-release-iap-request-authz \
  --source="${extension_source}" \
  --location="${GOOGLE_CLOUD_LOCATION}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --quiet

gcloud beta network-security authz-policies import \
  cargo-release-iap-request-authz \
  --source=deploy/agent-gateway-iap-policy.yaml \
  --location="${GOOGLE_CLOUD_LOCATION}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --quiet
