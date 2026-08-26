import assert from "node:assert/strict";
import test from "node:test";

import {
  authorizeRelayRequest,
  RelayPolicyError,
} from "../lib/relay-policy.ts";

const missionId = "mission-abe2d197faad";
const operatorActor =
  "demo-operator-via:cargo-web@ata-2026-cargo.iam.gserviceaccount.com";

function authorize(
  method: string,
  path: string,
  body = "",
  search = "",
) {
  return authorizeRelayRequest({
    method,
    path: path.split("/"),
    search,
    body,
    operatorActor,
  });
}

function rejects(
  method: string,
  path: string,
  expectedStatus: number,
  body = "",
  search = "",
) {
  assert.throws(
    () => authorize(method, path, body, search),
    (error: unknown) =>
      error instanceof RelayPolicyError && error.status === expectedStatus,
  );
}

test("allows only the public read surface", () => {
  assert.equal(authorize("GET", "health").action, "health.read");
  assert.equal(
    authorize("GET", `v1/missions/${missionId}`).action,
    "mission.read",
  );
  assert.equal(
    authorize("GET", `v1/missions/${missionId}/models/veo-replay/media`).action,
    "model.replay-media",
  );
  assert.equal(
    authorize(
      "GET",
      `v1/missions/${missionId}/evidence/ev-adjuster-rejection-scan-d197fa/media`,
    ).action,
    "evidence.media-read",
  );
  rejects(
    "GET",
    `v1/missions/${missionId}/evidence/ev-broker-email-d197fa/media`,
    404,
  );
});

test("allows the two demo workflow commands but no arbitrary body", () => {
  assert.equal(
    authorize("POST", "v1/missions/demo").action,
    "mission.create-demo",
  );
  assert.equal(
    authorize("POST", `v1/missions/${missionId}:run`).action,
    "mission.run",
  );
  rejects("POST", `v1/missions/${missionId}:run`, 400, "{}");
});

test("binds owner attestation to the server operator identity", () => {
  const decision = authorize(
    "POST",
    `v1/missions/${missionId}/approvals/owner-bond:approve-and-resume`,
    JSON.stringify({ expected_version: 1 }),
  );
  assert.equal(decision.action, "mission.owner-attest");
  assert.deepEqual(JSON.parse(decision.upstreamBody ?? ""), {
    expected_version: 1,
    actor: operatorActor,
  });
  rejects(
    "POST",
    `v1/missions/${missionId}/approvals/owner-bond:approve-and-resume`,
    400,
    JSON.stringify({ expected_version: 1, actor: "cargo-owner.attacker" }),
  );
});

test("binds optional replay generation to the server operator identity", () => {
  const decision = authorize(
    "POST",
    `v1/missions/${missionId}/models/veo-replay:generate`,
    JSON.stringify({ confirm_training_only: true }),
  );
  assert.equal(decision.action, "model.replay-generate");
  assert.deepEqual(JSON.parse(decision.upstreamBody ?? ""), {
    confirm_training_only: true,
    actor: operatorActor,
  });
  rejects(
    "POST",
    `v1/missions/${missionId}/models/veo-replay:generate`,
    400,
    JSON.stringify({ confirm_training_only: false }),
  );
});

test("fails closed when the server-bound operator identity is absent", () => {
  assert.throws(
    () =>
      authorizeRelayRequest({
        method: "POST",
        path: [
          "v1",
          "missions",
          missionId,
          "approvals",
          "owner-bond:approve-and-resume",
        ],
        search: "",
        body: JSON.stringify({ expected_version: 1 }),
      }),
    (error: unknown) =>
      error instanceof RelayPolicyError &&
      error.status === 503 &&
      error.code === "OPERATOR_IDENTITY_UNAVAILABLE",
  );
});

test("denies privileged controller routes", () => {
  for (const path of [
    "v1/events/casualty",
    "v1/partner-receipts",
    `v1/missions/${missionId}/approvals/owner-bond`,
    `v1/missions/${missionId}/notifications/release`,
    `v1/missions/${missionId}/models/gemma-critic:retry`,
    `v1/missions/${missionId}/models/case-retrieval:retry`,
    `v1/missions/${missionId}:submit-security`,
    `v1/missions/${missionId}:correct-security`,
  ]) {
    rejects("POST", path, 404, "{}");
  }
});

test("denies traversal, query forwarding, invalid identifiers, and other methods", () => {
  rejects("GET", "v1/missions/../secret", 400);
  rejects("GET", `v1/missions/${missionId}`, 400, "", "?admin=true");
  rejects("GET", "v1/missions/not-a-mission", 404);
  rejects("DELETE", `v1/missions/${missionId}`, 405);
});
