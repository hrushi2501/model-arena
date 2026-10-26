"""Confirmed publisher for persisted outbox payloads; never called by prediction routes."""

import logging
import os

import pika

logger = logging.getLogger(__name__)
QUEUE_NAME = "shadow_tasks"


def publish_shadow_task(request_id: str, payload_json: str) -> bool:
    """Return true only after RabbitMQ confirms the persistent, routable event."""
    try:
        parameters = pika.URLParameters(os.getenv("RABBITMQ_URL", "amqp://rabbitmq:5672/"))
        if not os.getenv("RABBITMQ_URL") and os.getenv("RABBITMQ_PASSWORD"):
            parameters.host = os.getenv("RABBITMQ_HOST", "rabbitmq")
            parameters.credentials = pika.PlainCredentials(
                os.getenv("RABBITMQ_USER", "model_arena"), os.environ["RABBITMQ_PASSWORD"]
            )
        parameters.socket_timeout = 3
        parameters.stack_timeout = 5
        parameters.blocked_connection_timeout = 5
        parameters.connection_attempts = 1
        parameters.heartbeat = 10
        with pika.BlockingConnection(parameters) as connection:
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.confirm_delivery()
            channel.basic_publish(
                exchange="",
                routing_key=QUEUE_NAME,
                body=payload_json,
                properties=pika.BasicProperties(
                    content_type="application/json", delivery_mode=2, message_id=request_id
                ),
                mandatory=True,
            )
        return True
    except (pika.exceptions.AMQPError, OSError, ValueError, TypeError) as exc:
        # Exception text can contain a broker URL with credentials.
        logger.warning("Shadow publish failed (%s)", type(exc).__name__)
        return False
