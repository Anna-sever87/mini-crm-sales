"""SQLite и CRUD. Денежные суммы хранятся целым числом копеек."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import sqlite3


class RecordNotFound(Exception):
    pass


class InvalidData(Exception):
    pass


FIELDS = {
    "clients": {"name", "company", "phone", "email", "status", "notes"},
    "deals": {"title", "client_id", "amount", "status", "expected_close_date", "notes"},
    "tasks": {"title", "client_id", "deal_id", "due_date", "status", "notes"},
}
REQUIRED = {
    "clients": {"name", "status", "notes"},
    "deals": {"title", "amount", "status", "notes"},
    "tasks": {"title", "status", "notes"},
}
SELECTS = {
    "clients": "SELECT c.* FROM clients c",
    "deals": "SELECT d.*, c.name AS client_name FROM deals d LEFT JOIN clients c ON c.id=d.client_id",
    "tasks": """SELECT t.*, c.name AS client_name, d.title AS deal_title FROM tasks t
        LEFT JOIN deals d ON d.id=t.deal_id
        LEFT JOIN clients c ON c.id=COALESCE(t.client_id,d.client_id)""",
}
ALIASES = {"clients": "c", "deals": "d", "tasks": "t"}


class CRMDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL CHECK(length(trim(name))>0),
                    company TEXT, phone TEXT, email TEXT,
                    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS deals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK(length(trim(title))>0),
                    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                    amount_cents INTEGER NOT NULL DEFAULT 0 CHECK(amount_cents>=0),
                    status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','in_progress','won','lost')),
                    expected_close_date TEXT, notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK(length(trim(title))>0),
                    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                    deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
                    due_date TEXT,
                    status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo','done')),
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS deals_client ON deals(client_id);
                CREATE INDEX IF NOT EXISTS tasks_client ON tasks(client_id);
                CREATE INDEX IF NOT EXISTS tasks_deal ON tasks(deal_id);
            """)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _present(row):
        result = dict(row)
        if "amount_cents" in result:
            result["amount"] = str((Decimal(result.pop("amount_cents")) / 100).quantize(Decimal("0.01")))
        return result

    @staticmethod
    def _check_entity(entity):
        if entity not in FIELDS:
            raise InvalidData("Неизвестный раздел CRM.")

    def _get(self, connection, entity, record_id):
        self._check_entity(entity)
        row = connection.execute(SELECTS[entity] + f" WHERE {ALIASES[entity]}.id=?", (record_id,)).fetchone()
        if row is None:
            raise RecordNotFound("Запись не найдена.")
        return self._present(row)

    @staticmethod
    def _check_references(connection, entity, record, record_id=None):
        if entity == "clients":
            return
        client_id = record.get("client_id")
        if client_id is not None and connection.execute("SELECT id FROM clients WHERE id=?", (client_id,)).fetchone() is None:
            raise InvalidData("Указанный клиент не существует.")
        if entity == "tasks" and record.get("deal_id") is not None:
            deal = connection.execute("SELECT client_id FROM deals WHERE id=?", (record["deal_id"],)).fetchone()
            if deal is None:
                raise InvalidData("Указанная сделка не существует.")
            if client_id is not None and deal["client_id"] is not None and client_id != deal["client_id"]:
                raise InvalidData("Клиент задачи должен совпадать с клиентом выбранной сделки.")
        if entity == "deals" and record_id is not None and client_id is not None:
            mismatch = connection.execute(
                "SELECT id FROM tasks WHERE deal_id=? AND client_id IS NOT NULL AND client_id<>? LIMIT 1",
                (record_id, client_id),
            ).fetchone()
            if mismatch:
                raise InvalidData("Сначала исправьте клиентов в связанных задачах, затем меняйте клиента сделки.")

    def _prepare(self, entity, values):
        self._check_entity(entity)
        if set(values) - FIELDS[entity]:
            raise InvalidData("В запросе есть неизвестные поля.")
        if any(values[field] is None for field in REQUIRED[entity] & values.keys()):
            raise InvalidData("Обязательное поле не может быть пустым.")
        result = dict(values)
        if entity == "deals" and "amount" in result:
            try:
                amount = Decimal(str(result.pop("amount")))
                if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
                    raise InvalidData("Сумма должна быть неотрицательной и содержать не более двух знаков после запятой.")
                result["amount_cents"] = int(amount * 100)
            except (InvalidOperation, ValueError):
                raise InvalidData("Некорректная сумма сделки.") from None
        return result

    def get(self, entity, record_id):
        with self.connection() as connection:
            return self._get(connection, entity, record_id)

    def list(self, entity, *, search="", status=None, client_id=None, deal_id=None, limit=200, offset=0):
        self._check_entity(entity)
        alias = ALIASES[entity]
        clauses, params = [], []
        if search:
            # casefold() обеспечивает поиск русских названий без учёта регистра.
            pattern = "%" + search.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            columns = {"clients": ["c.name", "c.company", "c.email", "c.phone"],
                       "deals": ["d.title", "c.name"], "tasks": ["t.title", "c.name", "d.title"]}[entity]
            clauses.append("(" + " OR ".join(f"casefold(COALESCE({col},'')) LIKE ? ESCAPE '\\'" for col in columns) + ")")
            params.extend([pattern] * len(columns))
        if status is not None:
            clauses.append(f"{alias}.status=?")
            params.append(status)
        if client_id is not None:
            if entity == "tasks":
                clauses.append("COALESCE(t.client_id,d.client_id)=?")
            else:
                clauses.append(f"{alias}.client_id=?")
            params.append(client_id)
        if entity == "tasks" and deal_id is not None:
            clauses.append("t.deal_id=?")
            params.append(deal_id)
        query = SELECTS[entity] + (" WHERE " + " AND ".join(clauses) if clauses else "")
        query += f" ORDER BY {alias}.id DESC LIMIT ? OFFSET ?"
        params.extend((limit, offset))
        with self.connection() as connection:
            connection.create_function("casefold", 1, lambda text: text.casefold())
            return [self._present(row) for row in connection.execute(query, params).fetchall()]

    def create(self, entity, values):
        prepared = self._prepare(entity, values)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        prepared.update(created_at=timestamp, updated_at=timestamp)
        with self.connection() as connection:
            self._check_references(connection, entity, values)
            columns = ",".join(prepared)
            placeholders = ",".join("?" for _ in prepared)
            try:
                cursor = connection.execute(f"INSERT INTO {entity} ({columns}) VALUES ({placeholders})", list(prepared.values()))
            except sqlite3.IntegrityError:
                raise InvalidData("Запись не сохранена: проверьте обязательные поля и допустимые статусы.") from None
            return self._get(connection, entity, cursor.lastrowid)

    def update(self, entity, record_id, values):
        prepared = self._prepare(entity, values)
        with self.connection() as connection:
            current = self._get(connection, entity, record_id)
            if not prepared:
                return current
            self._check_references(connection, entity, {**current, **values}, record_id)
            prepared["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            assignments = ",".join(f"{column}=?" for column in prepared)
            try:
                connection.execute(f"UPDATE {entity} SET {assignments} WHERE id=?", [*prepared.values(), record_id])
            except sqlite3.IntegrityError:
                raise InvalidData("Изменение не сохранено: проверьте поля и допустимые статусы.") from None
            return self._get(connection, entity, record_id)

    def delete(self, entity, record_id):
        with self.connection() as connection:
            self._get(connection, entity, record_id)
            connection.execute(f"DELETE FROM {entity} WHERE id=?", (record_id,))

    def stats(self):
        with self.connection() as connection:
            result = {entity: connection.execute(f"SELECT COUNT(*) FROM {entity}").fetchone()[0] for entity in FIELDS}
            row = connection.execute("SELECT COUNT(*),COALESCE(SUM(amount_cents),0) FROM deals").fetchone()
            total = Decimal(row[1]) / 100
            average = total / row[0] if row[0] else Decimal("0")
            result.update(total_amount=str(total.quantize(Decimal("0.01"))),
                          average_amount=str(average.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))
            result["clients_by_status"] = dict(connection.execute("SELECT status,COUNT(*) FROM clients GROUP BY status"))
            result["deals_by_status"] = dict(connection.execute("SELECT status,COUNT(*) FROM deals GROUP BY status"))
            result["tasks_by_status"] = dict(connection.execute("SELECT status,COUNT(*) FROM tasks GROUP BY status"))
            return result
