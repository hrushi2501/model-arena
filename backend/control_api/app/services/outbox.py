"""Retry committed shadow events until RabbitMQ confirms acceptance."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

from app.db.models import ShadowOutbox
from app.db.session import SessionLocal
from app.services.queue import publish_shadow_task

logger = logging.getLogger(__name__)
RETRY_SECONDS = 5


def dispatch_once(sessions=SessionLocal) -> bool:
    """Lock one due event; an interrupted transaction leaves it pending."""
    with sessions.begin() as db:
        event = (
            db.query(ShadowOutbox)
            .filter(ShadowOutbox.available_at <= datetime.now(UTC))
            .order_by(ShadowOutbox.available_at, ShadowOutbox.prediction_id)
            .with_for_update(skip_locked=True)
            .first()
        )
        if event is None:
            return False
        if publish_shadow_task(event.prediction_id, event.payload_json):
            db.delete(event)
        else:
            event.available_at = datetime.now(UTC) + timedelta(seconds=RETRY_SECONDS)
    return True


def dispatch_loop(stop: Event, sessions=SessionLocal):
    while not stop.is_set():
        try:
            if dispatch_once(sessions):
                continue
        except Exception as exc:  # noqa: BLE001 - dispatcher must retain and retry pending events
            logger.warning("Outbox dispatch failed (%s)", type(exc).__name__)
        stop.wait(1)


@asynccontextmanager
async def dispatching(sessions=SessionLocal):
    stop = Event()
    thread = Thread(target=dispatch_loop, args=(stop, sessions), daemon=True, name="shadow-outbox")
    thread.start()
    try:
        yield
    finally:
        stop.set()
        await asyncio.to_thread(thread.join, 10)


if __name__ == "__main__":
    dispatch_loop(Event())
