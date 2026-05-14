import json
import logging
import signal
import sys
import threading

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from kafka import KafkaConsumer

from .kafka_producer import send_dlq_event, send_notification_event, send_retry_event
from .models import Orders, payment, reservedslots, reservetournament, slots

logger = logging.getLogger(__name__)
MAX_RETRY = 3
_shutdown = threading.Event()


def consumer_config(group_id):
    return {
        "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group_id": group_id,
        "value_deserializer": lambda m: json.loads(m.decode("utf-8")),
        "enable_auto_commit": False,
        "auto_offset_reset": "earliest",
    }


def create_consumer(topic, group_id):
    return KafkaConsumer(topic, **consumer_config(group_id))


def _notify_booking_created(order, booked_slots):
    customer = getattr(order.user, "bookings_customer", None)
    phone = customer.phone if customer else None
    if not phone:
        return
    send_notification_event({
        "event": "BOOKING_CONFIRMED",
        "booking_id": str(order.id),
        "user_id": str(order.user.id),
        "phone": phone,
        "ground": order.ground.name,
        "date": str(order.date),
        "slots": [f"{s.starttime}-{s.endtime}" for s in booked_slots],
        "total_price": order.price,
        "booking_type": order.Tournament_or_normal,
        "timestamp": str(timezone.now()),
    })


def process_normal_booking(pay):
    session = pay.session
    if not session:
        logger.warning("Payment %s has no normal reservation session", pay.id)
        return
    if Orders.objects.filter(transaction_id=pay.payment_id, Tournament_or_normal="normal").exists():
        logger.info("Normal order already exists for payment %s", pay.id)
        return

    reserved = reservedslots.objects.select_for_update().filter(
        session=session,
        status="reserved",
    ).select_related("slot")

    slots_to_update = []
    rs_to_update = []
    booked_slots = []
    total_price = 0

    for rs in reserved:
        slot = rs.slot
        if slot.is_booked:
            continue
        slot.is_booked = True
        slot.is_blocked = False
        slot.blocked_at = None
        slots_to_update.append(slot)
        rs.status = "booked"
        rs_to_update.append(rs)
        booked_slots.append(slot)
        total_price += slot.price or 0

    if not booked_slots:
        logger.warning("No normal slots to book for payment %s", pay.id)
        return

    slots.objects.bulk_update(slots_to_update, ["is_booked", "is_blocked", "blocked_at"])
    reservedslots.objects.bulk_update(rs_to_update, ["status"])

    order = Orders.objects.create(
        session=None,
        user=pay.user,
        ground=session.ground,
        date=session.date,
        transaction_id=pay.payment_id or str(pay.id),
        booked=True,
        status="booked",
        price=total_price,
        Tournament_or_normal="normal",
    )
    order.slotsbooked.set(booked_slots)
    _notify_booking_created(order, booked_slots)
    logger.info("Normal order created for payment %s", pay.id)


def process_tournament_booking(pay):
    t_session = pay.tournament_session
    if not t_session:
        logger.warning("Payment %s has no tournament session", pay.id)
        return
    if Orders.objects.filter(transaction_id=pay.payment_id, Tournament_or_normal="tournament").exists():
        logger.info("Tournament order already exists for payment %s", pay.id)
        return

    reservations = reservetournament.objects.select_for_update().filter(
        session=t_session,
        status="reserved",
    ).prefetch_related("blocked_slots")

    booked_slots = []
    total_price = 0
    reservations_to_update = []
    slot_ids = []

    for reservation in reservations:
        reservation_slots = list(reservation.blocked_slots.all())
        for slot in reservation_slots:
            if slot.is_booked:
                continue
            booked_slots.append(slot)
            slot_ids.append(slot.id)
            total_price += slot.price or 0
        reservation.status = "booked"
        reservations_to_update.append(reservation)

    if not booked_slots:
        logger.warning("No tournament slots to book for payment %s", pay.id)
        return

    locked_slots = list(slots.objects.select_for_update().filter(id__in=slot_ids))
    for slot in locked_slots:
        slot.is_booked = True
        slot.is_blocked = False
        slot.blocked_at = None
    slots.objects.bulk_update(locked_slots, ["is_booked", "is_blocked", "blocked_at"])
    reservetournament.objects.bulk_update(reservations_to_update, ["status"])

    order = Orders.objects.create(
        session=t_session,
        user=pay.user,
        ground=t_session.ground,
        date=t_session.start_date,
        transaction_id=pay.payment_id or str(pay.id),
        booked=True,
        status="booked",
        price=total_price,
        Tournament_or_normal="tournament",
    )
    order.slotsbooked.set(locked_slots)
    _notify_booking_created(order, locked_slots)
    logger.info("Tournament order created for payment %s", pay.id)


def process_booking(data):
    payment_id = data.get("payment_id")
    retry_count = data.get("retry_count", 0)
    if not payment_id:
        logger.error("Missing payment_id in message")
        return

    try:
        with transaction.atomic():
            pay = payment.objects.select_for_update().select_related(
                "session", "session__ground", "tournament_session", "tournament_session__ground", "user"
            ).get(id=payment_id)
            if pay.status != "success":
                logger.warning("Payment %s is not successful yet", payment_id)
                return
            if pay.tournament_session_id:
                process_tournament_booking(pay)
            elif pay.session_id:
                process_normal_booking(pay)
            else:
                logger.error("Payment %s has no booking session", payment_id)
    except payment.DoesNotExist:
        logger.error("Payment not found: %s", payment_id)
    except Exception as e:
        logger.exception("Processing failed for payment %s: %s", payment_id, e)
        if retry_count < MAX_RETRY:
            new_data = data.copy()
            new_data["retry_count"] = retry_count + 1
            send_retry_event(new_data)
        else:
            send_dlq_event({
                "event": "BOOKING_FAILED",
                "failed_event": data,
                "error": str(e),
                "timestamp": str(timezone.now()),
            })


def consume_loop(topic, group_id, handler):
    consumer = create_consumer(topic, group_id)
    logger.info("Starting consumer topic=%s group=%s", topic, group_id)
    try:
        for message in consumer:
            if _shutdown.is_set():
                break
            try:
                handler(message.value)
                consumer.commit()
            except Exception as e:
                logger.exception("Consumer error topic=%s: %s", topic, e)
    finally:
        consumer.close()


def process_notification(data):
    phone = data.get("phone")
    if not phone:
        return
    message = (
        "Booking Confirmed!\n"
        f"Ground: {data.get('ground')}\n"
        f"Date: {data.get('date')}\n"
        f"Slots: {', '.join(data.get('slots', []))}\n"
        f"Amount: Rs.{data.get('total_price')}"
    )
    send_sms(phone, message)


def process_dlq(data):
    logger.error("DLQ EVENT: %s", data)


def send_sms(phone, message):
    logger.info("SMS to %s: %s", phone, message)


def shutdown_handler(sig, frame):
    logger.info("Shutting down consumers...")
    _shutdown.set()
    sys.exit(0)


def run_all_consumers(instances=1):
    signal.signal(signal.SIGINT, shutdown_handler)
    threads = []
    for i in range(instances):
        threads.extend([
            threading.Thread(
                target=consume_loop,
                args=(settings.KAFKA_BOOKING_TOPIC, "booking-group", process_booking),
                name=f"booking-{i}",
                daemon=True,
            ),
            threading.Thread(
                target=consume_loop,
                args=(settings.KAFKA_RETRY_TOPIC, "booking-retry-group", process_booking),
                name=f"retry-{i}",
                daemon=True,
            ),
        ])
    threads.extend([
        threading.Thread(
            target=consume_loop,
            args=(settings.KAFKA_DLQ_TOPIC, "booking-dlq-group", process_dlq),
            name="dlq",
            daemon=True,
        ),
        threading.Thread(
            target=consume_loop,
            args=(settings.KAFKA_NOTIFICATION_TOPIC, "booking-notification-group", process_notification),
            name="notification",
            daemon=True,
        ),
    ])
    for thread in threads:
        thread.start()
        logger.info("Started thread: %s", thread.name)
    for thread in threads:
        thread.join()
