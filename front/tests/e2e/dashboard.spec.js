// QA — Tarefa 5: dashboard (cards, gráficos, listas com %), seletor de mês e XSS.
/* global window -- usados dentro de page.evaluate() */
import { test, expect } from '@playwright/test';
import {
  AUTH_FILE,
  FIXED_MONTH,
  TAG,
  apiClient,
  brl,
  cleanupTagged,
  norm,
  trackPageErrors,
} from './helpers.js';

test.use({ storageState: AUTH_FILE });
test.describe.configure({ mode: 'serial' });

const day = `${FIXED_MONTH}-10`;
const SEED = {
  expenses: [
    { category: 'alimentacao', amount: '300.00' },
    { category: 'gasolina', amount: '100.00' },
    { category: 'lazer', amount: '100.00' },
  ],
  incomes: [
    { category: 'salario_fixo', amount: '100000.00' },
    { category: 'juros', amount: '1.00' },
  ],
};

test.describe('mês controlado com valores conhecidos', () => {
  test.beforeAll(async ({ playwright }) => {
    const request = await playwright.request.newContext({
      baseURL: test.info().project.use.baseURL,
      storageState: AUTH_FILE,
    });
    const api = apiClient(request);
    await cleanupTagged(api, [FIXED_MONTH]);
    const existing = [
      ...(await api.get(`/expenses/?month=${FIXED_MONTH}`)).body,
      ...(await api.get(`/incomes/?month=${FIXED_MONTH}`)).body,
    ];
    expect(existing, `o mês ${FIXED_MONTH} precisa estar vazio para o usuário de QA`).toEqual([]);
    for (const kind of ['expenses', 'incomes']) {
      for (const item of SEED[kind]) {
        const created = await api.post(`/${kind}/`, {
          ...item,
          date: day,
          description: `${TAG} seed`,
        });
        expect(created.status).toBe(201);
      }
    }
    await request.dispose();
  });

  test.afterAll(async ({ playwright }) => {
    const request = await playwright.request.newContext({
      baseURL: test.info().project.use.baseURL,
      storageState: AUTH_FILE,
    });
    await cleanupTagged(apiClient(request), [FIXED_MONTH]);
    await request.dispose();
  });

  test('cards, listas e % exatos; "< 0,01%" para fatia ínfima', async ({ page }) => {
    const errors = trackPageErrors(page);
    await page.goto(`/dashboard.html?month=${FIXED_MONTH}`);
    await expect(page.locator('#dashboard-status')).toContainText('carregado');
    await expect(page.locator('#month-input')).toHaveValue(FIXED_MONTH);
    await expect(page.locator('#period-label')).toHaveText('fevereiro de 2001');

    await expect(page.locator('#total-expenses')).toHaveText(brl('500'));
    await expect(page.locator('#total-incomes')).toHaveText(brl('100001'));
    await expect(page.locator('#balance')).toHaveText(brl('99501'));
    await expect(page.locator('#balance')).toHaveClass(/is-positive/);

    const expenseRows = page.locator('#expenses-list li');
    await expect(expenseRows).toHaveCount(3);
    const expenseTexts = (await expenseRows.allTextContents()).map(norm);
    expect(expenseTexts).toEqual([
      `Alimentação${norm(brl('300'))}60,00%`,
      `Gasolina${norm(brl('100'))}20,00%`,
      `Lazer${norm(brl('100'))}20,00%`,
    ]);

    const incomeRows = page.locator('#incomes-list li');
    await expect(incomeRows).toHaveCount(2);
    await expect(incomeRows.nth(0).locator('.category-percent')).toHaveText('100,00%');
    await expect(incomeRows.nth(1).locator('.category-name')).toHaveText(
      'Juros / rendimentos de aplicações',
    );
    await expect(incomeRows.nth(1).locator('.category-percent')).toHaveText('< 0,01%');

    // Gráficos renderizados (canvas com tamanho) e acessíveis.
    for (const id of ['expenses-chart', 'incomes-chart']) {
      const box = await page.locator(`#${id}`).boundingBox();
      expect(box.width).toBeGreaterThan(100);
      expect(box.height).toBeGreaterThan(100);
      await expect(page.locator(`#${id}`)).toHaveAttribute('aria-label', /por categoria\./);
    }
    // Cores: gastos quentes, ganhos frios — paletas distintas.
    const colors = await page.evaluate(() => ({
      expenses: window.Chart.getChart('expenses-chart').data.datasets[0].backgroundColor,
      incomes: window.Chart.getChart('incomes-chart').data.datasets[0].backgroundColor,
    }));
    expect(colors.expenses.some((color) => colors.incomes.includes(color))).toBe(false);
    expect(errors).toEqual([]);
  });

  test('seletor de mês: anterior/próximo atualizam URL, dados e links do menu', async ({
    page,
  }) => {
    await page.goto(`/dashboard.html?month=${FIXED_MONTH}`);
    await expect(page.locator('#total-expenses')).toHaveText(brl('500'));

    await page.getByRole('button', { name: 'Próximo mês' }).click();
    await expect(page).toHaveURL(/month=2001-03/);
    await expect(page.locator('#total-expenses')).toHaveText(brl('0'));
    await expect(page.locator('#expenses-state')).toHaveText('Nenhum gasto registrado neste mês.');
    await expect(page.locator('#incomes-state')).toHaveText(
      'Nenhum rendimento registrado neste mês.',
    );
    await expect(page.locator('#expenses-content')).toBeHidden();
    await expect(page.locator('a.nav-link[href*="gastos"]')).toHaveAttribute(
      'href',
      '/gastos.html?month=2001-03',
    );

    await page.getByRole('button', { name: 'Mês anterior' }).click();
    await expect(page).toHaveURL(new RegExp(`month=${FIXED_MONTH}`));
    await expect(page.locator('#total-expenses')).toHaveText(brl('500'));
    await expect(page.locator('#expenses-content')).toBeVisible();

    // O mês é mantido ao navegar para Gastos.
    await page.goto(`/gastos.html?month=${FIXED_MONTH}`);
    await expect(page.locator('#entries-body tr')).toHaveCount(3);
    expect(norm(await page.locator('#entries-total').textContent())).toBe(norm(brl('500')));
    await expect(page.locator('#entries-count')).toHaveText('3 lançamentos');
  });

  test('?month inválido cai no mês atual', async ({ page }) => {
    await page.goto('/dashboard.html?month=2026-13');
    await expect(page.locator('#dashboard-status')).toContainText('carregado');
    const value = await page.locator('#month-input').inputValue();
    expect(value).toMatch(/^\d{4}-\d{2}$/);
    expect(value).not.toBe('2026-13');
  });
});

test.describe('XSS: dados do usuário são renderizados como texto', () => {
  const PAYLOAD = '<img src=x onerror="window.__xss=1">&amp; "Zé" <script>window.__xss=2</script>';

  test('nome do usuário, rótulos do dashboard e descrição na tabela', async ({ page }) => {
    const errors = trackPageErrors(page);
    await page.route('**/api/auth/me/', (route) =>
      route.fulfill({
        json: { id: 1, email: 'qa@example.com', first_name: PAYLOAD, last_name: '' },
      }),
    );
    await page.route('**/api/dashboard/summary/**', (route) =>
      route.fulfill({
        json: {
          month: FIXED_MONTH,
          total_expenses: '10.00',
          total_incomes: '0.00',
          balance: '-10.00',
          expenses_by_category: [
            { category: 'outros', label: PAYLOAD, total: '10.00', percent: 100.0 },
          ],
          incomes_by_category: [],
        },
      }),
    );
    await page.goto(`/dashboard.html?month=${FIXED_MONTH}`);
    await expect(page.locator('#user-name')).toHaveText(PAYLOAD);
    await expect(page.locator('#expenses-list .category-name')).toHaveText(PAYLOAD);
    await expect(page.locator('#balance')).toHaveClass(/is-negative/);

    await page.route('**/api/expenses/**', (route) =>
      route.fulfill({
        json: [
          {
            id: 999999,
            category: 'outros',
            category_label: PAYLOAD,
            amount: '10.00',
            date: day,
            description: PAYLOAD,
          },
        ],
      }),
    );
    await page.goto(`/gastos.html?month=${FIXED_MONTH}`);
    const row = page.locator('#entries-body tr');
    await expect(row.locator('td[data-label="Descrição"]')).toHaveText(PAYLOAD);
    await expect(row.locator('td[data-label="Categoria"]')).toHaveText(PAYLOAD);

    expect(await page.locator('main img, main script, #user-name *').count()).toBe(0);
    expect(await page.evaluate(() => window.__xss)).toBeUndefined();
    expect(errors).toEqual([]);
  });
});
