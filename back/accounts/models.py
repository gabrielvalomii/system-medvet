from typing import Any

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager["User"]):
    """Manager para usuários identificados por e-mail (sem username)."""

    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email: str | None) -> str:
        """Normaliza o e-mail inteiro para minúsculas e sem espaços."""
        return (email or "").strip().lower()

    def get_by_natural_key(self, username: str | None) -> "User":
        """Busca por e-mail sem diferenciar maiúsculas (usado pelo ModelBackend).

        Mantém o login do admin consistente com a API, que já normaliza.
        """
        email = self.normalize_email(username)
        try:
            return self.get(email__iexact=email)
        except self.model.MultipleObjectsReturned:
            # Defesa em profundidade (QA-T1-05): a UniqueConstraint(Lower)
            # impede duplicados por caixa, mas se dados legados existirem o
            # login nunca deve virar 500. Só aceita o e-mail exato normalizado.
            return self.get(email=email)

    def _create_user(self, email: str, password: str | None, **extra: Any) -> "User":
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self, email: str, password: str | None = None, **extra: Any
    ) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(
        self, email: str, password: str | None = None, **extra: Any
    ) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superusuário precisa ter is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superusuário precisa ter is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Usuário do sistema; o login é feito por e-mail."""

    username = None  # type: ignore[assignment]
    email = models.EmailField("e-mail", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()  # type: ignore[misc]

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["email"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="accounts_user_email_ci_unique",
                violation_error_message="Já existe um usuário com este e-mail.",
            ),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Normaliza o e-mail (strip + minúsculas) em qualquer caminho de escrita."""
        self.email = UserManager.normalize_email(self.email)
        super().save(*args, **kwargs)
