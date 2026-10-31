"""Настольная CRM: действия пользователя отправляются в локальный API."""

from decimal import Decimal
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from crm_client import CRMClient, CRMError
from google_integration.api import GoogleAPIError, request as google_request
from google_integration.auth import GoogleLoginError, authorized_session
from report_data import STATUS_LABELS, TITLES
from reports import ReportError, export_report, folder_url
from .forms import RecordDialog, date_text


TABLE_COLUMNS = {
    "clients": [("id", "ID", 55), ("name", "Имя клиента", 190), ("company", "Компания", 230),
                ("phone", "Телефон", 150), ("email", "Email", 220), ("status", "Статус", 110)],
    "deals": [("id", "ID", 55), ("title", "Сделка", 260), ("client_name", "Клиент", 190),
              ("amount", "Сумма, руб.", 120), ("status", "Статус", 130), ("expected_close_date", "План завершения", 140)],
    "tasks": [("id", "ID", 55), ("title", "Задача", 260), ("client_name", "Клиент", 180),
              ("deal_title", "Сделка", 240), ("due_date", "Срок", 110), ("status", "Статус", 130)],
}


def money_text(value):
    return f"{Decimal(str(value)):,.2f}".replace(",", " ").replace(".", ",")


class CRMApp(tk.Tk):
    def __init__(self, *, auto_load=True):
        super().__init__()
        self.title("Mini CRM Sales — продажи")
        self.geometry("1180x760")
        self.minsize(1100, 740)
        self.api = CRMClient()
        self.events = queue.Queue()
        self.busy = False
        self.controls = []
        self.tabs = {}
        self.status_var = tk.StringVar(value="Готово к подключению к локальному серверу.")
        self.summary_var = tk.StringVar(value="Клиенты: —    Сделки: —    Задачи: —")
        self.configure(bg="#F4F6FA")
        self.configure_styles()
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        header = ttk.Frame(frame)
        header.pack(fill="x")
        ttk.Label(header, text="Mini CRM Sales", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Локальная CRM для продаж", style="Note.TLabel").pack(side="left", padx=18)
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(13, 8))
        self.button(toolbar, "Обновить данные", self.reload_all).pack(side="left")
        self.button(toolbar, "Войти в Google", self.google_login).pack(side="left", padx=8)
        self.button(toolbar, "Папка отчётов", self.open_folder).pack(side="left")
        ttk.Label(frame, textvariable=self.summary_var).pack(anchor="w", pady=(3, 13))
        self.notebook = ttk.Notebook(frame)
        self.notebook.pack(fill="both", expand=True)
        for entity in TITLES:
            self.create_tab(entity)
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(12, 5))
        ttk.Label(frame, textvariable=self.status_var, wraplength=1100).pack(anchor="w")
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.after(100, self.poll_events)
        if auto_load:
            self.after(150, self.reload_all)

    def configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#F4F6FA")
        style.configure("TLabel", background="#F4F6FA", foreground="#243247", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Note.TLabel", foreground="#64748B", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 10), padding=(9, 6))
        style.configure("TEntry", font=("Segoe UI", 10))
        style.configure("TCombobox", font=("Segoe UI", 10))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28, background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=(5, 7))
        style.configure("TNotebook.Tab", padding=(20, 9), font=("Segoe UI", 10, "bold"))

    def register(self, widget, ready_state="normal"):
        self.controls.append((widget, ready_state))
        return widget

    def button(self, frame, text, command):
        return self.register(ttk.Button(frame, text=text, command=command))

    def create_tab(self, entity):
        page = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(page, text=TITLES[entity])
        query = ttk.Frame(page)
        query.pack(fill="x", pady=(0, 10))
        ttk.Label(query, text="Поиск").pack(side="left", padx=(0, 8))
        search_var = tk.StringVar()
        search = self.register(ttk.Entry(query, textvariable=search_var, width=36))
        search.pack(side="left")
        search.bind("<Return>", lambda event: self.reload_all())
        status_var = tk.StringVar(value="Все статусы")
        status = self.register(ttk.Combobox(query, textvariable=status_var,
            values=["Все статусы", *STATUS_LABELS[entity].values()], state="readonly", width=19), "readonly")
        status.pack(side="left", padx=10)
        self.button(query, "Найти", self.reload_all).pack(side="left")
        count_var = tk.StringVar(value="Показано: 0")
        ttk.Label(query, textvariable=count_var, style="Note.TLabel").pack(side="right")
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=(0, 10))
        self.button(actions, "Добавить", lambda: self.edit(entity)).pack(side="left")
        self.button(actions, "Изменить", lambda: self.edit(entity, editing=True)).pack(side="left", padx=6)
        self.button(actions, "Удалить", lambda: self.delete_record(entity)).pack(side="left")
        if entity == "clients":
            self.button(actions, "В архив", lambda: self.change_status(entity, "archived")).pack(side="left", padx=6)
        if entity == "tasks":
            self.button(actions, "Выполнена", lambda: self.change_status(entity, "done")).pack(side="left", padx=6)
        open_button = self.button(actions, "Открыть отчёт", lambda: self.open_report(entity))
        open_button.pack(side="right")
        open_button.configure(state="disabled")
        self.button(actions, "Выгрузить отчёт", lambda: self.export(entity)).pack(side="right", padx=6)
        grid = ttk.Frame(page)
        grid.pack(fill="both", expand=True)
        grid.rowconfigure(0, weight=1)
        grid.columnconfigure(0, weight=1)
        columns = TABLE_COLUMNS[entity]
        tree = ttk.Treeview(grid, columns=[item[0] for item in columns], show="headings", selectmode="browse")
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=45, stretch=key not in ("id", "amount", "due_date", "expected_close_date"),
                        anchor="e" if key in ("id", "amount") else "w")
        vertical = ttk.Scrollbar(grid, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(grid, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        tree.tag_configure("even", background="#F0F4F9")
        tree.bind("<Double-1>", lambda event: self.edit(entity, editing=True) if not self.busy else None)
        self.tabs[entity] = {"search": search_var, "status": status_var, "count": count_var,
                             "tree": tree, "rows": [], "report_url": "", "open_button": open_button,
                             "loaded": False, "context": ""}

    def set_busy(self, busy):
        self.busy = busy
        for widget, ready_state in self.controls:
            widget.configure(state="disabled" if busy else ready_state)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
            for tab in self.tabs.values():
                tab["open_button"].configure(state="normal" if tab["report_url"] else "disabled")

    def run_job(self, action, success, *, error=None, notice="Выполняем действие…"):
        if self.busy:
            return False
        self.set_busy(True)
        self.status_var.set(notice)

        def worker():
            try:
                result = action()
                self.events.put(("done", result, success))
            except (CRMError, GoogleAPIError, GoogleLoginError, ReportError, ValueError, OSError) as exception:
                self.events.put(("error", str(exception), error))
            except Exception as exception:
                print("Неожиданная ошибка:", type(exception).__name__)
                self.events.put(("error", "Не удалось завершить действие. Проверь списки CRM и папку отчётов перед повтором.", error))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def poll_events(self):
        while True:
            try:
                kind, value, callback = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self.status_var.set(value)
                continue
            self.set_busy(False)
            if kind == "done":
                callback(value)
            else:
                self.status_var.set("Действие не завершено.")
                if callback:
                    callback(value)
                else:
                    messagebox.showerror("Проверь результат", value, parent=self)
        self.after(100, self.poll_events)

    def filters(self, entity):
        tab = self.tabs[entity]
        status = next((code for code, label in STATUS_LABELS[entity].items() if label == tab["status"].get()), None)
        return {"search": tab["search"].get().strip(), "status": status}

    def reload_all(self):
        filters = {entity: self.filters(entity) for entity in TITLES}

        def load():
            rows = {entity: self.api.list_all(entity, **filters[entity]) for entity in TITLES}
            return rows, self.api.stats(), filters

        self.run_job(load, self.render_all, notice="Загружаем записи CRM…")

    def render_all(self, result):
        all_rows, stats, filters = result
        for entity, rows in all_rows.items():
            tab = self.tabs[entity]
            tab["rows"] = rows
            tab["loaded"] = True
            status_label = STATUS_LABELS[entity].get(filters[entity]["status"], "Все статусы")
            search_label = filters[entity]["search"] or "не задан"
            tab["context"] = f"Статус: {status_label}. Поиск: {search_label}."
            tree = tab["tree"]
            tree.delete(*tree.get_children())
            for index, row in enumerate(rows):
                values = []
                for key, title, width in TABLE_COLUMNS[entity]:
                    value = row.get(key)
                    if key == "status":
                        value = STATUS_LABELS[entity].get(value, value)
                    elif key == "amount":
                        value = money_text(value)
                    elif key in ("due_date", "expected_close_date"):
                        value = date_text(value)
                    values.append("" if value is None else value)
                tree.insert("", "end", iid=str(row["id"]), values=values, tags=("even",) if index % 2 else ())
            tab["count"].set(f"Показано: {len(rows)}")
        self.summary_var.set(f"Клиенты: {stats['clients']}    Сделки: {stats['deals']}    Задачи: {stats['tasks']}    Общая сумма сделок: {money_text(stats['total_amount'])} руб.")
        self.status_var.set("Данные обновлены. Сервер CRM доступен.")

    def selected(self, entity):
        selection = self.tabs[entity]["tree"].selection()
        row = next((item for item in self.tabs[entity]["rows"] if selection and str(item["id"]) == selection[0]), None)
        if row is None:
            messagebox.showinfo("Выбери запись", "Сначала выдели строку в таблице.", parent=self)
        return row

    def edit(self, entity, editing=False):
        if self.busy:
            return
        record = self.selected(entity) if editing else None
        if editing and record is None:
            return

        def references():
            if entity == "clients":
                return {"clients": [], "deals": []}
            return {"clients": self.api.list_all("clients"),
                    "deals": self.api.list_all("deals") if entity == "tasks" else []}

        def show_form(data):
            RecordDialog(self, entity, record, data, lambda payload, dialog: self.save_record(entity, record, payload, dialog))

        self.run_job(references, show_form, notice="Готовим форму записи…")

    def save_record(self, entity, record, payload, dialog):
        def save():
            return self.api.update(entity, record["id"], payload) if record else self.api.create(entity, payload)

        def saved(result):
            dialog.destroy()
            self.reload_all()

        started = self.run_job(save, saved, error=dialog.show_error, notice="Сохраняем запись…")
        if not started:
            dialog.show_error("Дождись завершения текущего действия.")

    def delete_record(self, entity):
        record = self.selected(entity)
        if record is None:
            return
        text = f"Удалить запись №{record['id']}?"
        if entity in ("clients", "deals"):
            text += " Связанные записи сохранятся, связь с удалённой записью очистится."
        if messagebox.askyesno("Удаление записи", text, parent=self):
            self.run_job(lambda: self.api.delete(entity, record["id"]), lambda _: self.reload_all(), notice="Удаляем запись…")

    def change_status(self, entity, status):
        record = self.selected(entity)
        if record:
            self.run_job(lambda: self.api.update(entity, record["id"], {"status": status}), lambda _: self.reload_all(), notice="Меняем статус…")

    def google_login(self):
        def login():
            with authorized_session(interactive=True) as session:
                google_request(session, "GET", "https://www.googleapis.com/drive/v3/files", params={"pageSize": 1, "fields": "files(id)"})
            return True

        self.run_job(login, lambda _: self.status_var.set("Вход в Google выполнен. Подключение проверено."), notice="Проверяем вход в Google. При необходимости заверши его в браузере…")

    def export(self, entity):
        if not self.tabs[entity]["loaded"]:
            messagebox.showinfo("Обнови данные", "Сначала загрузи записи CRM кнопкой «Обновить данные».", parent=self)
            return
        rows = [dict(row) for row in self.tabs[entity]["rows"]]
        context = self.tabs[entity]["context"]

        def progress(message):
            self.events.put(("progress", message, None))

        def exported(result):
            tab = self.tabs[entity]
            tab["report_url"] = result["url"]
            tab["open_button"].configure(state="normal")
            self.status_var.set(f"Отчёт «{TITLES[entity]}» создан и проверен. Записей: {result['count']}. Нажми «Открыть отчёт».")

        self.run_job(lambda: export_report(entity, rows, context, progress), exported, notice="Готовим отчёт по текущему списку…")

    def open_report(self, entity):
        url = self.tabs[entity]["report_url"]
        if url:
            webbrowser.open(url)

    def open_folder(self):
        try:
            url = folder_url()
        except ReportError as error:
            messagebox.showerror("Настройки отчётов", str(error), parent=self)
            return
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("Папка отчётов", "Папка Mini CRM Sales Reports создастся на Google Диске при первой выгрузке.", parent=self)

    def close_window(self):
        if self.busy:
            messagebox.showinfo("Выполняется действие", "Дождись завершения операции, затем закрой окно.", parent=self)
            return
        self.api.close()
        self.destroy()
