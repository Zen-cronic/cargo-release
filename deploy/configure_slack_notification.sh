#!/usr/bin/env bash
set -euo pipefail

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-ata-2026-cargo}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
CONTROLLER_SERVICE="${CONTROLLER_SERVICE:-cargo-release-controller}"
CONTROLLER_SERVICE_ACCOUNT="${CONTROLLER_SERVICE_ACCOUNT:-cargo-controller@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com}"
NOTIFICATION_SECRET="${NOTIFICATION_SECRET:-cargo-release-notification-webhook}"
CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL="${CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL:-operator-owned Slack #cargo-release-demo}"
CARGO_RELEASE_PUBLIC_BASE_URL="${CARGO_RELEASE_PUBLIC_BASE_URL:-https://cargo-release-web-1015646664425.us-central1.run.app}"

if [[ "${CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL}" == *","* ]] || \
  [[ "${CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL}" == *"="* ]]; then
  printf '%s\n' "Endpoint label cannot contain a comma or equals sign." >&2
  exit 2
fi

if [[ ! -t 0 ]]; then
  printf '%s\n' \
    "Run this script in an interactive terminal so the Slack webhook is never placed in shell history." >&2
  exit 2
fi

printf '%s' "Paste the operator-owned Slack incoming webhook (input hidden): " >&2
IFS= read -r -s SLACK_WEBHOOK_URL
printf '\n' >&2

case "${SLACK_WEBHOOK_URL}" in
  https://hooks.slack.com/services/* | https://hooks.slack-gov.com/services/*) ;;
  *)
    unset SLACK_WEBHOOK_URL
    printf '%s\n' "Refusing non-Slack or non-HTTPS webhook URL." >&2
    exit 2
    ;;
esac

if ! gcloud secrets describe "${NOTIFICATION_SECRET}" \
  --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null 2>&1; then
  gcloud secrets create "${NOTIFICATION_SECRET}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --replication-policy=automatic
fi

printf '%s' "${SLACK_WEBHOOK_URL}" | gcloud secrets versions add "${NOTIFICATION_SECRET}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --data-file=- >/dev/null
unset SLACK_WEBHOOK_URL

gcloud secrets add-iam-policy-binding "${NOTIFICATION_SECRET}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --member="serviceAccount:${CONTROLLER_SERVICE_ACCOUNT}" \
  --role=roles/secretmanager.secretAccessor \
  --condition=None \
  --quiet >/dev/null

gcloud run services update "${CONTROLLER_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --update-secrets="CARGO_RELEASE_NOTIFICATION_WEBHOOK_URL=${NOTIFICATION_SECRET}:latest" \
  --update-env-vars="CARGO_RELEASE_SYNTHETIC_NOTIFICATION_ENABLED=1,CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL=${CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL},CARGO_RELEASE_PUBLIC_BASE_URL=${CARGO_RELEASE_PUBLIC_BASE_URL}"

printf '%s\n' \
  "Marked synthetic Slack delivery enabled." \
  "NOTIFICATION_SECRET=${NOTIFICATION_SECRET}" \
  "CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL=${CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL}" \
  "CARGO_RELEASE_PUBLIC_BASE_URL=${CARGO_RELEASE_PUBLIC_BASE_URL}" \
  "Secret Console: https://console.cloud.google.com/security/secret-manager/secret/${NOTIFICATION_SECRET}/versions?project=${GOOGLE_CLOUD_PROJECT}" \
  "Cloud Run Console: https://console.cloud.google.com/run/detail/${GOOGLE_CLOUD_LOCATION}/${CONTROLLER_SERVICE}/revisions?project=${GOOGLE_CLOUD_PROJECT}"
