// QA — Tarefas 4–6: responsividade (360/768/1440), sidebar, teclado/foco, tema escuro e CSP.
/* global document, getComputedStyle -- usados dentro de page.evaluate() */
import { test, expect } from '@playwright/test';
import {
  AUTH_FILE,
  FIXED_MONTH,
  NO_SESSION,
  expectNoHorizontalScroll,
  trackPageErrors,
} from './helpers.js';

const PROTECTED = ['/dashboard.html', '/gastos.html', '/rendimentos.html'];

test.describe('logado', () => {
  test.use({ storageState: AUTH_FILE });

  for (const path of PROTECTED) {
    test(`${path}: sem scroll horizontal, tema escuro e sem erros de CSP/JS`, async ({ page }) => {
      const errors = trackPageErrors(page);
      await page.goto(path);
      await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
      await page.waitForLoadState('networkidle');
      await expectNoHorizontalScroll(page);

      const theme = await page.evaluate(() => {
        const body = getComputedStyle(document.body);
        const root = getComputedStyle(document.documentElement);
        return {
          bg: body.backgroundColor,
          color: body.color,
          tokenBg: root.getPropertyValue('--bg').trim(),
          scheme: document.querySelector('meta[name="color-scheme"]')?.content,
        };
      });
      expect(theme.tokenBg).toBe('#0f1115');
      expect(theme.bg).toBe('rgb(15, 17, 21)');
      expect(theme.color).toBe('rgb(230, 232, 238)');
      expect(theme.scheme).toBe('dark');
      expect(errors).toEqual([]);
    });
  }

  test('dashboard: gráficos lado a lado ≥ 900px e empilhados abaixo', async ({ page }) => {
    await page.goto(`/dashboard.html?month=${FIXED_MONTH}`);
    await expect(page.locator('#dashboard-status')).toContainText('carregado');
    const panels = page.locator('.charts-grid > .panel');
    const [left, right] = [await panels.nth(0).boundingBox(), await panels.nth(1).boundingBox()];
    const width = page.viewportSize().width;
    if (width >= 900) {
      expect(Math.abs(left.y - right.y)).toBeLessThan(2);
      expect(right.x).toBeGreaterThan(left.x + left.width - 1);
    } else {
      expect(right.y).toBeGreaterThanOrEqual(left.y + left.height - 1);
      expect(Math.abs(left.x - right.x)).toBeLessThan(2);
    }
    // "Gastos" à esquerda/acima e "Ganhos" à direita/abaixo.
    await expect(panels.nth(0).getByRole('heading')).toHaveText('Gastos por categoria');
    await expect(panels.nth(1).getByRole('heading')).toHaveText('Ganhos por categoria');
  });

  test('sidebar: fixa ≥ 768px; gaveta colapsável < 768px (teclado e Escape)', async ({ page }) => {
    await page.goto('/dashboard.html');
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
    const sidebar = page.locator('#sidebar');
    const toggle = page.getByRole('button', { name: 'Abrir menu' });

    if (page.viewportSize().width >= 768) {
      await expect(sidebar).toBeVisible();
      await expect(page.locator('#menu-toggle')).toBeHidden();
      await expect(page.getByRole('link', { name: 'Adicionar gastos' })).toBeVisible();
      return;
    }

    await expect(sidebar).toBeHidden();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await toggle.focus();
    await page.keyboard.press('Enter');
    await expect(sidebar).toBeVisible();
    await expect(page.locator('#menu-toggle')).toHaveAttribute('aria-expanded', 'true');
    // Foco vai para o primeiro link do menu.
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeFocused();
    await expectNoHorizontalScroll(page);

    await page.keyboard.press('Escape');
    await expect(sidebar).toBeHidden();
    await expect(page.locator('#menu-toggle')).toBeFocused();

    // Clique no fundo escurecido fecha.
    await page.locator('#menu-toggle').click();
    await expect(sidebar).toBeVisible();
    await page.locator('#sidebar-backdrop').click({ position: { x: 340, y: 400 } });
    await expect(sidebar).toBeHidden();

    // Navegar pelo menu da gaveta.
    await page.locator('#menu-toggle').click();
    await page.getByRole('link', { name: 'Adicionar rendimentos' }).click();
    await expect(page).toHaveURL(/\/rendimentos\.html/);
  });

  test('teclado: skip link, foco visível e navegação pelo menu com Enter', async ({ page }) => {
    await page.goto('/gastos.html');
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');

    await page.keyboard.press('Tab');
    const skip = page.getByRole('link', { name: 'Pular para o conteúdo' });
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport();
    await page.keyboard.press('Enter');
    await expect(page.locator('#main')).toBeFocused();

    // Próximo Tab cai no formulário (categoria) e o foco é visível (outline).
    await page.keyboard.press('Tab');
    const category = page.getByLabel('Categoria');
    await expect(category).toBeFocused();
    const outline = await category.evaluate((node) => {
      const style = getComputedStyle(node);
      return { style: style.outlineStyle, width: style.outlineWidth, shadow: style.boxShadow };
    });
    expect(outline.style !== 'none' || outline.shadow !== 'none', JSON.stringify(outline)).toBe(
      true,
    );

    // Todos os campos têm label associado.
    for (const id of ['category', 'amount', 'date', 'description', 'month-input']) {
      const labelled = await page.locator(`#${id}`).evaluate((node) => node.labels?.length ?? 0);
      expect(labelled, id).toBeGreaterThan(0);
    }

    if (page.viewportSize().width >= 768) {
      const link = page.getByRole('link', { name: 'Dashboard' });
      await link.focus();
      const ring = await link.evaluate((node) => getComputedStyle(node).outlineStyle);
      expect(ring).not.toBe('none');
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(/\/dashboard\.html/);
    }
  });

  test('formulário de gasto pode ser enviado só com teclado (validação)', async ({ page }) => {
    await page.goto('/gastos.html');
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
    await page.getByLabel('Valor (R$)').focus();
    await page.keyboard.type('0');
    await page.keyboard.press('Enter');
    await expect(page.locator('#category-error')).toHaveText('Selecione uma categoria.');
    await expect(page.locator('#amount-error')).toHaveText('O valor deve ser maior que zero.');
    await expect(page.getByLabel('Categoria')).toBeFocused();
  });
});

test.describe('sem sessão', () => {
  test.use({ storageState: NO_SESSION });

  test('login: responsivo, tema escuro, foco por Tab e sem erros de CSP', async ({ page }) => {
    const errors = trackPageErrors(page);
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expectNoHorizontalScroll(page);
    const card = await page.locator('.auth-card').boundingBox();
    expect(card.x).toBeGreaterThanOrEqual(0);
    expect(card.x + card.width).toBeLessThanOrEqual(page.viewportSize().width);

    await page.keyboard.press('Tab');
    await expect(page.getByLabel('E-mail')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Senha')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Entrar' })).toBeFocused();

    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(bg).toBe('rgb(15, 17, 21)');
    expect(errors).toEqual([]);
  });

  test('404 amigável no tema escuro', async ({ page }) => {
    const response = await page.goto('/nao-existe');
    expect(response.status()).toBe(404);
    await expectNoHorizontalScroll(page);
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(bg).toBe('rgb(15, 17, 21)');
  });
});
