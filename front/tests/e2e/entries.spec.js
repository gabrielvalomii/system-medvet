// QA — Tarefas 5, 6 e 7: adicionar/editar/excluir gastos e rendimentos e conferir no dashboard.
/* global window, getComputedStyle -- usados dentro de page.evaluate() */
import { test, expect } from '@playwright/test';
import {
  AUTH_FILE,
  TAG,
  apiClient,
  brl,
  cleanupTagged,
  norm,
  pct,
  todaySaoPaulo,
  trackPageErrors,
} from './helpers.js';

test.use({ storageState: AUTH_FILE });
test.describe.configure({ mode: 'serial' });

const today = todaySaoPaulo();
const month = today.slice(0, 7);

/** Unique description per project/run, with "&" and quotes to check text rendering. */
function description(testInfo, suffix) {
  return `${TAG} ${testInfo.project.name} ${suffix} & "aspas" 'simples' Ção`;
}

function rowFor(page, text) {
  return page.locator('#entries-body tr').filter({ hasText: text });
}

async function fillEntry(page, { category, amount, desc }) {
  await page.getByLabel('Categoria').selectOption({ label: category });
  await page.getByLabel('Valor (R$)').fill(amount);
  await page.getByLabel(/Descrição/).fill(desc);
}

/** Compares the dashboard lists/cards with GET /api/dashboard/summary/. */
async function expectDashboardMatchesApi(page, targetMonth) {
  const api = apiClient(page.request);
  const { status, body: summary } = await api.get(`/dashboard/summary/?month=${targetMonth}`);
  expect(status).toBe(200);

  await expect(page.locator('#total-expenses')).toHaveText(brl(summary.total_expenses));
  await expect(page.locator('#total-incomes')).toHaveText(brl(summary.total_incomes));
  await expect(page.locator('#balance')).toHaveText(brl(summary.balance));

  for (const [kind, key] of [
    ['expenses', 'expenses_by_category'],
    ['incomes', 'incomes_by_category'],
  ]) {
    const items = summary[key];
    if (items.length === 0) continue;
    const sum = items.reduce((total, item) => total + item.percent, 0);
    expect(Math.abs(sum - 100), `soma dos % de ${kind}`).toBeLessThanOrEqual(0.01);

    const rows = page.locator(`#${kind}-list li`);
    await expect(rows).toHaveCount(items.length);
    for (const [index, item] of items.entries()) {
      const row = rows.nth(index);
      await expect(row.locator('.category-name')).toHaveText(item.label);
      expect(norm(await row.locator('.category-amount').textContent())).toBe(norm(brl(item.total)));
      await expect(row.locator('.category-percent')).toHaveText(pct(item.percent, item.total));
    }

    // Chart has one slice per category with the API totals, and the swatch has the slice color.
    const chart = await page.evaluate((id) => {
      const instance = window.Chart.getChart(id);
      const dataset = instance.data.datasets[0];
      return { data: dataset.data, colors: dataset.backgroundColor, labels: instance.data.labels };
    }, `${kind}-chart`);
    expect(chart.labels).toEqual(items.map((item) => item.label));
    expect(chart.data).toEqual(items.map((item) => Number(item.total)));
    const swatches = await rows
      .locator('.swatch')
      .evaluateAll((nodes) => nodes.map((node) => getComputedStyle(node).backgroundColor));
    const toRgb = (hex) => {
      const n = parseInt(hex.slice(1), 16);
      return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
    };
    expect(swatches).toEqual(chart.colors.map(toRgb));
  }
  return summary;
}

test.afterAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({
    baseURL: test.info().project.use.baseURL,
    storageState: AUTH_FILE,
  });
  await cleanupTagged(apiClient(request), [month]);
  await request.dispose();
});

test('fluxo completo: gasto + rendimento → tabela → dashboard → editar → excluir', async ({
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  const errors = trackPageErrors(page);
  const expenseDesc = description(testInfo, 'gasto');
  const incomeDesc = description(testInfo, 'rend');

  /* ---------- Adicionar gasto ---------- */
  await page.goto('/gastos.html');
  await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
  await expect(page.getByLabel('Data')).toHaveValue(today); // data padrão = hoje
  await expect(page.locator('#month-input')).toHaveValue(month);

  // Categorias vêm da API (não hard-coded): o select tem exatamente as opções de /api/categories/.
  const categories = (await apiClient(page.request).get('/categories/')).body;
  await expect(page.locator('#category option')).toHaveCount(categories.expenses.length + 1);
  const options = await page.locator('#category option:not([value=""])').allTextContents();
  expect(options).toEqual(categories.expenses.map((item) => item.label));

  // Validação inline: valor inválido não chama a API.
  await page.getByLabel('Valor (R$)').fill('abc');
  await page.getByRole('button', { name: 'Adicionar gasto' }).click();
  await expect(page.locator('#category-error')).toHaveText('Selecione uma categoria.');
  await expect(page.locator('#amount-error')).toContainText('Valor inválido');

  await fillEntry(page, { category: 'Alimentação', amount: '1.234,56', desc: expenseDesc });
  await page.getByRole('button', { name: 'Adicionar gasto' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Gasto adicionado.' })).toBeVisible();

  let row = rowFor(page, expenseDesc);
  await expect(row).toHaveCount(1);
  await expect(row.locator('td[data-label="Categoria"]')).toHaveText('Alimentação');
  await expect(row.locator('td[data-label="Descrição"]')).toHaveText(expenseDesc); // texto literal
  expect(norm(await row.locator('td[data-label="Valor"]').textContent())).toBe(
    norm(brl('1234.56')),
  );
  // Formulário volta ao estado inicial.
  await expect(page.getByLabel('Valor (R$)')).toHaveValue('');
  await expect(page.getByLabel('Data')).toHaveValue(today);

  /* ---------- Editar gasto ---------- */
  await row.getByRole('button', { name: /^Editar/ }).click();
  await expect(page.locator('#form-title')).toHaveText('Editar gasto');
  await expect(page.getByLabel('Valor (R$)')).toHaveValue('1234,56');
  await expect(page.getByLabel('Valor (R$)')).toBeFocused();
  await page.getByLabel('Categoria').selectOption({ label: 'Lazer' });
  await page.getByLabel('Valor (R$)').fill('99,90');
  await page.getByRole('button', { name: 'Salvar alterações' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Gasto atualizado.' })).toBeVisible();
  row = rowFor(page, expenseDesc);
  await expect(row).toHaveCount(1);
  await expect(row.locator('td[data-label="Categoria"]')).toHaveText('Lazer');
  expect(norm(await row.locator('td[data-label="Valor"]').textContent())).toBe(norm(brl('99.90')));
  await expect(page.locator('#form-title')).toHaveText('Novo gasto');

  /* ---------- Adicionar rendimento ---------- */
  await page.goto('/rendimentos.html');
  await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
  await expect(page.locator('#category option')).toHaveCount(categories.incomes.length + 1);
  const incomeOptions = await page.locator('#category option:not([value=""])').allTextContents();
  expect(incomeOptions).toEqual(categories.incomes.map((item) => item.label));
  await fillEntry(page, { category: 'Freelance', amount: '500', desc: incomeDesc });
  await page.getByRole('button', { name: 'Adicionar rendimento' }).click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Rendimento adicionado.' }),
  ).toBeVisible();
  await expect(rowFor(page, incomeDesc)).toHaveCount(1);
  await expect(rowFor(page, incomeDesc).locator('td[data-label="Descrição"]')).toHaveText(
    incomeDesc,
  );

  /* ---------- Dashboard confere com a API ---------- */
  await page.goto(`/dashboard.html?month=${month}`);
  await expect(page.locator('#dashboard-status')).toContainText('carregado');
  const summary = await expectDashboardMatchesApi(page, month);
  expect(summary.expenses_by_category.map((item) => item.category)).toContain('lazer');
  expect(summary.incomes_by_category.map((item) => item.category)).toContain('freelance');

  /* ---------- Excluir (cancelar mantém; confirmar remove) ---------- */
  await page.goto('/gastos.html');
  row = rowFor(page, expenseDesc);
  await row.getByRole('button', { name: /^Excluir/ }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Cancelar' })).toBeFocused();
  await dialog.getByRole('button', { name: 'Cancelar' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(rowFor(page, expenseDesc)).toHaveCount(1);

  await rowFor(page, expenseDesc)
    .getByRole('button', { name: /^Excluir/ })
    .click();
  await page.getByRole('dialog').getByRole('button', { name: 'Excluir' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Gasto excluído.' })).toBeVisible();
  await expect(rowFor(page, expenseDesc)).toBeHidden();

  await page.goto('/rendimentos.html');
  await rowFor(page, incomeDesc)
    .getByRole('button', { name: /^Excluir/ })
    .click();
  // Escape fecha o diálogo sem excluir.
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(rowFor(page, incomeDesc)).toHaveCount(1);
  await rowFor(page, incomeDesc)
    .getByRole('button', { name: /^Excluir/ })
    .click();
  await page.getByRole('dialog').getByRole('button', { name: 'Excluir' }).click();
  await expect(rowFor(page, incomeDesc)).toBeHidden();

  // Removidos também no back.
  const api = apiClient(page.request);
  const left = [
    ...(await api.get(`/expenses/?month=${month}`)).body,
    ...(await api.get(`/incomes/?month=${month}`)).body,
  ].filter((entry) => entry.description.includes(testInfo.project.name));
  expect(left).toEqual([]);

  expect(errors).toEqual([]);
});

test('erro 400 da API aparece inline (descrição com < >) e nada é criado', async ({ page }) => {
  await page.goto('/gastos.html');
  await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
  await fillEntry(page, { category: 'Outros', amount: '10', desc: `${TAG} <b>x</b>` });
  await page.getByRole('button', { name: 'Adicionar gasto' }).click();
  await expect(page.locator('#description-error')).toContainText('< ou >');
  await expect(rowFor(page, `${TAG} <b>`)).toHaveCount(0);
});

test('lançamento em outro mês: toast informa o mês e o seletor muda', async ({
  page,
}, testInfo) => {
  // Uses the previous month and deletes it at the end.
  const [y, m] = month.split('-').map(Number);
  const prev = m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, '0')}`;
  const desc = description(testInfo, 'outro-mes');
  await page.goto('/rendimentos.html');
  await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
  await fillEntry(page, { category: 'Juros / rendimentos de aplicações', amount: '0,01', desc });
  await page.getByLabel('Data').fill(`${prev}-15`);
  await page.getByRole('button', { name: 'Adicionar rendimento' }).click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Rendimento adicionado em' }),
  ).toBeVisible();
  await expect(page.locator('#month-input')).toHaveValue(prev);
  await expect(page).toHaveURL(new RegExp(`month=${prev}`));
  await expect(rowFor(page, desc)).toHaveCount(1);

  const removed = await cleanupTagged(apiClient(page.request), [prev]);
  expect(removed).toBeGreaterThanOrEqual(1);
});
