#!/usr/bin/env python
"""Точка входа Django для управляющих команд."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django не найден. Активировано ли виртуальное окружение? "
            "source /opt/newsite3/.venv/bin/activate"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
