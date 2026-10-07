from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from finances.models import Expense, ExpenseCategory, Income, IncomeCategory
from finances.tests.factories import ExpenseFactory, IncomeFactory

pytestmark = pytest.mark.django_db


def test_expense_categories_match_spec():
    assert ExpenseCategory.choices == [
        ("gasolina", "Gasolina"),
        ("alimentacao", "Alimentação"),
        ("lazer", "Lazer"),
        ("luz", "Luz"),
        ("agua", "Água"),
        ("faculdade", "Faculdade"),
        ("aluguel", "Aluguel / moradia"),
        ("internet", "Internet / telefone"),
        ("saude", "Saúde"),
        ("transporte", "Transporte"),
        ("mercado", "Mercado"),
        ("assinaturas", "Assinaturas"),
        ("outros", "Outros"),
    ]


def test_income_categories_match_spec():
    assert IncomeCategory.choices == [
        ("salario_fixo", "Rendimento fixo / salário"),
        ("dividendos", "Dividendos"),
        ("trabalho_informal", "Trabalhos informais"),
        ("freelance", "Freelance"),
        ("aluguel_recebido", "Aluguel recebido"),
        ("juros", "Juros / rendimentos de aplicações"),
        ("bonus", "Bônus / 13º"),
        ("vendas", "Vendas"),
        ("outros", "Outros"),
    ]


def test_expense_str_and_related_name():
    expense = ExpenseFactory(
        amount=Decimal("12.50"), date=date(2026, 10, 1), category="luz"
    )
    assert str(expense) == "2026-10-01 Luz R$ 12.50"
    assert list(expense.user.expenses.all()) == [expense]


def test_income_related_name():
    income = IncomeFactory()
    assert list(income.user.incomes.all()) == [income]


@pytest.mark.parametrize("model_factory", [ExpenseFactory, IncomeFactory])
@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1.00")])
def test_check_constraint_blocks_non_positive_amount(model_factory, amount):
    with pytest.raises(IntegrityError):
        model_factory(amount=amount)


def test_full_clean_rejects_zero_amount_and_invalid_category():
    expense = ExpenseFactory.build(amount=Decimal("0"), category="xpto")
    expense.user.save()
    with pytest.raises(ValidationError) as exc:
        expense.full_clean()
    assert {"amount", "category"} <= set(exc.value.message_dict)


def test_ordering_is_date_desc_then_id_desc():
    old = ExpenseFactory(date=date(2026, 1, 1))
    first = ExpenseFactory(user=old.user, date=date(2026, 2, 1))
    second = ExpenseFactory(user=old.user, date=date(2026, 2, 1))
    assert list(Expense.objects.all()) == [second, first, old]


def test_user_cascade_deletes_entries():
    expense = ExpenseFactory()
    IncomeFactory(user=expense.user)
    expense.user.delete()
    assert not Expense.objects.exists()
    assert not Income.objects.exists()


def test_indexes_on_user_date():
    for model in (Expense, Income):
        assert any(index.fields == ["user", "date"] for index in model._meta.indexes)
