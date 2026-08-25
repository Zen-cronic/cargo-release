const target = (process.env.APP_URL ?? "http://127.0.0.1:3030").replace(/\/$/, "");
const expectedActor =
  process.env.CARGO_RELEASE_WEB_OPERATOR_ACTOR ??
  "demo-operator-via:cargo-web.local";

async function request(path, options = {}) {
  const response = await fetch(`${target}/api/cargo/${path}`, {
    redirect: "manual",
    ...options,
  });
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = text;
  }
  return { response, payload };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const health = await request("health");
assert(health.response.status === 200, "health read did not traverse the relay");

const created = await request("v1/missions/demo", { method: "POST" });
assert(created.response.status === 200, "demo creation was not allowed");
const missionId = created.payload?.mission?.id;
assert(typeof missionId === "string", "demo creation returned no mission id");

const run = await request(`v1/missions/${missionId}:run`, { method: "POST" });
assert(run.response.status === 200, "bounded mission run was not allowed");
assert(
  run.payload?.mission?.release_state === "READY_FOR_SIGNATURE",
  "bounded run did not stop at the human gate",
);

const privileged = await request(
  `v1/missions/${missionId}/notifications/release`,
  { method: "POST", body: "{}" },
);
assert(privileged.response.status === 404, "privileged notification route was exposed");
assert(
  privileged.payload?.code === "COMMAND_NOT_ALLOWED",
  "privileged route was not rejected by the relay policy",
);

const injectedActor = await request(
  `v1/missions/${missionId}/approvals/owner-bond:approve-and-resume`,
  {
    method: "POST",
    body: JSON.stringify({
      expected_version: run.payload.mission.version,
      actor: "cargo-owner.attacker",
    }),
  },
);
assert(injectedActor.response.status === 400, "client-supplied actor was accepted");

const approved = await request(
  `v1/missions/${missionId}/approvals/owner-bond:approve-and-resume`,
  {
    method: "POST",
    body: JSON.stringify({ expected_version: run.payload.mission.version }),
  },
);
assert(approved.response.status === 200, "server-bound approval was not allowed");
assert(
  approved.payload?.mission?.release_state === "RELEASED",
  "approved mission did not complete",
);
assert(
  approved.payload?.approvals?.[0]?.actor === expectedActor,
  `approval actor was not server-bound: ${approved.payload?.approvals?.[0]?.actor}`,
);

const query = await request(`v1/missions/${missionId}?admin=true`);
assert(query.response.status === 400, "query forwarding was not denied");

console.log(
  `relay smoke passed: ${missionId} released under ${expectedActor}; privileged mutation denied`,
);
