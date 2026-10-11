import { defineConfig, devices } from '@playwright/test'

// The suite runs its own backend and Vite dev server on dedicated ports, never the
// developer's servers on 8000/5173: the backend launcher (e2e/support/backend_server.py)
// points it at a throwaway database under e2e/.tmp, forces LLM_PROVIDER=none and
// refuses to start unless those settings are confirmed. reuseExistingServer is off so
// an unrelated process on these ports can never be mistaken for the isolated one.
const API_PORT = 8100
const WEB_PORT = 5174
const PYTHON = process.env.E2E_PYTHON ?? '.venv/Scripts/python.exe'

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  testIgnore: '**/unit/**',
  outputDir: './e2e/.tmp/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // The HTML report keeps every step title; it is opt-in (PW_HTML=1) so a normal run
  // leaves no report artifact behind. Passwords are typed with fillSecret() regardless.
  reporter: process.env.PW_HTML === '1' ? [['list'], ['html', { outputFolder: './e2e/.tmp/report', open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    // Traces record typed text and request bodies, i.e. the throwaway test accounts'
    // passwords. Off by default; opt in locally with PW_TRACE=1 when debugging, and
    // delete e2e/.tmp afterwards. Screenshots show password fields masked.
    trace: process.env.PW_TRACE === '1' ? 'retain-on-failure' : 'off',
    screenshot: 'only-on-failure',
  },
  projects: [{
    name: 'chrome',
    // The installed Google Chrome is used because the bundled Chromium download is not
    // reachable from this machine; set PW_CHANNEL=chromium after `npx playwright install chromium`.
    use: { ...devices['Desktop Chrome'], channel: process.env.PW_CHANNEL ?? 'chrome' },
  }],
  webServer: [
    {
      command: `"${PYTHON}" e2e/support/backend_server.py --port ${API_PORT} --frontend-url http://localhost:${WEB_PORT}`,
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: 'pipe',
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_API_BASE_URL: `http://localhost:${API_PORT}` },
    },
  ],
})
