"""Обработка ошибок Google API без вывода токенов и ключей."""

import requests
from google.auth.exceptions import GoogleAuthError


class GoogleAPIError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def request(session, method, url, **kwargs):
    try:
        response = session.request(method, url, timeout=(10, 90), **kwargs)
    except (requests.RequestException, GoogleAuthError):
        raise GoogleAPIError("Нет ответа Google. Перед повтором выгрузки проверь папку отчётов: файл мог уже создаться.") from None
    if not response.ok:
        messages = {
            400: "Google отклонил данные запроса.",
            401: "Нужно повторно войти в Google.",
            403: "Google отказал в доступе. Проверь разрешение drive.file и включение нужного API.",
            404: "Файл или папка Google не найдены либо недоступны текущему аккаунту.",
            429: "Достигнут лимит запросов Google. Подожди минуту перед повтором.",
        }
        reason = ""
        try:
            reason = response.json().get("error", {}).get("errors", [{}])[0].get("reason", "")
        except (ValueError, IndexError, AttributeError):
            pass
        message = messages.get(response.status_code, "Ошибка сервиса Google. Повтори попытку позже.")
        if reason == "storageQuotaExceeded":
            message = "В аккаунте Google недостаточно места для нового файла."
        elif reason == "accessNotConfigured":
            message = "Нужный Google API не включён в проекте Google Cloud."
        raise GoogleAPIError(f"{message} Код: {response.status_code}.", response.status_code)
    return response.json() if response.content else {}
