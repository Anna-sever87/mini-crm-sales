"""Подготовка данных и расчётов отчёта без обращения к Google."""

from collections import Counter
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP


TITLES = {"clients": "Клиенты", "deals": "Сделки", "tasks": "Задачи"}
STATUS_LABELS = {
    "clients": {"active": "Активный", "archived": "В архиве"},
    "deals": {"new": "Новая", "in_progress": "В работе", "won": "Успешная", "lost": "Проиграна"},
    "tasks": {"todo": "К выполнению", "done": "Выполнена"},
}
# Ключ поля, подпись, тип значения, ширина столбца в пикселях.
COLUMNS = {
    "clients": [("id", "ID", "int", 55), ("name", "Имя клиента", "text", 200),
        ("company", "Компания", "text", 220), ("phone", "Телефон", "text", 150),
        ("email", "Email", "text", 240), ("status", "Статус", "status", 115),
        ("notes", "Примечание", "text", 240), ("created_at", "Создан", "datetime", 165)],
    "deals": [("id", "ID", "int", 55), ("title", "Сделка", "text", 240),
        ("client_name", "Клиент", "text", 200), ("amount", "Сумма в рублях", "money", 135),
        ("status", "Статус", "status", 125), ("expected_close_date", "План завершения", "date", 140),
        ("notes", "Примечание", "text", 220), ("created_at", "Создана", "datetime", 165)],
    "tasks": [("id", "ID", "int", 55), ("title", "Задача", "text", 240),
        ("client_name", "Клиент", "text", 200), ("deal_title", "Сделка", "text", 240),
        ("due_date", "Срок", "date", 115), ("status", "Статус", "status", 145),
        ("notes", "Примечание", "text", 220), ("created_at", "Создана", "datetime", 165)],
}


def summarize(entity, rows, today=None):
    if entity not in TITLES:
        raise ValueError("Неизвестный вид отчёта.")
    statuses = Counter(row["status"] for row in rows)
    if entity == "clients":
        metrics = [("Клиентов", len(rows), "int"), ("Активных", statuses["active"], "int"),
                   ("В архиве", statuses["archived"], "int")]
    elif entity == "deals":
        total = sum((Decimal(str(row["amount"])) for row in rows), Decimal("0"))
        average = (total / len(rows)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if rows else None
        metrics = [("Сделок", len(rows), "int"), ("Общая сумма в рублях", total, "money"),
                   ("Средняя сумма в рублях", average if average is not None else "Нет сделок", "money")]
    else:
        today = today or date.today()
        overdue = sum(row["status"] != "done" and bool(row.get("due_date")) and date.fromisoformat(row["due_date"]) < today for row in rows)
        metrics = [("Задач", len(rows), "int"), ("Выполнено", statuses["done"], "int"),
                   ("Просрочено", overdue, "int")]
    status_text = "; ".join(f"{label}: {statuses[code]}" for code, label in STATUS_LABELS[entity].items())
    return metrics, status_text


def sheet_value(value, kind="text"):
    if value is None or value == "":
        return {"userEnteredValue": {"stringValue": ""}}
    if kind in ("int", "money") and not isinstance(value, str):
        return {"userEnteredValue": {"numberValue": float(value)}}
    if kind == "money":
        try:
            return {"userEnteredValue": {"numberValue": float(Decimal(value))}}
        except Exception:
            return {"userEnteredValue": {"stringValue": str(value)}}
    if kind == "int":
        return {"userEnteredValue": {"numberValue": int(value)}}
    if kind in ("date", "datetime"):
        if kind == "date":
            serial = (date.fromisoformat(value) - date(1899, 12, 30)).days
        else:
            local = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
            serial = (local - datetime(1899, 12, 30)).total_seconds() / 86400
        return {"userEnteredValue": {"numberValue": serial}}
    # Строки всегда записываются как текст, в том числе начинающиеся с '=' и '+'.
    return {"userEnteredValue": {"stringValue": str(value)}}


def rgb(value):
    return {name: int(value[index * 2:index * 2 + 2], 16) / 255 for index, name in enumerate(("red", "green", "blue"))}


def report_operations(entity, rows, sheet_id, context="", now=None):
    columns = COLUMNS[entity]
    metrics, status_text = summarize(entity, rows)
    now = now or datetime.now().astimezone()
    count = len(columns)
    end_row = max(10, 9 + len(rows))

    def grid(start, end, left=0, right=count):
        return {"sheetId": sheet_id, "startRowIndex": start, "endRowIndex": end,
                "startColumnIndex": left, "endColumnIndex": right}

    def style(start, end, formatting, left=0, right=count):
        return {"repeatCell": {"range": grid(start, end, left, right), "cell": {"userEnteredFormat": formatting},
                               "fields": ",".join("userEnteredFormat." + key for key in formatting)}}

    values = [[], [sheet_value("Отчёт по " + {"clients": "клиентам", "deals": "сделкам", "tasks": "задачам"}[entity])],
              [sheet_value(f"Создан {now:%d.%m.%Y %H:%M}. Источник: текущий список CRM. {context}")], [], [], [],
              [sheet_value(status_text)], [], [sheet_value(column[1]) for column in columns]]
    groups = ((0, 3), (3, 6), (6, count))
    values[4] = [sheet_value("") for _ in range(count)]
    values[5] = [sheet_value("") for _ in range(count)]
    for (left, right), (label, value, kind) in zip(groups, metrics):
        values[4][left] = sheet_value(label)
        values[5][left] = sheet_value(value, kind)
    for row in rows:
        cells = []
        for key, label, kind, width in columns:
            value = row.get(key)
            if kind == "status":
                value = STATUS_LABELS[entity].get(value, value)
            cells.append(sheet_value(value, kind))
        values.append(cells)
    if not rows:
        values.append([sheet_value("Нет записей")])

    operations = [
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "title": "Отчёт", "gridProperties": {
            "rowCount": max(50, end_row + 3), "columnCount": count, "hideGridlines": True, "frozenRowCount": 9}},
            "fields": "title,gridProperties"}},
        {"updateCells": {"start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
                         "rows": [{"values": row} for row in values], "fields": "userEnteredValue"}},
        style(0, end_row, {"textFormat": {"fontFamily": "Arial", "fontSize": 10, "foregroundColor": rgb("243247")},
                           "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP"}),
        style(1, 2, {"textFormat": {"fontFamily": "Arial", "fontSize": 16, "bold": True}}),
        style(2, 3, {"textFormat": {"fontFamily": "Arial", "fontSize": 10, "foregroundColor": rgb("64748B")}}),
        style(4, 6, {"backgroundColor": rgb("EDF3F9")}),
        style(5, 6, {"textFormat": {"fontFamily": "Arial", "fontSize": 16, "bold": True}, "horizontalAlignment": "RIGHT"}),
        style(6, 7, {"textFormat": {"fontFamily": "Arial", "fontSize": 10, "foregroundColor": rgb("64748B")}}),
        style(8, 9, {"backgroundColor": rgb("243247"), "horizontalAlignment": "CENTER",
                     "textFormat": {"fontFamily": "Arial", "fontSize": 10, "bold": True, "foregroundColor": rgb("FFFFFF")}}),
        {"addBanding": {"bandedRange": {"range": grid(8, end_row), "rowProperties": {
            "headerColor": rgb("243247"), "firstBandColor": rgb("FFFFFF"), "secondBandColor": rgb("F3F6FA")}}}},
        {"setBasicFilter": {"filter": {"range": grid(8, end_row)}}},
    ]
    for start, end in ((1, 2), (2, 3), (6, 7)):
        operations.append({"mergeCells": {"range": grid(start, end), "mergeType": "MERGE_ALL"}})
    for left, right in groups:
        for row in (4, 5):
            operations.append({"mergeCells": {"range": grid(row, row + 1, left, right), "mergeType": "MERGE_ALL"}})
    formats = {"int": {"type": "NUMBER", "pattern": "#,##0"}, "money": {"type": "NUMBER", "pattern": "#,##0.00"},
               "date": {"type": "DATE", "pattern": "dd.mm.yyyy"}, "datetime": {"type": "DATE_TIME", "pattern": "dd.mm.yyyy hh:mm"}}
    for index, column in enumerate(columns):
        operations.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": index, "endIndex": index + 1},
                           "properties": {"pixelSize": column[3]}, "fields": "pixelSize"}})
        if column[2] in formats:
            operations.append(style(9, end_row, {"numberFormat": formats[column[2]], "horizontalAlignment": "RIGHT"}, index, index + 1))
    for (left, right), (_, _, kind) in zip(groups, metrics):
        operations.append(style(5, 6, {"numberFormat": formats[kind]}, left, right))
    for start, end, height in ((0, 1, 14), (1, 2, 38), (2, 3, 30), (4, 5, 30), (5, 6, 38), (6, 7, 28), (8, 9, 42)):
        operations.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": start, "endIndex": end},
                           "properties": {"pixelSize": height}, "fields": "pixelSize"}})
    return operations
