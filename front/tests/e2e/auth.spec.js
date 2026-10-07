// QA — Tarefa 4/7: login, páginas protegidas e logout.
import { test, expect } from '@playwright/test';
import { AUTH_FILE, EMAIL, PASSWORD, NO_SESSION, isDesktop, trackPageErrors } from './helpers.js';

test.use({ storageState: NO_SESSION });

test.describe('sem sessão', () => {
  for (const path of ['/dashboard.html', '/gastos.html', '/rendimentos.html']) {
    test(`${path} redireciona para o login sem exibir conteúdo protegido`, async ({ page }) => {
      const errors = trackPageErrors(page);
      await page.goto(path);
      await expect(page).toHaveURL(/\/index\.html$/);
      await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
      expect(errors).toEqual([]);
    });
  }

  test('API protegida responde 401/403 sem sessão', async ({ request }) => {
    for (const path of ['/api/auth/me/', '/api/expenses/', '/api/dashboard/summary/']) {
      const response = await request.get(path);
      expect([401, 403], path).toContain(response.status());
    }
  });

  test('login: e-mail inválido e campos vazios validam sem chamar a API', async ({ page }) => {
    let loginCalls = 0;
    page.on('request', (req) => {
      if (req.url().includes('/api/auth/login/')) loginCalls += 1;
    });
    await page.goto('/');
    await page.getByLabel('E-mail').fill('nao-e-email');
    await page.getByLabel('Senha').press('Enter');
    await expect(page.locator('#email-error')).toHaveText('E-mail inválido.');
    await expect(page.locator('#password-error')).toHaveText('Informe a senha.');
    await expect(page.getByLabel('E-mail')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByLabel('E-mail')).toBeFocused();
    expect(loginCalls).toBe(0);
  });

  // Respostas simuladas (page.route): não consomem o limite real de login.
  for (const [status, body, message] of [
    [429, { detail: 'Request was throttled.' }, 'Muitas tentativas. Aguarde um minuto'],
    [
      502,
      { detail: 'Servidor da API indisponível. Tente novamente em instantes.' },
      'Servidor da API indisponível',
    ],
  ]) {
    test(`login: resposta ${status} mostra mensagem amigável e reabilita o botão`, async ({
      page,
    }) => {
      await page.route('**/api/auth/login/', (route) => route.fulfill({ status, json: body }));
      await page.goto('/');
      await page.getByLabel('E-mail').fill('alguem@example.com');
      await page.getByLabel('Senha').fill('qualquer');
      await page.getByRole('button', { name: 'Entrar' }).click();
      await expect(page.locator('#login-error')).toContainText(message);
      await expect(page.getByRole('button', { name: 'Entrar' })).toBeEnabled();
      await expect(page).toHaveURL(/\/(index\.html)?$/);
    });
  }
});

test.describe('login real (consome o limite de 5/min)', () => {
  test.beforeEach(({ browserName: _browser }, testInfo) => {
    test.skip(!EMAIL || !PASSWORD, 'Defina E2E_EMAIL e E2E_PASSWORD no front/.env');
    test.skip(!isDesktop(testInfo), 'Login via UI só no desktop (throttle 5/min por IP)');
  });

  test('credenciais inválidas mostram erro genérico e limpam a senha', async ({ page }) => {
    const errors = trackPageErrors(page);
    await page.goto('/');
    await page.getByLabel('E-mail').fill(EMAIL);
    await page.getByLabel('Senha').fill('senha-errada-QA');
    await page.getByRole('button', { name: 'Entrar' }).click();

    await expect(page.locator('#login-error')).toHaveText('E-mail ou senha inválidos.');
    await expect(page).toHaveURL(/\/(index\.html)?$/);
    await expect(page.getByLabel('Senha')).toHaveValue('');
    await expect(page.getByLabel('Senha')).toBeFocused();
    await expect(page.getByRole('button', { name: 'Entrar' })).toBeEnabled();
    // 401 do login aparece como "Failed to load resource" (esperado) — nada além disso.
    expect(errors.filter((e) => !/status of 401/.test(e))).toEqual([]);
  });

  test('login válido → dashboard → logout encerra a sessão', async ({ page, context }) => {
    const errors = trackPageErrors(page);
    await page.goto('/');
    await page.getByLabel('E-mail').fill(EMAIL);
    await page.getByLabel('Senha').fill(PASSWORD);
    await page.getByLabel('Senha').press('Enter');

    await expect(page).toHaveURL(/\/dashboard\.html/);
    await expect(page.locator('#user-name')).not.toBeEmpty();
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');

    // Com sessão, abrir o login redireciona de volta ao dashboard.
    await page.goto('/index.html');
    await expect(page).toHaveURL(/\/dashboard\.html/);

    // Cookie de sessão HttpOnly + SameSite=Lax; nada sensível no localStorage.
    const cookies = await context.cookies();
    const session = cookies.find((cookie) => cookie.name === 'sessionid');
    expect(session?.httpOnly).toBe(true);
    expect(session?.sameSite).toBe('Lax');
    const storage = await page.evaluate(() => ({
      local: Object.keys(localStorage),
      session: Object.keys(sessionStorage),
    }));
    expect(storage).toEqual({ local: [], session: [] });

    await page.getByRole('button', { name: 'Sair' }).click();
    await expect(page).toHaveURL(/\/index\.html$/);

    // A sessão foi encerrada no servidor.
    const me = await page.request.get('/api/auth/me/');
    expect([401, 403]).toContain(me.status());
    await page.goto('/dashboard.html');
    await expect(page).toHaveURL(/\/index\.html$/);
    // "Voltar" do navegador não reabre o dashboard logado.
    await page.goBack();
    await expect(page).toHaveURL(/\/index\.html$/);

    expect(errors).toEqual([]);
  });
});

test.describe('sessão expirada / CSRF durante o uso', () => {
  test.use({ storageState: AUTH_FILE });

  test('403 de sessão ao salvar redireciona para o login', async ({ page }) => {
    await page.goto('/gastos.html');
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
    await page.route('**/api/expenses/', (route) =>
      route.request().method() === 'POST'
        ? route.fulfill({
            status: 403,
            json: { detail: 'As credenciais de autenticação não foram fornecidas.' },
          })
        : route.continue(),
    );
    await page.getByLabel('Categoria').selectOption({ index: 1 });
    await page.getByLabel('Valor (R$)').fill('1');
    await page.getByRole('button', { name: 'Adicionar gasto' }).click();
    await expect(page).toHaveURL(/\/index\.html$/);
  });

  test('falha de CSRF ao salvar mostra aviso e NÃO desloga', async ({ page }) => {
    await page.goto('/gastos.html');
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
    await page.route('**/api/expenses/', (route) =>
      route.request().method() === 'POST'
        ? route.fulfill({
            status: 403,
            json: { detail: 'CSRF Failed: CSRF token missing.' },
          })
        : route.continue(),
    );
    await page.getByLabel('Categoria').selectOption({ index: 1 });
    await page.getByLabel('Valor (R$)').fill('1');
    await page.getByRole('button', { name: 'Adicionar gasto' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Recarregue a página' })).toBeVisible();
    await expect(page).toHaveURL(/\/gastos\.html/);
  });

  test('POST real sem header X-CSRFToken é recusado (403)', async ({ page }) => {
    await page.goto('/gastos.html');
    const response = await page.request.post('/api/expenses/', {
      data: { category: 'outros', amount: '1.00', date: '2001-02-01', description: 'QA-E2E csrf' },
    });
    expect(response.status()).toBe(403);
  });
});
