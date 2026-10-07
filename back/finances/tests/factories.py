from datetime import date
from decimal import Decimal

import factory

from accounts.tests.factories import UserFactory
from finances.models import Expense, ExpenseCategory, Income, IncomeCategory


class ExpenseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Expense

    user = factory.SubFactory(UserFactory)
    category = ExpenseCategory.ALIMENTACAO
    amount = Decimal("100.00")
    date = factory.LazyFunction(date.today)
    description = "Almoço"


class IncomeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Income

    user = factory.SubFactory(UserFactory)
    category = IncomeCategory.SALARIO_FIXO
    amount = Decimal("5000.00")
    date = factory.LazyFunction(date.today)
    description = "Salário"
