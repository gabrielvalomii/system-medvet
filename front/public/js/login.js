// Login page.
import { DASHBOARD_PAGE, ensureCsrfCookie, getCurrentUser, login } from './auth.js';
import { setButtonLoading } from './ui.js';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const form = document.getElementById('login-form');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const submitButton = document.getElementById('login-button');
const formError = document.getElementById('login-error');

function setFieldError(input, message) {
  document.getElementById(`${input.id}-error`).textContent = message;
  if (message) input.setAttribute('aria-invalid', 'true');
  else input.removeAttribute('aria-invalid');
}

function validate() {
  const email = emailInput.value.trim();
  const errors = [
    [
      emailInput,
      !email ? 'Informe o e-mail.' : EMAIL_PATTERN.test(email) ? '' : 'E-mail inválido.',
    ],
    [passwordInput, passwordInput.value ? '' : 'Informe a senha.'],
  ];
  errors.forEach(([input, message]) => setFieldError(input, message));
  const firstInvalid = errors.find(([, message]) => message);
  firstInvalid?.[0].focus();
  return !firstInvalid;
}

async function submitLogin(email, password) {
  try {
    return await login(email, password);
  } catch (error) {
    // Missing/stale CSRF cookie: fetch a fresh one and retry once.
    if (!error.isCsrfFailure) throw error;
    await ensureCsrfCookie();
    return login(email, password);
  }
}

async function handleSubmit(event) {
  event.preventDefault();
  formError.textContent = '';
  if (!validate()) return;

  const restore = setButtonLoading(submitButton, 'Entrando...');
  try {
    await submitLogin(emailInput.value.trim(), passwordInput.value);
    window.location.replace(DASHBOARD_PAGE);
  } catch (error) {
    restore();
    formError.textContent = error.status === 401 ? 'E-mail ou senha inválidos.' : error.message;
    passwordInput.value = '';
    passwordInput.focus();
  }
}

async function init() {
  form.addEventListener('submit', handleSubmit);
  [emailInput, passwordInput].forEach((input) =>
    input.addEventListener('input', () => setFieldError(input, '')),
  );
  try {
    await ensureCsrfCookie();
  } catch {
    // The login request retries the CSRF cookie; connection errors show on submit.
  }
  if (await getCurrentUser()) window.location.replace(DASHBOARD_PAGE);
}

init();
