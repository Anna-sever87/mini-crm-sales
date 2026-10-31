"""Google Drive: создание, чтение, переименование и перемещение в корзину."""

from urllib.parse import quote

from .api import request


class GoogleDrive:
    ROOT = "https://www.googleapis.com/drive/v3/files"

    def __init__(self, session):
        self.session = session

    def list_files(self, folder_id=None):
        query = "trashed = false"
        if folder_id:
            escaped = folder_id.replace("\\", "\\\\").replace("'", "\\'")
            query += f" and '{escaped}' in parents"
        result, page_token = [], None
        while True:
            params = {"q": query, "fields": "nextPageToken,files(id,name,mimeType,webViewLink)", "pageSize": 1000}
            if page_token:
                params["pageToken"] = page_token
            data = request(self.session, "GET", self.ROOT, params=params)
            result.extend(data.get("files", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return result

    def get_file(self, file_id):
        return request(self.session, "GET", self.ROOT + "/" + quote(file_id, safe=""),
                       params={"fields": "id,name,mimeType,webViewLink,trashed"})

    def create_file(self, name, mime_type, folder_id=None):
        body = {"name": name, "mimeType": mime_type}
        if folder_id:
            body["parents"] = [folder_id]
        return request(self.session, "POST", self.ROOT, json=body, params={"fields": "id,name,mimeType,webViewLink"})

    def create_folder(self, name):
        return self.create_file(name, "application/vnd.google-apps.folder")

    def create_google_spreadsheet(self, name, parent_folder_id):
        return self.create_file(name, "application/vnd.google-apps.spreadsheet", parent_folder_id)

    def rename_file(self, file_id, name):
        return request(self.session, "PATCH", self.ROOT + "/" + quote(file_id, safe=""),
                       json={"name": name}, params={"fields": "id,name,webViewLink"})

    def delete_file(self, file_id):
        """Мягкое удаление: файл перемещается в корзину Google Диска."""
        return request(self.session, "PATCH", self.ROOT + "/" + quote(file_id, safe=""),
                       json={"trashed": True}, params={"fields": "id,trashed"})
