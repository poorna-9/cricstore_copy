from elasticsearch import logger

from celery import shared_task
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    Ground,
    slots,
    payment,
    reservationsession,
    tournamentsession,
    reservetournament,
)
from .redis_client import redis_client
from .utils import generateslots
ROLLING_SLOT_DAYS = 60
@shared_task
def maintain_60_days_slots_window():
    today = timezone.localdate()
    start_day = today + timedelta(days=60)
    end_day = today + timedelta(days=60 + 1)
    created_for_days = 0
    for ground in Ground.objects.all():
        current_date = start_day
        while current_date < end_day:
            before_count = slots.objects.filter(
                ground=ground,
                date=current_date
            ).count()
            generateslots(ground, current_date)
            after_count = slots.objects.filter(
                ground=ground,
                date=current_date
            ).count()
            if after_count > before_count:
                created_for_days += 1
            current_date += timedelta(days=1)
    return f"Generated slots from {start_day} to {end_day - timedelta(days=1)} for {created_for_days} ground-days"

@shared_task
def cleanup_expired_slots():
    cutoff = timezone.now() - timedelta(minutes=12)
    updated_count = slots.objects.filter(
        is_blocked=True,
        is_booked=False,
        blocked_at__lte=cutoff
    ).update(
        is_blocked=False,
        blocked_at=None
    )
    logger.info(f"Unblocked {updated_count} expired slots.")
    return f"Unblocked {updated_count} expired slots."

@shared_task
def generate_slots_for_ground(ground_id):
    ground = Ground.objects.get(id=ground_id)

    today = timezone.localdate()

    for i in range(60):
        generateslots(
            ground,
            today + timedelta(days=i)
        )

    return f"Generated slots for {ground.name}"




