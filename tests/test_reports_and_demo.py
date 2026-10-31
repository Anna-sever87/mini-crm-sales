from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import create_app
from fill_test_data import demo_plan, fill_data
from report_data import report_operations, sheet_value, summarize
from reports import ReportError, export_report


class DemoTests(unittest.TestCase):
    def test_repeat_fills_missing_records_and_keeps_existing(self):
        with TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory) / "test.db")) as client:
                class Adapter:
                    def list_all(self, entity):
                        return client.get("/" + entity, params={"limit": 5000}).json()

                    def create(self, entity, payload):
                        response = client.post("/" + entity, json=payload)
                        if response.status_code != 201:
                            raise AssertionError(response.text)
                        return response.json()

                api = Adapter()
                real = api.create("clients", {"name": "Существующая запись", "notes": "Не менять"})
                plan = demo_plan(12, today=date(2026, 10, 31))
                for item in plan["clients"][:3]:
                    api.create("clients", item)
                fill_data(api, plan, lambda message: None)
                fill_data(api, plan, lambda message: None)
                stats = client.get("/stats").json()
                self.assertEqual((stats["clients"], stats["deals"], stats["tasks"]), (13, 12, 12))
                self.assertEqual(client.get(f"/clients/{real['id']}").json()["notes"], "Не менять")
                deals = {row["id"]: row for row in api.list_all("deals")}
                for task in api.list_all("tasks"):
                    self.assertEqual(task["client_id"], deals[task["deal_id"]]["client_id"])

    def test_demo_plan_is_reproducible(self):
        first = demo_plan(1000, today=date(2026, 10, 31))
        second = demo_plan(1000, today=date(2026, 10, 31))
        self.assertEqual(first, second)
        self.assertEqual([len(rows) for rows in first.values()], [1000, 1000, 1000])


class ReportTests(unittest.TestCase):
    def test_summary_total_average_and_empty(self):
        rows = [{"id": 1, "amount": "100.10", "status": "new"},
                {"id": 2, "amount": "200.20", "status": "won"}]
        metrics, statuses = summarize("deals", rows)
        self.assertEqual(metrics[0][1], 2)
        self.assertEqual(metrics[1][1], Decimal("300.30"))
        self.assertEqual(metrics[2][1], Decimal("150.15"))
        self.assertIn("Успешная: 1", statuses)
        empty, _ = summarize("deals", [])
        self.assertEqual(empty[1][1], 0)
        self.assertEqual(empty[2][1], "Нет сделок")

    def test_overdue_excludes_completed_and_today(self):
        rows = [{"status": "done", "due_date": "2026-10-20"},
                {"status": "todo", "due_date": "2026-10-20"},
                {"status": "todo", "due_date": "2026-10-31"},
                {"status": "todo", "due_date": None}]
        metrics, _ = summarize("tasks", rows, today=date(2026, 10, 31))
        self.assertEqual([metric[1] for metric in metrics], [4, 1, 1])

    def test_text_is_literal_and_dates_are_numbers(self):
        self.assertEqual(sheet_value("=1+1")["userEnteredValue"], {"stringValue": "=1+1"})
        self.assertEqual(sheet_value("+70000000000")["userEnteredValue"], {"stringValue": "+70000000000"})
        self.assertEqual(sheet_value("1899-12-31", "date")["userEnteredValue"], {"numberValue": 1})
        self.assertEqual(sheet_value("1500.50", "money")["userEnteredValue"], {"numberValue": 1500.5})

    def test_report_has_all_thousand_records_and_fits_request(self):
        rows = [{**row, "id": index + 1, "client_name": "Учебный клиент"}
                for index, row in enumerate(demo_plan(1000, today=date(2026, 10, 31))["deals"])]
        operations = report_operations("deals", rows, 77)
        update = next(item["updateCells"] for item in operations if "updateCells" in item)
        self.assertEqual(len(update["rows"]), 1009)
        self.assertEqual(update["rows"][-1]["values"][0]["userEnteredValue"], {"numberValue": 1000.0})
        self.assertLess(len(json.dumps({"requests": operations}, ensure_ascii=False).encode()), 2_000_000)
        self.assertFalse(any("formulaValue" in value.get("userEnteredValue", {}) for row in update["rows"] for value in row["values"]))

    def test_export_does_not_claim_success_after_failed_readback(self):
        rows = [{"id": 1, "name": "Клиент", "status": "active"}]
        with patch("reports.authorized_session"), patch("reports.GoogleDrive") as drive_class, \
             patch("reports.GoogleSheets") as sheets_class, patch("reports.ensure_folder", return_value="folder-test"):
            drive_class.return_value.create_google_spreadsheet.return_value = {"id": "report-test"}
            sheets_class.return_value.metadata.return_value = {"sheets": [{"properties": {"sheetId": 0}}]}
            sheets_class.return_value.read.return_value = [[999]]
            with self.assertRaises(ReportError) as failure:
                export_report("clients", rows)
            self.assertIn("выгрузка не подтверждена", str(failure.exception))
            self.assertIn("report-test", str(failure.exception))

    def test_export_returns_link_only_after_readback(self):
        rows = [{"id": 12, "name": "Клиент", "status": "active"}]
        with patch("reports.authorized_session"), patch("reports.GoogleDrive") as drive_class, \
             patch("reports.GoogleSheets") as sheets_class, patch("reports.ensure_folder", return_value="folder-test"):
            drive_class.return_value.create_google_spreadsheet.return_value = {"id": "report-test"}
            sheets_class.return_value.metadata.return_value = {"sheets": [{"properties": {"sheetId": 0}}]}
            sheets_class.return_value.read.side_effect = [[[1]], [[12]]]
            result = export_report("clients", rows)
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["url"], "https://docs.google.com/spreadsheets/d/report-test/edit")


if __name__ == "__main__":
    unittest.main()
