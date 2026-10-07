"""
Re-teste de QA — Tarefa 1 (correções QA-T1-01..04).

Verifica NUM_PROXIES (X-Forwarded-For forjado), rate limit do admin com CSRF,
login do admin sem diferenciar maiúsculas e ausência de regressões.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from accounts.throttling import AdminLoginThrottle

pytestmark = pytest.mark.django_db

CSRF_URL = reverse("accounts:csrf")
LOGIN_URL = reverse("accounts:login")
ADMIN_LOGIN_URL = reverse("admin:login")
ADMIN_PASSWORD = "Adm!n-2026x"
BACK_DIR = Path(settings.BASE_DIR)


def _api_login(client: APIClient, email: str, password: str, **extra):
    token = client.get(CSRF_URL).cookies["csrftoken"].value
    return client.post(
        LOGIN_URL,
        {"email": email, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=token,
        **extra,
    )


def _admin_csrf_client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    response = client.get(ADMIN_LOGIN_URL)
    assert response.status_code == 200
    return client, client.cookies["csrftoken"].value


@pytest.fixture
def superuser():
    return User.objects.create_superuser(
        email="admin@example.com", password=ADMIN_PASSWORD
    )


@pytest.fixture
def one_proxy(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}


# --- QA-T1-01 ----------------------------------------------------------------


def test_num_proxies_default_is_zero_without_env():
    """Sem NUM_PROXIES no ambiente, o padrão é 0 (ignora XFF)."""
    env = {k: v for k, v in os.environ.items() if k != "NUM_PROXIES"}
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    code = (
        "import django; django.setup();"
        "from django.conf import settings as s;"
        "print(s.REST_FRAMEWORK['NUM_PROXIES'])"
    )
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "0"


def test_spoofed_xff_prefix_is_ignored_with_one_proxy(one_proxy, user):
    """NUM_PROXIES=1 e XFF "forjado, real": o contador usa o IP real."""
    proxy = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="127.0.0.1")
    statuses = [
        _api_login(
            proxy,
            user.email,
            "errada",
            HTTP_X_FORWARDED_FOR=f"6.6.6.{i}, 200.10.10.10",
        ).status_code
        for i in range(8)
    ]
    assert statuses == [401] * 5 + [429] * 3


def test_spoofed_multi_hop_xff_is_ignored_with_one_proxy(one_proxy, user):
    proxy = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="127.0.0.1")
    statuses = [
        _api_login(
            proxy,
            user.email,
            "errada",
            HTTP_X_FORWARDED_FOR=f"1.1.1.{i},2.2.2.{i} ,  200.10.10.11",
        ).status_code
        for i in range(6)
    ]
    assert statuses[-1] == 429


def test_one_proxy_without_xff_falls_back_to_remote_addr(one_proxy, user):
    client = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="10.9.9.9")
    statuses = [_api_login(client, user.email, "errada").status_code for _ in range(6)]
    assert statuses == [401] * 5 + [429]


def test_zero_proxies_ignores_any_xff_variation(user):
    client = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="10.0.0.50")
    statuses = [
        _api_login(
            client, user.email, "errada", HTTP_X_FORWARDED_FOR=f"7.7.7.{i}, 8.8.8.{i}"
        ).status_code
        for i in range(6)
    ]
    assert statuses == [401] * 5 + [429]


def test_api_429_does_not_create_session_even_with_right_password(one_proxy, user):
    proxy = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="127.0.0.1")
    for i in range(5):
        _api_login(
            proxy, user.email, "errada", HTTP_X_FORWARDED_FOR=f"9.{i}.0.1, 200.3.3.3"
        )
    response = _api_login(
        proxy, user.email, DEFAULT_PASSWORD, HTTP_X_FORWARDED_FOR="200.3.3.3"
    )
    assert response.status_code == 429
    assert "sessionid" not in response.cookies


# --- QA-T1-02 ----------------------------------------------------------------


def test_admin_login_without_csrf_is_rejected_and_not_counted(superuser):
    client = Client(enforce_csrf_checks=True)
    for _ in range(8):
        response = client.post(
            ADMIN_LOGIN_URL, {"username": superuser.email, "password": "errada"}
        )
        assert response.status_code == 403
    # Falhas de CSRF não consumiram o balde: login com CSRF válido funciona.
    client, token = _admin_csrf_client()
    response = client.post(
        ADMIN_LOGIN_URL,
        {
            "username": superuser.email,
            "password": ADMIN_PASSWORD,
            "csrfmiddlewaretoken": token,
        },
    )
    assert response.status_code == 302


def test_admin_login_with_csrf_is_throttled(superuser):
    client, token = _admin_csrf_client()
    data = {"username": superuser.email, "csrfmiddlewaretoken": token}
    for _ in range(5):
        response = client.post(ADMIN_LOGIN_URL, {**data, "password": "errada"})
        assert response.status_code == 200
    response = client.post(ADMIN_LOGIN_URL, {**data, "password": ADMIN_PASSWORD})
    assert response.status_code == 429
    assert int(response["Retry-After"]) > 0
    assert "sessionid" not in response.cookies


def test_admin_throttle_cannot_be_bypassed_with_xff(client, superuser):
    for i in range(5):
        client.post(
            ADMIN_LOGIN_URL,
            {"username": superuser.email, "password": "errada"},
            HTTP_X_FORWARDED_FOR=f"5.5.5.{i}",
        )
    response = client.post(
        ADMIN_LOGIN_URL,
        {"username": superuser.email, "password": ADMIN_PASSWORD},
        HTTP_X_FORWARDED_FOR="5.5.5.99",
    )
    assert response.status_code == 429


def test_admin_throttle_uses_real_ip_with_one_proxy(one_proxy, client, superuser):
    for i in range(5):
        client.post(
            ADMIN_LOGIN_URL,
            {"username": superuser.email, "password": "errada"},
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR=f"6.6.6.{i}, 200.20.20.20",
        )
    blocked = client.post(
        ADMIN_LOGIN_URL,
        {"username": superuser.email, "password": ADMIN_PASSWORD},
        REMOTE_ADDR="127.0.0.1",
        HTTP_X_FORWARDED_FOR="1.2.3.4, 200.20.20.20",
    )
    assert blocked.status_code == 429
    other = client.post(
        ADMIN_LOGIN_URL,
        {"username": superuser.email, "password": ADMIN_PASSWORD},
        REMOTE_ADDR="127.0.0.1",
        HTTP_X_FORWARDED_FOR="200.30.30.30",
    )
    assert other.status_code == 302


def test_admin_throttle_releases_after_window(client, superuser, monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(AdminLoginThrottle, "timer", lambda self: now[0])
    for _ in range(5):
        client.post(ADMIN_LOGIN_URL, {"username": superuser.email, "password": "x"})
    assert (
        client.post(
            ADMIN_LOGIN_URL, {"username": superuser.email, "password": ADMIN_PASSWORD}
        ).status_code
        == 429
    )
    now[0] += 61
    response = client.post(
        ADMIN_LOGIN_URL, {"username": superuser.email, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 302


def test_admin_and_api_throttles_are_independent(client, superuser, user):
    for _ in range(6):
        client.post(ADMIN_LOGIN_URL, {"username": superuser.email, "password": "x"})
    api = APIClient(enforce_csrf_checks=True)
    assert _api_login(api, user.email, DEFAULT_PASSWORD).status_code == 200


def test_admin_redirects_to_overridden_login(client):
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302
    assert response["Location"].startswith(ADMIN_LOGIN_URL)


def test_non_staff_cannot_enter_admin(client):
    u = UserFactory()
    response = client.post(
        ADMIN_LOGIN_URL, {"username": u.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


# --- QA-T1-03 ----------------------------------------------------------------


def test_admin_login_mixed_case_with_csrf(superuser):
    client, token = _admin_csrf_client()
    response = client.post(
        ADMIN_LOGIN_URL,
        {
            "username": "ADMIN@example.com",
            "password": ADMIN_PASSWORD,
            "csrfmiddlewaretoken": token,
        },
    )
    assert response.status_code == 302


def test_mixed_case_login_still_rejects_wrong_password(superuser):
    api = APIClient(enforce_csrf_checks=True)
    response = _api_login(api, "Admin@Example.com", "errada")
    assert response.status_code == 401


def test_case_duplicate_email_cannot_be_created():
    """QA-T1-05 (corrigido): duplicado por caixa é barrado em todos os caminhos."""
    User.objects.create_user(email="dup@example.com", password=DEFAULT_PASSWORD)
    # save() direto normaliza e bate no unique.
    with pytest.raises(IntegrityError), transaction.atomic():
        raw = User(email="DUP@example.com")
        raw.set_password(DEFAULT_PASSWORD)
        raw.save()
    # bulk_create e update() não passam por save(): a UniqueConstraint(Lower)
    # do banco é quem barra.
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(email="DUP@example.com")])
    other = UserFactory(email="other@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=other.pk).update(email="Dup@Example.com")
    assert User.objects.filter(email__iexact="dup@example.com").count() == 1


def test_save_normalizes_email():
    u = UserFactory(email="  Mixed.Case@Example.COM ")
    u.refresh_from_db()
    assert u.email == "mixed.case@example.com"
    u.email = "OUTRO@Example.com"
    u.save()
    u.refresh_from_db()
    assert u.email == "outro@example.com"


def _legacy_duplicates(*emails: str) -> None:
    """Simula banco legado: remove o índice Lower(email) (DDL transacional no
    SQLite, desfeito no rollback do teste) e grava e-mails sem normalizar."""
    with connection.cursor() as cursor:
        cursor.execute('DROP INDEX "accounts_user_email_ci_unique"')
    for i, email in enumerate(emails):
        u = UserFactory(email=f"legacy{i}@example.com")
        User.objects.filter(pk=u.pk).update(email=email)


@pytest.mark.parametrize("typed", ["dup@example.com", " Dup@Example.COM "])
def test_legacy_case_duplicates_login_uses_exact_normalized_email(typed):
    _legacy_duplicates("dup@example.com", "DUP@example.com")
    api = APIClient(enforce_csrf_checks=True, raise_request_exception=False)
    response = _api_login(api, typed, DEFAULT_PASSWORD)
    assert response.status_code == 200
    assert response.json()["email"] == "dup@example.com"


def test_legacy_case_duplicates_without_exact_match_return_401_not_500():
    _legacy_duplicates("Dup@example.com", "DUP@example.com")
    api = APIClient(enforce_csrf_checks=True, raise_request_exception=False)
    response = _api_login(api, "dup@example.com", DEFAULT_PASSWORD)
    assert response.status_code == 401


def test_legacy_case_duplicates_admin_login_does_not_crash():
    _legacy_duplicates("root@example.com", "ROOT@example.com")
    User.objects.filter(email="root@example.com").update(
        is_staff=True, is_superuser=True
    )
    client = Client(raise_request_exception=False)
    response = client.post(
        ADMIN_LOGIN_URL,
        {"username": "Root@Example.com", "password": DEFAULT_PASSWORD},
    )
    assert response.status_code == 302


# --- QA-T1-04 ----------------------------------------------------------------


def test_cache_backend_configurable_via_env(tmp_path):
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings"}
    env["CACHE_BACKEND"] = "django.core.cache.backends.filebased.FileBasedCache"
    env["CACHE_LOCATION"] = str(tmp_path)
    code = (
        "import django; django.setup();"
        "from django.core.cache import caches; cache = caches['default'];"
        "cache.set('k', 1); print(type(cache).__name__, cache.get('k'))"
    )
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "FileBasedCache 1"


def test_env_example_documents_new_settings():
    text = (BACK_DIR / ".env.example").read_text(encoding="utf-8")
    for key in ("NUM_PROXIES", "ADMIN_LOGIN_THROTTLE_RATE", "CACHE_BACKEND"):
        assert f"{key}=" in text
