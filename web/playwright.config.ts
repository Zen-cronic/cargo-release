import { defineConfig, devices } from "@playwright/test";

const webPort = process.env.CARGO_RELEASE_E2E_WEB_PORT ?? "3024";
const controllerPort = process.env.CARGO_RELEASE_E2E_CONTROLLER_PORT ?? "8095";

export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  retries: 0,
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        `bash -lc 'export VIRTUAL_ENV=/home/zin-kg/.pyenv/versions/.cargo-release; export PATH="$VIRTUAL_ENV/bin:$PATH"; CARGO_RELEASE_DB=/tmp/cargo-release-e2e-${controllerPort}.db CARGO_RELEASE_GEMMA_CRITIC_ENABLED=1 CARGO_RELEASE_GEMMA_CRITIC_MODE=FIXTURE CARGO_RELEASE_EMBEDDING_RETRIEVAL_ENABLED=1 CARGO_RELEASE_EMBEDDING_RETRIEVAL_MODE=FIXTURE CARGO_RELEASE_VEO_REPLAY_ENABLED=1 CARGO_RELEASE_VEO_REPLAY_MODE=FIXTURE poetry run uvicorn cargo_release.api:app --host 127.0.0.1 --port ${controllerPort}'`,
      cwd: "..",
      url: `http://127.0.0.1:${controllerPort}/healthz`,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: `CARGO_RELEASE_CONTROLLER_URL=http://127.0.0.1:${controllerPort} NEXT_PUBLIC_AGENT_URL=http://127.0.0.1:${webPort}/api/cargo npx next dev --hostname 127.0.0.1 --port ${webPort}`,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
