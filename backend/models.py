"""Поля и допустимые значения клиентов, сделок и задач."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ClientStatus(str, Enum):
    active = "active"
    archived = "archived"


class DealStatus(str, Enum):
    new = "new"
    in_progress = "in_progress"
    won = "won"
    lost = "lost"


class TaskStatus(str, Enum):
    todo = "todo"
    done = "done"


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ClientCreate(InputModel):
    name: str = Field(min_length=1, max_length=120, examples=["Анна Смирнова"])
    company: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    status: ClientStatus = ClientStatus.active
    notes: str = Field(default="", max_length=5000)


class ClientUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    company: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    status: ClientStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)


class DealCreate(InputModel):
    title: str = Field(min_length=1, max_length=200, examples=["Продажа партии товаров"])
    client_id: int | None = Field(default=None, gt=0)
    amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2, description="Сумма в рублях")
    status: DealStatus = DealStatus.new
    expected_close_date: date | None = None
    notes: str = Field(default="", max_length=5000)


class DealUpdate(InputModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    client_id: int | None = Field(default=None, gt=0)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    status: DealStatus | None = None
    expected_close_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class TaskCreate(InputModel):
    title: str = Field(min_length=1, max_length=200, examples=["Позвонить клиенту"])
    client_id: int | None = Field(default=None, gt=0)
    deal_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    status: TaskStatus = TaskStatus.todo
    notes: str = Field(default="", max_length=5000)


class TaskUpdate(InputModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    client_id: int | None = Field(default=None, gt=0)
    deal_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    status: TaskStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)


class Record(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime


class ClientRecord(ClientCreate, Record):
    pass


class DealRecord(DealCreate, Record):
    client_name: str | None = None


class TaskRecord(TaskCreate, Record):
    client_name: str | None = None
    deal_title: str | None = None
