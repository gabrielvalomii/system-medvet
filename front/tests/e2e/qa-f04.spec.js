// QA (2026-10-08) — QA-F-04: botão "Fechar menu" dentro da gaveta, do ponto de vista de
// teclado e da árvore de acessibilidade (o que um leitor de tela expõe).
/* global document */
import { test, expect } from '@playwright/test';
import { AUTH_FILE, trackPageErrors } from './helpers.js';

test.use({ storageState: AUTH_FILE });

const PAGES = ['/dashboard.html', '/gastos.html', '/rendimentos.html'];
const isMobile = (page) => page.viewportSize().width < 768;

/**
 * Buttons with this accessible name that Chromium really exposes to assistive technology
 * (CDP AX tree, non-ignored). Playwright's getByRole/ariaSnapshot do not honor `inert`.
 */
async function exposedButtons(page, name) {
  const cdp = await page.context().newCDPSession(page);
  const { nodes } = await cdp.send('Accessibility.getFullAXTree');
  await cdp.detach();
  return nodes.filter(
    (node) => !node.ignored && node.role?.value === 'button' && node.name?.value === name,
  ).length;
}

const activeId = (page) =>
  page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return 'body';
    if (el.closest('.app-main')) return 'main';
    return el.id || el.textContent.trim();
  });

test.describe('QA-F-04 (QA 2026-10-08)', () => {
  test('< 768px: árvore de acessibilidade e ciclo de Tab completos nas 3 páginas', async ({
    page,
  }) => {
    test.skip(!isMobile(page), 'só gaveta (< 768px)');
    const errors = trackPageErrors(page);
    for (const path of PAGES) {
      await page.goto(path);
      await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');

      // Fechada: nenhum "Fechar menu" exposto; o toggle diz "Abrir menu".
      expect(await exposedButtons(page, 'Fechar menu'), path).toBe(0);
      expect(await exposedButtons(page, 'Abrir menu'), path).toBe(1);

      await page.locator('#menu-toggle').focus();
      await page.keyboard.press('Enter');
      await expect(page.getByRole('link', { name: 'Dashboard' })).toBeFocused();

      // Aberta: exatamente um "Fechar menu" exposto ao leitor de tela (o toggle fica inert).
      expect(await exposedButtons(page, 'Fechar menu'), path).toBe(1);
      const close = page.locator('#sidebar').getByRole('button', { name: 'Fechar menu' });
      await expect(close, path).toHaveCount(1);
      await expect(close).toHaveAttribute('aria-controls', 'sidebar');
      await expect(close).toHaveAttribute('type', 'button');
      const snapshot = await page.locator('#sidebar').ariaSnapshot();
      expect(snapshot, path).toContain('button "Fechar menu"');
      expect(snapshot, path).toContain('link "Dashboard"');

      // Área de toque mínima (WCAG 2.5.8: 24x24).
      const box = await close.boundingBox();
      expect(box.width, path).toBeGreaterThanOrEqual(24);
      expect(box.height, path).toBeGreaterThanOrEqual(24);

      // Tab para frente: ciclo inclui o botão, os 4 itens do menu e nunca o conteúdo.
      const forward = [];
      for (let i = 0; i < 12; i += 1) {
        await page.keyboard.press('Tab');
        forward.push(await activeId(page));
      }
      expect(forward, path).not.toContain('main');
      expect(forward, path).toContain('sidebar-close');
      expect(forward, path).toContain('logout-button'); // "Sair"

      // Espaço (ativação padrão de botão) também fecha e devolve o foco ao toggle.
      await close.focus();
      await page.keyboard.press('Space');
      await expect(page.locator('#sidebar')).toBeHidden();
      await expect(page.locator('#menu-toggle')).toBeFocused();
      await expect(page.locator('#menu-toggle')).toHaveAttribute('aria-expanded', 'false');
      await expect(page.locator('#menu-toggle')).toHaveAttribute('aria-label', 'Abrir menu');
      expect(await exposedButtons(page, 'Fechar menu'), path).toBe(0);
    }
    expect(errors).toEqual([]);
  });

  test('≥ 768px: botão fora da árvore de acessibilidade e fora do ciclo de Tab', async ({
    page,
  }) => {
    test.skip(isMobile(page), 'só sidebar fixa (≥ 768px)');
    for (const path of PAGES) {
      await page.goto(path);
      await expect(page.locator('body')).toHaveAttribute('data-auth', 'ok');
      await expect(page.locator('#sidebar-close')).toBeHidden();
      expect(await exposedButtons(page, 'Fechar menu'), path).toBe(0);
      expect(await page.locator('#sidebar').ariaSnapshot(), path).not.toContain('Fechar menu');

      const visited = [];
      for (let i = 0; i < 40; i += 1) {
        await page.keyboard.press('Tab');
        visited.push(await activeId(page));
      }
      expect(visited, path).not.toContain('sidebar-close');
    }
  });
});
