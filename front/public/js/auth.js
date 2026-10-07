// Session helpers shared by the login page and the protected pages.
import { api, ensureCsrfCookie } from './api.js';

export const DASHBOARD_PAGE = '/dashboard.html';
export const LOGIN_PAGE = '/index.html';

/** Returns the logged user; on 401/403 api.js redirects to the login page. */
export function requireAuth() {
  return api.get('/auth/me/');
}

/** Returns the logged user or null (no redirect) — used by the login page. */
export async function getCurrentUser() {
  try {
    return await api.get('/auth/me/', undefined, { redirectOnAuthError: false });
  } catch {
    return null;
  }
}

export function login(email, password) {
  return api.post('/auth/login/', { email, password }, { redirectOnAuthError: false });
}

/** Ends the session and goes to the login page. Throws if the API fails. */
export async function logout() {
  try {
    await api.post('/auth/logout/', undefined, { redirectOnAuthError: false });
  } catch (error) {
    const alreadyLoggedOut = [401, 403].includes(error.status) && !error.isCsrfFailure;
    if (!alreadyLoggedOut) throw error;
  }
  window.location.replace(LOGIN_PAGE);
}

export { ensureCsrfCookie };

export function displayName(user) {
  const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim();
  return fullName || user?.email || '';
}
