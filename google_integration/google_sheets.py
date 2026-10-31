"""Чтение, запись, очистка и оформление Google Таблиц через OAuth2."""

import time
from urllib.parse import quote

from .api import GoogleAPIError, request


class GoogleSheets:
    def __init__(self, session, spreadsheet_id):
        self.session = session
        self.root = "https://sheets.googleapis.com/v4/spreadsheets/" + quote(spreadsheet_id, safe="")

    def metadata(self):
        # Новый файл Drive может стать доступен в Sheets с небольшой задержкой.
        for attempt in range(3):
            try:
                return request(self.session, "GET", self.root, params={"fields": "sheets(properties)"})
            except GoogleAPIError as error:
                if error.status not in (404, 429, 503) or attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))

    def read(self, cell_range):
        result = request(self.session, "GET", self.root + "/values/" + quote(cell_range, safe=""),
                         params={"valueRenderOption": "UNFORMATTED_VALUE"})
        return result.get("values", [])

    def write(self, cell_range, rows):
        return request(self.session, "PUT", self.root + "/values/" + quote(cell_range, safe=""),
                       json={"values": rows}, params={"valueInputOption": "RAW"})

    def append(self, cell_range, rows):
        return request(self.session, "POST", self.root + "/values/" + quote(cell_range, safe="") + ":append",
                       json={"values": rows}, params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"})

    def clear(self, cell_range):
        return request(self.session, "POST", self.root + "/values/" + quote(cell_range, safe="") + ":clear", json={})

    def batch_update(self, operations):
        return request(self.session, "POST", self.root + ":batchUpdate", json={"requests": operations})
