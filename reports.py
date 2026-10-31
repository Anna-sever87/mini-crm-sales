"""Выгрузка снимка списка CRM в новый файл Google Таблицы."""

from datetime import datetime
import json
from pathlib import Path
import secrets

from google_integration.api import GoogleAPIError
from google_integration.auth import authorized_session
from google_integration.google_drive import GoogleDrive
from google_integration.google_sheets import GoogleSheets
from report_data import TITLES, report_operations


CONFIG_PATH = Path(__file__).resolve().parent / "config.local.json"


class ReportError(Exception):
    pass


def settings():
    if not CONFIG_PATH.exists():
        return {}
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, ValueError):
        raise ReportError("Не удалось прочитать config.local.json. Проверь файл настроек.") from None


def folder_url():
    folder_id = settings().get("reports_folder_id")
    return "https://drive.google.com/drive/folders/" + folder_id if folder_id else None


def ensure_folder(drive):
    config = settings()
    folder_id = config.get("reports_folder_id")
    if folder_id:
        metadata = drive.get_file(folder_id)
        if metadata.get("trashed") or metadata.get("mimeType") != "application/vnd.google-apps.folder":
            raise ReportError("Сохранённая папка отчётов удалена или недоступна. Проверь папку на Google Диске.")
        return folder_id
    created = drive.create_folder("Mini CRM Sales Reports")
    config["reports_folder_id"] = created["id"]
    try:
        CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        raise ReportError("Папка отчётов создана в Google, но её адрес не удалось сохранить в config.local.json.") from None
    return created["id"]


def export_report(entity, rows, context="", progress=lambda message: None):
    if entity not in TITLES:
        raise ReportError("Неизвестный вид отчёта.")
    # Все расчёты и проверка типов выполняются до создания файлов в Google.
    operations = report_operations(entity, rows, sheet_id=0, context=context)
    title = f"{TITLES[entity]} {datetime.now():%d.%m.%Y %H-%M-%S} {secrets.token_hex(2)}"
    progress("Подключаемся к Google и проверяем папку отчётов…")
    with authorized_session() as session:
        drive = GoogleDrive(session)
        report_folder = ensure_folder(drive)
        progress("Создаём новую Google Таблицу…")
        created = drive.create_google_spreadsheet(title, report_folder)
        url = "https://docs.google.com/spreadsheets/d/" + created["id"] + "/edit"
        sheets = GoogleSheets(session, created["id"])
        try:
            sheet_id = sheets.metadata()["sheets"][0]["properties"]["sheetId"]
            if sheet_id != 0:
                operations = report_operations(entity, rows, sheet_id=sheet_id, context=context)
            progress(f"Записываем и оформляем {len(rows)} записей…")
            sheets.batch_update(operations)
            progress("Проверяем записанный отчёт…")
            if sheets.read("'Отчёт'!A6") != [[len(rows)]]:
                raise ReportError("Не совпало количество записей в итогах отчёта.")
            if rows and sheets.read(f"'Отчёт'!A{9 + len(rows)}") != [[rows[-1]["id"]]]:
                raise ReportError("Не удалось подтвердить запись последней строки отчёта.")
        except (GoogleAPIError, ReportError, KeyError, IndexError) as error:
            raise ReportError(f"Файл создан, но выгрузка не подтверждена. {error}\nПроверь файл перед повтором:\n{url}") from None
    return {"url": url, "folder_url": "https://drive.google.com/drive/folders/" + report_folder,
            "title": title, "count": len(rows)}
