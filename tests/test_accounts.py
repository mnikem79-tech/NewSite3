"""Базовые проверки кастомной модели пользователя."""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_create_user_normalizes_email():
    user = User.objects.create_user(email="Ivan@Example.COM", password="secret123")
    assert user.email == "ivan@example.com"
    assert user.is_active
    assert not user.is_staff


@pytest.mark.django_db
def test_create_superuser():
    admin = User.objects.create_superuser(email="admin@example.com", password="secret123")
    assert admin.is_staff and admin.is_superuser


@pytest.mark.django_db
def test_email_is_required():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="secret123")
