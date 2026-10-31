"""Клиент локального API, общий для окна CRM и заполнения демоданными."""

import requests


class CRMError(Exception):
    pass


class CRMClient:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def close(self):
        self.session.close()

    def request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, self.base_url + path, timeout=(5, 60), **kwargs)
        except requests.RequestException:
            raise CRMError("Нет ответа от сервера CRM. Проверь Docker и обнови список перед повтором операции.") from None
        if not response.ok:
            try:
                detail = response.json().get("detail", "Ошибка запроса")
            except ValueError:
                detail = "Ошибка запроса"
            if isinstance(detail, list):
                detail = "; ".join(".".join(str(p) for p in item.get("loc", [])[1:]) + ": " + item.get("msg", "Проверь поле") for item in detail)
            raise CRMError(f"{detail} (код {response.status_code})")
        return response.json() if response.content else None

    def list_all(self, entity, **filters):
        result = []
        filters = {key: value for key, value in filters.items() if value is not None and value != ""}
        while True:
            page = self.request("GET", "/" + entity, params={**filters, "limit": 1000, "offset": len(result)})
            result.extend(page)
            if len(page) < 1000:
                return result

    def create(self, entity, payload):
        return self.request("POST", "/" + entity, json=payload)

    def update(self, entity, record_id, payload):
        return self.request("PATCH", f"/{entity}/{record_id}", json=payload)

    def delete(self, entity, record_id):
        return self.request("DELETE", f"/{entity}/{record_id}")

    def stats(self):
        return self.request("GET", "/stats")
