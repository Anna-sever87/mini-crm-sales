"""Проверка API на отдельной временной базе, без Google и рабочей CRM."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from backend.main import create_app


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="mini-crm-test-")
        self.database_path = Path(self.directory.name) / "test.db"
        self.client = TestClient(create_app(self.database_path))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def create(self, entity, **data):
        response = self.client.post("/" + entity, json=data)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_crud_and_safe_unlinking(self):
        customer = self.create("clients", name="Анна Смирнова", company="Учебный клиент")
        deal = self.create("deals", title="Продажа", client_id=customer["id"], amount="1500.50")
        task = self.create("tasks", title="Позвонить", client_id=customer["id"], deal_id=deal["id"])
        self.assertEqual(task["client_name"], customer["name"])
        changed = self.client.patch(f"/tasks/{task['id']}", json={"status": "done"})
        self.assertEqual(changed.json()["status"], "done")
        self.assertEqual(self.client.get("/stats").json()["tasks_by_status"], {"done": 1})
        self.assertEqual(self.client.delete(f"/clients/{customer['id']}").status_code, 204)
        self.assertEqual(self.client.get(f"/clients/{customer['id']}").status_code, 404)
        self.assertIsNone(self.client.get(f"/deals/{deal['id']}").json()["client_id"])
        self.assertIsNone(self.client.get(f"/tasks/{task['id']}").json()["client_id"])
        self.assertEqual(self.client.delete(f"/deals/{deal['id']}").status_code, 204)
        self.assertIsNone(self.client.get(f"/tasks/{task['id']}").json()["deal_id"])
        self.assertEqual(self.client.delete(f"/tasks/{task['id']}").status_code, 204)
        self.assertEqual(self.client.get("/stats").json()["tasks"], 0)

    def test_references_and_atomic_rejection(self):
        first = self.create("clients", name="Клиент один")
        second = self.create("clients", name="Клиент два")
        deal = self.create("deals", title="Сделка", client_id=first["id"])
        self.create("tasks", title="Задача", client_id=first["id"], deal_id=deal["id"])
        self.assertEqual(self.client.post("/deals", json={"title": "Ошибка", "client_id": 9999}).status_code, 422)
        self.assertEqual(self.client.post("/tasks", json={"title": "Ошибка", "deal_id": 9999}).status_code, 422)
        self.assertEqual(self.client.post("/tasks", json={"title": "Ошибка", "client_id": second["id"], "deal_id": deal["id"]}).status_code, 422)
        result = self.client.patch(f"/deals/{deal['id']}", json={"client_id": second["id"]})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.client.get(f"/deals/{deal['id']}").json()["client_id"], first["id"])
        self.assertEqual(self.client.get("/stats").json()["deals"], 1)

    def test_average_is_not_total_and_cents_are_exact(self):
        self.create("deals", title="Первая", amount="100.10")
        self.create("deals", title="Вторая", amount="200.20")
        totals = self.client.get("/stats").json()
        self.assertEqual(totals["total_amount"], "300.30")
        self.assertEqual(totals["average_amount"], "150.15")
        self.assertEqual(totals["deals"], 2)

    def test_half_kopeck_rounding(self):
        self.create("deals", title="Первая", amount="0.01")
        self.create("deals", title="Вторая", amount="0.02")
        totals = self.client.get("/stats").json()
        self.assertEqual(totals["total_amount"], "0.03")
        self.assertEqual(totals["average_amount"], "0.02")

    def test_validation_and_nullable_fields(self):
        self.assertEqual(self.client.post("/clients", json={"name": "   "}).status_code, 422)
        self.assertEqual(self.client.post("/deals", json={"title": "Продажа", "amount": "-1"}).status_code, 422)
        self.assertEqual(self.client.post("/deals", json={"title": "Продажа", "amount": "0.001"}).status_code, 422)
        self.assertEqual(self.client.post("/tasks", json={"title": "Позвонить", "due_date": "2026-02-30"}).status_code, 422)
        self.assertEqual(self.client.post("/clients", json={"name": "Имя", "unexpected": True}).status_code, 422)
        customer = self.create("clients", name="Имя", phone="123")
        self.assertEqual(self.client.patch(f"/clients/{customer['id']}", json={"name": None}).status_code, 422)
        self.assertEqual(self.client.patch(f"/clients/{customer['id']}", json={"notes": None}).status_code, 422)
        cleared = self.client.patch(f"/clients/{customer['id']}", json={"phone": None})
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()["phone"])
        self.assertEqual(self.client.get("/clients?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/deals?status=unknown").status_code, 422)

    def test_search_filters_and_pagination(self):
        first = self.create("clients", name="МАРИЯ ПЕТРОВА", company="План 100%", status="archived")
        second = self.create("clients", name="Иван Иванов", company="План 1000")
        found = self.client.get("/clients", params={"search": "мария"}).json()
        self.assertEqual([item["id"] for item in found], [first["id"]])
        found = self.client.get("/clients", params={"search": "100%"}).json()
        self.assertEqual([item["id"] for item in found], [first["id"]])
        self.assertEqual(len(self.client.get("/clients?status=archived").json()), 1)
        self.assertEqual(self.client.get("/clients?limit=1&offset=1").json()[0]["id"], first["id"])
        self.assertEqual(self.client.get("/clients", params={"search": "%' OR 1=1 --"}).json(), [])
        deal = self.create("deals", title="Поставка", client_id=second["id"])
        self.create("tasks", title="Проверить", deal_id=deal["id"])
        tasks = self.client.get("/tasks", params={"client_id": second["id"]}).json()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["client_name"], second["name"])

    def test_data_survives_new_application_instance(self):
        customer = self.create("clients", name="Сохранённый клиент")
        with TestClient(create_app(self.database_path)) as restarted:
            result = restarted.get(f"/clients/{customer['id']}")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["name"], "Сохранённый клиент")
            self.assertEqual(restarted.get("/health").json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
