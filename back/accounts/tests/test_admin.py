import pytest
from django.urls import reverse

from accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client_logged(client):
    admin = User.objects.create_superuser(email="admin@example.com", password="x")
    client.force_login(admin)
    return client


def test_admin_user_changelist(admin_client_logged):
    response = admin_client_logged.get(reverse("admin:accounts_user_changelist"))
    assert response.status_code == 200


def test_admin_user_add_creates_user(admin_client_logged):
    response = admin_client_logged.post(
        reverse("admin:accounts_user_add"),
        {
            "email": "Novo@Example.com",
            "usable_password": "true",
            "password1": "S3nha-Forte!2026",
            "password2": "S3nha-Forte!2026",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(email="novo@example.com")
    assert user.check_password("S3nha-Forte!2026")


def test_admin_user_change_page(admin_client_logged):
    user = User.objects.create_user(email="x@example.com", password="x")
    url = reverse("admin:accounts_user_change", args=[user.pk])
    assert admin_client_logged.get(url).status_code == 200
