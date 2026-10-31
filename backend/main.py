"""FastAPI: операции с клиентами, сделками и задачами."""

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse

from .database import CRMDatabase, InvalidData, RecordNotFound
from .models import (
    ClientCreate, ClientRecord, ClientStatus, ClientUpdate,
    DealCreate, DealRecord, DealStatus, DealUpdate,
    TaskCreate, TaskRecord, TaskStatus, TaskUpdate,
)


def create_app(database_path=None):
    @asynccontextmanager
    async def lifespan(application):
        path = database_path or os.environ.get("CRM_DB_PATH") or Path(__file__).resolve().parent.parent / "data" / "crm.db"
        application.state.database = CRMDatabase(path)
        yield

    application = FastAPI(title="Mini CRM Sales", version="0.1.0", lifespan=lifespan,
                          description="Локальная CRM: клиенты, сделки и задачи. Суммы указаны в рублях.")

    @application.exception_handler(RecordNotFound)
    async def not_found_handler(request, error):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(InvalidData)
    async def invalid_data_handler(request, error):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @application.get("/health", tags=["Проверка сервера"])
    def health(request: Request):
        with request.app.state.database.connection() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "application": "Mini CRM Sales"}

    @application.get("/stats", tags=["Итоги"])
    def stats(request: Request):
        return request.app.state.database.stats()

    @application.get("/clients", response_model=list[ClientRecord], tags=["Клиенты"])
    def list_clients(request: Request, search: str = Query("", max_length=200), status: ClientStatus | None = None,
                     limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0)):
        return request.app.state.database.list("clients", search=search, status=status, limit=limit, offset=offset)

    @application.post("/clients", response_model=ClientRecord, status_code=201, tags=["Клиенты"])
    def add_client(payload: ClientCreate, request: Request):
        return request.app.state.database.create("clients", payload.model_dump(mode="json"))

    @application.get("/clients/{record_id}", response_model=ClientRecord, tags=["Клиенты"])
    def get_client(record_id: int, request: Request):
        return request.app.state.database.get("clients", record_id)

    @application.patch("/clients/{record_id}", response_model=ClientRecord, tags=["Клиенты"])
    def update_client(record_id: int, payload: ClientUpdate, request: Request):
        return request.app.state.database.update("clients", record_id, payload.model_dump(mode="json", exclude_unset=True))

    @application.delete("/clients/{record_id}", status_code=204, tags=["Клиенты"])
    def delete_client(record_id: int, request: Request):
        request.app.state.database.delete("clients", record_id)
        return Response(status_code=204)

    @application.get("/deals", response_model=list[DealRecord], tags=["Сделки"])
    def list_deals(request: Request, search: str = Query("", max_length=200), status: DealStatus | None = None,
                   client_id: int | None = Query(None, gt=0), limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0)):
        return request.app.state.database.list("deals", search=search, status=status, client_id=client_id, limit=limit, offset=offset)

    @application.post("/deals", response_model=DealRecord, status_code=201, tags=["Сделки"])
    def add_deal(payload: DealCreate, request: Request):
        return request.app.state.database.create("deals", payload.model_dump(mode="json"))

    @application.get("/deals/{record_id}", response_model=DealRecord, tags=["Сделки"])
    def get_deal(record_id: int, request: Request):
        return request.app.state.database.get("deals", record_id)

    @application.patch("/deals/{record_id}", response_model=DealRecord, tags=["Сделки"])
    def update_deal(record_id: int, payload: DealUpdate, request: Request):
        return request.app.state.database.update("deals", record_id, payload.model_dump(mode="json", exclude_unset=True))

    @application.delete("/deals/{record_id}", status_code=204, tags=["Сделки"])
    def delete_deal(record_id: int, request: Request):
        request.app.state.database.delete("deals", record_id)
        return Response(status_code=204)

    @application.get("/tasks", response_model=list[TaskRecord], tags=["Задачи"])
    def list_tasks(request: Request, search: str = Query("", max_length=200), status: TaskStatus | None = None,
                   client_id: int | None = Query(None, gt=0), deal_id: int | None = Query(None, gt=0),
                   limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0)):
        return request.app.state.database.list("tasks", search=search, status=status, client_id=client_id, deal_id=deal_id, limit=limit, offset=offset)

    @application.post("/tasks", response_model=TaskRecord, status_code=201, tags=["Задачи"])
    def add_task(payload: TaskCreate, request: Request):
        return request.app.state.database.create("tasks", payload.model_dump(mode="json"))

    @application.get("/tasks/{record_id}", response_model=TaskRecord, tags=["Задачи"])
    def get_task(record_id: int, request: Request):
        return request.app.state.database.get("tasks", record_id)

    @application.patch("/tasks/{record_id}", response_model=TaskRecord, tags=["Задачи"])
    def update_task(record_id: int, payload: TaskUpdate, request: Request):
        return request.app.state.database.update("tasks", record_id, payload.model_dump(mode="json", exclude_unset=True))

    @application.delete("/tasks/{record_id}", status_code=204, tags=["Задачи"])
    def delete_task(record_id: int, request: Request):
        request.app.state.database.delete("tasks", record_id)
        return Response(status_code=204)

    return application


app = create_app()
