const MISSION_ID = /^mission-[a-z0-9](?:[a-z0-9-]{4,78}[a-z0-9])?$/;
const SAFE_SEGMENT = /^[A-Za-z0-9._:-]+$/;
const ACTOR = /^[A-Za-z0-9][A-Za-z0-9:@._-]{2,191}$/;
const MAX_BODY_BYTES = 2_048;

export type RelayAction =
  | "health.read"
  | "mission.create-demo"
  | "mission.read"
  | "evidence.media-read"
  | "mission.run"
  | "mission.owner-attest"
  | "model.replay-generate"
  | "model.replay-media";

export interface RelayDecision {
  action: RelayAction;
  upstreamPath: string;
  upstreamBody?: string;
}

export interface RelayRequestInput {
  method: string;
  path: string[];
  search: string;
  body: string;
  operatorActor?: string;
}

export class RelayPolicyError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "RelayPolicyError";
    this.status = status;
    this.code = code;
  }
}

function reject(status: number, code: string, message: string): never {
  throw new RelayPolicyError(status, code, message);
}

function assertSafePath(path: string[], search: string): string {
  if (
    path.length === 0 ||
    path.some(
      (segment) =>
        segment === "." ||
        segment === ".." ||
        !SAFE_SEGMENT.test(segment),
    )
  ) {
    reject(400, "INVALID_PATH", "Invalid controller path");
  }
  if (search) {
    reject(400, "QUERY_NOT_ALLOWED", "Controller query parameters are not allowed");
  }
  return path.join("/");
}

function assertEmptyBody(body: string): void {
  if (body.trim()) {
    reject(400, "BODY_NOT_ALLOWED", "This command does not accept a request body");
  }
}

function parseObject(body: string): Record<string, unknown> {
  if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
    reject(413, "BODY_TOO_LARGE", "Controller command body is too large");
  }
  let value: unknown;
  try {
    value = JSON.parse(body);
  } catch {
    reject(400, "INVALID_JSON", "Controller command body must be valid JSON");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    reject(400, "INVALID_BODY", "Controller command body must be a JSON object");
  }
  return value as Record<string, unknown>;
}

function assertExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (
    actual.length !== wanted.length ||
    actual.some((key, index) => key !== wanted[index])
  ) {
    reject(
      400,
      "UNEXPECTED_FIELDS",
      `Expected only: ${wanted.join(", ")}`,
    );
  }
}

function requireOperatorActor(operatorActor?: string): string {
  if (!operatorActor || !ACTOR.test(operatorActor)) {
    reject(
      503,
      "OPERATOR_IDENTITY_UNAVAILABLE",
      "The server-bound demo operator identity is unavailable",
    );
  }
  return operatorActor;
}

function missionIdFromRunPath(upstreamPath: string): string | null {
  const match = /^v1\/missions\/(mission-[a-z0-9-]+):run$/.exec(upstreamPath);
  if (!match || !MISSION_ID.test(match[1])) return null;
  return match[1];
}

function missionIdFromPath(
  upstreamPath: string,
  suffix: string,
): string | null {
  const prefix = "v1/missions/";
  if (!upstreamPath.startsWith(prefix) || !upstreamPath.endsWith(suffix)) {
    return null;
  }
  const missionId = upstreamPath.slice(prefix.length, -suffix.length);
  return MISSION_ID.test(missionId) ? missionId : null;
}

export function authorizeRelayRequest(input: RelayRequestInput): RelayDecision {
  const method = input.method.toUpperCase();
  const upstreamPath = assertSafePath(input.path, input.search);

  if (method === "GET") {
    assertEmptyBody(input.body);
    if (upstreamPath === "health") {
      return { action: "health.read", upstreamPath };
    }
    if (/^v1\/missions\/mission-[a-z0-9-]+$/.test(upstreamPath)) {
      const missionId = upstreamPath.slice("v1/missions/".length);
      if (MISSION_ID.test(missionId)) {
        return { action: "mission.read", upstreamPath };
      }
    }
    if (missionIdFromPath(upstreamPath, "/models/veo-replay/media")) {
      return { action: "model.replay-media", upstreamPath };
    }
    const evidenceMedia = /^v1\/missions\/(mission-[a-z0-9-]+)\/evidence\/([A-Za-z0-9._:-]+)\/media$/.exec(upstreamPath);
    if (
      evidenceMedia &&
      MISSION_ID.test(evidenceMedia[1]) &&
      /^ev-adjuster-rejection-scan-[A-Za-z0-9]+$/.test(evidenceMedia[2])
    ) {
      return { action: "evidence.media-read", upstreamPath };
    }
    reject(404, "COMMAND_NOT_ALLOWED", "Controller command is not available");
  }

  if (method !== "POST") {
    reject(405, "METHOD_NOT_ALLOWED", "Controller method is not available");
  }

  if (upstreamPath === "v1/missions/demo") {
    assertEmptyBody(input.body);
    return { action: "mission.create-demo", upstreamPath };
  }

  if (missionIdFromRunPath(upstreamPath)) {
    assertEmptyBody(input.body);
    return { action: "mission.run", upstreamPath };
  }

  if (
    missionIdFromPath(
      upstreamPath,
      "/approvals/owner-bond:approve-and-resume",
    )
  ) {
    const value = parseObject(input.body);
    assertExactKeys(value, ["expected_version"]);
    const expectedVersion = value.expected_version;
    if (
      typeof expectedVersion !== "number" ||
      !Number.isSafeInteger(expectedVersion) ||
      expectedVersion < 0
    ) {
      reject(
        400,
        "INVALID_VERSION",
        "expected_version must be a non-negative integer",
      );
    }
    return {
      action: "mission.owner-attest",
      upstreamPath,
      upstreamBody: JSON.stringify({
        expected_version: expectedVersion,
        actor: requireOperatorActor(input.operatorActor),
      }),
    };
  }

  if (missionIdFromPath(upstreamPath, "/models/veo-replay:generate")) {
    const value = parseObject(input.body);
    assertExactKeys(value, ["confirm_training_only"]);
    if (value.confirm_training_only !== true) {
      reject(
        400,
        "TRAINING_CONFIRMATION_REQUIRED",
        "confirm_training_only=true is required",
      );
    }
    return {
      action: "model.replay-generate",
      upstreamPath,
      upstreamBody: JSON.stringify({
        confirm_training_only: true,
        actor: requireOperatorActor(input.operatorActor),
      }),
    };
  }

  reject(404, "COMMAND_NOT_ALLOWED", "Controller command is not available");
}
