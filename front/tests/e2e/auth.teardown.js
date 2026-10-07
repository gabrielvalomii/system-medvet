// Ends the shared QA session (server side) and removes the saved storageState.
import fs from 'node:fs';
import { test as teardown, expect } from '@playwright/test';
import { AUTH_FILE, FIXED_MONTH, apiClient, cleanupTagged, todaySaoPaulo } from './helpers.js';

teardown('limpa lançamentos de teste e encerra a sessão de QA', async ({ playwright, baseURL }) => {
  if (!fs.existsSync(AUTH_FILE)) return;
  const request = await playwright.request.newContext({ baseURL, storageState: AUTH_FILE });
  const api = apiClient(request);
  // Safety net: removes anything tagged QA-E2E left by an interrupted run.
  const month = todaySaoPaulo().slice(0, 7);
  const [y, m] = month.split('-').map(Number);
  const prev = m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, '0')}`;
  await cleanupTagged(api, [month, prev, FIXED_MONTH]);
  const logout = await api.post('/auth/logout/');
  expect([200, 204]).toContain(logout.status);
  await request.dispose();
  fs.rmSync(AUTH_FILE, { force: true });
});
