#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
: "${GOOGLE_CLOUD_LOCATION:=us-central1}"
: "${CARGO_RELEASE_CONTROLLER_SERVICE:=cargo-release-controller}"
: "${CARGO_RELEASE_CALLER_SERVICE_ACCOUNT:=cargo-coordinator@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com}"
: "${CARGO_RELEASE_AGENT_PRINCIPAL:?Set CARGO_RELEASE_AGENT_PRINCIPAL}"

if ! gcloud iam service-accounts describe \
  "${CARGO_RELEASE_CALLER_SERVICE_ACCOUNT}" \
  --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null 2>&1; then
  gcloud iam service-accounts create \
    "${CARGO_RELEASE_CALLER_SERVICE_ACCOUNT%%@*}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --display-name="Cargo Release coordinator caller"
fi

gcloud iam service-accounts add-iam-policy-binding \
  "${CARGO_RELEASE_CALLER_SERVICE_ACCOUNT}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --member="${CARGO_RELEASE_AGENT_PRINCIPAL}" \
  --role=roles/iam.serviceAccountTokenCreator \
  --quiet

for attempt in {1..6}; do
  if gcloud run services add-iam-policy-binding \
    "${CARGO_RELEASE_CONTROLLER_SERVICE}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --region="${GOOGLE_CLOUD_LOCATION}" \
    --member="serviceAccount:${CARGO_RELEASE_CALLER_SERVICE_ACCOUNT}" \
    --role=roles/run.invoker \
    --quiet; then
    exit 0
  fi
  if [[ "${attempt}" -lt 6 ]]; then
    sleep 5
  fi
done

echo "Coordinator service account did not propagate to Cloud Run IAM within 30 seconds." >&2
exit 1
