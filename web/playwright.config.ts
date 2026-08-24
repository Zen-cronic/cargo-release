import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:3024",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        'bash -lc \'export VIRTUAL_ENV=/home/zin-kg/.pyenv/versions/.cargo-release; export PATH="$VIRTUAL_ENV/bin:$PATH"; CARGO_RELEASE_DB=/tmp/cargo-release-e2e.db poetry run uvicorn cargo_release.api:app --host 127.0.0.1 --port 8095\'',
      cwd: "..",
      url: "http://127.0.0.1:8095/healthz",
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:3024",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
