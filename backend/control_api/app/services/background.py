"""Small background loops with isolated failures and cooperative shutdown."""

import asyncio
import logging
from contextlib import asynccontextmanager
from threading import Event, Thread

logger = logging.getLogger(__name__)


def run_forever(action, stop, interval=1):
    while not stop.is_set():
        try:
            if action():
                continue
        except Exception as exc:  # noqa: BLE001 - keep durable background jobs alive
            logger.warning("Background action failed (%s)", type(exc).__name__)
        stop.wait(interval)


@asynccontextmanager
async def background(action, name, interval=1):
    stop = Event()
    thread = Thread(target=run_forever, args=(action, stop, interval), daemon=True, name=name)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        await asyncio.to_thread(thread.join, 10)
