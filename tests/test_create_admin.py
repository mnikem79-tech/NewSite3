"""Команда создания администратора."""

import re
from io import StringIO

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.accounts.management.commands.create_admin import make_password

# Полный набор проверок пароля — как на боевом сервере. В настройках для
# разработки они ослаблены, и тест без этого ничего бы не проверял.
STRICT = [
    {"NAME": "django.contrib.auth.password_validation." "UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


def run(*args: str) -> str:
    out = StringIO()
    call_command("create_admin", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_creates_superuser_and_prints_password():
    output = run("--email", "Boss@Example.COM", "--name", "Шеф")

    user = get_user_model().objects.get(email="boss@example.com")
    assert user.is_superuser and user.is_staff and user.is_active
    assert user.first_name == "Шеф"

    shown = re.search(r"^\s{4}(\S{18})$", output, re.M)
    assert shown, "пароль не показан"
    assert user.check_password(shown.group(1)), "показан не тот пароль"


@pytest.mark.django_db
def test_generated_password_allows_login():
    output = run("--email", "boss@example.com")
    password = re.search(r"^\s{4}(\S{18})$", output, re.M).group(1)

    assert authenticate(username="boss@example.com", password=password) is not None


@pytest.mark.django_db
def test_existing_admin_is_not_overwritten_silently():
    run("--email", "boss@example.com")

    with pytest.raises(CommandError, match="уже есть"):
        run("--email", "boss@example.com")


@pytest.mark.django_db
def test_reset_password_changes_it():
    first = re.search(r"^\s{4}(\S{18})$", run("--email", "b@e.com"), re.M).group(1)

    second_output = run("--email", "b@e.com", "--reset-password")
    second = re.search(r"^\s{4}(\S{18})$", second_output, re.M).group(1)

    assert first != second
    user = get_user_model().objects.get(email="b@e.com")
    assert user.check_password(second)
    assert not user.check_password(first)


@pytest.mark.django_db
@override_settings(AUTH_PASSWORD_VALIDATORS=STRICT)
def test_weak_password_is_refused():
    with pytest.raises(CommandError, match="Пароль не принят"):
        run("--email", "boss@example.com", "--password", "12345678")

    assert not get_user_model().objects.filter(email="boss@example.com").exists()


@override_settings(AUTH_PASSWORD_VALIDATORS=STRICT)
def test_generated_passwords_always_pass_strict_checks():
    """Генератор не должен изредка выдавать пароль, который сам же отвергнет."""
    for _ in range(200):
        try:
            validate_password(make_password())
        except ValidationError as error:  # pragma: no cover - только при поломке
            pytest.fail(f"сгенерированный пароль отклонён: {error.messages}")


def test_generated_passwords_are_unique():
    assert len({make_password() for _ in range(100)}) == 100
