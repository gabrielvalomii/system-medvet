"""Views do app finances (finas: regras em serializers/services)."""

from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from .models import Expense, ExpenseCategory, Income, IncomeCategory
from .serializers import ExpenseSerializer, IncomeSerializer
from .services import build_monthly_summary, current_month, parse_month


class EntryViewSet(viewsets.ModelViewSet):
    """CRUD de lançamentos do usuário logado.

    - ``get_queryset`` sempre filtra por ``request.user``: recurso de outro
      usuário responde 404.
    - Listagem sem paginação (lista JSON simples), com filtro opcional
      ``?month=AAAA-MM``.
    """

    model: type[Expense] | type[Income]

    def get_queryset(self) -> QuerySet:
        queryset = self.model.objects.filter(user=self.request.user)
        if self.action == "list":
            month = self.request.query_params.get("month")
            if month is not None:
                start, end = parse_month(month)
                queryset = queryset.filter(date__gte=start, date__lt=end)
        return queryset

    def perform_create(self, serializer: BaseSerializer) -> None:
        serializer.save(user=self.request.user)


class ExpenseViewSet(EntryViewSet):
    model = Expense
    serializer_class = ExpenseSerializer


class IncomeViewSet(EntryViewSet):
    model = Income
    serializer_class = IncomeSerializer


class CategoriesView(APIView):
    """Lista de categorias (fonte única: TextChoices dos modelos)."""

    def get(self, request: Request) -> Response:
        return Response(
            {
                "expenses": _choices(ExpenseCategory),
                "incomes": _choices(IncomeCategory),
            }
        )


def _choices(enum: type[ExpenseCategory] | type[IncomeCategory]) -> list[dict]:
    return [{"value": value, "label": label} for value, label in enum.choices]


class DashboardSummaryView(APIView):
    """Resumo do mês (``?month=AAAA-MM``; padrão: mês atual) do usuário logado."""

    def get(self, request: Request) -> Response:
        month = request.query_params.get("month")
        if month is None:
            month = current_month()
        return Response(build_monthly_summary(request.user, month))
