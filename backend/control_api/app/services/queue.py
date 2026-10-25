"""Blocking publisher; call from a background task, never on the response path."""

import json
import logging
import os

import pika

logger = logging.getLogger(__name__)
QUEUE_NAME = "shadow_tasks"


def publish_shadow_task(
    request_id: str, features: list[float], champion_pred: int, candidate_url: str
) -> bool:
    """Publish a persistent task with broker confirmation, without failing inference."""
    connection = None
    try:
        parameters = pika.URLParameters(os.getenv("RABBITMQ_URL", "amqp://rabbitmq:5672/"))
        parameters.socket_timeout = 3
        parameters.stack_timeout = 5
        parameters.blocked_connection_timeout = 5
        parameters.connection_attempts = 1
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(
                {
                    "request_id": request_id,
                    "features": features,
                    "champion_pred": champion_pred,
                    "candidate_url": candidate_url,
                },
                allow_nan=False,
            ).encode(),
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
    finally:
        if connection is not None and connection.is_open:
            try:
                connection.close()
            except (pika.exceptions.AMQPError, OSError):
                logger.warning("Shadow publisher connection close failed")
