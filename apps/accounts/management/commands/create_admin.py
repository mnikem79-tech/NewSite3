"""Создание администратора сайта одной командой.

Штатная createsuperuser задаёт вопросы по очереди и требует придумать
пароль на месте — по SSH это неудобно, а придуманный second-hand пароль
обычно слабый. Здесь всё задаётся аргументами, а пароль по умолчанию
генерируется стойкий и показывается ровно один раз.

    python manage.py create_admin --email you@example.com
    python manage.py create_admin --email you@example.com --password "..."
    python manage.py create_admin --email you@example.com --reset-password
"""

import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# Без похожих друг на друга символов: пароль часто переписывают руками.
ALPHABET = (
    "".join(c for c in string.ascii_letters if c not in "lIO")
    + "".join(c for c in string.digits if c not in "01")
    + "!@#%*-_=+?"
)


def make_password(length: int = 18) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


class Command(BaseCommand):
    help = "Создаёт администратора или меняет ему пароль"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="адрес для входа")
        parser.add_argument("--password", help="пароль (по умолчанию придумывается)")
        parser.add_argument("--name", default="", help="имя для приветствия в админке")
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="сменить пароль, если такой администратор уже есть",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        email = options["email"].strip().lower()
        password = options["password"] or make_password()
        generated = not options["password"]

        user = User.objects.filter(email=email).first()

        if user and not options["reset_password"]:
            raise CommandError(
                f"Администратор {email} уже есть. " "Сменить пароль: добавьте --reset-password"
            )

        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError("Пароль не принят: " + "; ".join(error.messages)) from error

        if user:
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            if options["name"]:
                user.first_name = options["name"]
            user.save()
            action = "Пароль изменён"
        else:
            user = User.objects.create_superuser(
                email=email, password=password, first_name=options["name"]
            )
            action = "Администратор создан"

        self.stdout.write(self.style.SUCCESS(f"\n{action}: {email}"))
        if generated:
            self.stdout.write("Пароль (показан один раз, сохраните его):")
            self.stdout.write(self.style.WARNING(f"\n    {password}\n"))
            self.stdout.write("Этот пароль остался в истории терминала — очистить: history -c")
        self.stdout.write("\nВход: /admin/\n")
