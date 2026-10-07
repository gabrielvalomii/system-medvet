"""Modelos do app finances: gastos (Expense) e rendimentos (Income)."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

MIN_AMOUNT = Decimal("0.01")


class ExpenseCategory(models.TextChoices):
    GASOLINA = "gasolina", "Gasolina"
    ALIMENTACAO = "alimentacao", "Alimentação"
    LAZER = "lazer", "Lazer"
    LUZ = "luz", "Luz"
    AGUA = "agua", "Água"
    FACULDADE = "faculdade", "Faculdade"
    ALUGUEL = "aluguel", "Aluguel / moradia"
    INTERNET = "internet", "Internet / telefone"
    SAUDE = "saude", "Saúde"
    TRANSPORTE = "transporte", "Transporte"
    MERCADO = "mercado", "Mercado"
    ASSINATURAS = "assinaturas", "Assinaturas"
    OUTROS = "outros", "Outros"


class IncomeCategory(models.TextChoices):
    SALARIO_FIXO = "salario_fixo", "Rendimento fixo / salário"
    DIVIDENDOS = "dividendos", "Dividendos"
    TRABALHO_INFORMAL = "trabalho_informal", "Trabalhos informais"
    FREELANCE = "freelance", "Freelance"
    ALUGUEL_RECEBIDO = "aluguel_recebido", "Aluguel recebido"
    JUROS = "juros", "Juros / rendimentos de aplicações"
    BONUS = "bonus", "Bônus / 13º"
    VENDAS = "vendas", "Vendas"
    OUTROS = "outros", "Outros"


class Entry(models.Model):
    """Base abstrata de um lançamento financeiro (gasto ou rendimento)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)ss",  # user.expenses / user.incomes
        verbose_name="usuário",
    )
    amount = models.DecimalField(
        "valor",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(MIN_AMOUNT)],
    )
    date = models.DateField("data")
    description = models.CharField("descrição", max_length=255, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(
                fields=["user", "date"], name="%(app_label)s_%(class)s_user_date"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="%(app_label)s_%(class)s_amount_gt_0",
                violation_error_message="O valor deve ser maior que zero.",
            ),
        ]

    def __str__(self) -> str:
        label = self.get_category_display()  # type: ignore[attr-defined]
        return f"{self.date:%Y-%m-%d} {label} R$ {self.amount}"


class Expense(Entry):
    category = models.CharField(
        "categoria", max_length=32, choices=ExpenseCategory.choices
    )

    class Meta(Entry.Meta):
        verbose_name = "gasto"
        verbose_name_plural = "gastos"


class Income(Entry):
    category = models.CharField(
        "categoria", max_length=32, choices=IncomeCategory.choices
    )

    class Meta(Entry.Meta):
        verbose_name = "rendimento"
        verbose_name_plural = "rendimentos"
