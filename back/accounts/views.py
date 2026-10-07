"""
Views de autenticação baseadas em sessão.

CSRF: o ``SessionAuthentication`` do DRF só aplica a verificação CSRF para
usuários já autenticados. Como o login é feito por um usuário anônimo, a view
de login é decorada com ``csrf_protect`` para que o token CSRF também seja
exigido nela (proteção contra *login CSRF*). O cliente deve chamar
``GET /api/auth/csrf/`` antes e enviar o header ``X-CSRFToken``.
"""

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import LoginSerializer, UserSerializer

INVALID_CREDENTIALS = "E-mail ou senha inválidos"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Define o cookie ``csrftoken``."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        return Response({"detail": "CSRF cookie definido."})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return self._invalid()
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return self._invalid()
        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)

    @staticmethod
    def _invalid() -> Response:
        return Response(
            {"detail": INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)
