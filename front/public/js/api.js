// Single entry point for every API call (fetch wrapper).

const LOGIN_PAGE = '/index.html';
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

const STATUS_MESSAGES = {
  0: 'Não foi possível conectar ao servidor. Verifique sua conexão.',
  403: 'Você não tem permissão para esta ação.',
  404: 'Registro não encontrado.',
  429: 'Muitas tentativas. Aguarde um minuto e tente novamente.',
  500: 'Erro interno no servidor. Tente novamente em instantes.',
  502: 'Servidor da API indisponível. Tente novamente em instantes.',
  503: 'Servidor da API indisponível. Tente novamente em instantes.',
  504: 'O servidor demorou para responder. Tente novamente.',
};
const DEFAULT_MESSAGE = 'Não foi possível concluir a operação.';
const CSRF_MESSAGE = 'Sua sessão de segurança expirou. Recarregue a página e tente novamente.';

/**
 * CSRF failures come either from DRF ({detail: "CSRF Failed: ..."}) or from
 * Django's CsrfViewMiddleware (HTML page, no JSON). A 403 for a missing
 * session is always JSON from DRF.
 */
function isCsrfError(status, data) {
  if (status !== 403) return false;
  return data === null || /csrf/i.test(data?.detail ?? '');
}

export class ApiError extends Error {
  constructor(status, data, message) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }

  /** Field errors in DRF format: { field: ["msg"] } -> { field: "msg" }. */
  get fieldErrors() {
    const errors = {};
    if (!this.data || typeof this.data !== 'object' || Array.isArray(this.data)) return errors;
    for (const [field, messages] of Object.entries(this.data)) {
      if (field === 'detail') continue;
      errors[field] = Array.isArray(messages) ? messages.join(' ') : String(messages);
    }
    return errors;
  }

  get isCsrfFailure() {
    return isCsrfError(this.status, this.data);
  }
}

/** Reads the cookie on every call: Django rotates csrftoken after login. */
function readCookie(name) {
  const prefix = `${name}=`;
  const entry = document.cookie.split('; ').find((item) => item.startsWith(prefix));
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : '';
}

function buildUrl(path, query) {
  const url = new URL(`/api${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) url.searchParams.set(key, value);
  }
  return url;
}

function buildHeaders(method, hasBody) {
  const headers = { Accept: 'application/json' };
  if (hasBody) headers['Content-Type'] = 'application/json';
  if (!SAFE_METHODS.has(method)) {
    const token = readCookie('csrftoken');
    if (token) headers['X-CSRFToken'] = token;
  }
  return headers;
}

async function parseBody(response) {
  if (response.status === 204) return null;
  const type = response.headers.get('Content-Type') ?? '';
  if (!type.includes('application/json')) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function errorMessage(status, data) {
  if (isCsrfError(status, data)) return CSRF_MESSAGE;
  if (status === 429) return STATUS_MESSAGES[429];
  if (typeof data?.detail === 'string' && status < 500) return data.detail;
  if (Array.isArray(data?.non_field_errors)) return data.non_field_errors.join(' ');
  return STATUS_MESSAGES[status] ?? DEFAULT_MESSAGE;
}

function isSessionError(status, data) {
  if (status === 401) return true;
  return status === 403 && !isCsrfError(status, data);
}

function redirectToLogin() {
  window.location.replace(LOGIN_PAGE);
  // Never settles: the page is leaving, so callers must not render an error.
  return new Promise(() => {});
}

/**
 * Performs a request to `/api{path}`.
 * Options: method, body (JSON), query (object), redirectOnAuthError (default true).
 */
export async function request(path, options = {}) {
  const { method = 'GET', body, query, redirectOnAuthError = true } = options;
  const hasBody = body !== undefined;

  let response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers: buildHeaders(method, hasBody),
      body: hasBody ? JSON.stringify(body) : undefined,
      credentials: 'same-origin',
    });
  } catch {
    throw new ApiError(0, null, STATUS_MESSAGES[0]);
  }

  const data = await parseBody(response);
  if (response.ok) return data;

  if (redirectOnAuthError && isSessionError(response.status, data)) return redirectToLogin();
  throw new ApiError(response.status, data, errorMessage(response.status, data));
}

export const api = {
  get: (path, query, options) => request(path, { ...options, query }),
  post: (path, body, options) => request(path, { ...options, method: 'POST', body }),
  put: (path, body, options) => request(path, { ...options, method: 'PUT', body }),
  delete: (path, options) => request(path, { ...options, method: 'DELETE' }),
};

/** Ensures the csrftoken cookie exists (needed before login). */
export function ensureCsrfCookie() {
  return api.get('/auth/csrf/', undefined, { redirectOnAuthError: false });
}
