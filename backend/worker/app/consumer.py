"""Consume shadow tasks, commit comparisons, then acknowledge delivery."""

import logging
import os
import time
from functools import lru_cache

import httpx
import pika
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat
from sqlalchemy.exc import SQLAlchemyError

from app.storage import ComparisonStore

logger = logging.getLogger("worker")
QUEUE_NAME = "shadow_tasks"
FAILED_QUEUE = "shadow_tasks.failed"
MAX_ATTEMPTS = 3


class ShadowTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=64)
    features: list[FiniteFloat]
    champion_pred: int = Field(strict=True)
    candidate_url: str


class CandidateResult(BaseModel):
    prediction: int = Field(strict=True)


@lru_cache(maxsize=1)
def get_store():
    return ComparisonStore()


def candidate_endpoint() -> str:
    url = os.getenv("CANDIDATE_URL", "http://model-candidate:8000/predict").rstrip("/")
    return url if url.endswith("/predict") else url + "/predict"


def rabbitmq_parameters():
    parameters = pika.URLParameters(os.getenv("RABBITMQ_URL", "amqp://rabbitmq:5672/"))
    # The current Compose worker supplies separate environment variables.
    if not os.getenv("RABBITMQ_URL") and os.getenv("RABBITMQ_PASSWORD"):
        parameters.host = os.getenv("RABBITMQ_HOST", "rabbitmq")
        parameters.credentials = pika.PlainCredentials(
            os.getenv("RABBITMQ_USER", "model_arena"), os.environ["RABBITMQ_PASSWORD"]
        )
    parameters.socket_timeout = 3
    parameters.stack_timeout = 5
    parameters.blocked_connection_timeout = 5
    parameters.heartbeat = 60
    return parameters


def retry_or_park(ch, method, properties, body, *, permanent: bool) -> None:
    headers = dict(properties.headers or {})
    retries = headers.get("x-shadow-retries", 0)
    if type(retries) is not int or not 0 <= retries < MAX_ATTEMPTS:
        retries = MAX_ATTEMPTS - 1
    target = FAILED_QUEUE if permanent or retries >= MAX_ATTEMPTS - 1 else QUEUE_NAME
    headers["x-shadow-retries"] = retries + 1
    # Confirms are enabled. If re-publishing fails, the original stays unacked
    # and RabbitMQ redelivers it after reconnect.
    ch.basic_publish(
        exchange="",
        routing_key=target,
        body=body,
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
            message_id=properties.message_id,
            headers=headers,
        ),
        mandatory=True,
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)
    logger.warning("Shadow task routed to %s", target)


def process_shadow_task(ch, method, properties, body):
    try:
        task = ShadowTask.model_validate_json(body)
        # Never trust an arbitrary HTTP destination from a queue message.
        if task.candidate_url != candidate_endpoint():
            raise ValueError("Unconfigured candidate endpoint")
    except ValueError:
        retry_or_park(ch, method, properties, body, permanent=True)
        return

    try:
        store = get_store()
        if store.completed(task.request_id):
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            response = client.post(task.candidate_url, json={"features": task.features})
            response.raise_for_status()
            candidate_pred = CandidateResult.model_validate(response.json()).prediction
        store.save(task, candidate_pred)
    except (httpx.HTTPError, ValueError, SQLAlchemyError) as exc:
        # Exception text can expose database DSNs or private input values.
        logger.warning("Shadow processing failed (%s)", type(exc).__name__)
        retry_or_park(ch, method, properties, body, permanent=False)
        return
    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    logging.basicConfig(level=logging.INFO)
    get_store()
    while True:
        try:
            # Wait for API-owned tables before accepting messages. Worker and
            # API start concurrently in Compose.
            get_store().check_schema()
            with pika.BlockingConnection(rabbitmq_parameters()) as connection:
                channel = connection.channel()
                channel.queue_declare(queue=QUEUE_NAME, durable=True)
                channel.queue_declare(queue=FAILED_QUEUE, durable=True)
                channel.confirm_delivery()
                channel.basic_qos(prefetch_count=1)
                channel.basic_consume(
                    queue=QUEUE_NAME, on_message_callback=process_shadow_task, auto_ack=False
                )
                logger.info("Worker listening on %s", QUEUE_NAME)
                channel.start_consuming()
        except KeyboardInterrupt:
            return
        except (pika.exceptions.AMQPError, OSError, SQLAlchemyError, ValueError) as exc:
            logger.warning("Worker reconnecting (%s)", type(exc).__name__)
        time.sleep(5)


if __name__ == "__main__":
    main()
