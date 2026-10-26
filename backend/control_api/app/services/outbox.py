"""Retry committed shadow events until RabbitMQ confirms acceptance."""

from datetime import UTC, datetime, timedelta
from functools import partial
from threading import Event

from app.db.models import ShadowOutbox
from app.db.session import SessionLocal
from app.services.background import background, run_forever
from app.services.queue import publish_shadow_task

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


def dispatching(sessions=SessionLocal):
    return background(partial(dispatch_once, sessions), "shadow-outbox")


if __name__ == "__main__":
    run_forever(dispatch_once, Event())
