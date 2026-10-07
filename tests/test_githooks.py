"""Проверка хука, который не пускает секреты в репозиторий.

Хук ломался трижды: не видел значение в кавычках, считал «коротким»
значение с кириллицей и однажды блокировал сам себя из-за примера
в комментарии. Поэтому он проверяется настоящими коммитами во
временном репозитории, а не чтением глазами.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".githooks" / "pre-commit"

# Образцы токенов собираются из кусков: написанные целиком, они заставили бы
# хук заблокировать коммит этого же файла.
SECRET = "SECRET" + "_KEY"
PASSWORD = "DB_" + "PASSWORD"
PAT = "github" + "_pat_" + "11ABCDEFG0abcdefghijklmnop"
SK = "sk" + "-" + "abcdefghij1234567890abcdefghij1234"
AKIA = "AKIA" + "IOSFODNN7EXAMPLE"
BEGIN_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"

# (имя, путь в репозитории, содержимое, должен ли коммит пройти)
CASES = [
    # — секреты, которые обязаны быть пойманы —
    ("секрет латиницей", "s.py", f"{SECRET} = 'aB3xK9mQ7zR2tY5w'", False),
    ("секрет кириллицей", "s.py", f'{SECRET} = "qwerty-очень-длинный-секрет"', False),
    ("пароль без кавычек", "s.py", f"{PASSWORD}=SuperSecret123456789", False),
    ("токен GitHub", "s.py", f"t = '{PAT}'", False),
    ("ключ OpenAI", "s.py", f"k = '{SK}'", False),
    ("ключ AWS", "s.py", f"AWS_ACCESS_KEY={AKIA}", False),
    ("тело приватного ключа", "s.txt", BEGIN_KEY, False),
    ("файл с ключом", "server.key", "неважно", False),
    ("файл сертификата", "cert.pem", "неважно", False),
    ("файл .env", ".env", f"{SECRET}=abc", False),
    ("вложенный .env", "deploy/.env", f"{SECRET}=abc", False),
    # — нормальный код, который обязан пройти —
    ("чтение из окружения", "p.py", f'{SECRET} = os.environ["{SECRET}"]', True),
    ("env() из django-environ", "p.py", f'{SECRET} = env("DJANGO_{SECRET}")', True),
    ("подстановка в bash", "p.sh", f'{PASSWORD}="${{{PASSWORD}}}"', True),
    ("заглушка change-me", "p.py", f'{SECRET} = "change-me-in-production"', True),
    ("подсказка в скобках", "p.md", "TOKEN=<ваш-токен-из-настроек>", True),
    ("образец окружения", ".env.example", f"{SECRET}=замените-на-свой-ключ", True),
    ("обычный код", "p.py", "def total(items): return sum(items)", True),
    ("слово «токен» в тексте", "p.md", "Токен хранится в переменной окружения.", True),
]


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """Временный репозиторий с установленным хуком."""

    def run(*a):
        return git(tmp_path, *a)

    run("init", "-q", "-b", "main")
    run("config", "user.name", "test")
    run("config", "user.email", "test@example.com")
    hooks = tmp_path / ".githooks"
    hooks.mkdir()
    shutil.copy(HOOK, hooks / "pre-commit")
    (hooks / "pre-commit").chmod(0o755)
    run("config", "core.hooksPath", ".githooks")
    (tmp_path / ".gitignore").write_text(".env\n")
    run("add", "-A")
    committed = run("commit", "-q", "-m", "начало")
    assert committed.returncode == 0, "хук заблокировал сам себя"
    return tmp_path


def commit(repo: Path, path: str, body: str) -> bool:
    """Пробует закоммитить файл. Возвращает True, если коммит прошёл."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body + "\n", encoding="utf-8")
    git(repo, "add", "-f", path)
    done = git(repo, "commit", "-q", "-m", "проверка").returncode == 0
    git(repo, "reset", "--hard", "HEAD")
    git(repo, "clean", "-qfd")
    return done


@pytest.mark.parametrize("name,path,body,should_pass", CASES, ids=[c[0] for c in CASES])
def test_hook(repo, name, path, body, should_pass):
    assert commit(repo, path, body) is should_pass


def test_hook_is_executable():
    assert HOOK.exists(), "хук отсутствует"
    assert HOOK.stat().st_mode & 0o111, "хук не исполняемый"
