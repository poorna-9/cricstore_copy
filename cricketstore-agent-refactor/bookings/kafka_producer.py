import json
import logging
import ssl
from functools import lru_cache

from django.conf import settings
from kafka import KafkaProducer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_producer():
    return KafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,

        # Reliability
        retries=5,
        acks="all",
        retry_backoff_ms=300,

        # Timeouts
        request_timeout_ms=30000,
        delivery_timeout_ms=120000,

        # Redpanda Cloud
        security_protocol="SASL_SSL",
        sasl_mechanism="SCRAM-SHA-256",
        sasl_plain_username=settings.KAFKA_SASL_USERNAME,
        sasl_plain_password=settings.KAFKA_SASL_PASSWORD,
        ssl_context=ssl.create_default_context(),
    )


def send_event(topic, data, key=None):
    event_key = (
        key
        or data.get("payment_id")
        or data.get("booking_id")
        or data.get("event")
    )
    try:
        producer = get_producer()
        future = producer.send(
            topic,
            key=str(event_key) if event_key is not None else None,
            value=data,
        )
        record_metadata = future.get(timeout=30)
        producer.flush()
        logger.info(
            "Kafka event sent topic=%s partition=%s offset=%s key=%s",
            record_metadata.topic,
            record_metadata.partition,
            record_metadata.offset,
            event_key,
        )
        return True

    except KafkaError as e:
        logger.error("Kafka send failed topic=%s key=%s error=%s", topic, event_key, e)
        return False

    except Exception as e:
        logger.error("Unexpected error sending to Kafka topic=%s key=%s error=%s", topic, event_key, e)
        return False


def send_booking_event(data):
    return send_event(settings.KAFKA_BOOKING_TOPIC, data)


def send_notification_event(data):
    return send_event(settings.KAFKA_NOTIFICATION_TOPIC, data, key=data.get("booking_id"))