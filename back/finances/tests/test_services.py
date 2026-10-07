from datetime import UTC, date, datetime
from decimal import Decimal
from unittest import mock

import pytest
from rest_framework.exceptions import ValidationError

from accounts.tests.factories import UserFactory
from finances.services import (
    _largest_remainder_percents,
    build_monthly_summary,
    current_month,
    parse_month,
)
from finances.tests.factories import ExpenseFactory, IncomeFactory


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10", (date(2026, 10, 1), date(2026, 11, 1))),
        ("2026-12", (date(2026, 12, 1), date(2027, 1, 1))),
        ("2000-01", (date(2000, 1, 1), date(2000, 2, 1))),
    ],
)
def test_parse_month_valid(value, expected):
    assert parse_month(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2026",
        "2026-13",
        "2026-00",
        "1999-12",
        "26-10",
        "2026-1",
        "abc",
        "2026-10\n",
        "2026-10-01",
        "２０２６-10",
    ],
)
def test_parse_month_invalid(value):
    with pytest.raises(ValidationError) as exc:
        parse_month(value)
    assert "month" in exc.value.detail


# --- build_monthly_summary ---------------------------------------------------

OCT = date(2026, 10, 15)


def _sum_percent(items: list[dict]) -> Decimal:
    return sum((Decimal(str(i["percent"])) for i in items), Decimal(0))


@pytest.mark.django_db
def test_summary_totals_balance_and_categories(user):
    ExpenseFactory(
        user=user, category="alimentacao", amount=Decimal("500.00"), date=OCT
    )
    ExpenseFactory(
        user=user, category="alimentacao", amount=Decimal("300.00"), date=OCT
    )
    ExpenseFactory(user=user, category="luz", amount=Decimal("720.00"), date=OCT)
    IncomeFactory(
        user=user, category="salario_fixo", amount=Decimal("5000.00"), date=OCT
    )

    summary = build_monthly_summary(user, "2026-10")

    assert summary == {
        "month": "2026-10",
        "total_expenses": "1520.00",
        "total_incomes": "5000.00",
        "balance": "3480.00",
        "expenses_by_category": [
            {
                "category": "alimentacao",
                "label": "Alimentação",
                "total": "800.00",
                "percent": 52.63,
            },
            {"category": "luz", "label": "Luz", "total": "720.00", "percent": 47.37},
        ],
        "incomes_by_category": [
            {
                "category": "salario_fixo",
                "label": "Rendimento fixo / salário",
                "total": "5000.00",
                "percent": 100.0,
            }
        ],
    }


@pytest.mark.django_db
def test_summary_empty_month(user):
    ExpenseFactory(user=user, date=date(2026, 9, 30))
    summary = build_monthly_summary(user, "2026-10")
    assert summary == {
        "month": "2026-10",
        "total_expenses": "0.00",
        "total_incomes": "0.00",
        "balance": "0.00",
        "expenses_by_category": [],
        "incomes_by_category": [],
    }


@pytest.mark.django_db
def test_summary_negative_balance(user):
    ExpenseFactory(user=user, amount=Decimal("1000.50"), date=OCT)
    IncomeFactory(user=user, amount=Decimal("200.25"), date=OCT)
    summary = build_monthly_summary(user, "2026-10")
    assert summary["balance"] == "-800.25"
    assert summary["total_expenses"] == "1000.50"
    assert summary["total_incomes"] == "200.25"


@pytest.mark.django_db
def test_summary_percent_rounding_adjusts_largest_slice(user):
    # 3 fatias iguais: 33.33 * 3 = 99.99 -> o centésimo que falta vai para a
    # 1a fatia (empate no resto -> ordem da lista).
    for category in ("agua", "luz", "lazer"):
        ExpenseFactory(user=user, category=category, amount=Decimal("10.00"), date=OCT)
    items = build_monthly_summary(user, "2026-10")["expenses_by_category"]
    # empate no total -> ordem alfabética da categoria
    assert [i["category"] for i in items] == ["agua", "lazer", "luz"]
    assert [i["percent"] for i in items] == [33.34, 33.33, 33.33]
    assert _sum_percent(items) == Decimal("100")


@pytest.mark.django_db
def test_summary_percent_sum_is_100_with_many_categories(user):
    amounts = ["0.01", "0.02", "1.00", "3.33", "7.77", "10.10", "99.99", "1234.56"]
    categories = ["agua", "luz", "lazer", "saude", "mercado", "gasolina", "outros"]
    for amount, category in zip(amounts, [*categories, "internet"], strict=True):
        ExpenseFactory(user=user, category=category, amount=Decimal(amount), date=OCT)
    items = build_monthly_summary(user, "2026-10")["expenses_by_category"]
    assert abs(_sum_percent(items) - 100) <= Decimal("0.01")
    totals = [Decimal(i["total"]) for i in items]
    assert totals == sorted(totals, reverse=True)
    for item in items:
        assert round(item["percent"], 2) == item["percent"]


@pytest.mark.parametrize(
    ("totals", "expected"),
    [
        # QA-T3-01: maior fatia não pode ficar com % menor que as seguintes.
        (["100.01"] + ["100.00"] * 6, ["14.29"] * 4 + ["14.28"] * 3),
        (["1"] * 6, ["16.67"] * 4 + ["16.66"] * 2),
        (["1"] * 3, ["33.34", "33.33", "33.33"]),
        (["2", "1"], ["66.67", "33.33"]),
        (["5"], ["100.00"]),
    ],
)
def test_largest_remainder_percents(totals, expected):
    values = [Decimal(t) for t in totals]
    result = _largest_remainder_percents(values, sum(values, Decimal(0)))
    assert result == [Decimal(e) for e in expected]
    assert sum(result, Decimal(0)) == Decimal("100.00")
    assert result == sorted(result, reverse=True)


@pytest.mark.django_db
def test_summary_month_boundaries(user):
    ExpenseFactory(user=user, amount=Decimal("1.00"), date=date(2026, 9, 30))
    ExpenseFactory(user=user, amount=Decimal("2.00"), date=date(2026, 10, 1))
    ExpenseFactory(user=user, amount=Decimal("4.00"), date=date(2026, 10, 31))
    ExpenseFactory(user=user, amount=Decimal("8.00"), date=date(2026, 11, 1))
    assert build_monthly_summary(user, "2026-10")["total_expenses"] == "6.00"


@pytest.mark.django_db
def test_summary_isolated_by_user(user):
    other = UserFactory()
    ExpenseFactory(user=other, amount=Decimal("999.00"), date=OCT)
    IncomeFactory(user=other, amount=Decimal("999.00"), date=OCT)
    ExpenseFactory(user=user, amount=Decimal("10.00"), date=OCT)
    summary = build_monthly_summary(user, "2026-10")
    assert summary["total_expenses"] == "10.00"
    assert summary["total_incomes"] == "0.00"
    assert summary["incomes_by_category"] == []


@pytest.mark.django_db
def test_summary_invalid_month(user):
    with pytest.raises(ValidationError) as exc:
        build_monthly_summary(user, "2026-13")
    assert "month" in exc.value.detail


def test_current_month_uses_project_timezone():
    # 01/11 02:00 UTC == 31/10 23:00 em America/Sao_Paulo
    instant = datetime(2026, 11, 1, 2, 0, tzinfo=UTC)
    with mock.patch("django.utils.timezone.now", return_value=instant):
        assert current_month() == "2026-10"
