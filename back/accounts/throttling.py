"""Rate limit do login do admin, reaproveitando o throttle do DRF.

O ``/admin/login/`` é uma view comum do Django (fora do DRF), então não é
coberto pelo ``throttle_scope = "login"`` da API. Esta view envolve o login
do admin com um ``SimpleRateThrottle``: a identificação do cliente usa o
mesmo ``get_ident()`` do DRF (respeitando ``NUM_PROXIES``), e a taxa vem de
``DEFAULT_THROTTLE_RATES["admin_login"]``.
"""

from math import ceil

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from rest_framework.throttling import SimpleRateThrottle

ADMIN_THROTTLED_MESSAGE = "Muitas tentativas de login. Tente novamente mais tarde."


class AdminLoginThrottle(SimpleRateThrottle):
    """Limita tentativas de login no admin por IP (sucesso e falha contam)."""

    scope = "admin_login"

    def get_cache_key(self, request: HttpRequest, view: object) -> str:
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


def throttled_admin_login(
    request: HttpRequest, extra_context: dict | None = None
) -> HttpResponse:
    """``admin.site.login`` com rate limit nas submissões (POST)."""
    if request.method == "POST":
        throttle = AdminLoginThrottle()
        if not throttle.allow_request(request, None):
            response = HttpResponse(
                ADMIN_THROTTLED_MESSAGE,
                status=429,
                content_type="text/plain; charset=utf-8",
            )
            wait = throttle.wait()
            if wait is not None:
                response["Retry-After"] = str(ceil(wait))
            return response
    return admin.site.login(request, extra_context)
