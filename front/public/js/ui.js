// Shared UI helpers: palette, DOM builders, toasts, confirm dialog, states.

/**
 * Slice palette — the ONLY place where chart colors are defined.
 * Expenses use warm tones; incomes use cool/green tones.
 */
export const PALETTE = {
  expenses: [
    '#ff6b6b',
    '#f5b84b',
    '#ff8c42',
    '#e8590c',
    '#f06595',
    '#ffd43b',
    '#e03131',
    '#ffa8a8',
    '#d9480f',
    '#fcc2d7',
    '#e67700',
    '#d6336c',
    '#ffc078',
  ],
  incomes: [
    '#2ecc8f',
    '#6c8cff',
    '#3bc9db',
    '#94d82d',
    '#4dabf7',
    '#b197fc',
    '#0ca678',
    '#91a7ff',
    '#99e9f2',
  ],
};

/** Stable color for a category, based on its position in /api/categories/. */
export function colorFor(kind, index) {
  const colors = PALETTE[kind];
  return colors[((index % colors.length) + colors.length) % colors.length];
}

/** Reads a token from css/variables.css (e.g. cssVar('--surface')). */
export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Small createElement helper. Text is always set with textContent (XSS safe). */
export function el(tag, { className, text, attrs } = {}, children = []) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  for (const [name, value] of Object.entries(attrs ?? {})) {
    if (value !== undefined && value !== null && value !== false) node.setAttribute(name, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

/** Puts a button in the loading state (spinner + text) and returns a restore function. */
export function setButtonLoading(button, loadingText) {
  const originalText = button.textContent;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  button.textContent = loadingText;
  return () => {
    button.disabled = false;
    button.removeAttribute('aria-busy');
    button.textContent = originalText;
  };
}

/* ---------- States ---------- */

export function loadingState(message = 'Carregando...') {
  return el('div', { className: 'state', attrs: { role: 'status' } }, [
    el('span', { className: 'spinner', attrs: { 'aria-hidden': 'true' } }),
    el('p', { text: message }),
  ]);
}

export function emptyState(message) {
  return el('div', { className: 'state' }, [el('p', { text: message })]);
}

export function errorState(message, onRetry) {
  const retry = onRetry
    ? el('button', { className: 'btn btn-secondary btn-sm', text: 'Tentar novamente' })
    : null;
  retry?.addEventListener('click', onRetry);
  return el('div', { className: 'state is-error', attrs: { role: 'alert' } }, [
    el('p', { text: message }),
    retry,
  ]);
}

/* ---------- Toasts ---------- */

const TOAST_DURATION = 4500;
let toastRegion;

function getToastRegion() {
  if (!toastRegion) {
    toastRegion = el('div', {
      className: 'toast-region',
      attrs: { 'aria-live': 'polite', 'aria-atomic': 'false' },
    });
    document.body.append(toastRegion);
  }
  return toastRegion;
}

/** Shows a toast. type: 'success' | 'error' | 'info'. */
export function showToast(message, type = 'info') {
  const close = el('button', {
    className: 'btn btn-ghost btn-sm',
    text: '×',
    attrs: { type: 'button', 'aria-label': 'Fechar aviso' },
  });
  const toast = el(
    'div',
    { className: `toast is-${type}`, attrs: { role: type === 'error' ? 'alert' : 'status' } },
    [el('p', { text: message }), close],
  );
  const dismiss = () => toast.remove();
  close.addEventListener('click', dismiss);
  setTimeout(dismiss, type === 'error' ? TOAST_DURATION * 1.5 : TOAST_DURATION);
  getToastRegion().append(toast);
}

/* ---------- Confirm dialog ---------- */

/** Accessible confirmation (native <dialog>). Resolves true when confirmed. */
export function confirmDialog({ title, message, confirmText = 'Confirmar', danger = false }) {
  return new Promise((resolve) => {
    const titleId = `dialog-title-${Date.now()}`;
    const cancel = el('button', {
      className: 'btn btn-secondary',
      text: 'Cancelar',
      attrs: { type: 'button' },
    });
    const confirm = el('button', {
      className: `btn ${danger ? 'btn-danger' : 'btn-primary'}`,
      text: confirmText,
      attrs: { type: 'button' },
    });
    const dialog = el('dialog', { className: 'dialog', attrs: { 'aria-labelledby': titleId } }, [
      el('div', { className: 'dialog-body' }, [
        el('h2', { text: title, attrs: { id: titleId } }),
        el('p', { text: message }),
        el('div', { className: 'dialog-actions' }, [cancel, confirm]),
      ]),
    ]);

    let confirmed = false;
    cancel.addEventListener('click', () => dialog.close());
    confirm.addEventListener('click', () => {
      confirmed = true;
      dialog.close();
    });
    dialog.addEventListener('close', () => {
      dialog.remove();
      resolve(confirmed);
    });

    document.body.append(dialog);
    dialog.showModal();
    cancel.focus(); // safest default for destructive actions
  });
}
