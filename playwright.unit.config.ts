import { defineConfig } from '@playwright/test'

// Pure-logic unit tests (no browser, no servers) run with Playwright's test runner, so
// no second test framework is needed. Browser journeys live in e2e/ (playwright.config.ts).
export default defineConfig({
  testDir: './tests/unit',
  testMatch: '**/*.test.ts',
  outputDir: './e2e/.tmp/unit-results',
  reporter: 'list',
})
