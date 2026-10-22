"""Приём картинок из визуального редактора.

Картинка, вставленная в редакторе, попадает в ту же медиатеку, что и
загруженная вручную. Иначе файлы копились бы отдельной кучей, которую
не видно в админке и невозможно переиспользовать.

Ответ отдаётся в формате, которого ждёт загрузчик Jodit.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.cms.models import MediaFile

MAX_SIZE = 12 * 1024 * 1024  # 12 МБ — больше для страницы сайта не нужно
ALLOWED = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}


def _error(message: str) -> JsonResponse:
    """Формат ошибки, который Jodit показывает всплывающей подсказкой."""
    return JsonResponse(
        {"success": False, "data": {"error": 1, "messages": [message]}},
        status=200,  # Jodit читает тело ответа, а не код
    )


@staff_member_required
@require_POST
def upload_image(request):
    uploaded = request.FILES.getlist("files[]") or request.FILES.getlist("files")
    if not uploaded:
        return _error("Файл не получен.")

    saved, errors = [], []
    for item in uploaded:
        if item.size > MAX_SIZE:
            errors.append(f"{item.name}: больше 12 МБ.")
            continue
        if item.content_type not in ALLOWED:
            errors.append(f"{item.name}: это не картинка.")
            continue

        media = MediaFile.objects.create(
            image=item,
            title=item.name.rsplit(".", 1)[0][:200],
        )
        saved.append(media.image.url)

    if not saved:
        return _error(" ".join(errors) or "Не удалось сохранить файл.")

    return JsonResponse(
        {
            "success": True,
            "data": {
                "baseurl": "",
                "files": saved,
                "isImages": [True] * len(saved),
                "messages": errors,
            },
        }
    )
