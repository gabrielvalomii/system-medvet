"""Serializers de gastos e rendimentos.

Decisões:
- ``user`` não faz parte dos campos: é sempre definido na view
  (``perform_create``) e qualquer valor enviado no payload é ignorado.
- ``amount`` é serializado como string decimal (``COERCE_DECIMAL_TO_STRING``).
- ``description``: espaços nas pontas são removidos e os caracteres ``<`` e
  ``>`` são **rejeitados** (400). Rejeitar é mais simples e previsível que
  escapar: não altera o texto do usuário, não estoura o limite de 255 com
  entidades HTML e evita escape duplo no front (que já usa ``textContent``).
"""

from datetime import date, timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import MIN_AMOUNT, Expense, Income

MIN_DATE = date(2000, 1, 1)
MAX_FUTURE_DAYS = 365
FORBIDDEN_DESCRIPTION_CHARS = ("<", ">")


class EntrySerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(
        source="get_category_display", read_only=True
    )
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=MIN_AMOUNT,
        error_messages={"min_value": "O valor deve ser maior que zero."},
    )
    description = serializers.CharField(
        max_length=255, allow_blank=True, required=False, trim_whitespace=True
    )

    class Meta:
        fields = [
            "id",
            "category",
            "category_label",
            "amount",
            "date",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_date(self, value: date) -> date:
        if value < MIN_DATE:
            raise serializers.ValidationError("A data deve ser a partir de 01/01/2000.")
        limit = timezone.localdate() + timedelta(days=MAX_FUTURE_DAYS)
        if value > limit:
            raise serializers.ValidationError(
                "A data não pode ser mais de 1 ano no futuro."
            )
        return value

    def validate_description(self, value: str) -> str:
        if any(char in value for char in FORBIDDEN_DESCRIPTION_CHARS):
            raise serializers.ValidationError(
                "A descrição não pode conter os caracteres < ou >."
            )
        return value


class ExpenseSerializer(EntrySerializer):
    class Meta(EntrySerializer.Meta):
        model = Expense


class IncomeSerializer(EntrySerializer):
    class Meta(EntrySerializer.Meta):
        model = Income
