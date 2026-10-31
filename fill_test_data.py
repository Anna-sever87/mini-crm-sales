"""Создать учебных клиентов, сделки и задачи через API.

Повтор с тем же batch дополняет недостающие записи, не создавая копии.
Реальные записи не удаляются и не меняются.
"""

import argparse
from datetime import date, timedelta
from decimal import Decimal
import random

from crm_client import CRMClient, CRMError


def demo_plan(count=1000, seed=42, batch="lesson3-v1", today=None):
    if not 1 <= count <= 5000:
        raise ValueError("Количество записей должно быть от 1 до 5000.")
    if not batch or len(batch) > 40 or not all(c.isalnum() or c in "-_" for c in batch):
        raise ValueError("Метка batch: до 40 букв, цифр, дефисов или подчёркиваний.")
    rng = random.Random(seed)
    today = today or date.today()
    first_names = ["Анна", "Мария", "Ирина", "Елена", "Ольга", "Иван", "Алексей", "Дмитрий", "Михаил", "Андрей"]
    last_names = ["Смирнова", "Иванова", "Петрова", "Соколова", "Волкова", "Смирнов", "Иванов", "Петров", "Соколов", "Волков"]
    companies = ["Вектор", "Горизонт", "Комфорт", "Север", "Ресурс", "Практика", "Партнёр", "Меридиан"]
    plan = {"clients": [], "deals": [], "tasks": []}
    for index in range(count):
        name_index = rng.randrange(len(first_names))
        plan["clients"].append({
            "name": f"{first_names[name_index]} {last_names[name_index]}",
            "company": f"Учебная компания «{rng.choice(companies)} {index + 1}»" if rng.random() < 0.85 else None,
            "phone": f"+7 (000) {index + 1:07d}",
            "email": f"demo.customer.{index + 1}@example.com",
            "status": rng.choices(["active", "archived"], weights=[85, 15])[0],
            "notes": f"[DEMO:{batch}:clients:{index + 1}] Вымышленный контакт для проверки CRM.",
        })
    for index in range(count):
        amount = Decimal(rng.randint(50000, 50000000)) / 100
        plan["deals"].append({
            "title": f"{rng.choice(['Поставка товаров', 'Заказ оборудования', 'Повторный заказ', 'Продажа материалов'])} №{index + 1}",
            "client_index": rng.randrange(count),
            "amount": str(amount.quantize(Decimal("0.01"))),
            "status": rng.choices(["new", "in_progress", "won", "lost"], weights=[20, 40, 25, 15])[0],
            "expected_close_date": (today + timedelta(days=rng.randint(-30, 60))).isoformat(),
            "notes": f"[DEMO:{batch}:deals:{index + 1}] Учебная сделка.",
        })
    for index in range(count):
        plan["tasks"].append({
            "title": f"{rng.choice(['Позвонить клиенту', 'Отправить предложение', 'Уточнить заказ', 'Согласовать поставку', 'Подготовить документы'])} №{index + 1}",
            "deal_index": rng.randrange(count),
            "due_date": (today + timedelta(days=rng.randint(-10, 30))).isoformat(),
            "status": rng.choices(["todo", "done"], weights=[65, 35])[0],
            "notes": f"[DEMO:{batch}:tasks:{index + 1}] Учебная задача.",
        })
    return plan


def fill_data(api, plan, progress=print):
    saved = {}
    for entity in ("clients", "deals", "tasks"):
        existing = {row["notes"].split("]", 1)[0] + "]": row for row in api.list_all(entity)
                    if row.get("notes", "").startswith("[DEMO:")}
        saved[entity] = []
        created = 0
        for index, specification in enumerate(plan[entity]):
            marker = specification["notes"].split("]", 1)[0] + "]"
            if marker in existing:
                row = existing[marker]
            else:
                payload = dict(specification)
                if entity == "deals":
                    payload["client_id"] = saved["clients"][payload.pop("client_index")]["id"]
                if entity == "tasks":
                    deal = saved["deals"][payload.pop("deal_index")]
                    payload.update(deal_id=deal["id"], client_id=deal["client_id"])
                row = api.create(entity, payload)
                created += 1
            saved[entity].append(row)
            if (index + 1) % 100 == 0 or index + 1 == len(plan[entity]):
                progress(f"{entity}: обработано {index + 1}/{len(plan[entity])}, добавлено {created}")
    return {entity: len(rows) for entity, rows in saved.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000, help="Число записей в каждом разделе")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch", default="lesson3-v1")
    args = parser.parse_args()
    api = CRMClient()
    try:
        plan = demo_plan(args.count, args.seed, args.batch)
        print("Заполняем учебную базу через локальный API. Существующие записи сохраняются.", flush=True)
        result = fill_data(api, plan, lambda message: print(message, flush=True))
        print("Готово:", result)
        print("Всего записей в CRM:", api.stats())
    except (CRMError, ValueError) as error:
        print(error)
        return 1
    finally:
        api.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
