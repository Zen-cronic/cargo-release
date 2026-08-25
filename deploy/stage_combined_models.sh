#!/usr/bin/env bash
set -euo pipefail

GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-ata-2026-cargo}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
CONTROLLER_SERVICE="${CONTROLLER_SERVICE:-cargo-release-controller}"
WEB_SERVICE="${WEB_SERVICE:-cargo-release-web}"
CONTROLLER_SERVICE_ACCOUNT="${CONTROLLER_SERVICE_ACCOUNT:-cargo-controller@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com}"
RUNTIME_BUCKET="${CARGO_RELEASE_STAGING_BUCKET:-gs://ata-2026-cargo-cargo-release-runtime}"
APP_SOURCE_COMMIT="${CARGO_RELEASE_APP_SOURCE_COMMIT:-059c0446c38526aaf774eb23e99531aebf615d32}"
DEPLOY_TAG="${CARGO_RELEASE_DEPLOY_TAG:-combined-059c044}"
BACKEND_IMAGE="${CONTROLLER_IMAGE:-us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/backend@sha256:a9135191dea2be124f9ecd0b8c974c5daff2ec66eb6d63c541023e6c2aa836d1}"
WEB_IMAGE="${WEB_IMAGE:-us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/web@sha256:2534fde9e5a67b092a8b2f6727aeba424c13334a2aff29141d1e3cc9ae82e22f}"
IAM_APPROVAL="${CARGO_RELEASE_PERSISTENT_IAM_APPROVED:-}"
IAM_APPROVAL_PHRASE="I_APPROVE_AIPLATFORM_USER_AND_PREFIX_STORAGE"
STORAGE_CONDITION="deploy/controller-veo-storage-condition.yaml"
NOTIFICATION_SECRET="cargo-release-notification-webhook"
EXPECTED_CONTROLLER_SERVICE_ACCOUNT="cargo-controller@ata-2026-cargo.iam.gserviceaccount.com"
EXPECTED_RUNTIME_BUCKET="gs://ata-2026-cargo-cargo-release-runtime"
EXPECTED_BACKEND_IMAGE="us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/backend@sha256:a9135191dea2be124f9ecd0b8c974c5daff2ec66eb6d63c541023e6c2aa836d1"
EXPECTED_WEB_IMAGE="us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/web@sha256:2534fde9e5a67b092a8b2f6727aeba424c13334a2aff29141d1e3cc9ae82e22f"

if [[ "${GOOGLE_CLOUD_PROJECT}" != "ata-2026-cargo" ]] || \
  [[ "${GOOGLE_CLOUD_LOCATION}" != "us-central1" ]]; then
  printf '%s\n' "This retained proof packet is pinned to ata-2026-cargo/us-central1." >&2
  exit 2
fi

if [[ "${CONTROLLER_SERVICE_ACCOUNT}" != "${EXPECTED_CONTROLLER_SERVICE_ACCOUNT}" ]] || \
  [[ "${RUNTIME_BUCKET}" != "${EXPECTED_RUNTIME_BUCKET}" ]] || \
  [[ "${BACKEND_IMAGE}" != "${EXPECTED_BACKEND_IMAGE}" ]] || \
  [[ "${WEB_IMAGE}" != "${EXPECTED_WEB_IMAGE}" ]]; then
  printf '%s\n' \
    "Refusing an override of the retained controller identity, bucket, or immutable images." >&2
  exit 2
fi

if [[ ! -f "${STORAGE_CONDITION}" ]]; then
  printf 'Missing storage condition: %s\n' "${STORAGE_CONDITION}" >&2
  exit 2
fi

if ! git merge-base --is-ancestor "${APP_SOURCE_COMMIT}" HEAD; then
  printf 'Expected application source %s is not an ancestor of HEAD.\n' "${APP_SOURCE_COMMIT}" >&2
  exit 2
fi

unexpected_app_changes="$({
  git diff --name-only "${APP_SOURCE_COMMIT}..HEAD" -- \
    .dockerignore Dockerfile README.md pyproject.toml poetry.lock src web
  git diff --name-only -- \
    .dockerignore Dockerfile README.md pyproject.toml poetry.lock src web
  git diff --cached --name-only -- \
    .dockerignore Dockerfile README.md pyproject.toml poetry.lock src web
} | sort -u)"
uncommitted_app_changes="$(git status --porcelain -- \
  .dockerignore Dockerfile README.md pyproject.toml poetry.lock src web)"
if [[ -n "${unexpected_app_changes}" ]] || [[ -n "${uncommitted_app_changes}" ]]; then
  printf '%s\n%s\n' \
    "The retained images do not cover these application changes:" \
    "${unexpected_app_changes}${uncommitted_app_changes}" >&2
  exit 2
fi

active_account="$(gcloud config get-value account 2>/dev/null)"
if [[ -z "${active_account}" ]]; then
  printf '%s\n' "No active gcloud account is configured." >&2
  exit 2
fi

gcloud artifacts docker images describe "${BACKEND_IMAGE}" --format='value(image_summary.digest)' >/dev/null
gcloud artifacts docker images describe "${WEB_IMAGE}" --format='value(image_summary.digest)' >/dev/null
gcloud run services describe "${CONTROLLER_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" >/dev/null
gcloud run services describe "${WEB_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" >/dev/null

enabled_notification_versions="$(gcloud secrets versions list "${NOTIFICATION_SECRET}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --filter='state=ENABLED' \
  --format='value(name)' 2>/dev/null || true)"
if [[ -n "${enabled_notification_versions}" ]]; then
  printf '%s\n' \
    "The Slack secret now has an enabled version; refuse to run the delivery-disabled staging helper." >&2
  exit 2
fi

if [[ "${IAM_APPROVAL}" != "${IAM_APPROVAL_PHRASE}" ]]; then
  printf '%s\n' \
    "Preflight passed; no mutation performed." \
    "Active account: ${active_account}" \
    "Backend image: ${BACKEND_IMAGE}" \
    "Web image: ${WEB_IMAGE}" \
    "To authorize the two persistent IAM bindings and no-traffic staging, set:" \
    "CARGO_RELEASE_PERSISTENT_IAM_APPROVED=${IAM_APPROVAL_PHRASE}" >&2
  exit 3
fi

gcloud projects add-iam-policy-binding "${GOOGLE_CLOUD_PROJECT}" \
  --member="serviceAccount:${CONTROLLER_SERVICE_ACCOUNT}" \
  --role=roles/aiplatform.user \
  --condition=None \
  --quiet

gcloud storage buckets add-iam-policy-binding "${RUNTIME_BUCKET}" \
  --member="serviceAccount:${CONTROLLER_SERVICE_ACCOUNT}" \
  --role=roles/storage.objectUser \
  --condition-from-file="${STORAGE_CONDITION}"

gcloud run deploy "${CONTROLLER_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --image="${BACKEND_IMAGE}" \
  --no-traffic \
  --tag="${DEPLOY_TAG}" \
  --remove-env-vars="CARGO_RELEASE_GEMMA_CRITIC_MODE,CARGO_RELEASE_EMBEDDING_RETRIEVAL_MODE,CARGO_RELEASE_VEO_REPLAY_MODE,CARGO_RELEASE_SYNTHETIC_NOTIFICATION_ENABLED,CARGO_RELEASE_NOTIFICATION_ENDPOINT_LABEL,CARGO_RELEASE_PUBLIC_BASE_URL" \
  --update-env-vars="CARGO_RELEASE_GEMMA_CRITIC_ENABLED=1,CARGO_RELEASE_MODEL_PROJECT=${GOOGLE_CLOUD_PROJECT},CARGO_RELEASE_GEMMA_MODEL=google/gemma-4-26b-a4b-it-maas,CARGO_RELEASE_GEMMA_LOCATION=global,CARGO_RELEASE_EMBEDDING_RETRIEVAL_ENABLED=1,CARGO_RELEASE_EMBEDDING_MODEL=gemini-embedding-2,CARGO_RELEASE_EMBEDDING_LOCATION=global,CARGO_RELEASE_EMBEDDING_DIMENSIONS=128,CARGO_RELEASE_VEO_REPLAY_ENABLED=1,CARGO_RELEASE_VEO_MODEL=veo-3.1-fast-generate-001,CARGO_RELEASE_VEO_LOCATION=us-central1,CARGO_RELEASE_VEO_OUTPUT_URI=${RUNTIME_BUCKET}/post-release-media/,CARGO_RELEASE_VEO_POLL_SECONDS=10,CARGO_RELEASE_VEO_MAX_POLLS=60" \
  --remove-secrets="CARGO_RELEASE_NOTIFICATION_WEBHOOK_URL" \
  --quiet

gcloud run deploy "${WEB_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --image="${WEB_IMAGE}" \
  --no-traffic \
  --tag="${DEPLOY_TAG}" \
  --quiet

controller_tag_url="$(gcloud run services describe "${CONTROLLER_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --format="value(status.traffic[?tag='${DEPLOY_TAG}'].url)")"
web_tag_url="$(gcloud run services describe "${WEB_SERVICE}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${GOOGLE_CLOUD_LOCATION}" \
  --format="value(status.traffic[?tag='${DEPLOY_TAG}'].url)")"

if [[ -z "${controller_tag_url}" ]] || [[ -z "${web_tag_url}" ]]; then
  printf '%s\n' "Staged revisions did not return both tagged URLs." >&2
  exit 1
fi

printf '%s\n' \
  "Combined revisions staged with zero percent default traffic." \
  "CONTROLLER_TAG_URL=${controller_tag_url}" \
  "WEB_TAG_URL=${web_tag_url}" \
  "Run: poetry run python scripts/probe_managed_bonus_models.py --controller-url=${controller_tag_url} --event-id=evt-combined-models-UNIQUE"
