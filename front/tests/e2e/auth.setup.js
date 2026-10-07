// Logs in ONCE per run through the API and saves the session for the other specs.
// The back-end throttles login to 5 requests/min per IP, so the suite must not
// log in through the UI in every test/project.
import { test as setup, expect } from '@playwright/test';
import { AUTH_FILE, EMAIL, PASSWORD } from './helpers.js';

setup('autentica o usuário de QA (storageState)', async ({ request }) => {
  setup.skip(!EMAIL || !PASSWORD, 'Defina E2E_EMAIL e E2E_PASSWORD no front/.env');
  setup.setTimeout(150_000);

  expect((await request.get('/api/auth/csrf/')).ok()).toBeTruthy();

  const login = async () => {
    const state = await request.storageState();
    const csrf = state.cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
    return request.post('/api/auth/login/', {
      headers: { 'X-CSRFToken': csrf },
      data: { email: EMAIL, password: PASSWORD },
    });
  };

  let response = await login();
  if (response.status() === 429) {
    // A previous run used the 5/min budget: wait for the window and retry once.
    const wait = Number(response.headers()['retry-after'] ?? 60);
    await new Promise((resolve) => setTimeout(resolve, (wait + 1) * 1000));
    response = await login();
  }
  expect(response.status(), await response.text()).toBe(200);
  await request.storageState({ path: AUTH_FILE });
});
