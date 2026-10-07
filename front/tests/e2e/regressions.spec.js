// QA — re-teste de QA-F-01 (gaveta/foco/inert), QA-F-02 (rótulo "Descrição"), QA-F-03 (tbody vazio)
// e QA-F-04 (botão "Fechar menu" dentro da gaveta).
/* global document, getComputedStyle -- usados dentro de page.evaluate() */
import { test, expect } from '@playwright/test';
import { AUTH_FILE, trackPageErrors } from './helpers.js';

test.use({ storageState: AUTH_FILE });

const isMobile = (page) => page.viewportSize().width < 768;

/** Where the focus is: 'sidebar', 'main', 'skip', 'body' or 'other'. */
function focusZone(page) {
  return page.evaluate(() => {
    const active = document.activeElement;
    if (!active || active === document.body) return 'body';
    if (active.closest('#sidebar')) return 'sidebar';
    if (active.closest('.app-main')) return 'main';
    if (active.classList.contains('skip-link')) return 'skip';
    return 'other';
  });
}

function inertState(page) {
  return page.evaluate(() => ({
    main: document.querySelector('.app-main').hasAttribute('inert'),
    skip: document.querySelector('.skip-link').hasAttribute('inert'),
  }));
}

test.describe('QA-F-01 gaveta do menu', () => {
  test('< 768px: Enter abre e foca o 1º link; Tab fica no menu; Escape fecha e devolve o foco', async ({
    page,
  }) => {
    test.skip(!isMobile(page), 'só gaveta (< 768px)');
    const errors = trackPageErrors(page);
    await page.goto('/dashboard.html');
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
    expect(await inertState(page)).toEqual({ main: false, skip: false });

    await page.locator('#menu-toggle').focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('#sidebar')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeFocused();
    expect(await inertState(page)).toEqual({ main: true, skip: true });

    // Tab e Shift+Tab nunca saem para o conteúdo atrás do fundo escurecido.
    const zones = [];
    for (let i = 0; i < 10; i += 1) {
      await page.keyboard.press('Tab');
      zones.push(await focusZone(page));
    }
    for (let i = 0; i < 10; i += 1) {
      await page.keyboard.press('Shift+Tab');
      zones.push(await focusZone(page));
    }
    expect(zones.filter((zone) => zone !== 'sidebar' && zone !== 'body')).toEqual([]);
    expect(zones).toContain('sidebar');
    // "Sair" é alcançável pelo teclado.
    await page.getByRole('link', { name: 'Dashboard' }).focus();
    const names = [];
    for (let i = 0; i < 3; i += 1) {
      await page.keyboard.press('Tab');
      names.push(await page.evaluate(() => document.activeElement.textContent.trim()));
    }
    expect(names).toEqual(['Adicionar gastos', 'Adicionar rendimentos', 'Sair']);

    await page.keyboard.press('Escape');
    await expect(page.locator('#sidebar')).toBeHidden();
    await expect(page.locator('#menu-toggle')).toBeFocused();
    await expect(page.locator('#menu-toggle')).toHaveAttribute('aria-expanded', 'false');
    expect(await inertState(page)).toEqual({ main: false, skip: false });

    // Tab volta a andar pelo conteúdo normalmente.
    await page.keyboard.press('Tab');
    expect(await focusZone(page)).toBe('main');

    // Fechar pelo fundo também devolve o foco e remove o inert.
    await page.locator('#menu-toggle').click();
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeFocused();
    await page.locator('#sidebar-backdrop').click({ position: { x: 340, y: 400 } });
    await expect(page.locator('#sidebar')).toBeHidden();
    await expect(page.locator('#menu-toggle')).toBeFocused();
    expect(await inertState(page)).toEqual({ main: false, skip: false });

    // Gaveta aberta + troca para desktop: fecha e remove o inert.
    await page.locator('#menu-toggle').click();
    expect(await inertState(page)).toEqual({ main: true, skip: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(page.locator('#sidebar')).not.toHaveClass(/is-open/);
    await expect.poll(() => inertState(page)).toEqual({ main: false, skip: false });
    await expect(page.locator('#sidebar-backdrop')).toBeHidden();
    await page.locator('#month-prev').click(); // conteúdo clicável de novo
    expect(errors).toEqual([]);
  });

  test('≥ 768px: .app-main e skip link nunca ficam inert', async ({ page }) => {
    test.skip(isMobile(page), 'só sidebar fixa (≥ 768px)');
    for (const path of ['/dashboard.html', '/gastos.html', '/rendimentos.html']) {
      await page.goto(path);
      await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
      expect(await inertState(page), path).toEqual({ main: false, skip: false });
      await page.keyboard.press('Escape');
      await page.locator('#month-prev').click();
      await page.keyboard.press('Tab');
      expect(await inertState(page), path).toEqual({ main: false, skip: false });
      await expect(page.locator('#sidebar-backdrop')).toBeHidden();
    }
    // Skip link continua funcionando.
    await page.goto('/gastos.html');
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Pular para o conteúdo' })).toBeFocused();
  });
});

test.describe('QA-F-04 botão "Fechar menu" na gaveta', () => {
  test('< 768px: botão focável dentro da gaveta fecha e devolve o foco (3 páginas)', async ({
    page,
  }) => {
    test.skip(!isMobile(page), 'só gaveta (< 768px)');
    const errors = trackPageErrors(page);
    for (const path of ['/dashboard.html', '/gastos.html', '/rendimentos.html']) {
      await page.goto(path);
      await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
      const close = page.locator('#sidebar').getByRole('button', { name: 'Fechar menu' });
      await expect(close).toBeHidden();

      await page.locator('#menu-toggle').click();
      await expect(page.getByRole('link', { name: 'Dashboard' })).toBeFocused();
      await expect(close).toBeVisible();

      // Faz parte do ciclo de foco: Shift+Tab a partir do 1º link chega nele.
      await page.keyboard.press('Shift+Tab');
      await expect(close, path).toBeFocused();
      const outline = await close.evaluate((node) => getComputedStyle(node).outlineStyle);
      expect(outline, path).not.toBe('none');

      // Enter fecha, remove o inert e devolve o foco ao botão do menu.
      await page.keyboard.press('Enter');
      await expect(page.locator('#sidebar')).toBeHidden();
      await expect(page.locator('#menu-toggle')).toBeFocused();
      await expect(page.locator('#menu-toggle')).toHaveAttribute('aria-expanded', 'false');
      expect(await inertState(page), path).toEqual({ main: false, skip: false });

      // Clique (toque) também fecha.
      await page.locator('#menu-toggle').click();
      await close.click();
      await expect(page.locator('#sidebar')).toBeHidden();
      await expect(page.locator('#menu-toggle')).toBeFocused();
    }
    expect(errors).toEqual([]);
  });

  test('≥ 768px: botão "Fechar menu" não aparece nem é focável', async ({ page }) => {
    test.skip(isMobile(page), 'só sidebar fixa (≥ 768px)');
    for (const path of ['/dashboard.html', '/gastos.html', '/rendimentos.html']) {
      await page.goto(path);
      await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
      await expect(page.locator('#sidebar-close')).toBeHidden();
      // Shift+Tab a partir do 1º link não cai no botão.
      await page.getByRole('link', { name: 'Dashboard' }).focus();
      await page.keyboard.press('Shift+Tab');
      expect(await page.evaluate(() => document.activeElement?.id), path).not.toBe('sidebar-close');
    }
  });
});

/** Mocks the expenses list of one month with a single long entry; DELETE empties it. */
async function mockOneExpense(page) {
  let entries = [
    {
      id: 987654,
      category: 'outros',
      category_label: 'Outros',
      amount: '12.34',
      date: '2001-03-10',
      description: 'Descrição bem comprida para forçar a quebra de linha no layout de cartões QA',
      created_at: '2001-03-10T10:00:00Z',
      updated_at: '2001-03-10T10:00:00Z',
    },
  ];
  await page.route('**/api/expenses/**', async (route) => {
    const request = route.request();
    if (request.method() === 'DELETE') {
      entries = [];
      return route.fulfill({ status: 204, body: '' });
    }
    if (request.method() === 'GET') return route.fulfill({ json: entries });
    return route.fallback();
  });
}

test('QA-F-02: rótulo "Descrição" do cartão não quebra no meio da palavra', async ({ page }) => {
  await mockOneExpense(page);
  await page.goto('/gastos.html?month=2001-03');
  await expect(page.locator('#entries-body tr')).toHaveCount(1);
  const info = await page.evaluate(() => {
    const td = document.querySelector('#entries-body td[data-label="Descrição"]');
    const before = getComputedStyle(td, '::before');
    // Width the label needs on a single line, with the same font.
    const canvas = document.createElement('canvas').getContext('2d');
    canvas.font = `${before.fontWeight} ${before.fontSize} ${before.fontFamily}`;
    return {
      display: getComputedStyle(td).display,
      content: before.content,
      overflowWrap: before.overflowWrap,
      wordBreak: before.wordBreak,
      flexShrink: before.flexShrink,
      width: parseFloat(before.width),
      needed: canvas.measureText('Descrição').width,
    };
  });
  test.skip(info.content === 'none' || info.content === 'normal', 'layout de tabela (sem rótulo)');
  expect(info.overflowWrap).toBe('normal');
  expect(info.wordBreak).toBe('normal');
  expect(info.flexShrink).toBe('0');
  if (!Number.isNaN(info.width)) expect(info.width + 1).toBeGreaterThanOrEqual(info.needed);
  await page
    .locator('#entries-body tr')
    .screenshot({ path: test.info().outputPath('card-descricao.png') });
});

test('QA-F-03: excluir o último lançamento limpa o tbody', async ({ page }) => {
  await mockOneExpense(page);
  await page.goto('/gastos.html?month=2001-03');
  await expect(page.locator('#entries-body tr')).toHaveCount(1);
  await page
    .locator('#entries-body tr')
    .getByRole('button', { name: /^Excluir/ })
    .click();
  await page.getByRole('dialog').getByRole('button', { name: 'Excluir' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Gasto excluído.' })).toBeVisible();
  await expect(page.locator('#entries-table')).toBeHidden();
  await expect(page.locator('#entries-body tr')).toHaveCount(0);
  expect(await page.locator('#entries-body').evaluate((node) => node.childNodes.length)).toBe(0);
});
