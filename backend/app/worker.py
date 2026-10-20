"""Celery-воркер: отдельный процесс, который берёт задачи из очереди Redis.

Запуск (из папки backend):
    celery -A app.worker worker --loglevel=info
На Windows добавьте --pool=solo (стандартный пул Celery на Windows не работает).

Зачем очередь: запрос к Google Earth Engine идёт 10–60 секунд. Если делать его прямо в HTTP-запросе,
браузер фермера будет висеть, а API — простаивать. С очередью API сразу отвечает «заявка принята»,
а воркер считает в фоне; фронтенд раз в пару секунд спрашивает статус.
"""

from celery import Celery

from .config import get_settings
from .db import SessionLocal
from .services.pipeline import process_application

settings = get_settings()

celery_app = Celery("harvestpay", broker=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,  # задача подтверждается после выполнения — не потеряется при падении воркера
    worker_prefetch_multiplier=1,  # длинные задачи: не берём лишние про запас
    broker_connection_retry_on_startup=True,
)


# Повторы не нужны: process_application сам ловит ошибки и ставит заявке статус error,
# а аналитик может перезапустить расчёт кнопкой.
@celery_app.task(name="harvestpay.process_application")
def process_application_task(application_id: str) -> None:
    db = SessionLocal()
    try:
        process_application(db, application_id)
    finally:
        db.close()
