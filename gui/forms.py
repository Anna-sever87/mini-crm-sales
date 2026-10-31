"""Формы добавления и редактирования записей."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import messagebox, ttk

from report_data import STATUS_LABELS, TITLES


def date_text(value):
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y") if value else ""


def parse_date(value):
    value = value.strip()
    if not value:
        return None
    for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError("Введи существующую дату в формате ДД.ММ.ГГГГ.")


class RecordDialog(tk.Toplevel):
    def __init__(self, owner, entity, record, references, on_save):
        super().__init__(owner)
        self.entity, self.record, self.on_save = entity, record or {}, on_save
        self.references = references
        self.variables, self.id_maps = {}, {}
        self.saving = False
        self.title(("Изменить запись — " if record else "Добавить запись — ") + TITLES[entity])
        self.geometry("660x640")
        self.minsize(620, 620)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        frame = ttk.Frame(self, padding=22)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        self.frame = frame
        self.next_row = 0
        if entity == "clients":
            self.entry("name", "Имя клиента *")
            self.entry("company", "Компания")
            self.entry("phone", "Телефон")
            self.entry("email", "Email")
        else:
            self.entry("title", "Название *")
            self.reference("client_id", "Клиент", references["clients"], "name")
            if entity == "deals":
                self.entry("amount", "Сумма в рублях", self.record.get("amount", "0.00"))
                self.entry("expected_close_date", "План завершения", date_text(self.record.get("expected_close_date")))
            else:
                deal_box = self.reference("deal_id", "Сделка", references["deals"], "title")
                deal_box.bind("<<ComboboxSelected>>", self.select_deal)
                self.entry("due_date", "Срок", date_text(self.record.get("due_date")))
            ttk.Label(frame, text="Даты: ДД.ММ.ГГГГ. Необязательную дату можно оставить пустой.", style="Note.TLabel", wraplength=580).grid(row=self.next_row, column=0, columnspan=2, sticky="w", pady=(0, 8))
            self.next_row += 1
        labels = STATUS_LABELS[entity]
        current = self.record.get("status", next(iter(labels)))
        self.variables["status"] = tk.StringVar(value=labels[current])
        ttk.Label(frame, text="Статус").grid(row=self.next_row, column=0, sticky="w", pady=7)
        ttk.Combobox(frame, textvariable=self.variables["status"], values=list(labels.values()), state="readonly").grid(row=self.next_row, column=1, sticky="ew", padx=(14, 0), pady=7)
        self.next_row += 1
        ttk.Label(frame, text="Примечание").grid(row=self.next_row, column=0, sticky="nw", pady=7)
        self.notes = tk.Text(frame, width=40, height=5, wrap="word", font=("Segoe UI", 10), relief="solid", borderwidth=1)
        self.notes.insert("1.0", self.record.get("notes", ""))
        self.notes.grid(row=self.next_row, column=1, sticky="nsew", padx=(14, 0), pady=7)
        frame.rowconfigure(self.next_row, weight=1)
        self.next_row += 1
        buttons = ttk.Frame(frame)
        buttons.grid(row=self.next_row, column=0, columnspan=2, sticky="e", pady=(18, 0))
        self.cancel_button = ttk.Button(buttons, text="Отмена", command=self.cancel)
        self.cancel_button.pack(side="left", padx=5)
        self.save_button = ttk.Button(buttons, text="Сохранить", command=self.submit)
        self.save_button.pack(side="left", padx=5)
        self.grab_set()
        self.focus_set()

    def entry(self, key, label, value=None):
        self.variables[key] = tk.StringVar(value=self.record.get(key, "") or "" if value is None else value)
        ttk.Label(self.frame, text=label).grid(row=self.next_row, column=0, sticky="w", pady=7)
        ttk.Entry(self.frame, textvariable=self.variables[key]).grid(row=self.next_row, column=1, sticky="ew", padx=(14, 0), pady=7)
        self.next_row += 1

    def reference(self, key, label, records, name_key):
        choices = {"Не выбран": None}
        choices.update({f"{row['id']} — {row[name_key]}": row["id"] for row in records})
        self.id_maps[key] = choices
        current = next((text for text, record_id in choices.items() if record_id == self.record.get(key)), "Не выбран")
        self.variables[key] = tk.StringVar(value=current)
        ttk.Label(self.frame, text=label).grid(row=self.next_row, column=0, sticky="w", pady=7)
        box = ttk.Combobox(self.frame, textvariable=self.variables[key], values=list(choices), state="readonly")
        box.grid(row=self.next_row, column=1, sticky="ew", padx=(14, 0), pady=7)
        self.next_row += 1
        return box

    def select_deal(self, _=None):
        deal_id = self.id_maps["deal_id"].get(self.variables["deal_id"].get())
        deal = next((row for row in self.references["deals"] if row["id"] == deal_id), None)
        if deal and deal.get("client_id") is not None:
            choice = next((text for text, value in self.id_maps["client_id"].items() if value == deal["client_id"]), None)
            if choice:
                self.variables["client_id"].set(choice)

    def payload(self):
        data = {key: value.get().strip() for key, value in self.variables.items()}
        required = "name" if self.entity == "clients" else "title"
        if not data[required]:
            raise ValueError("Заполни поле со звёздочкой.")
        data["status"] = next(code for code, label in STATUS_LABELS[self.entity].items() if label == data["status"])
        for key, choices in self.id_maps.items():
            data[key] = choices[data[key]]
        for key in ("due_date", "expected_close_date"):
            if key in data:
                data[key] = parse_date(data[key])
        if "amount" in data:
            try:
                amount = Decimal(data["amount"].replace(" ", "").replace(",", "."))
                if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
                    raise ValueError
                data["amount"] = str(amount.quantize(Decimal("0.01")))
            except (InvalidOperation, ValueError):
                raise ValueError("Укажи неотрицательную сумму с точностью до копейки.") from None
        data["notes"] = self.notes.get("1.0", "end-1c").strip()
        if self.entity == "clients":
            for key in ("company", "phone", "email"):
                data[key] = data[key] or None
        return data

    def submit(self):
        try:
            payload = self.payload()
        except ValueError as error:
            messagebox.showwarning("Проверь поля", str(error), parent=self)
            return
        self.saving = True
        self.save_button.configure(state="disabled")
        self.cancel_button.configure(state="disabled")
        self.on_save(payload, self)

    def show_error(self, message):
        self.saving = False
        self.save_button.configure(state="normal")
        self.cancel_button.configure(state="normal")
        messagebox.showerror("Не удалось сохранить", message, parent=self)

    def cancel(self):
        if not self.saving:
            self.destroy()
