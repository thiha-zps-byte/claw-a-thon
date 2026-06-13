import { defineConfig, devices } from '@playwright/test'

// BASE_URL points at the app under test:
// - local: the backend serving the built frontend (http://localhost:8080)
// - prod : the deployed AgentBase endpoint
const BASE_URL = process.env.BASE_URL ?? 'http://localhost:8080'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: BASE_URL,
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
