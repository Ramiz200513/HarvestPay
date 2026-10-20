"""Постановка заявки в обработку. API не знает, кто именно будет считать — это решает настройка."""

from fastapi import BackgroundTasks

from .config import get_settings
from .db import SessionLocal
from .services.pipeline import process_application


def _run_in_background(application_id: str) -> None:
    db = SessionLocal()  # своя сессия: сессия запроса к этому моменту уже закрыта
    try:
        process_application(db, application_id)
    finally:
        db.close()


def enqueue_application(application_id: str, background: BackgroundTasks) -> None:
    if get_settings().task_mode == "celery":
        from .worker import process_application_task  # импорт здесь: в режиме background Celery не нужен

        process_application_task.delay(application_id)
    else:
        background.add_task(_run_in_background, application_id)
