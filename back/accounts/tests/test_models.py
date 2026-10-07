import pytest
from django.db import IntegrityError, transaction

from accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_uses_email_and_hashes_password():
    user = User.objects.create_user(email="  Ana@Example.COM ", password="x-Pass-123")
    assert user.email == "ana@example.com"
    assert user.password != "x-Pass-123"
    assert user.check_password("x-Pass-123")
    assert not user.is_staff
    assert not user.is_superuser
    assert str(user) == "ana@example.com"


def test_user_has_no_username_field():
    assert User.USERNAME_FIELD == "email"
    assert "username" not in [f.name for f in User._meta.get_fields()]


def test_create_user_requires_email():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="x")


def test_email_is_unique_case_insensitive():
    User.objects.create_user(email="dup@example.com", password="x")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="DUP@example.com", password="x")


def test_create_superuser():
    admin = User.objects.create_superuser(email="root@example.com", password="x")
    assert admin.is_staff
    assert admin.is_superuser


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
def test_create_superuser_rejects_false_flags(flag):
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="root@example.com", password="x", **{flag: False}
        )


def test_user_without_password_has_unusable_password():
    user = User.objects.create_user(email="nopass@example.com")
    assert not user.has_usable_password()


def test_save_normalizes_email_outside_manager():
    user = User(email="  Mixed@Example.COM ")
    user.set_password("x")
    user.save()
    user.refresh_from_db()
    assert user.email == "mixed@example.com"


def test_case_duplicate_blocked_even_bypassing_save():
    """QA-T1-05: a UniqueConstraint(Lower) barra também update()/bulk_create."""
    User.objects.create_user(email="dup@example.com", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        User(email="DUP@example.com").save()
    other = User.objects.create_user(email="other@example.com", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=other.pk).update(email="DUP@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(email="Dup@Example.com")])


def test_get_by_natural_key_handles_legacy_duplicates(monkeypatch):
    """Defesa em profundidade: duplicados legados não podem gerar 500."""
    user = User.objects.create_user(email="dup@example.com", password="x")
    original_get = User.objects.get
    calls = []

    def fake_get(**kwargs):
        calls.append(kwargs)
        if "email__iexact" in kwargs:
            raise User.MultipleObjectsReturned
        return original_get(**kwargs)

    monkeypatch.setattr(User.objects, "get", fake_get)
    assert User.objects.get_by_natural_key(" DUP@example.com") == user
    assert calls[-1] == {"email": "dup@example.com"}
