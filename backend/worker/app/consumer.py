import json
import logging
import os
import pika

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "model_arena")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "")
QUEUE_NAME = "shadow_tasks"


def process_shadow_task(ch, method, properties, body):
    try:
        data = json.loads(body)
        logger.info(f"Received shadow comparison task for request: {data.get('request_id')}")
        # Member 3 will add candidate HTTP prediction call and database comparison record here
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    logger.info("Connecting to RabbitMQ...")
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD) if RABBITMQ_PASSWORD else None
        parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, port=5672, credentials=credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_qos(prefetch_count=10)
        channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_shadow_task)
        logger.info(f"Worker listening on queue: {QUEUE_NAME}")
        channel.start_consuming()
    except Exception as e:
        logger.warning(f"Could not connect to RabbitMQ ({e}). Worker will exit and can be restarted.")


if __name__ == "__main__":
    main()
