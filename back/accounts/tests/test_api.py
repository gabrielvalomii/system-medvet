import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

CSRF_URL = reverse("accounts:csrf")
LOGIN_URL = reverse("accounts:login")
LOGOUT_URL = reverse("accounts:logout")
ME_URL = reverse("accounts:me")
GENERIC_ERROR = {"detail": "E-mail ou senha inválidos"}


def _csrf_token(client: APIClient) -> str:
    response = client.get(CSRF_URL)
    assert response.status_code == 200
    return response.cookies["csrftoken"].value


def _login(client: APIClient, email: str, password: str):
    token = _csrf_token(client)
    return client.post(
        LOGIN_URL,
        {"email": email, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )


# --- CSRF --------------------------------------------------------------------


def test_csrf_endpoint_sets_cookie(csrf_client):
    response = csrf_client.get(CSRF_URL)
    assert response.status_code == 200
    cookie = response.cookies["csrftoken"]
    assert cookie.value
    assert cookie["samesite"] == "Lax"


def test_login_requires_csrf_token(csrf_client, user, password):
    response = csrf_client.post(
        LOGIN_URL, {"email": user.email, "password": password}, format="json"
    )
    assert response.status_code == 403
    assert "_auth_user_id" not in csrf_client.session


def test_login_rejects_wrong_csrf_token(csrf_client, user, password):
    _csrf_token(csrf_client)
    response = csrf_client.post(
        LOGIN_URL,
        {"email": user.email, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN="x" * 32,
    )
    assert response.status_code == 403


# --- Login -------------------------------------------------------------------


def test_login_success_returns_user_and_session(csrf_client, user, password):
    response = _login(csrf_client, user.email, password)
    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }
    session_cookie = response.cookies["sessionid"]
    assert session_cookie["httponly"]
    assert session_cookie["samesite"] == "Lax"
    assert csrf_client.get(ME_URL).status_code == 200


def test_login_email_is_case_insensitive(csrf_client, user, password):
    response = _login(csrf_client, f"  {user.email.upper()} ", password)
    assert response.status_code == 200


def test_wrong_password_and_unknown_email_get_same_response(
    csrf_client, user, password
):
    wrong_password = _login(csrf_client, user.email, password + "x")
    unknown_email = _login(csrf_client, "naoexiste@example.com", password)
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == GENERIC_ERROR


@pytest.mark.parametrize(
    "payload",
    [{}, {"email": "invalido", "password": "x"}, {"email": "a@b.com"}],
)
def test_login_invalid_payload_returns_generic_error(csrf_client, payload):
    token = _csrf_token(csrf_client)
    response = csrf_client.post(
        LOGIN_URL, payload, format="json", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 401
    assert response.json() == GENERIC_ERROR


def test_inactive_user_cannot_login(csrf_client, user, password):
    user.is_active = False
    user.save()
    response = _login(csrf_client, user.email, password)
    assert response.status_code == 401
    assert response.json() == GENERIC_ERROR


def test_login_is_throttled_after_five_attempts(csrf_client, user, password):
    for _ in range(5):
        assert _login(csrf_client, user.email, "errada").status_code == 401
    response = _login(csrf_client, user.email, password)
    assert response.status_code == 429
    assert "detail" in response.json()
    assert "_auth_user_id" not in csrf_client.session


def test_login_rejects_get(csrf_client):
    assert csrf_client.get(LOGIN_URL).status_code == 405


# --- Me ----------------------------------------------------------------------


def test_me_requires_authentication(api_client):
    response = api_client.get(ME_URL)
    assert response.status_code in (401, 403)


def test_me_returns_logged_user(auth_client, user):
    response = auth_client.get(ME_URL)
    assert response.status_code == 200
    assert response.json()["email"] == user.email
    assert "password" not in response.json()


# --- Logout ------------------------------------------------------------------


def test_logout_ends_session(csrf_client, user, password):
    _login(csrf_client, user.email, password)
    token = csrf_client.cookies["csrftoken"].value
    response = csrf_client.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 204
    assert csrf_client.get(ME_URL).status_code in (401, 403)


def test_logout_requires_csrf(csrf_client, user, password):
    _login(csrf_client, user.email, password)
    response = csrf_client.post(LOGOUT_URL)
    assert response.status_code == 403
    assert csrf_client.get(ME_URL).status_code == 200


def test_logout_requires_authentication(api_client):
    assert api_client.post(LOGOUT_URL).status_code in (401, 403)
