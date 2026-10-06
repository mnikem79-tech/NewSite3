"""
Модель пользователя NewSite3.

Заводится ДО первой миграции: сменить AUTH_USER_MODEL в работающем проекте
практически невозможно без ручной пересборки базы.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Менеджер пользователей с логином по e-mail вместо username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_("E-mail обязателен"))
        # Приводим к нижнему регистру целиком: Django нормализует только
        # доменную часть, а нам нужно, чтобы Ivan@mail.ru и ivan@mail.ru
        # были одним пользователем.
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Суперпользователь должен иметь is_staff=True"))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Суперпользователь должен иметь is_superuser=True"))

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Пользователь сайта: и покупатель, и сотрудник — различаются флагами и группами."""

    email = models.EmailField(_("e-mail"), unique=True)
    first_name = models.CharField(_("имя"), max_length=150, blank=True)
    last_name = models.CharField(_("фамилия"), max_length=150, blank=True)
    phone = models.CharField(_("телефон"), max_length=32, blank=True)

    is_staff = models.BooleanField(
        _("доступ в админку"),
        default=False,
        help_text=_("Может входить в административную панель."),
    )
    is_active = models.BooleanField(
        _("активен"),
        default=True,
        help_text=_("Снимите флаг вместо удаления — история заказов сохранится."),
    )
    date_joined = models.DateTimeField(_("дата регистрации"), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("пользователь")
        verbose_name_plural = _("пользователи")
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email).lower()

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_short_name(self):
        return self.first_name or self.email.split("@")[0]
