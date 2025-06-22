import json
import logging
import pika

logger = logging.getLogger(__name__)


def publish_message(event: str, routing_key: str, queue_name: str, **kwargs):
    # Publish registration event to email service
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()

        # Ensure exchange exists
        channel.queue_declare(queue=queue_name, durable=True)

        # Create message payload
        message = {"event": event, **kwargs}
        # Publish message
        channel.basic_publish(
            exchange="",
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
                content_type="application/json",
            ),
        )

        connection.close()

    except Exception as e:
        logger.error(f"Failed to publish registration event: {str(e)}")
        # Don't raise exception - registration succeeded even if notification fails
