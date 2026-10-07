"""
QA — Tarefa 2 (Finanças): gastos, rendimentos e categorias.

Testes de caixa-preta pela API com sessão real (login + CSRF), isolamento
entre usuários, validações de borda, filtro de mês, categorias x CLAUDE.md,
constraints do banco e admin.
"""

import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from finances.models import Expense, ExpenseCategory, Income, IncomeCategory
from finances.tests.factories import ExpenseFactory, IncomeFactory

pytestmark = pytest.mark.django_db

CSRF_URL = reverse("accounts:csrf")
LOGIN_URL = reverse("accounts:login")
LOGOUT_URL = reverse("accounts:logout")
CATEGORIES_URL = reverse("finances:categories")
CLAUDE_MD = Path(settings.BASE_DIR).parent / "CLAUDE.md"

RESOURCES = [
    pytest.param(
        "expense", ExpenseFactory, Expense, "mercado", "salario_fixo", id="exp"
    ),
    pytest.param("income", IncomeFactory, Income, "freelance", "gasolina", id="inc"),
]
ARGS = ("name", "factory", "model", "cat", "other")


def list_url(name: str) -> str:
    return reverse(f"finances:{name}-list")


def detail_url(name: str, pk: int) -> str:
    return reverse(f"finances:{name}-detail", args=[pk])


def body(cat: str, **over) -> dict:
    data = {
        "category": cat,
        "amount": "10.00",
        "date": timezone.localdate().isoformat(),
        "description": "teste",
    }
    data.update(over)
    return data


class Browser:
    """Cliente que se comporta como o navegador: sessão real + X-CSRFToken."""

    def __init__(self, user: User) -> None:
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get(CSRF_URL).cookies["csrftoken"].value
        response = self.client.post(
            LOGIN_URL,
            {"email": user.email, "password": DEFAULT_PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        assert response.status_code == 200
        # O login roda rotate_token: usa o token novo do cookie.
        self.token = self.client.cookies["csrftoken"].value

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def send(self, method: str, url: str, data=None, csrf: bool = True):
        extra = {"HTTP_X_CSRFTOKEN": self.token} if csrf else {}
        return getattr(self.client, method)(url, data, format="json", **extra)


@pytest.fixture
def alice():
    return UserFactory(email="alice@example.com")


@pytest.fixture
def bob():
    return UserFactory(email="bob@example.com")


@pytest.fixture
def browser_a(alice) -> Browser:
    return Browser(alice)


# --- Isolamento A x B --------------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_isolation_full_crud_returns_404_and_keeps_b_data(
    browser_a, alice, bob, name, factory, model, cat, other
):
    b_obj = factory(user=bob, amount=Decimal("77.70"), description="do bob")
    snapshot = model.objects.filter(pk=b_obj.pk).values().get()
    url = detail_url(name, b_obj.pk)

    listed = browser_a.get(list_url(name)).json()
    assert listed == []
    month = b_obj.date.strftime("%Y-%m")
    assert browser_a.get(list_url(name), data={"month": month}).json() == []
    assert browser_a.get(url).status_code == 404
    assert browser_a.send("put", url, body(cat, amount="1.00")).status_code == 404
    assert browser_a.send("patch", url, {"amount": "1.00"}).status_code == 404
    assert browser_a.send("patch", url, {}).status_code == 404
    assert browser_a.send("delete", url).status_code == 404

    assert model.objects.filter(pk=b_obj.pk).values().get() == snapshot


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_404_for_other_user_equals_404_for_missing_id(
    browser_a, bob, name, factory, model, cat, other
):
    """Não deve ser possível enumerar ids de outro usuário."""
    b_obj = factory(user=bob)
    other_resp = browser_a.get(detail_url(name, b_obj.pk))
    missing_resp = browser_a.get(detail_url(name, 999_999))
    assert other_resp.status_code == missing_resp.status_code == 404
    assert other_resp.json() == missing_resp.json()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_list_only_returns_own_entries_mixed(
    browser_a, alice, bob, name, factory, model, cat, other
):
    mine = [factory(user=alice) for _ in range(3)]
    factory.create_batch(4, user=bob)
    ids = {item["id"] for item in browser_a.get(list_url(name)).json()}
    assert ids == {obj.pk for obj in mine}


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_user_in_payload_is_ignored_on_create_put_patch(
    browser_a, alice, bob, name, factory, model, cat, other
):
    created = browser_a.send("post", list_url(name), body(cat, user=bob.pk))
    assert created.status_code == 201
    assert "user" not in created.json()
    obj = model.objects.get(pk=created.json()["id"])
    assert obj.user == alice

    url = detail_url(name, obj.pk)
    assert browser_a.send("put", url, body(cat, user=bob.pk)).status_code == 200
    assert browser_a.send("patch", url, {"user": bob.pk}).status_code == 200
    assert browser_a.send("patch", url, {"user_id": bob.pk}).status_code == 200
    obj.refresh_from_db()
    assert obj.user == alice
    assert not model.objects.filter(user=bob).exists()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_read_only_fields_ignored(browser_a, name, factory, model, cat, other):
    fake = "2001-01-01T00:00:00Z"
    resp = browser_a.send(
        "post",
        list_url(name),
        body(
            cat,
            id=424242,
            created_at=fake,
            updated_at=fake,
            category_label="Hackeado",
        ),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] != 424242
    assert not data["created_at"].startswith("2001")
    assert data["category_label"] != "Hackeado"


# --- Autenticação / CSRF ----------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_anonymous_gets_403_on_all_methods(
    api_client, name, factory, model, cat, other
):
    obj = factory()
    url = detail_url(name, obj.pk)
    for method, target in [
        ("get", list_url(name)),
        ("post", list_url(name)),
        ("get", url),
        ("put", url),
        ("patch", url),
        ("delete", url),
        ("options", list_url(name)),
    ]:
        response = getattr(api_client, method)(target, body(cat), format="json")
        assert response.status_code == 403, (method, target)
    assert api_client.get(CATEGORIES_URL).status_code == 403
    assert model.objects.filter(pk=obj.pk).exists()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_real_session_without_csrf_token_is_403_for_all_writes(
    browser_a, alice, name, factory, model, cat, other
):
    obj = factory(user=alice, amount=Decimal("50.00"))
    url = detail_url(name, obj.pk)
    attempts = [
        ("post", list_url(name), body(cat)),
        ("put", url, body(cat, amount="1.00")),
        ("patch", url, {"amount": "1.00"}),
        ("delete", url, None),
    ]
    for method, target, data in attempts:
        response = browser_a.send(method, target, data, csrf=False)
        assert response.status_code == 403, method
        assert "CSRF" in response.json()["detail"]
    obj.refresh_from_db()
    assert obj.amount == Decimal("50.00")
    assert model.objects.filter(user=alice).count() == 1


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_real_session_with_wrong_csrf_token_is_403(
    browser_a, name, factory, model, cat, other
):
    resp = browser_a.client.post(
        list_url(name), body(cat), format="json", HTTP_X_CSRFTOKEN="x" * 64
    )
    assert resp.status_code == 403
    assert not model.objects.exists()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_full_crud_with_real_session_and_csrf(
    browser_a, name, factory, model, cat, other
):
    created = browser_a.send("post", list_url(name), body(cat, amount="10.50"))
    assert created.status_code == 201
    pk = created.json()["id"]
    url = detail_url(name, pk)
    assert browser_a.get(url).json()["amount"] == "10.50"
    put = browser_a.send("put", url, body(cat, amount="20", description=""))
    assert put.status_code == 200
    assert put.json()["amount"] == "20.00"
    assert put.json()["description"] == ""
    patch = browser_a.send("patch", url, {"description": "  novo  "})
    assert patch.json()["description"] == "novo"
    assert browser_a.send("delete", url).status_code == 204
    assert browser_a.get(url).status_code == 404


def test_after_logout_finance_routes_are_403(browser_a, alice):
    ExpenseFactory(user=alice)
    assert browser_a.send("post", LOGOUT_URL).status_code in (200, 204)
    assert browser_a.get(list_url("expense")).status_code == 403
    assert browser_a.get(CATEGORIES_URL).status_code == 403


# --- Validações: amount ------------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
@pytest.mark.parametrize(
    "amount",
    [
        "0",
        "0.00",
        "0.001",
        "-0.01",
        "-10",
        "10.123",
        "10000000000.00",  # 11 dígitos inteiros (max_digits=12, 2 decimais)
        "1e20",
        "NaN",
        "Infinity",
        "-Infinity",
        "abc",
        "",
        "1,50",
        None,
        True,
        [],
        {},
    ],
)
def test_invalid_amount_returns_400(
    browser_a, amount, name, factory, model, cat, other
):
    resp = browser_a.send("post", list_url(name), body(cat, amount=amount))
    assert resp.status_code == 400, resp.content
    assert "amount" in resp.json()
    assert not model.objects.exists()


@pytest.mark.parametrize(ARGS, RESOURCES)
@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0.01", "0.01"),
        ("9999999999.99", "9999999999.99"),
        (" 15.5 ", "15.50"),
        (12, "12.00"),
        (12.5, "12.50"),
        ("1e3", "1000.00"),
    ],
)
def test_valid_amount_boundaries_serialized_as_string(
    browser_a, amount, expected, name, factory, model, cat, other
):
    resp = browser_a.send("post", list_url(name), body(cat, amount=amount))
    assert resp.status_code == 201, resp.content
    assert resp.json()["amount"] == expected
    assert isinstance(resp.json()["amount"], str)
    obj = model.objects.get()
    assert obj.amount == Decimal(expected)


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_values_are_strings_in_list_and_detail(
    browser_a, alice, name, factory, model, cat, other
):
    obj = factory(user=alice, amount=Decimal("1234.50"))
    item = browser_a.get(list_url(name)).json()[0]
    assert item["amount"] == "1234.50"
    assert browser_a.get(detail_url(name, obj.pk)).json()["amount"] == "1234.50"
    assert set(item) == {
        "id",
        "category",
        "category_label",
        "amount",
        "date",
        "description",
        "created_at",
        "updated_at",
    }


# --- Validações: data --------------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_date_boundaries(browser_a, name, factory, model, cat, other):
    today = timezone.localdate()
    ok = [
        "2000-01-01",
        today.isoformat(),
        (today + timedelta(days=365)).isoformat(),
        "2024-02-29",
    ]
    for value in ok:
        resp = browser_a.send("post", list_url(name), body(cat, date=value))
        assert resp.status_code == 201, (value, resp.content)

    bad = [
        "1999-12-31",
        "0001-01-01",
        (today + timedelta(days=366)).isoformat(),
        "9999-12-31",
        "2026-02-30",
        "2025-02-29",
        "2026-13-01",
        "31/12/2026",
        "2026-10",
        "hoje",
        "",
        None,
        20261006,
    ]
    for value in bad:
        resp = browser_a.send("post", list_url(name), body(cat, date=value))
        assert resp.status_code == 400, (value, resp.content)
        assert "date" in resp.json()
    assert model.objects.count() == len(ok)


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_patch_date_out_of_range_is_400(
    browser_a, alice, name, factory, model, cat, other
):
    obj = factory(user=alice)
    resp = browser_a.send("patch", detail_url(name, obj.pk), {"date": "1999-01-01"})
    assert resp.status_code == 400
    obj.refresh_from_db()
    assert obj.date == timezone.localdate()


# --- Validações: descrição ---------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
@pytest.mark.parametrize(
    "desc",
    [
        "<script>alert(1)</script>",
        "a < b",
        "a > b",
        "<",
        "x" * 256,
        "  " + "x" * 256 + "  ",
        "nulo\x00aqui",
        None,
        ["a"],
    ],
)
def test_invalid_description_returns_400(
    browser_a, desc, name, factory, model, cat, other
):
    resp = browser_a.send("post", list_url(name), body(cat, description=desc))
    assert resp.status_code == 400, (desc, resp.content)
    assert "description" in resp.json()
    assert not model.objects.exists()


@pytest.mark.parametrize(ARGS, RESOURCES)
@pytest.mark.parametrize(
    ("desc", "expected"),
    [
        ("x" * 255, "x" * 255),
        ("   " + "y" * 255 + "\t\n", "y" * 255),
        ("   ", ""),
        ("", ""),
        ("Pão & café \"especial\" 'ok' ção 🙂", "Pão & café \"especial\" 'ok' ção 🙂"),
        ("&lt;b&gt;", "&lt;b&gt;"),
    ],
)
def test_valid_description_is_trimmed_and_kept(
    browser_a, desc, expected, name, factory, model, cat, other
):
    resp = browser_a.send("post", list_url(name), body(cat, description=desc))
    assert resp.status_code == 201, resp.content
    assert resp.json()["description"] == expected
    assert model.objects.get().description == expected


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_description_is_optional(browser_a, name, factory, model, cat, other):
    data = body(cat)
    del data["description"]
    resp = browser_a.send("post", list_url(name), data)
    assert resp.status_code == 201
    assert resp.json()["description"] == ""


# --- Validações: categoria ---------------------------------------------------


@pytest.mark.parametrize(
    ("name", "valid", "invalid"),
    [
        ("expense", ExpenseCategory.values, IncomeCategory.values),
        ("income", IncomeCategory.values, ExpenseCategory.values),
    ],
)
def test_category_cross_validation(browser_a, name, valid, invalid):
    for value in valid:
        resp = browser_a.send("post", list_url(name), body(value))
        assert resp.status_code == 201, value
        assert resp.json()["category"] == value
    for value in set(invalid) - set(valid):
        resp = browser_a.send("post", list_url(name), body(value))
        assert resp.status_code == 400, value
        assert "category" in resp.json()


@pytest.mark.parametrize(ARGS, RESOURCES)
@pytest.mark.parametrize(
    "value", ["", None, "MERCADO", " mercado", "Outros", "inexistente", 1, ["outros"]]
)
def test_invalid_category_values(browser_a, value, name, factory, model, cat, other):
    resp = browser_a.send("post", list_url(name), body(cat, category=value))
    assert resp.status_code == 400, (value, resp.content)
    assert "category" in resp.json()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_patch_to_other_type_category_is_400(
    browser_a, alice, name, factory, model, cat, other
):
    obj = factory(user=alice)
    before = obj.category
    resp = browser_a.send("patch", detail_url(name, obj.pk), {"category": other})
    assert resp.status_code == 400
    obj.refresh_from_db()
    assert obj.category == before


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_required_fields_and_put_requires_all(
    browser_a, alice, name, factory, model, cat, other
):
    resp = browser_a.send("post", list_url(name), {})
    assert resp.status_code == 400
    assert {"category", "amount", "date"} <= set(resp.json())
    obj = factory(user=alice)
    resp = browser_a.send("put", detail_url(name, obj.pk), {"amount": "5.00"})
    assert resp.status_code == 400
    assert {"category", "date"} <= set(resp.json())


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_non_json_payload_is_rejected(browser_a, name, factory, model, cat, other):
    resp = browser_a.client.post(
        list_url(name),
        "category=x",
        content_type="application/x-www-form-urlencoded",
        HTTP_X_CSRFTOKEN=browser_a.token,
    )
    assert resp.status_code == 415
    resp = browser_a.client.post(
        list_url(name),
        "{nao e json",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=browser_a.token,
    )
    assert resp.status_code == 400
    assert not model.objects.exists()


# --- Filtro de mês -----------------------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_month_filter_boundaries_and_december(
    browser_a, alice, name, factory, model, cat, other
):
    from datetime import date

    dates = [
        date(2025, 11, 30),
        date(2025, 12, 1),
        date(2025, 12, 31),
        date(2026, 1, 1),
        date(2024, 2, 29),
        date(2024, 3, 1),
    ]
    objs = {d: factory(user=alice, date=d) for d in dates}

    def ids(month):
        resp = browser_a.get(list_url(name), data={"month": month})
        assert resp.status_code == 200
        return [item["id"] for item in resp.json()]

    assert ids("2025-12") == [objs[date(2025, 12, 31)].pk, objs[date(2025, 12, 1)].pk]
    assert ids("2026-01") == [objs[date(2026, 1, 1)].pk]
    assert ids("2025-11") == [objs[date(2025, 11, 30)].pk]
    assert ids("2024-02") == [objs[date(2024, 2, 29)].pk]
    assert ids("2024-03") == [objs[date(2024, 3, 1)].pk]
    assert ids("2000-01") == []
    assert len(browser_a.get(list_url(name)).json()) == len(dates)


@pytest.mark.parametrize(ARGS, RESOURCES)
@pytest.mark.parametrize(
    "month",
    [
        "",
        "2026",
        "2026-1",
        "2026-001",
        "26-10",
        "2026-00",
        "2026-13",
        "1999-12",
        "9999-12",
        "2026/10",
        "10-2026",
        "2026-10-01",
        " 2026-10",
        "2026-10 ",
        "2026-10\n",
        "２０２６-１０",
        "abcd-ef",
        "2026-10' OR 1=1--",
    ],
)
def test_month_filter_invalid_formats_400(
    browser_a, month, name, factory, model, cat, other
):
    resp = browser_a.get(list_url(name), data={"month": month})
    assert resp.status_code == 400, month
    assert "month" in resp.json()


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_list_ordering_desc_date_then_id(
    browser_a, alice, name, factory, model, cat, other
):
    from datetime import date

    a = factory(user=alice, date=date(2026, 1, 5))
    b = factory(user=alice, date=date(2026, 1, 5))
    c = factory(user=alice, date=date(2026, 1, 20))
    ids = [i["id"] for i in browser_a.get(list_url(name)).json()]
    assert ids == [c.pk, b.pk, a.pk]


# --- Categorias x CLAUDE.md --------------------------------------------------


def _spec_categories() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Lê a tabela de categorias diretamente do CLAUDE.md."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    section = text.split("### Categorias", 1)[1].split("\n---", 1)[0]
    expenses, incomes = [], []
    cell = re.compile(r"`([a-z_]+)` — (.+)")
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        for col, target in zip(cols, (expenses, incomes), strict=True):
            match = cell.fullmatch(col)
            if match:
                target.append((match.group(1), match.group(2).strip()))
    return expenses, incomes


def test_categories_identical_to_claude_md(browser_a):
    spec_exp, spec_inc = _spec_categories()
    assert len(spec_exp) == 13 and len(spec_inc) == 9
    assert ExpenseCategory.choices == spec_exp
    assert IncomeCategory.choices == spec_inc
    data = browser_a.get(CATEGORIES_URL).json()
    assert set(data) == {"expenses", "incomes"}
    assert [(c["value"], c["label"]) for c in data["expenses"]] == spec_exp
    assert [(c["value"], c["label"]) for c in data["incomes"]] == spec_inc


def test_categories_endpoint_is_read_only(browser_a):
    assert browser_a.send("post", CATEGORIES_URL, {}).status_code == 405
    assert browser_a.send("delete", CATEGORIES_URL).status_code == 405


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_category_label_in_response(browser_a, name, factory, model, cat, other):
    resp = browser_a.send("post", list_url(name), body(cat))
    enum = ExpenseCategory if model is Expense else IncomeCategory
    assert resp.json()["category_label"] == enum(cat).label


# --- Banco: constraints e cascata -------------------------------------------


@pytest.mark.parametrize(ARGS, RESOURCES)
@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-0.01"), Decimal("-100")])
def test_check_constraint_blocks_non_positive_amount_in_db(
    alice, amount, name, factory, model, cat, other
):
    obj = factory(user=alice)
    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.create(user=alice, category=cat, amount=amount, date=obj.date)
    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.filter(pk=obj.pk).update(amount=amount)
    obj.refresh_from_db()
    assert obj.amount > 0


@pytest.mark.parametrize(ARGS, RESOURCES)
def test_index_user_date_exists_in_db(name, factory, model, cat, other):
    from django.db import connection

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor, model._meta.db_table
        )
    assert any(
        c["index"] and c["columns"] == ["user_id", "date"] for c in constraints.values()
    )


def test_deleting_user_cascades_only_own_entries(alice, bob):
    ExpenseFactory(user=alice)
    IncomeFactory(user=alice)
    ExpenseFactory(user=bob)
    IncomeFactory(user=bob)
    alice.delete()
    assert Expense.objects.get().user == bob
    assert Income.objects.get().user == bob


# --- Admin -------------------------------------------------------------------


@pytest.fixture
def admin_client_logged(client):
    admin = User.objects.create_superuser(
        email="root@example.com", password="Adm!n-2026x"
    )
    client.force_login(admin)
    return client


@pytest.mark.parametrize("model_name", ["expense", "income"])
def test_admin_pages_load(admin_client_logged, alice, model_name):
    ExpenseFactory(user=alice, description="cafe")
    IncomeFactory(user=alice, description="sal")
    base = f"admin:finances_{model_name}"
    assert admin_client_logged.get(reverse(f"{base}_changelist")).status_code == 200
    resp = admin_client_logged.get(
        reverse(f"{base}_changelist"), {"q": "alice@example.com"}
    )
    assert resp.status_code == 200
    assert admin_client_logged.get(reverse(f"{base}_add")).status_code == 200
    model = Expense if model_name == "expense" else Income
    obj = model.objects.get()
    resp = admin_client_logged.get(reverse(f"{base}_change", args=[obj.pk]))
    assert resp.status_code == 200
    # autocomplete de usuário (autocomplete_fields) funciona
    resp = admin_client_logged.get(
        reverse("admin:autocomplete"),
        {
            "term": "alice",
            "app_label": "finances",
            "model_name": model_name,
            "field_name": "user",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["text"] == "alice@example.com"


def test_admin_rejects_zero_amount_via_form(admin_client_logged, alice):
    resp = admin_client_logged.post(
        reverse("admin:finances_expense_add"),
        {
            "user": alice.pk,
            "category": "mercado",
            "amount": "0",
            "date": "2026-10-01",
            "description": "",
        },
    )
    assert resp.status_code == 200  # formulário reexibido com erro
    assert not Expense.objects.exists()


def test_admin_forbidden_for_regular_user(client, alice):
    client.force_login(alice)
    resp = client.get(reverse("admin:finances_expense_changelist"))
    assert resp.status_code == 302
