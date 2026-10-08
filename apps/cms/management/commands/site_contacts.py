"""Просмотр, заполнение и очистка контактов сайта.

Контакты видны в шапке и подвале каждой страницы, поэтому менять их
через консоль безопаснее, чем вручную править базу. Без аргументов
команда ничего не меняет — только показывает текущие значения.

    python manage.py site_contacts                      # показать
    python manage.py site_contacts --clear              # убрать все
    python manage.py site_contacts --phone "+7 ..." \\
                                   --email shop@...     # задать
"""

from django.core.management.base import BaseCommand

from apps.cms.models import SiteSettings

FIELDS = (
    ("phone", "телефон"),
    ("email", "почта"),
    ("address", "адрес"),
    ("work_hours", "часы работы"),
)


class Command(BaseCommand):
    help = "Показывает, задаёт или убирает контакты, видные на сайте"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="убрать все контакты")
        parser.add_argument("--phone", help="телефон")
        parser.add_argument("--email", help="почта")
        parser.add_argument("--address", help="адрес")
        parser.add_argument("--hours", dest="work_hours", help="часы работы")

    def show(self, obj) -> None:
        self.stdout.write("Контакты сайта:")
        for field, label in FIELDS:
            value = getattr(obj, field) or self.style.WARNING("не указано")
            self.stdout.write(f"  {label:12} {value}")
        state = "показан" if obj.show_phone_in_header else "скрыт"
        self.stdout.write(f"  {'в шапке':12} телефон {state}")

    def handle(self, *args, **options):
        obj = SiteSettings.load()

        if options["clear"]:
            for field, _label in FIELDS:
                setattr(obj, field, "")
            obj.show_phone_in_header = False
            obj.save()
            self.stdout.write(self.style.SUCCESS("Контакты убраны с сайта."))
            self.show(obj)
            return

        changed = [
            (field, options[field]) for field, _label in FIELDS if options.get(field) is not None
        ]
        if changed:
            for field, value in changed:
                setattr(obj, field, value)
            if options.get("phone"):
                obj.show_phone_in_header = True
            obj.save()
            self.stdout.write(self.style.SUCCESS("Контакты обновлены."))

        self.show(obj)
