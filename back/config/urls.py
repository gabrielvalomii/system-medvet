from django.contrib import admin
from django.urls import include, path

from accounts.throttling import throttled_admin_login

urlpatterns = [
    # Sobrepõe o login do admin com rate limit (QA-T1-02); deve vir antes
    # de admin.site.urls. reverse("admin:login") continua apontando para cá.
    path("admin/login/", throttled_admin_login),
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("finances.urls")),
]
