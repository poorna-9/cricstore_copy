import json
import logging
from functools import lru_cache

from django.conf import settings
from kafka import KafkaProducer

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_producer():
    return KafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        retries=5,
        acks="all",
    )


def send_event(topic, data, key=None):
    event_key = key or data.get("payment_id") or data.get("booking_id") or data.get("event")
    try:
        producer = get_producer()
        future = producer.send(
            topic,
            key=str(event_key).encode("utf-8") if event_key is not None else None,
            value=data,
        )
        future.get(timeout=10)
        producer.flush()
        return True
    except Exception as e:
        logger.error("Kafka send failed topic=%s error=%s", topic, e)
        return False


def send_booking_event(data):
    return send_event(settings.KAFKA_BOOKING_TOPIC, data)


def send_retry_event(data):
    return send_event(settings.KAFKA_RETRY_TOPIC, data)


def send_dlq_event(data):
    return send_event(settings.KAFKA_DLQ_TOPIC, data, key=data.get("event"))


def send_notification_event(data):
    return send_event(settings.KAFKA_NOTIFICATION_TOPIC, data, key=data.get("booking_id"))
