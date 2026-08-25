import assert from "node:assert/strict";
import test from "node:test";

import type { MissionSnapshot } from "../lib/cargo-api.ts";
import { missionFrictionMetric } from "../lib/mission-metrics.ts";

function releasedSnapshot(): Pick<
  MissionSnapshot,
  "approvals" | "events" | "notifications" | "receipts"
> {
  const receiptKinds = [
    "INSURER_GUARANTEE",
    "ADJUSTER_REJECTION",
    "ADJUSTER_ACCEPTANCE",
    "CARRIER_RELEASE_ORDER",
    "CARRIER_RELEASE_READBACK",
  ] as const;
  return {
    approvals: [
      {
        id: "approval-1",
        kind: "OWNER_BOND",
        actor: "operator@example.test",
        artifact_ref: "artifact://bond",
        approved_at: "2026-08-25T00:00:00Z",
      },
    ],
    events: [
      ...["SECURITY_SUBMITTED", "SECURITY_PACK_CORRECTED"].map(
        (event_type, index) => ({
          seq: index + 1,
          event_type,
          actor: "agent:security-pack@1.0.0",
          payload: {},
          event_hash: `hash-${index}`,
          created_at: "2026-08-25T00:00:00Z",
        }),
      ),
      {
        seq: 3,
        event_type: "SECURITY_PACK_CORRECTED",
        actor: "duplicate-delivery",
        payload: {},
        event_hash: "duplicate-hash",
        created_at: "2026-08-25T00:00:01Z",
      },
    ],
    receipts: [
      ...receiptKinds.map((kind, index) => ({
        id: `receipt-${index}`,
        kind,
        issuer: kind.startsWith("CARRIER") ? "carrier" : "adjuster",
        external_id: `external-${index}`,
        subject_ref: "mission-test",
        status: "VERIFIED",
        issued_at: "2026-08-25T00:00:00Z",
        payload: {},
        verified: true,
        digest: `digest-${index}`,
      })),
      {
        id: "duplicate-receipt",
        kind: "CARRIER_RELEASE_READBACK",
        issuer: "carrier",
        external_id: "duplicate",
        subject_ref: "mission-test",
        status: "VERIFIED",
        issued_at: "2026-08-25T00:00:01Z",
        payload: {},
        verified: true,
        digest: "duplicate-digest",
      },
    ],
    notifications: [
      {
        id: "notification-1",
        kind: "RELEASE_OPERATOR_NOTICE",
        endpoint_label: "operator-owned Slack #general",
        provider_ref: "slack-test",
        payload_digest: "notification-digest",
        status: "DELIVERED",
        delivered_at: "2026-08-25T00:00:00Z",
      },
      {
        id: "notification-duplicate",
        kind: "RELEASE_OPERATOR_NOTICE",
        endpoint_label: "operator-owned Slack #general",
        provider_ref: "slack-test",
        payload_digest: "notification-digest",
        status: "DELIVERED",
        delivered_at: "2026-08-25T00:00:01Z",
      },
    ],
  };
}

test("one attestation yields eight unique downstream actions", () => {
  assert.deepEqual(missionFrictionMetric(releasedSnapshot()), {
    humanAttestations: 1,
    partnerReceipts: 5,
    securitySubmissions: 1,
    securityCorrections: 1,
    operatorNotifications: 1,
    autonomousActions: 8,
    expectedAutonomousActions: 8,
  });
});

test("duplicate events, receipts, and notices never inflate the metric", () => {
  const snapshot = releasedSnapshot();
  snapshot.receipts.push(...snapshot.receipts);
  snapshot.events.push(...snapshot.events);
  snapshot.notifications?.push(...snapshot.notifications);

  assert.equal(missionFrictionMetric(snapshot).autonomousActions, 8);
});
