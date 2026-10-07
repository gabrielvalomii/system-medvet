from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import CategoriesView, DashboardSummaryView, ExpenseViewSet, IncomeViewSet

app_name = "finances"

router = SimpleRouter()
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("incomes", IncomeViewSet, basename="income")

urlpatterns = [
    path("categories/", CategoriesView.as_view(), name="categories"),
    path(
        "dashboard/summary/",
        DashboardSummaryView.as_view(),
        name="dashboard-summary",
    ),
    *router.urls,
]
