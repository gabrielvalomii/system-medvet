// Protected-page shell: auth check, user chip, collapsible sidebar, logout, month picker.
import { requireAuth, logout, displayName } from './auth.js';
import { currentMonth, formatMonthLabel, isValidMonth, shiftMonth } from './format.js';
import { setButtonLoading, showToast } from './ui.js';

const MOBILE_QUERY = window.matchMedia('(max-width: 767px)');

function setupSidebar() {
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('menu-toggle');
  const backdrop = document.getElementById('sidebar-backdrop');
  const closeButton = document.getElementById('sidebar-close');
  if (!sidebar || !toggle || !backdrop) return;

  // Content behind the drawer is made inert while it is open, so Tab stays in the menu.
  const outside = [document.querySelector('.skip-link'), document.querySelector('.app-main')];

  const setOpen = (open) => {
    const wasOpen = sidebar.classList.contains('is-open');
    sidebar.classList.toggle('is-open', open);
    backdrop.hidden = !open;
    outside.forEach((node) => node?.toggleAttribute('inert', open));
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
    if (open) sidebar.querySelector('.nav-link')?.focus();
    else if (wasOpen && MOBILE_QUERY.matches) toggle.focus();
  };

  toggle.addEventListener('click', () => setOpen(!sidebar.classList.contains('is-open')));
  backdrop.addEventListener('click', () => setOpen(false));
  // Explicit, focusable close control inside the drawer (the toggle is inert while open).
  closeButton?.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && sidebar.classList.contains('is-open')) setOpen(false);
  });
  MOBILE_QUERY.addEventListener('change', () => setOpen(false));
}

function setupLogout() {
  const button = document.getElementById('logout-button');
  button?.addEventListener('click', async () => {
    const restore = setButtonLoading(button, 'Saindo...');
    try {
      await logout();
    } catch (error) {
      restore();
      showToast(error.message, 'error');
    }
  });
}

function renderUser(user) {
  const name = displayName(user);
  const nameNode = document.getElementById('user-name');
  const avatar = document.getElementById('user-avatar');
  if (nameNode) {
    nameNode.textContent = name;
    nameNode.title = user.email;
  }
  if (avatar) avatar.textContent = name.charAt(0);
}

/** Checks the session and wires the shell. Resolves with the logged user. */
export async function initLayout() {
  setupSidebar();
  setupLogout();
  const user = await requireAuth();
  renderUser(user);
  document.body.dataset.auth = 'ok';
  return user;
}

/* ---------- Month picker ---------- */

function monthFromUrl() {
  const month = new URLSearchParams(window.location.search).get('month');
  return isValidMonth(month) ? month : currentMonth();
}

function syncUrl(month) {
  const url = new URL(window.location.href);
  url.searchParams.set('month', month);
  window.history.replaceState(null, '', url);
  // Keep the selected month while navigating between pages.
  document.querySelectorAll('[data-keep-month]').forEach((link) => {
    const target = new URL(link.href);
    target.searchParams.set('month', month);
    link.href = target.pathname + target.search;
  });
}

/**
 * Wires #month-input, #month-prev and #month-next.
 * Returns { get, set } and calls onChange(month) whenever the month changes.
 */
export function initMonthPicker(onChange) {
  const input = document.getElementById('month-input');
  const prev = document.getElementById('month-prev');
  const next = document.getElementById('month-next');
  let month = monthFromUrl();

  const apply = (value, notify = true) => {
    if (!isValidMonth(value)) {
      input.value = month;
      return;
    }
    month = value;
    input.value = month;
    input.title = formatMonthLabel(month);
    syncUrl(month);
    if (notify) onChange(month);
  };

  input.addEventListener('change', () => apply(input.value));
  prev.addEventListener('click', () => apply(shiftMonth(month, -1)));
  next.addEventListener('click', () => apply(shiftMonth(month, 1)));
  apply(month, false);

  return { get: () => month, set: (value) => apply(value) };
}
