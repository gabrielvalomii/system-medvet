import { test, expect } from '@playwright/test';

const EMAIL = process.env.E2E_EMAIL;
const PASSWORD = process.env.E2E_PASSWORD;

/** Collects CSP violations and uncaught errors on the page. */
function trackPageErrors(page) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error' && /Content Security Policy/i.test(message.text())) {
      errors.push(message.text());
    }
  });
  return errors;
}

test('tela de login carrega sem erros de CSP', async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
  await expect(page.getByLabel('E-mail')).toBeVisible();
  await expect(page.getByLabel('Senha')).toBeVisible();
  expect(errors).toEqual([]);
});

test('validação inline no login sem chamar a API', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.locator('#email-error')).toHaveText('Informe o e-mail.');
  await expect(page.locator('#password-error')).toHaveText('Informe a senha.');
});

test('página protegida sem sessão redireciona para o login', async ({ page }) => {
  await page.goto('/dashboard.html');
  await expect(page).toHaveURL(/\/index\.html$/);
});

test('login → dashboard → logout', async ({ page }, testInfo) => {
  test.skip(!EMAIL || !PASSWORD, 'Defina E2E_EMAIL e E2E_PASSWORD no .env');
  // QA: login via UI só no desktop — o back limita o login a 5/min por IP.
  test.skip(testInfo.project.name !== 'desktop-1440', 'Login via UI apenas no desktop');
  const errors = trackPageErrors(page);

  await page.goto('/');
  await page.getByLabel('E-mail').fill(EMAIL);
  await page.getByLabel('Senha').fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();

  await expect(page).toHaveURL(/\/dashboard\.html/);
  await expect(page.getByRole('heading', { name: 'Gastos por categoria' })).toBeVisible();
  await expect(page.locator('#total-expenses')).toContainText('R$');

  const toggle = page.locator('#menu-toggle');
  if (await toggle.isVisible()) await toggle.click();
  await page.getByRole('button', { name: 'Sair' }).click();
  await expect(page).toHaveURL(/\/index\.html$/);
  expect(errors).toEqual([]);
});
