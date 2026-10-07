// Shared helpers for the E2E suite (QA).
/* global document -- usados dentro de page.evaluate() */
import { expect } from '@playwright/test';

export const EMAIL = process.env.E2E_EMAIL;
export const PASSWORD = process.env.E2E_PASSWORD;

/** Session saved once by auth.setup.js (only 1 login per run: throttle 5/min). */
export const AUTH_FILE = 'test-results/.auth/user.json';

/** Empty storage: used by tests that must start logged out. */
export const NO_SESSION = { cookies: [], origins: [] };

/** Tag added to every description created by the suite (used by the cleanup). */
export const TAG = 'QA-E2E';

/** Month reserved for the controlled percentage test (must be empty for the QA user). */
export const FIXED_MONTH = '2001-02';

/** Only the desktop project runs the UI login tests (the back limits login to 5/min per IP). */
export function isDesktop(testInfo) {
  return testInfo.project.name === 'desktop-1440';
}

/** Collects CSP violations, uncaught errors and console errors on the page. */
export function trackPageErrors(page) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    // 401/403 on /api/auth/me/ is the expected "not logged in" answer.
    if (/Failed to load resource: the server responded with a status of 40[13]/.test(text)) return;
    errors.push(`console: ${text}`);
  });
  return errors;
}

const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const percent = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Expected UI text for an API decimal string. */
export function brl(value) {
  return currency.format(Number(value));
}

/** Expected UI text for an API percent. */
export function pct(value, total) {
  if (Number(value) === 0 && Number(total) > 0) return '< 0,01%';
  return `${percent.format(Number(value))}%`;
}

/** Normalizes whitespace (Intl uses NBSP after "R$"). */
export function norm(text) {
  return String(text).replace(/\s+/g, ' ').trim();
}

/** YYYY-MM-DD in America/Sao_Paulo (same timezone as the Playwright config). */
export function todaySaoPaulo() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
}

/**
 * Thin API client that reuses the cookies of a Playwright request context
 * (page.request / context.request) and sends the CSRF header.
 */
export function apiClient(requestContext) {
  async function csrf() {
    const state = await requestContext.storageState();
    return state.cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
  }
  async function send(method, path, data) {
    const headers = { Accept: 'application/json' };
    if (method !== 'GET') headers['X-CSRFToken'] = await csrf();
    const response = await requestContext.fetch(`/api${path}`, { method, headers, data });
    const body = response.status() === 204 ? null : await response.json().catch(() => null);
    return { status: response.status(), body };
  }
  return {
    get: (path) => send('GET', path),
    post: (path, data) => send('POST', path, data),
    delete: (path) => send('DELETE', path),
  };
}

/** Deletes every expense/income whose description contains TAG (any month). */
export async function cleanupTagged(api, months) {
  let removed = 0;
  for (const kind of ['expenses', 'incomes']) {
    for (const month of months) {
      const list = await api.get(`/${kind}/?month=${month}`);
      expect(list.status, `GET /${kind}/ ${month}`).toBe(200);
      for (const entry of list.body) {
        if (!String(entry.description).includes(TAG)) continue;
        const del = await api.delete(`/${kind}/${entry.id}/`);
        expect(del.status).toBe(204);
        removed += 1;
      }
    }
  }
  return removed;
}

/** Opens the sidebar on mobile (drawer) when needed. */
export async function openMenuIfNeeded(page) {
  const toggle = page.locator('#menu-toggle');
  if (await toggle.isVisible()) {
    await toggle.click();
    await expect(page.locator('#sidebar')).toHaveClass(/is-open/);
  }
}

/** Asserts there is no horizontal scroll on the page. */
export async function expectNoHorizontalScroll(page) {
  const sizes = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(
    sizes.scroll,
    `scrollWidth ${sizes.scroll} > clientWidth ${sizes.client}`,
  ).toBeLessThanOrEqual(sizes.client);
}
