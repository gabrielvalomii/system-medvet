"""
Testes adicionais de QA — Tarefa 1 (configuração e autenticação).

Cobrem CSRF/Origin, enumeração de usuários, rate limit, cookies, sessão,
logout, usuário inativo, hash de senha, admin por e-mail e configurações
de produção. Testes marcados com ``BUG QA-T1-xx`` documentam defeitos
abertos no relatório ``docs/qa/2026-10-06-tarefa1-auth.md``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.db import connection
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from accounts.tests.factories import DEFAULT_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db

CSRF_URL = reverse("accounts:csrf")
LOGIN_URL = reverse("accounts:login")
LOGOUT_URL = reverse("accounts:logout")
ME_URL = reverse("accounts:me")
GENERIC_ERROR = {"detail": "E-mail ou senha inválidos"}
BACK_DIR = Path(settings.BASE_DIR)


def _token(client: APIClient) -> str:
    response = client.get(CSRF_URL)
    assert response.status_code == 200
    return response.cookies["csrftoken"].value


def _post_login(client: APIClient, email: str, password: str, **extra):
    token = _token(client)
    return client.post(
        LOGIN_URL,
        {"email": email, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=token,
        **extra,
    )


@pytest.fixture
def browser() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


# --- CSRF / Origin -----------------------------------------------------------


def test_login_without_csrf_does_not_create_session(browser, user):
    _token(browser)  # tem o cookie, mas não envia o header
    response = browser.post(
        LOGIN_URL,
        {"email": user.email, "password": DEFAULT_PASSWORD},
        format="json",
    )
    assert response.status_code == 403
    assert "sessionid" not in response.cookies
    assert browser.get(ME_URL).status_code == 403


def test_login_with_token_from_other_client_is_rejected(browser, user):
    other_token = _token(APIClient(enforce_csrf_checks=True))
    _token(browser)
    response = browser.post(
        LOGIN_URL,
        {"email": user.email, "password": DEFAULT_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=other_token,
    )
    assert response.status_code == 403


def test_login_rejects_untrusted_origin(browser, user):
    response = _post_login(
        browser, user.email, DEFAULT_PASSWORD, HTTP_ORIGIN="http://evil.example"
    )
    assert response.status_code == 403
    assert "sessionid" not in response.cookies


def test_login_accepts_front_trusted_origin(browser, user):
    response = _post_login(
        browser, user.email, DEFAULT_PASSWORD, HTTP_ORIGIN="http://localhost:3000"
    )
    assert response.status_code == 200


def test_csrf_failure_is_not_counted_by_throttle(browser, user):
    for _ in range(10):
        browser.post(LOGIN_URL, {"email": user.email, "password": "x"}, format="json")
    assert _post_login(browser, user.email, DEFAULT_PASSWORD).status_code == 200


# --- Enumeração de usuários --------------------------------------------------


def test_wrong_password_and_unknown_email_are_byte_identical(browser, user):
    wrong = _post_login(browser, user.email, "senha-errada")
    unknown = _post_login(browser, "ninguem@example.com", "senha-errada")
    inactive_user = UserFactory(is_active=False)
    inactive = _post_login(browser, inactive_user.email, DEFAULT_PASSWORD)
    for response in (wrong, unknown, inactive):
        assert response.status_code == 401
        assert response.json() == GENERIC_ERROR
        assert "sessionid" not in response.cookies
    assert wrong.content == unknown.content == inactive.content
    assert wrong["Content-Type"] == unknown["Content-Type"]


@pytest.mark.parametrize(
    "email",
    [
        "' OR 1=1 --@example.com",
        "a" * 300 + "@example.com",
        "<script>@example.com",
        None,
        123,
    ],
)
def test_malformed_email_gets_generic_401(browser, email):
    token = _token(browser)
    response = browser.post(
        LOGIN_URL,
        {"email": email, "password": "x"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 401
    assert response.json() == GENERIC_ERROR


def test_password_over_max_length_gets_generic_401(browser, user):
    response = _post_login(browser, user.email, "x" * 5000)
    assert response.status_code == 401
    assert response.json() == GENERIC_ERROR


def test_login_ignores_privilege_fields_in_payload(browser, user):
    token = _token(browser)
    response = browser.post(
        LOGIN_URL,
        {
            "email": user.email,
            "password": DEFAULT_PASSWORD,
            "is_staff": True,
            "is_superuser": True,
        },
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert not user.is_staff
    assert not user.is_superuser


# --- Rate limit --------------------------------------------------------------


def test_sixth_login_in_a_minute_returns_429_with_retry_after(browser, user):
    for _ in range(5):
        assert _post_login(browser, user.email, "errada").status_code == 401
    response = _post_login(browser, user.email, DEFAULT_PASSWORD)
    assert response.status_code == 429
    assert "Retry-After" in response
    assert "sessionid" not in response.cookies


def test_successful_logins_also_count_for_throttle(browser, user):
    for _ in range(5):
        assert _post_login(browser, user.email, DEFAULT_PASSWORD).status_code == 200
    assert _post_login(browser, user.email, DEFAULT_PASSWORD).status_code == 429


def test_throttle_is_per_ip(user):
    attacker = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="10.0.0.1")
    victim = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="10.0.0.2")
    for _ in range(6):
        _post_login(attacker, user.email, "errada")
    assert _post_login(attacker, user.email, "errada").status_code == 429
    assert _post_login(victim, user.email, DEFAULT_PASSWORD).status_code == 200


def test_throttle_cannot_be_bypassed_with_spoofed_x_forwarded_for(user):
    """BUG QA-T1-01: X-Forwarded-For forjado gera um balde novo por requisição."""
    client = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="10.0.0.1")
    statuses = [
        _post_login(
            client, user.email, "errada", HTTP_X_FORWARDED_FOR=f"1.2.3.{i}"
        ).status_code
        for i in range(10)
    ]
    assert 429 in statuses, f"rate limit contornado via X-Forwarded-For: {statuses}"


# --- Sessão e cookies --------------------------------------------------------


def test_cookie_flags(browser, user):
    csrf_cookie = browser.get(CSRF_URL).cookies["csrftoken"]
    assert csrf_cookie["samesite"] == "Lax"
    assert not csrf_cookie["httponly"]  # o front precisa ler o token
    response = _post_login(browser, user.email, DEFAULT_PASSWORD)
    session_cookie = response.cookies["sessionid"]
    assert session_cookie["httponly"]
    assert session_cookie["samesite"] == "Lax"


def test_login_rotates_session_key(browser, user):
    session = browser.session
    session["pre_login"] = True
    session.save()
    old_key = session.session_key
    browser.cookies[settings.SESSION_COOKIE_NAME] = old_key
    assert _post_login(browser, user.email, DEFAULT_PASSWORD).status_code == 200
    assert browser.cookies[settings.SESSION_COOKIE_NAME].value != old_key


def test_login_rotates_csrf_token(browser, user):
    old_token = _token(browser)
    browser.post(
        LOGIN_URL,
        {"email": user.email, "password": DEFAULT_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=old_token,
    )
    # Após o login o token antigo deixa de valer; o front deve reler o cookie.
    assert browser.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=old_token).status_code == 403
    new_token = browser.cookies["csrftoken"].value
    assert browser.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=new_token).status_code == 204


def test_session_invalidated_when_user_deactivated(browser, user):
    _post_login(browser, user.email, DEFAULT_PASSWORD)
    user.is_active = False
    user.save()
    assert browser.get(ME_URL).status_code == 403


def test_session_invalidated_when_password_changes(browser, user):
    _post_login(browser, user.email, DEFAULT_PASSWORD)
    user.set_password("Outra-S3nha!2026")
    user.save()
    assert browser.get(ME_URL).status_code == 403


# --- Logout ------------------------------------------------------------------


def test_logout_flow_and_old_session_cookie_is_dead(browser, user):
    _post_login(browser, user.email, DEFAULT_PASSWORD)
    old_session = browser.cookies["sessionid"].value

    assert browser.post(LOGOUT_URL).status_code == 403  # sem CSRF
    assert browser.get(ME_URL).status_code == 200

    token = browser.cookies["csrftoken"].value
    response = browser.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 204
    assert response.cookies["sessionid"].value == ""
    assert browser.get(ME_URL).status_code == 403

    replay = APIClient()
    replay.cookies["sessionid"] = old_session
    assert replay.get(ME_URL).status_code == 403


def test_logout_rejects_get(browser, user):
    _post_login(browser, user.email, DEFAULT_PASSWORD)
    assert browser.get(LOGOUT_URL).status_code == 405
    assert browser.get(ME_URL).status_code == 200


def test_unauthenticated_errors_use_detail_format(api_client):
    response = api_client.get(ME_URL)
    assert response.status_code == 403
    assert set(response.json()) == {"detail"}


# --- Senha nunca exposta -----------------------------------------------------


def test_no_response_leaks_password_or_hash(browser, user):
    responses = [
        _post_login(browser, user.email, DEFAULT_PASSWORD),
        browser.get(ME_URL),
    ]
    user.refresh_from_db()
    for response in responses:
        body = response.content.decode()
        assert "password" not in body
        assert DEFAULT_PASSWORD not in body
        assert user.password not in body
    assert set(responses[0].json()) == {"id", "email", "first_name", "last_name"}


def test_password_is_stored_as_pbkdf2_hash(user):
    with connection.cursor() as cursor:
        cursor.execute("SELECT password FROM accounts_user WHERE id = %s", [user.pk])
        (stored,) = cursor.fetchone()
    assert stored.startswith(("pbkdf2_sha256$", "argon2"))
    assert DEFAULT_PASSWORD not in stored


# --- Modelo / admin ----------------------------------------------------------


def test_full_clean_normalizes_email_and_blocks_case_duplicate(user):
    from django.core.exceptions import ValidationError

    dup = User(email=user.email.upper(), password="x")
    with pytest.raises(ValidationError):
        dup.full_clean()
    assert dup.email == user.email


def test_admin_login_by_email(client):
    User.objects.create_superuser(email="admin@example.com", password="Adm!n-2026x")
    response = client.post(
        reverse("admin:login"),
        {"username": "admin@example.com", "password": "Adm!n-2026x"},
    )
    assert response.status_code == 302
    assert client.get(reverse("admin:index")).status_code == 200


def test_admin_add_rejects_case_insensitive_duplicate(client):
    admin = User.objects.create_superuser(email="admin@example.com", password="x")
    client.force_login(admin)
    UserFactory(email="dup@example.com")
    response = client.post(
        reverse("admin:accounts_user_add"),
        {
            "email": "DUP@Example.com",
            "usable_password": "true",
            "password1": DEFAULT_PASSWORD,
            "password2": DEFAULT_PASSWORD,
        },
    )
    assert response.status_code == 200  # formulário reexibido com erro
    assert User.objects.filter(email__iexact="dup@example.com").count() == 1


def test_admin_add_enforces_password_validators(client):
    admin = User.objects.create_superuser(email="admin@example.com", password="x")
    client.force_login(admin)
    response = client.post(
        reverse("admin:accounts_user_add"),
        {
            "email": "fraca@example.com",
            "usable_password": "true",
            "password1": "12345678",
            "password2": "12345678",
        },
    )
    assert response.status_code == 200
    assert not User.objects.filter(email="fraca@example.com").exists()


# --- Configurações -----------------------------------------------------------


def test_security_settings():
    assert "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert len(settings.AUTH_PASSWORD_VALIDATORS) == 4
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]
    assert settings.PASSWORD_HASHERS[0].endswith(
        ("PBKDF2PasswordHasher", "Argon2PasswordHasher")
    )


def _settings_in_subprocess(env_overrides: dict) -> dict:
    code = (
        "import json, django; from django.conf import settings as s; "
        "print(json.dumps({k: getattr(s, k, None) for k in ["
        "'DEBUG','SESSION_COOKIE_SECURE','CSRF_COOKIE_SECURE',"
        "'SECURE_SSL_REDIRECT','SECURE_HSTS_SECONDS']}))"
    )
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", **env_overrides}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_production_settings_enable_secure_cookies_and_hsts():
    values = _settings_in_subprocess({"DEBUG": "False", "SECRET_KEY": "x" * 50})
    assert values["DEBUG"] is False
    assert values["SESSION_COOKIE_SECURE"] is True
    assert values["CSRF_COOKIE_SECURE"] is True
    assert values["SECURE_SSL_REDIRECT"] is True
    assert values["SECURE_HSTS_SECONDS"] >= 31536000


def test_settings_have_no_hardcoded_secret():
    source = (BACK_DIR / "config" / "settings.py").read_text(encoding="utf-8")
    assert 'SECRET_KEY = config("SECRET_KEY")' in source
    assert "django-insecure" not in source


def test_env_is_gitignored_and_example_exists():
    gitignore = (BACK_DIR.parent / ".gitignore").read_text(encoding="utf-8")
    for entry in (
        "back/venv/",
        "back/.env",
        "front/node_modules/",
        "front/.env",
        "__pycache__/",
        ".coverage",
        "playwright-report/",
    ):
        assert entry in gitignore.splitlines(), entry
    example = (BACK_DIR / ".env.example").read_text(encoding="utf-8")
    for key in ("SECRET_KEY", "DEBUG", "ALLOWED_HOSTS"):
        assert f"{key}=" in example


def test_admin_login_is_rate_limited(client):
    """BUG QA-T1-02: /admin/login/ não tem rate limit (força bruta no superusuário)."""
    User.objects.create_superuser(email="admin@example.com", password="Adm!n-2026x")
    for _ in range(10):
        client.post(
            reverse("admin:login"),
            {"username": "admin@example.com", "password": "errada"},
        )
    response = client.post(
        reverse("admin:login"),
        {"username": "admin@example.com", "password": "Adm!n-2026x"},
    )
    assert response.status_code in (
        403,
        429,
    ), "11ª tentativa no admin foi aceita: sem rate limit"
