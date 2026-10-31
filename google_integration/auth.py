"""Пользовательская OAuth2-авторизация для настольного приложения.

JSON OAuth-клиента и токен хранятся только в локальной папке .secrets.
Запрашивается доступ к файлам, созданным или выбранным через приложение.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from oauthlib.oauth2 import OAuth2Error


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLIENT_PATH = PROJECT_ROOT / ".secrets" / "oauth-client.json"
TOKEN_PATH = PROJECT_ROOT / ".secrets" / "token.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleLoginError(Exception):
    """Ошибка входа с понятным сообщением без секретных данных."""


def _save_token(credentials: Credentials) -> None:
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    except OSError:
        raise GoogleLoginError("Не удалось сохранить токен в папке .secrets. Проверь права на папку.") from None


def _read_client_config() -> dict:
    try:
        config = json.loads(CLIENT_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise GoogleLoginError("Не найден или повреждён файл .secrets/oauth-client.json.") from None
    installed = config.get("installed") if isinstance(config, dict) else None
    if not isinstance(installed, dict):
        raise GoogleLoginError("Нужен JSON OAuth-клиента типа Desktop app, скачанный из Google Cloud.")
    if not installed.get("client_id") or not installed.get("client_secret"):
        raise GoogleLoginError("В файле OAuth-клиента отсутствуют обязательные поля. Скачай JSON заново.")
    allowed_auth_urls = {
        "https://accounts.google.com/o/oauth2/auth",
        "https://accounts.google.com/o/oauth2/v2/auth",
    }
    if installed.get("token_uri") != "https://oauth2.googleapis.com/token" or installed.get("auth_uri") not in allowed_auth_urls:
        raise GoogleLoginError("В файле указаны неожиданные адреса авторизации. Используй исходный JSON из Google Cloud.")
    return config


def get_credentials(*, interactive: bool = False, force: bool = False) -> Credentials:
    """Читает/обновляет токен; запускает браузер только при interactive=True."""
    if force and not interactive:
        raise GoogleLoginError("Для повторного входа нужен интерактивный запуск авторизации.")

    if TOKEN_PATH.is_file() and not force:
        try:
            credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH))
            if credentials.has_scopes(SCOPES):
                if credentials.valid:
                    return credentials
                if credentials.refresh_token:
                    credentials.refresh(Request())
                    if credentials.valid:
                        _save_token(credentials)
                        return credentials
        except (OSError, ValueError, GoogleAuthError, requests.RequestException):
            if not interactive:
                raise GoogleLoginError("Сохранённый вход больше не действует. Запусти authorize_google.py для повторного входа.") from None

    if not interactive:
        raise GoogleLoginError("Сначала выполни вход: запусти authorize_google.py.")

    config = _read_client_config()
    try:
        flow = InstalledAppFlow.from_client_config(config, scopes=SCOPES, autogenerate_code_verifier=True)
        credentials = flow.run_local_server(
            host="localhost",
            port=0,
            open_browser=True,
            authorization_prompt_message="Заверши вход в открывшемся браузере. Программа ожидает до пяти минут.",
            success_message="Вход завершён. Можешь закрыть эту вкладку и вернуться в VS Code.",
            timeout_seconds=300,
            access_type="offline",
            prompt="consent",
        )
    except (OSError, ValueError, GoogleAuthError, OAuth2Error, requests.RequestException, TimeoutError, AttributeError):
        raise GoogleLoginError("Вход не завершён. Проверь сообщение в браузере и запусти команду ещё раз.") from None

    if not credentials.valid or not credentials.has_scopes(SCOPES):
        raise GoogleLoginError("Google не выдал нужное разрешение для файлов приложения. Повтори вход и проверь разрешение.")
    _save_token(credentials)
    return credentials


def authorized_session(*, interactive: bool = False, force: bool = False) -> AuthorizedSession:
    return AuthorizedSession(get_credentials(interactive=interactive, force=force))
