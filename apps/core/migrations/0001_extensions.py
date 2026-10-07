"""
Расширения PostgreSQL ставятся миграцией, а не руками.

Иначе они есть только в той базе, где их создали вручную: тестовая база,
новая установка из дистрибутива и база после restore останутся без них,
а поиск упадёт с «function similarity() does not exist».

pg_trgm, unaccent и citext с PostgreSQL 13 помечены как trusted — их может
установить владелец базы, суперпользователь не нужен.
"""

from django.contrib.postgres.operations import (
    CITextExtension,
    TrigramExtension,
    UnaccentExtension,
)
from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        TrigramExtension(),
        UnaccentExtension(),
        CITextExtension(),
    ]
