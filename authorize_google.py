r"""Вход через браузер и проверка доступа к Google Drive.

Запуск: .venv\Scripts\python.exe authorize_google.py
Повторный вход с выбором аккаунта: добавить --force.
Проверка не создаёт, не изменяет и не удаляет файлы Google Диска.
"""

import argparse

import requests
from google.auth.exceptions import GoogleAuthError

from google_integration.auth import GoogleLoginError, authorized_session


def main() -> int:
    parser = argparse.ArgumentParser(description="Вход в Google для Mini CRM Sales")
    parser.add_argument("--force", action="store_true", help="Заново пройти вход через браузер")
    args = parser.parse_args()
    print("Проверяем вход в Google…", flush=True)
    try:
        with authorized_session(interactive=True, force=args.force) as session:
            response = session.get(
                "https://www.googleapis.com/drive/v3/files",
                params={"pageSize": 1, "fields": "files(id)", "q": "trashed = false"},
                timeout=30,
            )
            if not response.ok:
                print(f"Google Drive вернул код {response.status_code}.")
                print("Проверь включение Google Drive API и разрешение drive.file в настройках приложения.")
                return 1
    except GoogleLoginError as error:
        print(error)
        return 1
    except (GoogleAuthError, requests.RequestException):
        print("Не удалось получить ответ Google Drive. Проверь соединение и повтори запуск.")
        return 1

    print("Вход в Google выполнен. Доступ к Google Drive проверен.")
    print("Токен сохранён в .secrets/token.json и исключён из GitHub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
