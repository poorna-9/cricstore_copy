from datetime import datetime, timedelta, time
import time as _time

from functools import wraps as _wraps
from django.db import OperationalError, DatabaseError

from .models import slots

SHIFT_RANGES = {
    "morning": (time(6, 0), time(11, 0)),
    "afternoon": (time(11, 0), time(15, 0)),
    "evening": (time(15, 0), time(19, 0)),
    "night": (time(19, 0), time(23, 59)),
}


def get_shift(starttime):
    for shift, (s, e) in SHIFT_RANGES.items():
        if s <= starttime < e:
            return shift
    return None


def generateslots(ground, slot_date):

    existing_slots = set(
        slots.objects.filter(
            ground=ground,
            date=slot_date
        ).values_list(
            "starttime",
            "endtime"
        )
    )

    price_map = {
        "morning": ground.morning_price,
        "afternoon": ground.afternoon_price,
        "evening": ground.evening_price,
        "night": ground.night_price,
    }

    slot_objects = []

    if ground.types == "ground":
        slot_duration = timedelta(hours=3, minutes=30)
    else:
        slot_duration = timedelta(hours=1)

    start_datetime = datetime.combine(slot_date, time(6, 0))
    end_datetime = datetime.combine(slot_date, time(23, 59))

    current = start_datetime

    while current + slot_duration <= end_datetime:

        slot_endtime = current + slot_duration

        start_time = current.time()
        end_time = slot_endtime.time()

        if (start_time, end_time) not in existing_slots:

            shift = get_shift(start_time)

            slot_price = price_map.get(shift, ground.price)

            slot_objects.append(
                slots(
                    ground=ground,
                    starttime=start_time,
                    endtime=end_time,
                    date=slot_date,
                    shift=shift,
                    price=slot_price,
                    is_booked=False,
                    is_blocked=False,
                )
            )

        current += slot_duration

    if slot_objects:
        slots.objects.bulk_create(
            slot_objects,
            batch_size=500
        )
def db_retry(max_attempts=3, base_delay=0.1, allowed_exceptions=(OperationalError, DatabaseError)):
    def decorator(func):
        @_wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except allowed_exceptions as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    sleep_time = base_delay * (2 ** (attempt - 1))
                    _time.sleep(sleep_time)
        return wrapper
    return decorator
