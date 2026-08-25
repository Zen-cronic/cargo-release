#!/usr/bin/env bash
set -euo pipefail

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-ata-2026-cargo}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
CLOUD_SQL_INSTANCE="${CLOUD_SQL_INSTANCE:-cargo-release-postgres}"
CLOUD_SQL_TIER="${CLOUD_SQL_TIER:-db-f1-micro}"
CLOUD_SQL_DATABASE="${CLOUD_SQL_DATABASE:-cargo_release}"
CLOUD_SQL_USER="${CLOUD_SQL_USER:-cargo_release_app}"
CLOUD_SQL_PASSWORD_SECRET="${CLOUD_SQL_PASSWORD_SECRET:-cargo-release-db-password}"
CONTROLLER_SERVICE_ACCOUNT="${CONTROLLER_SERVICE_ACCOUNT:-cargo-controller@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com}"

CLOUD_SQL_CONNECTION_NAME="${GOOGLE_CLOUD_PROJECT}:${GOOGLE_CLOUD_LOCATION}:${CLOUD_SQL_INSTANCE}"
CARGO_RELEASE_DB_HOST="/cloudsql/${CLOUD_SQL_CONNECTION_NAME}"
CARGO_RELEASE_DB_NAME="${CLOUD_SQL_DATABASE}"
CARGO_RELEASE_DB_USER="${CLOUD_SQL_USER}"
CARGO_RELEASE_DB_PASSWORD_SECRET="${CLOUD_SQL_PASSWORD_SECRET}"

if ! gcloud sql instances describe "${CLOUD_SQL_INSTANCE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null 2>&1; then
  gcloud sql instances create "${CLOUD_SQL_INSTANCE}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --region="${GOOGLE_CLOUD_LOCATION}" \
    --database-version=POSTGRES_16 \
    --edition=ENTERPRISE \
    --tier="${CLOUD_SQL_TIER}" \
    --availability-type=ZONAL \
    --storage-type=SSD \
    --storage-size=10
fi

if ! gcloud sql databases describe "${CLOUD_SQL_DATABASE}" \
  --instance="${CLOUD_SQL_INSTANCE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null 2>&1; then
  gcloud sql databases create "${CLOUD_SQL_DATABASE}" \
    --instance="${CLOUD_SQL_INSTANCE}" \
    --project="${GOOGLE_CLOUD_PROJECT}"
fi

if gcloud secrets describe "${CLOUD_SQL_PASSWORD_SECRET}" \
  --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null 2>&1; then
  DATABASE_PASSWORD="$(gcloud secrets versions access latest \
    --secret="${CLOUD_SQL_PASSWORD_SECRET}" \
    --project="${GOOGLE_CLOUD_PROJECT}")"
else
  DATABASE_PASSWORD="$(openssl rand -hex 32)"
  printf '%s' "${DATABASE_PASSWORD}" | gcloud secrets create \
    "${CLOUD_SQL_PASSWORD_SECRET}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --data-file=-
fi

if gcloud sql users list \
  --instance="${CLOUD_SQL_INSTANCE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --filter="name=${CLOUD_SQL_USER}" \
  --format='value(name)' | grep -qx "${CLOUD_SQL_USER}"; then
  gcloud sql users set-password "${CLOUD_SQL_USER}" \
    --instance="${CLOUD_SQL_INSTANCE}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --password="${DATABASE_PASSWORD}"
else
  gcloud sql users create "${CLOUD_SQL_USER}" \
    --instance="${CLOUD_SQL_INSTANCE}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --password="${DATABASE_PASSWORD}"
fi
unset DATABASE_PASSWORD

gcloud projects add-iam-policy-binding "${GOOGLE_CLOUD_PROJECT}" \
  --member="serviceAccount:${CONTROLLER_SERVICE_ACCOUNT}" \
  --role='roles/cloudsql.client' \
  --condition=None \
  --quiet >/dev/null

gcloud secrets add-iam-policy-binding "${CLOUD_SQL_PASSWORD_SECRET}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --member="serviceAccount:${CONTROLLER_SERVICE_ACCOUNT}" \
  --role='roles/secretmanager.secretAccessor' \
  --condition=None \
  --quiet >/dev/null

printf '%s\n' \
  "Cloud SQL authority provisioned." \
  "CLOUD_SQL_INSTANCE=${CLOUD_SQL_INSTANCE}" \
  "CLOUD_SQL_TIER=${CLOUD_SQL_TIER}" \
  "CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME}" \
  "CARGO_RELEASE_DB_HOST=${CARGO_RELEASE_DB_HOST}" \
  "CARGO_RELEASE_DB_NAME=${CARGO_RELEASE_DB_NAME}" \
  "CARGO_RELEASE_DB_USER=${CARGO_RELEASE_DB_USER}" \
  "CARGO_RELEASE_DB_PASSWORD_SECRET=${CARGO_RELEASE_DB_PASSWORD_SECRET}"
