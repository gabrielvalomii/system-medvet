import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ quiet: true });

const PORT = Number(process.env.PORT) || 3000;
const baseURL = `http://localhost:${PORT}`;

// The Django API must already be running on API_URL (default http://127.0.0.1:8000).
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1, // login is rate limited (5/min per IP) on the back-end
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    // QA: logs in once (API) and saves the session in test-results/.auth/user.json.
    { name: 'setup', testMatch: /auth\.setup\.js$/, teardown: 'teardown' },
    // QA: removes leftover QA-E2E entries and logs the shared session out.
    { name: 'teardown', testMatch: /auth\.teardown\.js$/ },
    {
      name: 'desktop-1440',
      dependencies: ['setup'],
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'tablet-768',
      dependencies: ['setup'],
      use: { ...devices['Desktop Chrome'], viewport: { width: 768, height: 1024 } },
    },
    {
      name: 'mobile-360',
      dependencies: ['setup'],
      use: { ...devices['Desktop Chrome'], viewport: { width: 360, height: 740 } },
    },
  ],
  webServer: {
    command: 'node server.js',
    url: baseURL,
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
