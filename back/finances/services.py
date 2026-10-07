"""Regras de negócio do app finances (fora das views)."""

import re
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Expense, Income

MONTH_RE = re.compile(r"([0-9]{4})-([0-9]{2})")  # usado com fullmatch
MIN_YEAR = 2000
MAX_YEAR = 9998
INVALID_MONTH = "Mês inválido. Use o formato AAAA-MM (ex.: 2026-10)."


def parse_month(value: str) -> tuple[date, date]:
    """Converte ``AAAA-MM`` em ``(primeiro dia, primeiro dia do mês seguinte)``.

    Levanta ``ValidationError({"month": [...]})`` (HTTP 400) se inválido.
    """
    match = MONTH_RE.fullmatch(value or "")
    if not match:
        raise ValidationError({"month": [INVALID_MONTH]})
    year, month = int(match.group(1)), int(match.group(2))
    if not (1 <= month <= 12 and MIN_YEAR <= year <= MAX_YEAR):
        raise ValidationError({"month": [INVALID_MONTH]})
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


# --- Dashboard ---------------------------------------------------------------

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
ZERO = Decimal("0.00")


def current_month() -> str:
    """Mês atual (``AAAA-MM``) no fuso ``TIME_ZONE`` do projeto."""
    return timezone.localdate().strftime("%Y-%m")


def _money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _largest_remainder_percents(totals: list[Decimal], total: Decimal) -> list[Decimal]:
    """Percentuais com 2 casas pelo método do maior resto (Hamilton).

    1. Calcula o percentual exato de cada fatia (``Decimal``) e o trunca em
       centésimos.
    2. Os centésimos que faltam para 100.00 são distribuídos, um por fatia, às
       de maior resto; empates seguem a ordem da lista (total desc, categoria).

    A soma é sempre exatamente 100.00 e uma fatia com total maior nunca recebe
    percentual menor que outra com total menor. ``total`` deve ser > 0.
    """
    exact = [value * HUNDRED / total for value in totals]
    floored = [p.quantize(CENT, rounding=ROUND_DOWN) for p in exact]
    missing = int((HUNDRED - sum(floored, Decimal(0))) / CENT)
    by_remainder = sorted(
        range(len(exact)), key=lambda i: (-(exact[i] - floored[i]), i)
    )
    for i in by_remainder[:missing]:
        floored[i] += CENT
    return floored


def _by_category(
    model: type[Expense] | type[Income],
    user: AbstractBaseUser,
    start: date,
    end: date,
) -> tuple[Decimal, list[dict[str, Any]]]:
    """Total do mês e agregação por categoria, ambos calculados no banco.

    A lista vem ordenada por total desc e categoria asc. Os percentuais são
    calculados por ``_largest_remainder_percents`` (método do maior resto),
    somando exatamente 100.00 e preservando a ordem dos totais.
    """
    queryset = model.objects.filter(user=user, date__gte=start, date__lt=end)
    total: Decimal = queryset.aggregate(total=Sum("amount"))["total"] or ZERO
    rows = list(
        queryset.order_by()
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("-total", "category")
    )
    if not rows or total <= 0:
        return total, []

    labels = dict(model._meta.get_field("category").choices)
    percents = _largest_remainder_percents([row["total"] for row in rows], total)
    items = [
        {
            "category": row["category"],
            "label": str(labels.get(row["category"], row["category"])),
            "total": _money(row["total"]),
            "percent": float(percent),
        }
        for row, percent in zip(rows, percents, strict=True)
    ]
    return total, items


def build_monthly_summary(user: AbstractBaseUser, month: str) -> dict[str, Any]:
    """Resumo do mês ``AAAA-MM`` do usuário (formato da seção 4.3 do CLAUDE.md).

    Levanta ``ValidationError({"month": [...]})`` se ``month`` for inválido.
    Executa um número constante de queries (4), independente do volume.
    """
    start, end = parse_month(month)
    total_expenses, expenses = _by_category(Expense, user, start, end)
    total_incomes, incomes = _by_category(Income, user, start, end)
    return {
        "month": month,
        "total_expenses": _money(total_expenses),
        "total_incomes": _money(total_incomes),
        "balance": _money(total_incomes - total_expenses),
        "expenses_by_category": expenses,
        "incomes_by_category": incomes,
    }
