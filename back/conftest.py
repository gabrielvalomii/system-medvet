import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.tests.factories import DEFAULT_PASSWORD, UserFactory


@pytest.fixture(autouse=True)
def _clear_cache():
    """Zera o cache (usado pelo throttle) entre os testes."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _no_trusted_proxies(settings):
    """Testes usam NUM_PROXIES=0 (padrão), independente do .env local."""
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}


@pytest.fixture
def password() -> str:
    return DEFAULT_PASSWORD


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def csrf_client() -> APIClient:
    """Cliente que aplica a verificação CSRF como um navegador."""
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def auth_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client
