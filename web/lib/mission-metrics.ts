import type { MissionSnapshot, ReceiptKind } from "@/lib/cargo-api";

const downstreamReceiptKinds: readonly ReceiptKind[] = [
  "INSURER_GUARANTEE",
  "ADJUSTER_REJECTION",
  "ADJUSTER_ACCEPTANCE",
  "CARRIER_RELEASE_ORDER",
  "CARRIER_RELEASE_READBACK",
];

export interface FrictionMetric {
  humanAttestations: number;
  partnerReceipts: number;
  securitySubmissions: number;
  securityCorrections: number;
  operatorNotifications: number;
  autonomousActions: number;
  expectedAutonomousActions: 8;
}

export function missionFrictionMetric(
  snapshot: Pick<
    MissionSnapshot,
    "approvals" | "events" | "notifications" | "receipts"
  >,
): FrictionMetric {
  const receiptKinds = new Set(
    snapshot.receipts
      .filter((receipt) => receipt.verified)
      .map((receipt) => receipt.kind),
  );
  const eventTypes = new Set(snapshot.events.map((event) => event.event_type));
  const partnerReceipts = downstreamReceiptKinds.filter((kind) =>
    receiptKinds.has(kind),
  ).length;
  const securitySubmissions = eventTypes.has("SECURITY_SUBMITTED") ? 1 : 0;
  const securityCorrections = eventTypes.has("SECURITY_PACK_CORRECTED") ? 1 : 0;
  const operatorNotifications = snapshot.notifications?.some(
    (notification) => notification.status === "DELIVERED",
  )
    ? 1
    : 0;

  return {
    humanAttestations: snapshot.approvals.some(
      (approval) => approval.kind === "OWNER_BOND",
    )
      ? 1
      : 0,
    partnerReceipts,
    securitySubmissions,
    securityCorrections,
    operatorNotifications,
    autonomousActions:
      partnerReceipts +
      securitySubmissions +
      securityCorrections +
      operatorNotifications,
    expectedAutonomousActions: 8,
  };
}
