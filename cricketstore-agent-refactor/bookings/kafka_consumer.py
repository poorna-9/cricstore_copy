import json
import logging
import signal
import ssl
import threading
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from kafka import KafkaConsumer
from kafka.errors import KafkaError

from .kafka_producer import send_notification_event
from .models import Bookings, Orders, payment, slots

logger = logging.getLogger(__name__)

MAX_RETRY = 3           # retry process_booking this many times before giving up
RECONNECT_DELAY = 5     # seconds to wait before reconnecting after connection drop

_shutdown = threading.Event()


# ─── Consumer config ──────────────────────────────────────────────────────────

def consumer_config(group_id):
    return {
        "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group_id": group_id,
        "value_deserializer": lambda m: json.loads(m.decode("utf-8")),

        # Manual commit — only commit after successful processing
        "enable_auto_commit": False,
        "auto_offset_reset": "earliest",

        # Heartbeat settings
        "session_timeout_ms": 30000,
        "heartbeat_interval_ms": 10000,

        # process_booking does heavy DB work — give it 5 minutes
        "max_poll_interval_ms": 300000,

        # Redpanda Cloud
        "security_protocol": "SASL_SSL",
        "sasl_mechanism": "SCRAM-SHA-256",
        "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
        "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
        "ssl_context": ssl.create_default_context(),
    }


def create_consumer(topic, group_id):
    return KafkaConsumer(topic, **consumer_config(group_id))


# ─── Notification helper ──────────────────────────────────────────────────────

def _notify_booking_created(booking, booked_slots):
    customer = getattr(booking.user, "bookings_customer", None)
    phone = customer.phone if customer else None
    if not phone:
        logger.warning("No phone found for user %s — skipping notification", booking.user.id)
        return
    send_notification_event({
        "event": "BOOKING_CONFIRMED",
        "booking_id": str(booking.id),
        "user_id": str(booking.user.id),
        "phone": phone,
        "ground": booking.ground.name,
        "date": str(booking.date),
        "slots": [f"{s.starttime}-{s.endtime}" for s in booked_slots],
        "total_price": str(booking.price),
        "booking_type": booking.Tournament_or_normal,
        "timestamp": str(timezone.now()),
    })


# ─── Handlers ─────────────────────────────────────────────────────────────────

def process_booking(data):
    """
    Process a booking event from booking-events topic.
    Retries up to MAX_RETRY times on failure.
    If all retries fail — logs error for manual inspection.
    No separate retry/dlq topics needed.
    """
    payment_id = data.get("payment_id")

    if not payment_id:
        logger.error("Missing payment_id in message — skipping")
        return

    last_error = None

    for attempt in range(1, MAX_RETRY + 1):
        try:
            with transaction.atomic():
                pay = (
                    payment.objects
                    .select_for_update()
                    .select_related(
                        "session",
                        "tournament_session",
                        "user",
                        "session__ground",
                        "tournament_session__ground",
                    )
                    .get(id=payment_id)
                )

                if not pay.status:
                    logger.warning("Payment %s not successful yet — skipping", payment_id)
                    return

                session = pay.tournament_session if pay.tournament_session_id else pay.session
                if not session:
                    logger.error("Payment %s has no booking session — skipping", payment_id)
                    return

                # Idempotency — don't create duplicate bookings
                if Bookings.objects.filter(
                    user=pay.user,
                    normal_session=pay.session,
                    tournament_session=pay.tournament_session,
                    payment_status=True,
                ).exists():
                    logger.info("Booking already exists for payment %s — skipping", payment_id)
                    return

                booking_type = "tournament" if pay.tournament_session else "normal"

                slot_ids = list(
                    Orders.objects.filter(
                        user=pay.user,
                        booked=True,
                        payment_status=True,
                        Tournament_or_normal=booking_type,
                        **(
                            {"normal_session": pay.session}
                            if pay.session
                            else {"tournament_session": pay.tournament_session}
                        ),
                    ).values_list("slotsbooked_id", flat=True)
                )

                if not slot_ids:
                    logger.warning("No booked slots found for payment %s — skipping", payment_id)
                    return

                slot_objs = list(slots.objects.filter(id__in=slot_ids))
                total = sum(float(s.price or 0) for s in slot_objs)

                booking = Bookings.objects.create(
                    user=pay.user,
                    ground=session.ground,
                    date=session.date,
                    transaction_id=pay.razorpay_payment_id or str(pay.id),
                    booked=True,
                    price=total,
                    payment_status=True,
                    tournament_session=pay.tournament_session if pay.tournament_session_id else None,
                    normal_session=pay.session if pay.session_id else None,
                    Tournament_or_normal=booking_type,
                )
                booking.slotsbooked.set(slot_objs)
                _notify_booking_created(booking, slot_objs)

                logger.info("Booking created for payment %s", payment_id)
                return  # success — exit retry loop

        except payment.DoesNotExist:
            # No point retrying — payment simply doesn't exist
            logger.error("Payment not found: %s — skipping", payment_id)
            return

        except Exception as e:
            last_error = e
            logger.warning(
                "Attempt %s/%s failed for payment %s: %s",
                attempt, MAX_RETRY, payment_id, e,
            )
            if attempt < MAX_RETRY:
                time.sleep(2 ** attempt)  # exponential backoff: 2s, 4s, 8s

    # All retries exhausted — log for manual inspection
    logger.error(
        "All %s attempts failed for payment %s — MANUAL ACTION REQUIRED. Last error: %s",
        MAX_RETRY, payment_id, last_error,
    )


def process_notification(data):
    """
    Process a notification event from booking-notifications topic.
    Sends SMS to the customer.
    """
    phone = data.get("phone")
    if not phone:
        logger.warning("Notification message missing phone — skipping")
        return

    message = (
        "Booking Confirmed!\n"
        f"Ground: {data.get('ground')}\n"
        f"Date: {data.get('date')}\n"
        f"Slots: {', '.join(data.get('slots', []))}\n"
        f"Amount: Rs.{data.get('total_price')}"
    )
    send_sms(phone, message)


def send_sms(phone, message):
    # Replace with your actual SMS provider — Twilio, MSG91 etc
    logger.info("SMS to %s: %s", phone, message)


# ─── Consume loop with reconnect ──────────────────────────────────────────────

def consume_loop(topic, group_id, handler):
    """
    Infinite loop consuming from one topic.
    Reconnects automatically if connection drops.
    Stops cleanly when _shutdown is set.
    """
    logger.info("Starting consumer topic=%s group=%s", topic, group_id)

    while not _shutdown.is_set():
        consumer = None
        try:
            consumer = create_consumer(topic, group_id)

            for message in consumer:
                if _shutdown.is_set():
                    break
                try:
                    handler(message.value)
                    consumer.commit()
                except Exception as e:
                    logger.exception(
                        "Handler error topic=%s partition=%s offset=%s: %s",
                        topic, message.partition, message.offset, e,
                    )

        except KafkaError as e:
            logger.error(
                "Kafka connection error topic=%s: %s — reconnecting in %ss",
                topic, e, RECONNECT_DELAY,
            )
            _shutdown.wait(timeout=RECONNECT_DELAY)

        except Exception as e:
            logger.exception(
                "Unexpected error topic=%s: %s — reconnecting in %ss",
                topic, e, RECONNECT_DELAY,
            )
            _shutdown.wait(timeout=RECONNECT_DELAY)

        finally:
            if consumer:
                try:
                    consumer.close()
                except Exception:
                    pass

    logger.info("Consumer stopped topic=%s group=%s", topic, group_id)


# ─── Shutdown handler ─────────────────────────────────────────────────────────

def shutdown_handler(sig, frame):
    logger.info("Shutdown signal received — stopping all consumers...")
    _shutdown.set()


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_all_consumers(instances=1):
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    threads = []

    for i in range(instances):
        threads.append(
            threading.Thread(
                target=consume_loop,
                args=(settings.KAFKA_BOOKING_TOPIC, "booking-group", process_booking),
                name=f"booking-{i}",
                daemon=True,
            )
        )

    # Notification — single thread always sufficient
    threads.append(
        threading.Thread(
            target=consume_loop,
            args=(settings.KAFKA_NOTIFICATION_TOPIC, "booking-notification-group", process_notification),
            name="notification",
            daemon=True,
        )
    )

    for thread in threads:
        thread.start()
        logger.info("Started thread: %s", thread.name)

    # Main thread waits here until shutdown signal
    _shutdown.wait()
    logger.info("All consumers shutting down...")

    for thread in threads:
        thread.join(timeout=30)

    logger.info("All consumer threads stopped cleanly")