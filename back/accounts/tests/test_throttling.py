import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from accounts.tests.factories import DEFAULT_PASSWORD
from accounts.throttling import ADMIN_THROTTLED_MESSAGE

pytestmark = pytest.mark.django_db

CSRF_URL = reverse("accounts:csrf")
LOGIN_URL = reverse("accounts:login")
ADMIN_LOGIN_URL = reverse("admin:login")
ADMIN_PASSWORD = "Adm!n-2026x"


def _api_login(client: APIClient, email: str, password: str, **extra):
    token = client.get(CSRF_URL).cookies["csrftoken"].value
    return client.post(
        LOGIN_URL,
        {"email": email, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=token,
        **extra,
    )


@pytest.fixture
def superuser():
    return User.objects.create_superuser(
        email="admin@example.com", password=ADMIN_PASSWORD
    )


# --- NUM_PROXIES (QA-T1-01) -------------------------------------------------


def test_default_ignores_x_forwarded_for(user):
    client = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="10.0.0.9")
    statuses = [
        _api_login(
            client, user.email, "errada", HTTP_X_FORWARDED_FOR=f"9.9.9.{i}"
        ).status_code
        for i in range(6)
    ]
    assert statuses == [401] * 5 + [429]


def test_behind_one_proxy_uses_client_ip_from_x_forwarded_for(settings, user):
    """Atrás do Express (NUM_PROXIES=1) cada cliente real tem o seu balde."""
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    proxy = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="127.0.0.1")
    for _ in range(5):
        response = _api_login(
            proxy, user.email, "errada", HTTP_X_FORWARDED_FOR="200.1.1.1"
        )
        assert response.status_code == 401
    blocked = _api_login(proxy, user.email, "errada", HTTP_X_FORWARDED_FOR="200.1.1.1")
    assert blocked.status_code == 429
    # Outro cliente atrás do mesmo proxy não é afetado.
    other = _api_login(proxy, user.email, "errada", HTTP_X_FORWARDED_FOR="200.2.2.2")
    assert other.status_code == 401
    # Prefixo forjado pelo cliente é ignorado: vale o IP anexado pelo proxy.
    spoofed = _api_login(
        proxy, user.email, "errada", HTTP_X_FORWARDED_FOR="1.2.3.4, 200.1.1.1"
    )
    assert spoofed.status_code == 429


# --- Admin (QA-T1-02 / QA-T1-03) --------------------------------------------


def test_admin_login_blocks_sixth_attempt(client, superuser):
    for _ in range(5):
        response = client.post(
            ADMIN_LOGIN_URL, {"username": superuser.email, "password": "errada"}
        )
        assert response.status_code == 200  # formulário com erro
    response = client.post(
        ADMIN_LOGIN_URL, {"username": superuser.email, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 429
    assert response["Retry-After"]
    assert response.content.decode() == ADMIN_THROTTLED_MESSAGE
    assert "_auth_user_id" not in client.session


def test_admin_login_get_is_not_throttled(client):
    for _ in range(10):
        assert client.get(ADMIN_LOGIN_URL).status_code == 200


def test_admin_login_throttle_is_per_ip(client, superuser):
    for _ in range(6):
        client.post(
            ADMIN_LOGIN_URL,
            {"username": superuser.email, "password": "errada"},
            REMOTE_ADDR="10.0.0.1",
        )
    response = client.post(
        ADMIN_LOGIN_URL,
        {"username": superuser.email, "password": ADMIN_PASSWORD},
        REMOTE_ADDR="10.0.0.2",
    )
    assert response.status_code == 302


def test_admin_login_is_case_insensitive(client, superuser):
    response = client.post(
        ADMIN_LOGIN_URL, {"username": " Admin@Example.COM ", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 302
    assert client.get(reverse("admin:index")).status_code == 200


def test_api_login_with_mixed_case_email(user):
    client = APIClient(enforce_csrf_checks=True)
    response = _api_login(client, user.email.upper(), DEFAULT_PASSWORD)
    assert response.status_code == 200


def test_get_by_natural_key_is_case_insensitive(user):
    assert User.objects.get_by_natural_key(user.email.upper()) == user
    with pytest.raises(User.DoesNotExist):
        User.objects.get_by_natural_key("ninguem@example.com")
