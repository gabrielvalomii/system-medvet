from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from finances.models import Expense, Income
from finances.tests.factories import ExpenseFactory, IncomeFactory

pytestmark = pytest.mark.django_db

CATEGORIES_URL = reverse("finances:categories")

# (nome da rota, factory, modelo, categoria válida, categoria do outro tipo)
RESOURCES = [
    pytest.param(
        "expense", ExpenseFactory, Expense, "mercado", "salario_fixo", id="expenses"
    ),
    pytest.param(
        "income", IncomeFactory, Income, "freelance", "gasolina", id="incomes"
    ),
]
ARGS = ("name", "factory", "model", "cat", "other")


def list_url(name: str) -> str:
    return reverse(f"finances:{name}-list")


def detail_url(name: str, pk: int) -> str:
    return reverse(f"finances:{name}-detail", args=[pk])


def payload(category: str, /, **overrides) -> dict:
    data = {
        "category": category,
        "amount": "123.45",
        "date": timezone.localdate().isoformat(),
        "description": "  Compra do mês  ",
    }
    data.update(overrides)
    return data


# --- Categorias --------------------------------------------------------------


def test_categories_returns_value_label_lists(auth_client):
    response = auth_client.get(CATEGORIES_URL)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"expenses", "incomes"}
    assert len(body["expenses"]) == 13
    assert len(body["incomes"]) == 9
    assert body["expenses"][0] == {"value": "gasolina", "label": "Gasolina"}
    assert {"value": "bonus", "label": "Bônus / 13º"} in body["incomes"]


def test_categories_requires_login(api_client):
    response = api_client.get(CATEGORIES_URL)
    assert response.status_code == 403
    assert "detail" in response.json()


# --- CRUD --------------------------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_create(auth_client, user, name, factory, model, cat, other):
    response = auth_client.post(list_url(name), payload(cat), format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["amount"] == "123.45"  # string decimal
    assert body["category"] == cat
    assert body["category_label"]
    assert body["description"] == "Compra do mês"  # strip
    assert set(body) == {
        "id",
        "category",
        "category_label",
        "amount",
        "date",
        "description",
        "created_at",
        "updated_at",
    }
    obj = model.objects.get(pk=body["id"])
    assert obj.user == user
    assert obj.amount == Decimal("123.45")


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_create_ignores_user_in_payload(
    auth_client, user, name, factory, model, cat, other
):
    other_user = UserFactory()
    response = auth_client.post(
        list_url(name), payload(cat, user=other_user.pk), format="json"
    )
    assert response.status_code == 201
    assert model.objects.get(pk=response.json()["id"]).user == user
    assert not model.objects.filter(user=other_user).exists()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_create_without_description(auth_client, name, factory, model, cat, other):
    data = payload(cat)
    del data["description"]
    response = auth_client.post(list_url(name), data, format="json")
    assert response.status_code == 201
    assert response.json()["description"] == ""


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_retrieve_update_patch_delete(
    auth_client, user, name, factory, model, cat, other
):
    obj = factory(user=user)
    url = detail_url(name, obj.pk)

    response = auth_client.get(url)
    assert response.status_code == 200
    assert response.json()["id"] == obj.pk

    response = auth_client.put(url, payload(cat, amount="10.10"), format="json")
    assert response.status_code == 200
    assert response.json()["amount"] == "10.10"

    response = auth_client.patch(url, {"description": "novo"}, format="json")
    assert response.status_code == 200
    assert response.json()["description"] == "novo"
    obj.refresh_from_db()
    assert obj.amount == Decimal("10.10")
    assert obj.description == "novo"

    assert auth_client.delete(url).status_code == 204
    assert not model.objects.filter(pk=obj.pk).exists()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_list_returns_plain_array_of_own_entries(
    auth_client, user, name, factory, model, cat, other
):
    mine = factory(user=user)
    factory()  # de outro usuário
    response = auth_client.get(list_url(name))
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert [item["id"] for item in body] == [mine.pk]


# --- Validações --------------------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", "0"),
        ("amount", "0.00"),
        ("amount", "-5"),
        ("amount", "abc"),
        ("amount", "1.234"),
        ("amount", "10000000000.00"),
        ("amount", "NaN"),
        ("amount", None),
        ("category", "inexistente"),
        ("category", ""),
        ("date", "1999-12-31"),
        ("date", "2026-02-30"),
        ("date", "ontem"),
        ("description", "x" * 256),
        ("description", "<script>alert(1)</script>"),
        ("description", "a > b"),
        ("description", None),
    ],
)
def test_create_validation_errors(
    auth_client, name, factory, model, cat, other, field, value
):
    response = auth_client.post(
        list_url(name), payload(cat, **{field: value}), format="json"
    )
    assert response.status_code == 400
    assert field in response.json()
    assert not model.objects.exists()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_create_rejects_category_of_other_type(
    auth_client, name, factory, model, cat, other
):
    response = auth_client.post(list_url(name), payload(other), format="json")
    assert response.status_code == 400
    assert "category" in response.json()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_required_fields(auth_client, name, factory, model, cat, other):
    response = auth_client.post(list_url(name), {}, format="json")
    assert response.status_code == 400
    assert {"category", "amount", "date"} <= set(response.json())


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_date_limits(auth_client, name, factory, model, cat, other):
    today = timezone.localdate()
    for value in (date(2000, 1, 1), today + timedelta(days=365)):
        response = auth_client.post(
            list_url(name), payload(cat, date=value.isoformat()), format="json"
        )
        assert response.status_code == 201, response.json()
    too_far = today + timedelta(days=366)
    response = auth_client.post(
        list_url(name), payload(cat, date=too_far.isoformat()), format="json"
    )
    assert response.status_code == 400
    assert "date" in response.json()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_amount_limits(auth_client, name, factory, model, cat, other):
    for value in ("0.01", "9999999999.99", 15):
        response = auth_client.post(
            list_url(name), payload(cat, amount=value), format="json"
        )
        assert response.status_code == 201, response.json()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_description_max_length_after_strip(
    auth_client, name, factory, model, cat, other
):
    text = "  " + "x" * 255 + "  "
    response = auth_client.post(
        list_url(name), payload(cat, description=text), format="json"
    )
    assert response.status_code == 201
    assert response.json()["description"] == "x" * 255


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_patch_validates_amount(auth_client, user, name, factory, model, cat, other):
    obj = factory(user=user)
    response = auth_client.patch(
        detail_url(name, obj.pk), {"amount": "-1"}, format="json"
    )
    assert response.status_code == 400
    obj.refresh_from_db()
    assert obj.amount > 0


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_patch_cannot_change_owner(auth_client, user, name, factory, model, cat, other):
    obj = factory(user=user)
    other_user = UserFactory()
    response = auth_client.patch(
        detail_url(name, obj.pk), {"user": other_user.pk}, format="json"
    )
    assert response.status_code == 200
    obj.refresh_from_db()
    assert obj.user == user


# --- Filtro por mês ----------------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_month_filter(auth_client, user, name, factory, model, cat, other):
    first_day = factory(user=user, date=date(2026, 10, 1))
    last_day = factory(user=user, date=date(2026, 10, 31))
    factory(user=user, date=date(2026, 9, 30))
    factory(user=user, date=date(2026, 11, 1))
    factory(date=date(2026, 10, 15))  # outro usuário

    response = auth_client.get(list_url(name), {"month": "2026-10"})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [last_day.pk, first_day.pk]


@pytest.mark.parametrize(ARGS, RESOURCES)
@pytest.mark.parametrize("month", ["2026-13", "10-2026", "", "2026-1", "x"])
def test_month_filter_invalid_returns_400(
    auth_client, name, factory, model, cat, other, month
):
    response = auth_client.get(list_url(name), {"month": month})
    assert response.status_code == 400
    assert isinstance(response.json()["month"], list)


# --- Isolamento entre usuários -----------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_user_cannot_access_other_users_entry(
    auth_client, name, factory, model, cat, other
):
    foreign = factory(amount=Decimal("77.00"), description="do B")
    url = detail_url(name, foreign.pk)

    assert auth_client.get(url).status_code == 404
    assert auth_client.put(url, payload(cat), format="json").status_code == 404
    response = auth_client.patch(url, {"amount": "1.00"}, format="json")
    assert response.status_code == 404
    assert auth_client.delete(url).status_code == 404
    listed = [item["id"] for item in auth_client.get(list_url(name)).json()]
    assert foreign.pk not in listed

    foreign.refresh_from_db()
    assert foreign.amount == Decimal("77.00")
    assert foreign.description == "do B"


# --- Autenticação e CSRF -----------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_requires_login(api_client, name, factory, model, cat, other):
    obj = factory()
    assert api_client.get(list_url(name)).status_code == 403
    response = api_client.post(list_url(name), payload(cat), format="json")
    assert response.status_code == 403
    assert api_client.get(detail_url(name, obj.pk)).status_code == 403
    assert api_client.delete(detail_url(name, obj.pk)).status_code == 403
    assert model.objects.filter(pk=obj.pk).exists()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_post_without_csrf_is_forbidden_with_session(
    user, name, factory, model, cat, other
):
    client = APIClient(enforce_csrf_checks=True)
    assert client.login(email=user.email, password=DEFAULT_PASSWORD)

    response = client.post(list_url(name), payload(cat), format="json")
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]
    assert not model.objects.exists()

    token = client.get(reverse("accounts:csrf")).cookies["csrftoken"].value
    response = client.post(
        list_url(name), payload(cat), format="json", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 201


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_delete_without_csrf_is_forbidden_with_session(
    user, name, factory, model, cat, other
):
    obj = factory(user=user)
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.delete(detail_url(name, obj.pk)).status_code == 403
    assert model.objects.filter(pk=obj.pk).exists()


# --- Dashboard summary -------------------------------------------------------

SUMMARY_URL = reverse("finances:dashboard-summary")
SUMMARY_KEYS = {
    "month",
    "total_expenses",
    "total_incomes",
    "balance",
    "expenses_by_category",
    "incomes_by_category",
}


def test_summary_requires_login(api_client):
    response = api_client.get(SUMMARY_URL, {"month": "2026-10"})
    assert response.status_code == 403
    assert "detail" in response.json()


def test_summary_format(auth_client, user):
    day = date(2026, 10, 10)
    ExpenseFactory(user=user, category="alimentacao", amount=Decimal("800"), date=day)
    ExpenseFactory(user=user, category="gasolina", amount=Decimal("720"), date=day)
    IncomeFactory(user=user, category="salario_fixo", amount=Decimal("5000"), date=day)

    response = auth_client.get(SUMMARY_URL, {"month": "2026-10"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == SUMMARY_KEYS
    assert body["month"] == "2026-10"
    assert body["total_expenses"] == "1520.00"
    assert body["total_incomes"] == "5000.00"
    assert body["balance"] == "3480.00"
    assert body["expenses_by_category"] == [
        {
            "category": "alimentacao",
            "label": "Alimentação",
            "total": "800.00",
            "percent": 52.63,
        },
        {
            "category": "gasolina",
            "label": "Gasolina",
            "total": "720.00",
            "percent": 47.37,
        },
    ]
    assert body["incomes_by_category"] == [
        {
            "category": "salario_fixo",
            "label": "Rendimento fixo / salário",
            "total": "5000.00",
            "percent": 100.0,
        }
    ]


def test_summary_defaults_to_current_month(auth_client, user):
    today = timezone.localdate()
    ExpenseFactory(user=user, amount=Decimal("12.34"), date=today)
    ExpenseFactory(user=user, amount=Decimal("99.00"), date=today - timedelta(days=62))

    body = auth_client.get(SUMMARY_URL).json()

    assert body["month"] == today.strftime("%Y-%m")
    assert body["total_expenses"] == "12.34"


def test_summary_empty_month(auth_client):
    body = auth_client.get(SUMMARY_URL, {"month": "2001-01"}).json()
    assert body["total_expenses"] == body["total_incomes"] == "0.00"
    assert body["balance"] == "0.00"
    assert body["expenses_by_category"] == body["incomes_by_category"] == []


def test_summary_negative_balance(auth_client, user):
    day = date(2026, 10, 10)
    ExpenseFactory(user=user, amount=Decimal("300.00"), date=day)
    IncomeFactory(user=user, amount=Decimal("100.10"), date=day)
    body = auth_client.get(SUMMARY_URL, {"month": "2026-10"}).json()
    assert body["balance"] == "-199.90"


def test_summary_excludes_other_months(auth_client, user):
    ExpenseFactory(user=user, amount=Decimal("1.00"), date=date(2026, 9, 30))
    ExpenseFactory(user=user, amount=Decimal("2.00"), date=date(2026, 10, 31))
    IncomeFactory(user=user, amount=Decimal("3.00"), date=date(2026, 11, 1))
    body = auth_client.get(SUMMARY_URL, {"month": "2026-10"}).json()
    assert body["total_expenses"] == "2.00"
    assert body["total_incomes"] == "0.00"


def test_summary_only_current_user_data(auth_client, user):
    other = UserFactory()
    day = date(2026, 10, 10)
    ExpenseFactory(user=other, amount=Decimal("500"), date=day)
    IncomeFactory(user=other, amount=Decimal("500"), date=day)
    IncomeFactory(user=user, amount=Decimal("100"), date=day)

    body = auth_client.get(SUMMARY_URL, {"month": "2026-10"}).json()

    assert body["total_expenses"] == "0.00"
    assert body["total_incomes"] == "100.00"
    assert body["expenses_by_category"] == []


@pytest.mark.parametrize(
    "month", ["", "2026-13", "2026-1", "abc", "1999-12", "2026/10", "2026-10 "]
)
def test_summary_invalid_month(auth_client, month):
    response = auth_client.get(SUMMARY_URL, {"month": month})
    assert response.status_code == 400
    assert list(response.json()) == ["month"]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_summary_is_read_only(auth_client, method):
    response = getattr(auth_client, method)(SUMMARY_URL)
    assert response.status_code == 405


@pytest.mark.parametrize("entries", [0, 1, 30])
def test_summary_constant_queries(
    auth_client, user, django_assert_num_queries, entries
):
    day = date(2026, 10, 10)
    categories = ["agua", "luz", "lazer", "mercado", "saude"]
    for i in range(entries):
        ExpenseFactory(user=user, category=categories[i % 5], date=day)
        IncomeFactory(user=user, date=day)

    # 2 por modelo: total (aggregate) + agrupamento por categoria.
    with django_assert_num_queries(4):
        response = auth_client.get(SUMMARY_URL, {"month": "2026-10"})
    assert response.status_code == 200
