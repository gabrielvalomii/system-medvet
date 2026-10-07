"""
QA — Tarefa 3 (Dashboard): GET /api/dashboard/summary/?month=AAAA-MM.

Testes de caixa-preta pela API com sessão real (login + CSRF) e testes do
serviço ``build_monthly_summary``: formato x CLAUDE.md 4.3, totais/saldo com
valores extremos, porcentagens (soma 100, sem negativos/> 100), limites de
mês, mês padrão em America/Sao_Paulo perto da virada UTC, isolamento A x B,
month inválido, queries constantes, 405 em escrita e 403 sem login.
"""

import inspect
import json
import random
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from finances import services
from finances.models import Expense, ExpenseCategory, Income, IncomeCategory
from finances.services import build_monthly_summary, current_month
from finances.tests.factories import ExpenseFactory, IncomeFactory

pytestmark = pytest.mark.django_db

CSRF_URL = reverse("accounts:csrf")
LOGIN_URL = reverse("accounts:login")
LOGOUT_URL = reverse("accounts:logout")
SUMMARY_URL = reverse("finances:dashboard-summary")

TOP_KEYS = [
    "month",
    "total_expenses",
    "total_incomes",
    "balance",
    "expenses_by_category",
    "incomes_by_category",
]
ITEM_KEYS = ["category", "label", "total", "percent"]
MONEY_RE = re.compile(r"-?[0-9]+\.[0-9]{2}")
OCT = date(2026, 10, 10)
MAX = Decimal("9999999999.99")
CENT = Decimal("0.01")


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
        self.token = self.client.cookies["csrftoken"].value

    def summary(self, month: str | None = None):
        data = {} if month is None else {"month": month}
        return self.client.get(SUMMARY_URL, data)

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


def _bulk(model, user, items):
    """Cria lançamentos em lote: items = [(category, amount, date), ...]."""
    model.objects.bulk_create(
        [model(user=user, category=c, amount=Decimal(a), date=d) for c, a, d in items]
    )


def _psum(items) -> Decimal:
    return sum((Decimal(str(i["percent"])) for i in items), Decimal(0))


def _assert_percent_invariants(items, totals_by_cat=None):
    if not items:
        return
    # Maior resto (Hamilton): soma exatamente 100.00.
    assert _psum(items) == Decimal("100.00"), _psum(items)
    for item in items:
        p = item["percent"]
        assert isinstance(p, float)
        assert 0 <= p <= 100, item
        assert round(p, 2) == p, item
    totals = [Decimal(i["total"]) for i in items]
    assert totals == sorted(totals, reverse=True)
    percents = [i["percent"] for i in items]
    # a ordem dos % acompanha a dos totais (monotônica não crescente)
    assert percents == sorted(percents, reverse=True), percents
    for a, b in zip(items, items[1:], strict=False):
        if Decimal(a["total"]) == Decimal(b["total"]):
            assert abs(Decimal(str(a["percent"])) - Decimal(str(b["percent"]))) <= CENT
    grand = sum(totals, Decimal(0))
    for item in items:
        exact = Decimal(item["total"]) * 100 / grand
        # maior resto: cada % fica a menos de 1 centésimo do valor exato
        assert abs(Decimal(str(item["percent"])) - exact) < CENT, item


# --- Formato x CLAUDE.md 4.3 ------------------------------------------------


def test_format_matches_claude_md_exactly(browser_a, alice):
    ExpenseFactory(user=alice, category="alimentacao", amount=Decimal("800"), date=OCT)
    ExpenseFactory(user=alice, category="gasolina", amount=Decimal("720"), date=OCT)
    IncomeFactory(user=alice, category="salario_fixo", amount=Decimal("5000"), date=OCT)

    resp = browser_a.summary("2026-10")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/json")
    raw = json.loads(resp.content)

    assert list(raw) == TOP_KEYS  # mesmas chaves, mesma ordem do exemplo
    assert raw["month"] == "2026-10"
    for key in ("total_expenses", "total_incomes", "balance"):
        assert isinstance(raw[key], str) and MONEY_RE.fullmatch(raw[key]), key
    assert (raw["total_expenses"], raw["total_incomes"], raw["balance"]) == (
        "1520.00",
        "5000.00",
        "3480.00",
    )
    for key in ("expenses_by_category", "incomes_by_category"):
        assert isinstance(raw[key], list)
        for item in raw[key]:
            assert list(item) == ITEM_KEYS
            assert isinstance(item["category"], str)
            assert isinstance(item["label"], str)
            assert isinstance(item["total"], str) and MONEY_RE.fullmatch(item["total"])
            assert isinstance(item["percent"], float)
    assert raw["expenses_by_category"][0] == {
        "category": "alimentacao",
        "label": "Alimentação",
        "total": "800.00",
        "percent": 52.63,
    }
    assert raw["incomes_by_category"] == [
        {
            "category": "salario_fixo",
            "label": "Rendimento fixo / salário",
            "total": "5000.00",
            "percent": 100.0,
        }
    ]
    # percent é número JSON (100.0), nunca string
    assert b'"percent":100.0' in resp.content.replace(b" ", b"")


def test_empty_month_format(browser_a):
    raw = browser_a.summary("2026-10").json()
    assert raw == {
        "month": "2026-10",
        "total_expenses": "0.00",
        "total_incomes": "0.00",
        "balance": "0.00",
        "expenses_by_category": [],
        "incomes_by_category": [],
    }


def test_response_does_not_leak_user_or_ids(browser_a, alice):
    ExpenseFactory(user=alice, date=OCT, description="segredo-xyz")
    content = browser_a.summary("2026-10").content.decode()
    assert "segredo-xyz" not in content
    assert alice.email not in content
    assert '"id"' not in content and '"user"' not in content


@pytest.mark.parametrize(
    "model, enum, key",
    [
        (Expense, ExpenseCategory, "expenses_by_category"),
        (Income, IncomeCategory, "incomes_by_category"),
    ],
)
def test_all_categories_labels_from_textchoices(browser_a, alice, model, enum, key):
    _bulk(model, alice, [(c, "1.00", OCT) for c in enum.values])
    items = browser_a.summary("2026-10").json()[key]
    assert {i["category"]: i["label"] for i in items} == dict(enum.choices)
    # empate em todos os totais -> ordem alfabética da categoria
    assert [i["category"] for i in items] == sorted(enum.values)
    _assert_percent_invariants(items)


# --- Totais e saldo --------------------------------------------------------


def test_totals_with_cents_no_float_error(browser_a, alice):
    _bulk(
        Expense,
        alice,
        [("lazer", "0.10", OCT), ("lazer", "0.20", OCT), ("luz", "0.01", OCT)]
        + [("agua", "0.01", OCT)] * 99,
    )
    _bulk(Income, alice, [("vendas", "0.07", OCT)] * 3)
    raw = browser_a.summary("2026-10").json()
    assert raw["total_expenses"] == "1.30"
    assert raw["total_incomes"] == "0.21"
    assert raw["balance"] == "-1.09"
    by_cat = {i["category"]: i["total"] for i in raw["expenses_by_category"]}
    assert by_cat == {"agua": "0.99", "lazer": "0.30", "luz": "0.01"}


def test_large_values_summed(browser_a, alice):
    _bulk(Expense, alice, [("aluguel", str(MAX), OCT)] * 3 + [("agua", "0.01", OCT)])
    _bulk(Income, alice, [("vendas", str(MAX), OCT)] * 10 + [("juros", "0.01", OCT)])
    raw = browser_a.summary("2026-10").json()
    assert raw["total_expenses"] == "29999999999.98"
    assert raw["total_incomes"] == "99999999999.91"
    assert raw["balance"] == "69999999999.93"
    exp = raw["expenses_by_category"]
    assert exp[0] == {
        "category": "aluguel",
        "label": "Aluguel / moradia",
        "total": "29999999999.97",
        "percent": 100.0,
    }
    assert exp[1]["total"] == "0.01" and exp[1]["percent"] == 0.0
    _assert_percent_invariants(exp)
    _assert_percent_invariants(raw["incomes_by_category"])


def test_large_values_100_rows_keep_cents(alice):
    _bulk(Expense, alice, [("aluguel", str(MAX), OCT)] * 100 + [("agua", "0.01", OCT)])
    s = build_monthly_summary(alice, "2026-10")
    assert s["total_expenses"] == "999999999999.01"
    assert s["balance"] == "-999999999999.01"


def test_single_max_and_min(browser_a, alice):
    _bulk(Expense, alice, [("outros", "0.01", OCT)])
    _bulk(Income, alice, [("outros", str(MAX), OCT)])
    raw = browser_a.summary("2026-10").json()
    assert raw["total_expenses"] == "0.01"
    assert raw["total_incomes"] == "9999999999.99"
    assert raw["balance"] == "9999999999.98"
    assert raw["expenses_by_category"][0]["percent"] == 100.0


def test_negative_and_zero_balance(browser_a, alice):
    _bulk(Expense, alice, [("luz", "150.55", OCT)])
    _bulk(Income, alice, [("bonus", "150.55", OCT)])
    assert browser_a.summary("2026-10").json()["balance"] == "0.00"
    _bulk(Expense, alice, [("luz", "0.01", OCT)])
    assert browser_a.summary("2026-10").json()["balance"] == "-0.01"


def test_only_expenses_or_only_incomes(browser_a, alice):
    _bulk(Expense, alice, [("saude", "42.00", OCT)])
    raw = browser_a.summary("2026-10").json()
    assert raw["incomes_by_category"] == [] and raw["total_incomes"] == "0.00"
    assert raw["balance"] == "-42.00"


def test_totals_equal_sum_of_categories_and_reflect_crud(browser_a, alice):
    url = reverse("finances:expense-list")
    created = []
    for cat, amount in [("mercado", "10.50"), ("mercado", "4.50"), ("lazer", "20")]:
        r = browser_a.send(
            "post",
            url,
            {"category": cat, "amount": amount, "date": "2026-10-05"},
        )
        assert r.status_code == 201
        created.append(r.json()["id"])
    raw = browser_a.summary("2026-10").json()
    assert raw["total_expenses"] == "35.00"
    assert [(i["category"], i["total"]) for i in raw["expenses_by_category"]] == [
        ("lazer", "20.00"),
        ("mercado", "15.00"),
    ]
    detail = reverse("finances:expense-detail", args=[created[2]])
    assert browser_a.send("patch", detail, {"amount": "1.00"}).status_code == 200
    raw = browser_a.summary("2026-10").json()
    assert raw["total_expenses"] == "16.00"
    assert raw["expenses_by_category"][0]["category"] == "mercado"
    assert browser_a.send("delete", detail).status_code == 204
    raw = browser_a.summary("2026-10").json()
    assert raw["expenses_by_category"] == [
        {"category": "mercado", "label": "Mercado", "total": "15.00", "percent": 100.0}
    ]


# --- Porcentagens ------------------------------------------------------------


@pytest.mark.parametrize("n", [3, 6, 7, 9, 11, 12, 13])
def test_equal_slices_sum_100(alice, n):
    cats = ExpenseCategory.values[:n]
    _bulk(Expense, alice, [(c, "0.01", OCT) for c in cats])
    items = build_monthly_summary(alice, "2026-10")["expenses_by_category"]
    assert len(items) == n
    _assert_percent_invariants(items)


def test_one_huge_many_tiny_no_negative(alice):
    cats = ExpenseCategory.values
    _bulk(Expense, alice, [(cats[0], str(MAX), OCT)])
    _bulk(Expense, alice, [(c, "0.01", OCT) for c in cats[1:]])
    items = build_monthly_summary(alice, "2026-10")["expenses_by_category"]
    assert items[0]["percent"] == 100.0
    assert all(i["percent"] == 0.0 for i in items[1:])
    _assert_percent_invariants(items)


def test_tiny_slices_largest_remainder(alice):
    # total = 200.00 -> cada 0.01 vale exatamente 0.005%; 199.88 vale 99.94%.
    # Truncado: 99.94 + 12 x 0.00 = 99.94 -> faltam 6 centésimos, que vão para
    # as 6 primeiras fatias de 0.01 (resto 0.005, empate pela ordem categoria).
    cats = ExpenseCategory.values
    _bulk(Expense, alice, [(cats[0], "199.88", OCT)])
    _bulk(Expense, alice, [(c, "0.01", OCT) for c in cats[1:]])
    items = build_monthly_summary(alice, "2026-10")["expenses_by_category"]
    _assert_percent_invariants(items)
    assert items[0]["percent"] == 99.94  # valor exato, sem ajuste
    tiny = items[1:]
    assert [i["category"] for i in tiny] == sorted(cats[1:])
    assert [i["percent"] for i in tiny] == [0.01] * 6 + [0.0] * 6
    assert all(0 <= i["percent"] <= 100 for i in items)


@pytest.mark.parametrize("n", [2, 3, 6, 7, 9, 13])
def test_equal_totals_percents_differ_at_most_one_cent(alice, n):
    cats = ExpenseCategory.values[:n]
    _bulk(Expense, alice, [(c, "100.00", OCT) for c in cats])
    items = build_monthly_summary(alice, "2026-10")["expenses_by_category"]
    _assert_percent_invariants(items)
    ps = [Decimal(str(i["percent"])) for i in items]
    assert max(ps) - min(ps) <= CENT, ps


def test_largest_remainder_pure_function_random():
    from finances.services import _largest_remainder_percents

    rng = random.Random(42)  # noqa: S311 - semente fixa, só teste
    for _ in range(3000):
        n = rng.randint(1, 13)
        scale = rng.choice([1, 100, 10**4, 10**9])
        totals = sorted(
            (Decimal(rng.randint(1, scale)) / 100 for _ in range(n)), reverse=True
        )
        grand = sum(totals, Decimal(0))
        ps = _largest_remainder_percents(totals, grand)
        assert sum(ps, Decimal(0)) == Decimal("100.00"), (totals, ps)
        assert all(Decimal(0) <= p <= Decimal(100) for p in ps), ps
        assert all(p == p.quantize(CENT) for p in ps), ps
        assert ps == sorted(ps, reverse=True), (totals, ps)
        for t, p in zip(totals, ps, strict=True):
            assert abs(p - t * 100 / grand) < CENT, (totals, ps)


def test_random_scenarios_percent_invariants(alice):
    rng = random.Random(20261006)  # noqa: S311 - semente fixa, só teste
    for _ in range(60):
        Expense.objects.filter(user=alice).delete()
        Income.objects.filter(user=alice).delete()
        for model, enum in ((Expense, ExpenseCategory), (Income, IncomeCategory)):
            cats = rng.sample(enum.values, rng.randint(1, len(enum.values)))
            rows = []
            for c in cats:
                for _ in range(rng.randint(1, 3)):
                    kind = rng.random()
                    if kind < 0.3:
                        amount = "0.01"
                    elif kind < 0.6:
                        amount = f"{rng.randint(1, 999)}.{rng.randint(0, 99):02d}"
                    else:
                        amount = f"{rng.randint(1, 10**7)}.{rng.randint(0, 99):02d}"
                    rows.append((c, amount, OCT))
            _bulk(model, alice, rows)
        s = build_monthly_summary(alice, "2026-10")
        for key, model in (
            ("expenses_by_category", Expense),
            ("incomes_by_category", Income),
        ):
            items = s[key]
            _assert_percent_invariants(items)
            expected = sum(
                model.objects.filter(user=alice).values_list("amount", flat=True),
                Decimal(0),
            )
            assert sum((Decimal(i["total"]) for i in items), Decimal(0)) == expected
        te, ti = Decimal(s["total_expenses"]), Decimal(s["total_incomes"])
        assert Decimal(s["balance"]) == ti - te


def test_largest_slice_ordering_kept_after_adjustment(alice):
    """Após o ajuste, a 1a fatia (maior total) não deve exibir % menor que a 2a."""
    # 7 fatias com totais quase iguais: cada uma ~14.2857 -> 14.29 (soma 100.03)
    cats = ExpenseCategory.values[:7]
    _bulk(Expense, alice, [(cats[0], "100.01", OCT)])
    _bulk(Expense, alice, [(c, "100.00", OCT) for c in cats[1:]])
    items = build_monthly_summary(alice, "2026-10")["expenses_by_category"]
    _assert_percent_invariants(items)
    percents = [i["percent"] for i in items]
    assert percents[0] >= percents[1], percents


# --- Limites de mês ----------------------------------------------------------


def test_month_boundaries_dec_jan_and_leap(browser_a, alice):
    _bulk(
        Expense,
        alice,
        [
            ("luz", "1.00", date(2025, 11, 30)),
            ("luz", "2.00", date(2025, 12, 1)),
            ("luz", "4.00", date(2025, 12, 31)),
            ("luz", "8.00", date(2026, 1, 1)),
            ("luz", "16.00", date(2026, 1, 31)),
            ("luz", "32.00", date(2026, 2, 1)),
            ("luz", "64.00", date(2024, 2, 28)),
            ("luz", "128.00", date(2024, 2, 29)),
            ("luz", "256.00", date(2024, 3, 1)),
            ("luz", "512.00", date(2026, 2, 28)),
            ("luz", "1024.00", date(2026, 3, 1)),
        ],
    )
    _bulk(Income, alice, [("juros", "5.00", date(2025, 12, 31))])

    def total(month):
        resp = browser_a.summary(month)
        assert resp.status_code == 200
        assert resp.json()["month"] == month
        return resp.json()["total_expenses"]

    assert total("2025-11") == "1.00"
    assert total("2025-12") == "6.00"
    assert total("2026-01") == "24.00"
    assert total("2026-02") == "544.00"
    assert total("2024-02") == "192.00"
    assert total("2024-03") == "256.00"
    assert browser_a.summary("2026-01").json()["total_incomes"] == "0.00"
    assert browser_a.summary("2025-12").json()["balance"] == "-1.00"


@pytest.mark.parametrize("month", ["2000-01", "9998-12"])
def test_extreme_valid_months(browser_a, month):
    resp = browser_a.summary(month)
    assert resp.status_code == 200
    assert resp.json()["month"] == month


# --- Mês padrão (America/Sao_Paulo) ------------------------------------------


@pytest.mark.parametrize(
    "instant_utc, expected",
    [
        (datetime(2026, 11, 1, 2, 59, 59, tzinfo=UTC), "2026-10"),  # SP 23:59:59
        (datetime(2026, 11, 1, 3, 0, 0, tzinfo=UTC), "2026-11"),  # SP 00:00
        (datetime(2027, 1, 1, 2, 30, tzinfo=UTC), "2026-12"),  # virada do ano
        (datetime(2027, 1, 1, 3, 0, tzinfo=UTC), "2027-01"),
        (datetime(2028, 3, 1, 1, 0, tzinfo=UTC), "2028-02"),  # 29/02 em SP
        (datetime(2026, 10, 31, 23, 30, tzinfo=UTC), "2026-10"),
    ],
)
def test_default_month_sao_paulo_near_utc_turn(alice, instant_utc, expected):
    # force_authenticate: a sessão real expiraria com o relógio adiantado.
    client = APIClient()
    client.force_authenticate(user=alice)
    sp_day = instant_utc.astimezone(timezone.get_default_timezone()).date()
    _bulk(Expense, alice, [("lazer", "7.00", sp_day)])
    with mock.patch("django.utils.timezone.now", return_value=instant_utc):
        assert current_month() == expected
        resp = client.get(SUMMARY_URL)
    assert resp.status_code == 200
    raw = resp.json()
    assert raw["month"] == expected
    assert raw["total_expenses"] == "7.00"


def test_default_month_equals_explicit_current_month(browser_a, alice):
    _bulk(Income, alice, [("freelance", "3.21", timezone.localdate())])
    default = browser_a.summary().json()
    explicit = browser_a.summary(timezone.localdate().strftime("%Y-%m")).json()
    assert default == explicit
    assert default["total_incomes"] == "3.21"


# --- Isolamento A x B --------------------------------------------------------


def test_isolation_a_never_sees_b(browser_a, alice, bob):
    _bulk(Expense, bob, [(c, "1000.00", OCT) for c in ExpenseCategory.values])
    _bulk(Income, bob, [(c, "1000.00", OCT) for c in IncomeCategory.values])
    empty = browser_a.summary("2026-10").json()
    assert empty["total_expenses"] == empty["total_incomes"] == "0.00"
    assert empty["expenses_by_category"] == empty["incomes_by_category"] == []

    _bulk(Expense, alice, [("luz", "10.00", OCT)])
    _bulk(Income, alice, [("vendas", "30.00", OCT)])
    raw = browser_a.summary("2026-10").json()
    assert raw["total_expenses"] == "10.00"
    assert raw["total_incomes"] == "30.00"
    assert raw["balance"] == "20.00"
    assert [i["category"] for i in raw["expenses_by_category"]] == ["luz"]
    assert raw["expenses_by_category"][0]["percent"] == 100.0
    assert [i["category"] for i in raw["incomes_by_category"]] == ["vendas"]

    browser_b = Browser(bob)
    raw_b = browser_b.summary("2026-10").json()
    assert raw_b["total_expenses"] == "13000.00"
    assert raw_b["total_incomes"] == "9000.00"
    # default month também isolado
    assert browser_a.summary().json()["total_expenses"] in ("0.00", "10.00")


def test_isolation_user_param_ignored(browser_a, alice, bob):
    _bulk(Expense, bob, [("luz", "99.00", OCT)])
    resp = browser_a.client.get(
        SUMMARY_URL, {"month": "2026-10", "user": bob.pk, "user_id": bob.pk}
    )
    assert resp.status_code == 200
    assert resp.json()["total_expenses"] == "0.00"


# --- month inválido ----------------------------------------------------------


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
        "0000-01",
        "+2026-10",
        "-2026-10",
    ],
)
def test_invalid_month_400(browser_a, month):
    resp = browser_a.summary(month)
    assert resp.status_code == 400, month
    body = resp.json()
    assert list(body) == ["month"]
    assert isinstance(body["month"], list) and body["month"]
    assert all(isinstance(m, str) for m in body["month"])


# --- Métodos e autenticação ---------------------------------------------------


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_write_methods_405_with_csrf(browser_a, alice, method):
    _bulk(Expense, alice, [("luz", "1.00", OCT)])
    resp = browser_a.send(method, SUMMARY_URL + "?month=2026-10", {"x": 1})
    assert resp.status_code == 405
    assert "detail" in resp.json()
    assert Expense.objects.filter(user=alice).count() == 1


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_write_methods_without_csrf_rejected(browser_a, method):
    resp = browser_a.send(method, SUMMARY_URL, {}, csrf=False)
    assert resp.status_code in (403, 405)


def test_head_and_options_do_not_error(browser_a):
    assert browser_a.client.head(SUMMARY_URL).status_code == 200
    resp = browser_a.client.options(SUMMARY_URL)
    assert resp.status_code == 200
    assert "POST" not in resp.get("Allow", "")


@pytest.mark.parametrize("month", [None, "2026-10", "invalido"])
def test_without_login_403(bob, month):
    _bulk(Expense, bob, [("luz", "1.00", OCT)])
    client = APIClient(enforce_csrf_checks=True)
    data = {} if month is None else {"month": month}
    resp = client.get(SUMMARY_URL, data)
    assert resp.status_code == 403  # autenticação antes da validação do mês
    assert "detail" in resp.json()
    assert "1.00" not in resp.content.decode()


def test_after_logout_403(browser_a):
    assert browser_a.summary("2026-10").status_code == 200
    assert browser_a.send("post", LOGOUT_URL).status_code in (200, 204)
    assert browser_a.summary("2026-10").status_code == 403


# --- Agregação no banco / queries constantes ---------------------------------


@pytest.mark.parametrize("rows", [0, 1, 13, 200])
def test_service_constant_queries(alice, django_assert_num_queries, rows):
    cats = ExpenseCategory.values
    icats = IncomeCategory.values
    _bulk(Expense, alice, [(cats[i % 13], "1.23", OCT) for i in range(rows)])
    _bulk(Income, alice, [(icats[i % 9], "4.56", OCT) for i in range(rows)])
    with django_assert_num_queries(4):
        build_monthly_summary(alice, "2026-10")


@pytest.mark.parametrize("rows", [0, 50])
def test_view_queries_do_not_grow(rows, django_assert_max_num_queries, alice):
    client = APIClient()
    client.force_authenticate(user=alice)
    _bulk(Expense, alice, [("luz", "1.00", OCT)] * rows)
    _bulk(Income, alice, [("juros", "1.00", OCT)] * rows)
    with django_assert_max_num_queries(4):
        assert client.get(SUMMARY_URL, {"month": "2026-10"}).status_code == 200


def test_service_aggregates_in_db_code_review():
    """Revisão estática: agregação via Sum/annotate, sem somar amounts em Python."""
    src = inspect.getsource(services._by_category)
    assert "aggregate(total=Sum(" in src
    assert '.values("category")' in src and ".annotate(total=Sum(" in src
    # nenhum loop percorre lançamentos individuais (só linhas agregadas)
    assert "for row in rows" in src and ".objects.all()" not in src
    assert "float(" not in src.replace('"percent": float(percent)', "")
