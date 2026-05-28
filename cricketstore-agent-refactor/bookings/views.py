from calendar import calendar
from datetime import time, date, datetime, timedelta
import json
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render,get_object_or_404, redirect
from .models import *
from django.views.decorators.csrf import csrf_exempt
from .document import GroundDocument
import requests
import logging
logger = logging.getLogger(__name__)
from .utils import db_retry
from ai.ground import interpret_ground_query
from django.contrib import messages
from ai.chatcric import interpretgroundquery
import math
from django.db.models import Avg
from django.db import transaction
import razorpay
from django.conf import settings
from .models import payment
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from .agent_state import get_agent_context, merge_agent_filters, normalize_required_fields, read_chat_payload, reset_agent_context
import logging
logger = logging.getLogger(__name__)
from .redis_client import redis_client

AFFIRMATIVE_REPLIES = {
    "yes", "y", "confirm", "confirm booking", "confirm cancellation",
    "confirm tournament booking",
    "continue", "proceed", "book it", "go ahead", "pay now"
}
NEGATIVE_REPLIES = {
    "no", "n", "change", "change details", "edit", "cancel", "not now", "stop",
    "keep booking"
}


def is_affirmative_reply(text):
    return (text or "").strip().lower() in AFFIRMATIVE_REPLIES


def is_negative_reply(text):
    return (text or "").strip().lower() in NEGATIVE_REPLIES


def set_pending_action(context, action, summary, booking_id=None):
    context["pending_action"] = action
    context["pending_summary"] = summary
    if booking_id is not None:
        context["pending_booking_id"] = booking_id
    context["stage"] = "awaiting_confirmation"
    context["last_modified_at"] = timezone.now().isoformat()


def clear_pending_action(context):
    for key in ("pending_action", "pending_summary", "pending_booking_id", "confirmation_approved"):
        context.pop(key, None)


def format_slot_window(slot):
    return f"{slot.starttime.strftime('%I:%M %p')} - {slot.endtime.strftime('%I:%M %p')}"


def format_order_slots(order):
    slot_labels = [format_slot_window(slot) for slot in order.slotsbooked.all()]
    return ", ".join(slot_labels) if slot_labels else "No slots recorded"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371 
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def findgroundsnear(grounds, radius, userlat, userlon):
    nearby_grounds = []
    for ground in grounds:
        if ground.lattitude is None or ground.longitude is None:
            continue
        distance = haversine(userlat, userlon, ground.lattitude, ground.longitude)
        if distance <= radius:
            nearby_grounds.append(ground)
    return nearby_grounds

@login_required
def bookingagent(request):
    return render(request,"bookings/booking-agent.html",{})

from datetime import datetime, time, timedelta

def timingstoslots(timings, sporttype=None, groundorturf="turf", am_pm=None, shift="evening", constraint="between"):
    shift_ampm = {
        "morning": "AM",
        "afternoon": "PM",
        "evening": "PM",
        "night": "PM"
    }
    constraint_map = {
        "from": "after",
        "starting": "after",
        "until": "before"
    }
    if shift and am_pm is None:
        am_pm = shift_ampm.get(shift)
    constraint = constraint_map.get(constraint, constraint)
    opening_time = time(6, 0)
    closing_time = time(23, 0)
    userslots = []
    starttime, endtime = parse_natural_timings(timings, shift, am_pm)
    if not starttime or not endtime:
        return userslots
    if constraint == "after":
        endtime = closing_time
    elif constraint == "before" and "-" not in timings:
        endtime, starttime = starttime, opening_time
    slotduration = timedelta(hours=3.5) if groundorturf == "ground" else timedelta(hours=1)
    current = datetime.combine(datetime.today(), starttime)
    end_dt = datetime.combine(datetime.today(), endtime)
    while current + slotduration <= end_dt:
        slot_end = current + slotduration
        userslots.append(f"{current.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}")
        current = slot_end
    if am_pm == "AM":
        userslots = [
            s for s in userslots
            if datetime.strptime(s.split(" - ")[0], "%I:%M %p").hour < 12
        ]
    return userslots


def normalize_date_text(text):
    text = text.lower().strip()
    keywords = [
        "this", "next", "coming", "upcoming", "current"
    ]
    weekdays = [
        "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday"
    ]
    for k in keywords:
        for d in weekdays:
            text = text.replace(k + d, f"{k} {d}")
    text = text.replace("thisweekend", "this weekend")
    text = text.replace("nextweekend", "next weekend")
    return text
import re
from datetime import datetime, timedelta, date
def parse_natural_date(text):
    NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10
    }
    text = normalize_date_text(text)
    text = text.lower()
    explicit_year_provided = bool(re.search(r'\b\d{4}\b', text))
    def ensure_future_date(d):
        if explicit_year_provided:
            return d
        today = datetime.now().date()
        if d < today:
            return None
        return d
    for word, num in NUMBER_WORDS.items():
      text = re.sub(rf'\b{word}\b', str(num), text)
    today = datetime.now().date()
    text = text.lower().strip()
    text = re.sub(r'\b(on|at|by|the)\b', '', text).strip()
    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text)
    WEEKDAYS = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6
    }
    words = text.split()
    current_day = today.weekday()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            candidate= datetime.strptime(text, fmt).date()
            return ensure_future_date(candidate)
        except ValueError:
            pass
    current_year = today.year
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            candidate= datetime.strptime(text, fmt).date()
            return ensure_future_date(candidate)
        except ValueError:
            pass
    for fmt in ("%d %b", "%d %B"):
        try:
            parsed = datetime.strptime(text, fmt)
            candidate=parsed.replace(year=current_year).date()
            return ensure_future_date(candidate)
        except ValueError:
            pass
    for fmt in ("%B %d", "%b %d"):
      try:
        parsed = datetime.strptime(text, fmt)
        candidate=parsed.replace(year=current_year).date()
        return ensure_future_date(candidate)
      except ValueError:
        pass
    for fmt in ("%B %d %Y", "%b %d %Y"):
      try:
        return datetime.strptime(text, fmt).date()
      except ValueError:
        pass
      
    match_in = re.search(
        r'in\s+(?:next\s+)?(a|\d+)\s+(day|days)',
        text
        )
    match_later = re.search(
        r'(a|\d+)\s+(day|days)\s+later',
        text
        )
    match_relative=match_in or match_later
    if match_relative:
        raw_value = match_relative.group(1)
        value = 1 if raw_value == "a" else int(raw_value)
        unit = match_relative.group(2)
        if "day" in unit:
            base_date = today + timedelta(days=value)
        elif "week" in unit:
            base_date = today + timedelta(weeks=value)
        elif "month" in unit: 
            month = today.month + value
            year = today.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            day = min(today.day, [31,
                29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                31,30,31,30,31,31,30,31,30,31][month-1])
            base_date = date(year, month, day)
        return ensure_future_date(base_date)
    match_for_now =re.search(
        r'(\d+)\s+(day|days|week|weeks|month|months)\s+from now(?:\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday))?',
        text
        )
    if match_for_now:
        value = int(match_for_now.group(1))
        unit = match_for_now.group(2)
        weekday_target = match_for_now.group(3)
        if "day" in unit:
            base_date= today + timedelta(days=value)
        elif "week" in unit:
            base_date = today + timedelta(weeks=value)
        elif "month" in unit:
            month = (today.month + value) 
            year = today.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            day = min(today.day, [31,
                29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                31,30,31,30,31,31,30,31,30,31][month-1])
            base_date= date(year, month, day)
        else:
            base_date = today
        if weekday_target:
            target_weekday = WEEKDAYS[weekday_target]
            delta = (target_weekday - base_date.weekday()) % 7
            if delta == 0:
                delta = 7
            base_date = base_date + timedelta(days=delta)
        return ensure_future_date(base_date)
    
    match_after=re.search(r'after\s+(\d+)\s+(day|days|week|weeks|month|months)', text)
    if match_after:
        value=int(match_after.group(1))
        unit=match_after.group(2)
        if "day" in unit:
            base_date = today + timedelta(days=value)
        elif "week" in unit:
            base_date = today + timedelta(weeks=value)
        elif "month" in unit:
            month = (today.month + value) 
            year = today.year + (month - 1) // 12
            month=((month - 1) % 12) + 1
            day = min(today.day, [31,
                29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                31,30,31,30,31,31,30,31,30,31][month-1])
            base_date = date(year, month , day)
        else:
            base_date = today
        for day_name,day_ind in WEEKDAYS.items():
            if day_name in text:
                delta=(day_ind - base_date.weekday())%7
                if delta==0:
                    delta=7
                return ensure_future_date(base_date + timedelta(days=delta))
        if words[-1]=="weekend":
            days_until_sat=(5 - base_date.weekday())%7
            if days_until_sat==0:
                days_until_sat=7
            return ensure_future_date(base_date + timedelta(days=days_until_sat))
        
    match_this_month = re.search(r'this\s+month\s+(\d{1,2})', text)
    if match_this_month:
        day = int(match_this_month.group(1))
        year = today.year
        month = today.month
        try:
            candidate = date(year, month, day)
        except ValueError:
            pass
        if candidate<today:
            month+=1
            if month>12:
                month=1
                year+=1
            try:
                candidate = date(year, month, day)
            except ValueError:
                pass
        return candidate
    match_next_month = re.search(r'next\s+month\s+(\d{1,2})', text)
    if match_next_month:
        day = int(match_next_month.group(1))
        year = today.year
        month = today.month + 1
        if month > 12:
            month = 1
            year += 1
        try:
            candidate = date(year, month, day)
        except ValueError:
            pass
        return candidate   
    
    if len(words) == 1 and words[0] in WEEKDAYS:
        words = ["this", words[0]]
    if words[-1] == "weekend":
        days_until_sat = (5 - current_day) % 7
        if words[0] in ["this","coming"] and days_until_sat == 0:
            return today
        if words[0] in ["next", "upcoming"]:
            days_until_sat += 7
        return today + timedelta(days=days_until_sat)
    if words[-1] in WEEKDAYS:
        target = WEEKDAYS[words[-1]]
        delta = (target - current_day) % 7
        if words[0] in ["this","coming"]:
            if delta==0:
                return today
            return ensure_future_date(today + timedelta(days=delta))
        if words[0] in ["next", "upcoming"]:
            if delta==0:
                delta=7
        result=today + timedelta(days=delta)
        if delta==0:
            result+=timedelta(days=7)
        return ensure_future_date(result)
    return None

def infer_ampm(hour, shift=None, am_or_pm=None):
    if am_or_pm:
        return am_or_pm.upper()
    if shift in ("afternoon", "evening", "night"):
        return "PM"
    if shift == "morning":
        return "AM"
    return "PM" if hour >= 6 else "AM"
from datetime import datetime, time
def normalize_timings_text(t):
   if not t:
     return t
   t = t.lower().strip()
   t = re.sub(r'between\s+(\d+)\s+and\s+(\d+)', r'\1-\2', t)
   t = re.sub(r'from\s+(\d+)\s+to\s+(\d+)', r'\1-\2', t)
   t = re.sub(r'(\d+)\s+to\s+(\d+)', r'\1-\2', t)
   return t

def parse_natural_timings(timings, shift=None, am_or_pm=None):
    opening = time(6, 0)
    closing = time(23, 0)
    if not timings or not any(c.isdigit() for c in timings):
        timings = ""
    if not timings and shift:
        return {
            "morning": (opening, time(11, 0)),
            "afternoon": (time(11, 0), time(15, 0)),
            "evening": (time(15, 0), time(19, 0)),
            "night": (time(19, 0), closing),
        }.get(shift, (opening, closing))
    if timings:
        timings = normalize_timings_text(timings)
        print("Normalized timings:", timings)
    if "-" in timings:
        start, end = timings.split("-")
        start, end = start.strip(), end.strip()
        def parse_part(part):
            if "am" in part.lower() or "pm" in part.lower():
                return datetime.strptime(part.upper(), "%I %p").time()
            hour = int(part.split(":")[0])
            if hour > 12:
                return time(hour, 0)
            inferred = infer_ampm(hour, shift, am_or_pm)
            part = f"{part} {inferred}"
            return datetime.strptime(part.upper(), "%I %p").time()
        return parse_part(start), parse_part(end)
    start = timings.strip()
    if "am" in start.lower() or "pm" in start.lower():
        start_time = datetime.strptime(start.upper(), "%I %p").time()
    else:
        hour = int(start.split(":")[0])
        inferred = infer_ampm(hour, shift, am_or_pm)
        start_time = datetime.strptime(f"{start} {inferred}".upper(), "%I %p").time()
    if shift == "morning":
        return start_time, time(12, 0)
    if shift == "afternoon":
        return start_time, time(17, 0)
    if shift == "evening":
        return start_time, time(21, 0)
    if shift == "night":
        return start_time, closing
    print("opening", opening, "closing", closing)
    return opening, closing


def checkpage(request):
    city=request.GET.get('city','')
    searchquery=request.GET.get('q','')
    ajax=request.GET.get('ajax')
    grounds = Ground.objects.all()
    if city:
        grounds = grounds.filter(city=city)
    if searchquery:
        gptresults = interpret_ground_query(searchquery)
        filters = gptresults.get("filters", {})
        avail_date_str = filters.get("available_date")
        if avail_date_str:
            parsed_date = parse_natural_date(avail_date_str)
            if parsed_date:
                request.session['selected_date'] = parsed_date.strftime('%Y-%m-%d')
        search_ids = GroundDocument.search().query(
            "multi_match",
            query=searchquery,
            fields=["sporttype","name", "location","description","address","price"],
            fuzziness="AUTO"
        )
        if filters.get("price"):
            search_ids=search_ids.filter("match",price=filters["price"])
        if filters.get("address"):
            search_ids = search_ids.filter("match", address=filters["address"])
        if filters.get("location"):
            search_ids = search_ids.filter("match", location=filters["location"])
        if filters.get("sporttype"):
            search_ids = search_ids.filter("match", sporttype=filters["sporttype"])
        if filters.get("name"):
            search_ids= search_ids.filter("match", name=filters["name"])
        search_ids=search_ids.execute()
        ground_ids = [int(hit.meta.id) for hit in search_ids]
        grounds = grounds.filter(id__in=ground_ids)
    if ajax:
        data=[
          {"id": g.id, "name": g.name, "imageURL": g.imageURL, "price": g.price} #type: ignore
            for g in grounds
        ]  
        return JsonResponse({'grounds':data})
    cities= Ground.objects.values_list('city', flat=True).distinct()
    return render(request, 'bookings/checkpage.html', {'grounds': grounds, 'cities': cities,'selected_city':city})
    
def selectcity(request):
    cities=Ground.objects.values_list('city',flat=True).distinct()
    return render(request,'bookings/homepage.html',{'cities':cities})

def grounddetail(request, pk):
    date_str = request.session.pop('selected_date', None)

    if request.GET.get('date'):
        date_str = request.GET.get('date')

    ground = get_object_or_404(Ground, id=pk)

    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            date_obj = timezone.now().date()
    else:
        date_obj = timezone.now().date()

    date_for_input = date_obj.strftime('%Y-%m-%d')
    today = timezone.now().date().strftime('%Y-%m-%d')
    cities = Ground.objects.values_list('city', flat=True).distinct()

    if request.method == "POST":
        selectedslots = request.POST.get('selected_slots', '')
        slots_list = [s for s in selectedslots.split(',') if s]
        slot_ids = [int(s) for s in selectedslots.split(',') if s]
        selected_slot_objs = slots.objects.filter(id__in=slot_ids)
        total = sum(slot.price for slot in selected_slot_objs)

        context = {
            'ground': ground,
            'slots_list': slots_list,
            'total': total
        }
        return render(request, 'bookings/checkoutpage.html', context)

    time_slots = slots.objects.filter(
        ground=ground,
        date=date_obj
    ).order_by('starttime')

    now = timezone.localtime()
    today_date = now.date()
    current_time = now.time()

    booked = time_slots.filter(is_booked=True)

    if date_obj < today_date:
        passed_slots = time_slots
    elif date_obj == today_date:
        passed_slots = time_slots.filter(endtime__lte=current_time)
    else:
        passed_slots = slots.objects.none()

    booked = booked | passed_slots

    booked_ids = booked.values_list("id", flat=True)

    reserved = time_slots.filter(
        is_blocked=True
    ).exclude(id__in=booked_ids)

    available = time_slots.filter(
        is_blocked=False,
        is_booked=False
    ).exclude(id__in=booked_ids)

    userreservedslots = []

    if request.user.is_authenticated:
        usersession = reservationsession.objects.filter(
        user=request.user,
        ground=ground,
        date=date_obj,
          ).order_by('-created_at').first()
        if usersession:
            session_key = f"session:{usersession.id}"
            if redis_client.exists(session_key):
                session_slots_key = f"session_slots:{usersession.id}"
                redis_slot_ids = redis_client.smembers(session_slots_key)
                userreservedslots = [
                   int(sid.decode() if isinstance(sid, bytes) else sid)
                   for sid in redis_slot_ids
                ]
            else:
                userreservedslots = []
    booked_id_list = list(booked.values_list("id", flat=True))
    reserved_id_list = list(reserved.values_list("id", flat=True))
    context = {
        'ground': ground,
        'date': date_for_input,
        'today': today,
        'cities': cities,
        'selected_city': ground.city,
        'reserved': reserved_id_list,
        'booked': booked_id_list,
        'available': available,
        'all_slots': time_slots,
        'userreservedslots': userreservedslots,
    }

    return render(request, 'bookings/groundpage.html', context)



def decode_redis_ids(raw_ids):
    return [int(s.decode() if isinstance(s, bytes) else s) for s in raw_ids]

from django.db import transaction

def cancel_normal_booking_session(session):
    order_objs = Orders.objects.filter(
        normal_session=session,
        Tournament_or_normal="normal",
        payment_status=False,
        booked=False,
    )
    slot_ids = list(
        order_objs.values_list("slotsbooked_id", flat=True)
    )

    with transaction.atomic():
        if slot_ids:
          slots.objects.filter(id__in=slot_ids).update(
                is_blocked=False,
                blocked_at=None
            )
        



from django.db import transaction

def cancel_tournament_booking_session(t_session):
    slot_ids = Orders.objects.filter(
        session=t_session,
        Tournament_or_normal="tournament",
    ).values_list('slot_id', flat=True)

    with transaction.atomic():
        slots.objects.filter(id__in=slot_ids).update(
            is_blocked=False,
            blocked_at=None
        )

def tournamentBookingPage(request, pk):
    today = date.today()
    ground = get_object_or_404(Ground, id=pk)
    SHIFTS = ["morning", "afternoon", "evening", "night"]
    user = request.user if request.user.is_authenticated else None
    user_session_id = None

    if user:
        latest_session = tournamentsession.objects.filter(
            user=user,
            ground=ground,
        ).order_by('-created_at').first()

        if latest_session:
            session_key = f"tournament_session:{latest_session.id}"
            if redis_client.exists(session_key):
                user_session_id = str(latest_session.id)

    dates = []
    user_reserved = {}
    others_reserved = {}
    booked = {}

    for i in range(30):
        d = today + timedelta(days=i)
        date_str = str(d)
        dates.append({
            "date": d,
            "day_num": d.day
        })
        for shift in SHIFTS:
            shift_lock_key = f"lock:shift:{ground.id}:{date_str}:{shift}"
            owner = redis_client.get(shift_lock_key)
            if owner:
                owner = owner.decode() if isinstance(owner, bytes) else str(owner)
                if user_session_id and owner == user_session_id:
                    user_reserved.setdefault(date_str, []).append(shift)
                else:
                    others_reserved.setdefault(date_str, []).append(shift)
                continue
            is_booked = slots.objects.filter(
                ground=ground,
                date=d,
                shift=shift,
                is_booked=True
            ).exists()
            if is_booked:
                booked.setdefault(date_str, []).append(shift)

    context = {
        "ground": ground,
        "dates": dates,
        "shifts": SHIFTS,
        "user_reserved": user_reserved,
        "others_reserved": others_reserved,
        "booked": booked,
    }
    return render(request, "bookings/tournament.html", context)
TOURNAMENT_SESSION_TTL_SECONDS = 15 * 60


@csrf_exempt
@db_retry(max_attempts=3)
def reservetournamentday(request):
    logger.info(
        "reservetournamentday called user=%s",
        request.user.id if getattr(request, "user", None) and request.user.is_authenticated else None
    )
    if request.method != "POST":
        return JsonResponse({"success": False})
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Login required"})
    try:
        user = request.user
        ground_id = request.POST.get("ground_id")
        date_str = request.POST.get("date")
        session_type = request.POST.get("session_type")
        if not (ground_id and date_str and session_type):
            return JsonResponse({"success": False, "message": "Missing params"})
        ground = get_object_or_404(Ground, id=ground_id)
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        SHIFT_MAP = {
            "morning": ["morning"],
            "afternoon": ["afternoon"],
            "evening": ["evening"],
            "night": ["night"],
        }
        if session_type not in SHIFT_MAP:
          return JsonResponse({
           "success": False,
           "message": "Invalid session type"
          })
        shifts_to_lock = SHIFT_MAP[session_type]
        session = tournamentsession.objects.filter(
           user=user,
           ground=ground,
           ).order_by('-created_at').first()
        if session:
            existing_session_key = f"tournament_session:{session.id}"
            if not redis_client.exists(existing_session_key):
                cancel_tournament_booking_session(session)
                session = tournamentsession.objects.create(
                    user=user,
                    ground=ground,
                    start_date=date_obj,
                    end_date=date_obj,
                    session_type=session_type,
                )
        else:
            session = tournamentsession.objects.create(
                user=user,
                ground=ground,
                start_date=date_obj,
                end_date=date_obj,
                session_type=session_type,
            )
        session_id = str(session.id)
        session_key = f"tournament_session:{session_id}"
        session_slots_key = f"tournament_session_slots:{session_id}"
        ttl = redis_client.ttl(session_key)
        if ttl is None or ttl <= 0:
            redis_client.set(
                session_key,
                json.dumps({
                    "user_id": user.id,
                    "ground_id": ground.id,
                }),
                ex=TOURNAMENT_SESSION_TTL_SECONDS
            )
            remaining_seconds = TOURNAMENT_SESSION_TTL_SECONDS
        else:
            remaining_seconds = ttl
        redis_client.expire(session_slots_key, remaining_seconds)
        def get_shift_owner(shift):
            val = redis_client.get(f"lock:shift:{ground_id}:{date_str}:{shift}")
            if not val:
                return None
            return val.decode() if isinstance(val, bytes) else str(val)
        already_selected = all(
            get_shift_owner(shift) == session_id
            for shift in shifts_to_lock
        )
        if already_selected:
            for shift in shifts_to_lock:
                redis_client.delete(f"lock:shift:{ground_id}:{date_str}:{shift}")
                slot_ids = list(
                    slots.objects.filter(
                        ground=ground,
                        date=date_obj,
                        shift=shift
                    ).values_list("id", flat=True)
                )
                for sid in slot_ids:
                    redis_client.delete(f"lock:slot:{ground_id}:{sid}:{date_str}")
                    redis_client.srem(session_slots_key, str(sid))
            reservetournament.objects.filter(
                session=session,
                ground=ground,
                date=date_obj,
            ).delete()
            return JsonResponse({
                "success": True,
                "action": "unreserved",
                "session_id": session_id,
                "remaining_seconds": remaining_seconds,
            })
        for shift in shifts_to_lock:
            owner = get_shift_owner(shift)
            if owner and owner != session_id:
                return JsonResponse({
                    "success": False,
                    "message": f"{shift} shift on {date_str} is already reserved"
                })
        all_slot_ids = list(
            slots.objects.filter(
                ground=ground,
                date=date_obj,
                shift__in=shifts_to_lock,
                is_booked=False,
                is_blocked=False,
            ).values_list("id", flat=True)
        )
        if not all_slot_ids:
            return JsonResponse({
                "success": False,
                "message": "No available slots found for this session type"
            })
        acquired_slot_locks = []
        for sid in all_slot_ids:
            lock_key = f"lock:slot:{ground_id}:{sid}:{date_str}"
            acquired = redis_client.set(
                lock_key,
                session_id,
                nx=True,
                ex=remaining_seconds
            )
            if not acquired:
                for lk in acquired_slot_locks:
                    redis_client.delete(lk)
                return JsonResponse({
                    "success": False,
                    "message": "One or more slots already reserved"
                })
            acquired_slot_locks.append(lock_key)
        for shift in shifts_to_lock:
            redis_client.set(
                f"lock:shift:{ground_id}:{date_str}:{shift}",
                session_id,
                ex=remaining_seconds
            )
        redis_client.sadd(session_slots_key, *[str(sid) for sid in all_slot_ids])
        redis_client.expire(session_slots_key, remaining_seconds)
        with transaction.atomic():
            rt, _ = reservetournament.objects.get_or_create(
                session=session,
                ground=ground,
                date=date_obj,
                defaults={
                    "status": "reserved",
                    "session_type": session_type
                }
            )
            rt.status = "reserved"
            rt.session_type = session_type
            rt.save(update_fields=["status", "session_type"])
            rt.blocked_slots.set(all_slot_ids)
            if not session.start_date or date_obj < session.start_date:
                session.start_date = date_obj
            if not session.end_date or date_obj > session.end_date:
                session.end_date = date_obj
            session.session_type = session_type
            session.save(update_fields=["start_date", "end_date", "session_type"])
        return JsonResponse({
            "success": True,
            "action": "selected",
            "session_id": session_id,
            "remaining_seconds": remaining_seconds,
        })
    except Exception as e:
        logger.exception("Tournament reserve failed: %s", e)
        return JsonResponse({
            "success": False,
            "message": f"Invalid request: {str(e)}"
        })
    

def gettournamentreserveddays(request):
    ground_id = request.GET.get("ground_id")
    if not ground_id:
        return JsonResponse({"success": False, "message": "Missing ground_id"})

    today = date.today()
    SHIFTS = ["morning", "afternoon", "evening", "night"]
    user = request.user if request.user.is_authenticated else None
    user_session_id = None

    if user:
        latest_session = tournamentsession.objects.filter(
            user=user,
            ground_id=ground_id,
        ).order_by('-created_at').first()

        if latest_session:
            session_key = f"tournament_session:{latest_session.id}"
            if redis_client.exists(session_key):
                user_session_id = str(latest_session.id)

    user_reserved = {}
    others_reserved = {}
    booked = {}

    for i in range(30):
        d = today + timedelta(days=i)
        date_str = str(d)
        for shift in SHIFTS:
            shift_lock_key = f"lock:shift:{ground_id}:{date_str}:{shift}"
            owner = redis_client.get(shift_lock_key)
            if owner:
                owner = owner.decode() if isinstance(owner, bytes) else str(owner)
                if user_session_id and owner == user_session_id:
                    user_reserved.setdefault(date_str, []).append(shift)
                else:
                    others_reserved.setdefault(date_str, []).append(shift)
                continue
            is_booked = slots.objects.filter(
                ground_id=ground_id,
                date=d,
                shift=shift,
                is_booked=True
            ).exists()
            if is_booked:
                booked.setdefault(date_str, []).append(shift)

    return JsonResponse({
        "success": True,
        "user_reserved": user_reserved,
        "others_reserved": others_reserved,
        "booked": booked,
        "session_id": user_session_id,
    })

MAX_SLOTS_PER_SESSION = 6

SESSION_TTL_SECONDS = 10 * 60
MAX_SLOTS_PER_SESSION = 6


@csrf_exempt
@db_retry(max_attempts=3)
def reserveslot(request):
    logger.info(
        "reserveslot called user=%s",
        request.user.id if getattr(request, "user", None) and request.user.is_authenticated else None
    )
    try:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": "Invalid request method"})
        if not request.user.is_authenticated:
            return JsonResponse({"success": False, "message": "User not authenticated"})
        user = request.user
        groundid = request.POST.get("ground_id")
        slotid = request.POST.get("slot_id")
        date_str = request.POST.get("date")
        if not (groundid and slotid and date_str):
            return JsonResponse({"success": False, "message": "Missing parameters"})
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            ground = Ground.objects.get(id=groundid)
            slot_obj = slots.objects.get(
                id=slotid,
                ground=ground,
                date=date_obj
            )
        except Exception:
            return JsonResponse({"success": False, "message": "Invalid input"})
        if slot_obj.is_booked or slot_obj.is_blocked:
            return JsonResponse({
                "success": False,
                "message": "Slot unavailable"
            })
        shift_lock_key = f"lock:shift:{groundid}:{date_str}:{slot_obj.shift}"
        if redis_client.exists(shift_lock_key):
            return JsonResponse({"success": False, "message": "Slot unavailable"})
        session = reservationsession.objects.filter(
            user=request.user,
            ground_id=groundid,
            date=date_obj,
            ).order_by('-created_at').first()
        if session:
            existing_session_key = f"session:{session.id}"
            if not redis_client.exists(existing_session_key):
                cancel_normal_booking_session(session)
                session = reservationsession.objects.create(
                    user=user,
                    ground=ground,
                    date=date_obj,
                )
        else:
            session = reservationsession.objects.create(
                user=user,
                ground=ground,
                date=date_obj,
            )
        session_id = str(session.id)
        session_key = f"session:{session_id}"
        session_slots_key = f"session_slots:{session_id}"
        lock_key = f"lock:slot:{groundid}:{slotid}:{date_str}"
        ttl = redis_client.ttl(session_key)
        if ttl is None or ttl <= 0:
            redis_client.set(
                session_key,
                json.dumps({
                    "user_id": user.id,
                    "ground_id": ground.id,
                    "date": date_str
                }),
                ex=SESSION_TTL_SECONDS
            )
            remaining_seconds = SESSION_TTL_SECONDS
        else:
            remaining_seconds = ttl
        redis_client.expire(session_slots_key, remaining_seconds)
        if redis_client.sismember(session_slots_key, slotid):
            redis_client.srem(session_slots_key, slotid)
            redis_client.delete(lock_key)
            return JsonResponse({
                "success": True,
                "action": "unselected",
                "session_id": session_id,
                "remaining_seconds": remaining_seconds,
            })
        current_count = redis_client.scard(session_slots_key)
        if current_count >= MAX_SLOTS_PER_SESSION:
            return JsonResponse({
                "success": False,
                "message": f"Max {MAX_SLOTS_PER_SESSION} slots allowed"
            })
        acquired = redis_client.set(
            lock_key,
            session_id,
            nx=True,
            ex=remaining_seconds
        )
        if not acquired:
            return JsonResponse({
                "success": False,
                "message": "Slot already reserved"
            })
        redis_client.sadd(session_slots_key, slotid)
        redis_client.expire(session_slots_key, remaining_seconds)
        return JsonResponse({
            "success": True,
            "action": "selected",
            "session_id": session_id,
            "remaining_seconds": remaining_seconds,
        })
    except Exception as e:
        logger.exception("reserveslot failed: %s", e)
        return JsonResponse({
            "success": False,
            "message": "Internal server error"
        }, status=500)


from django.http import JsonResponse
from django.utils import timezone

from django.utils import timezone
from datetime import datetime

def getreservedslots(request):
    groundid = request.GET.get("ground_id")
    date_str = request.GET.get("date")
    if not (groundid and date_str):
        return JsonResponse({"success": False, "message": "Missing parameters"})
    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"success": False, "message": "Invalid date"})

    now = timezone.localtime()
    today = now.date()
    current_time = now.time()

    slot_qs = slots.objects.filter(
        ground_id=groundid,
        date=selected_date,
    )

    booked_slots = set(
        slot_qs.filter(is_booked=True).values_list("id", flat=True)
    )

    if selected_date < today:
        passed_slot_ids = set(slot_qs.values_list("id", flat=True))
    elif selected_date == today:
        passed_slot_ids = set(
            slot_qs.filter(endtime__lte=current_time).values_list("id", flat=True)
        )
    else:
        passed_slot_ids = set()

    booked_slots.update(passed_slot_ids)
    slot_ids = slot_qs.values_list("id", flat=True)
    user_reserved = []
    others_reserved = []
    user_session_id = None
    if request.user.is_authenticated:
        latest_session = reservationsession.objects.filter(
        user=request.user,
        ground_id=groundid,
        date=selected_date,
    ).order_by('-created_at').first()
    if latest_session:
        session_key = f"session:{latest_session.id}"
        if redis_client.exists(session_key):
            user_session_id = str(latest_session.id)
    for slot_id in slot_ids:
        slot_id = str(slot_id)
        if int(slot_id) in booked_slots:
            continue
        lock_key = f"lock:slot:{groundid}:{slot_id}:{date_str}"
        session_id = redis_client.get(lock_key)
        if not session_id:
            continue
        session_id = session_id.decode() if isinstance(session_id, bytes) else str(session_id)
        if user_session_id and session_id == user_session_id:
            user_reserved.append(slot_id)
        else:
            others_reserved.append(slot_id)
    return JsonResponse({
        "user_reserved": list(set(user_reserved)),
        "others_reserved": list(set(others_reserved)),
        "booked": [str(s) for s in booked_slots],
        "session_id": user_session_id,
    })



client=razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_SECRET_KEY))


def lock_tournament_order_slots_for_payment(t_session):
    order_objs = list(
        Orders.objects.filter(
            tournament_session=t_session,
            Tournament_or_normal="tournament",
            payment_status=False,
            booked=False,
        )
    )

    slot_ids = [
        order.slotsbooked_id
        for order in order_objs
        if order.slotsbooked_id
    ]

    if not slot_ids:
        return False, "No tournament order slots found"

    locked_slots = list(
        slots.objects
        .select_for_update()
        .filter(id__in=slot_ids)
    )

    if len(locked_slots) != len(slot_ids):
        return False, "Some tournament slots were not found"

    now = timezone.now()

    for slot in locked_slots:
        if slot.is_booked:
            return False, "One or more tournament slots are already booked"

        if slot.is_blocked:
            continue

        slot.is_blocked = True
        slot.blocked_at = now

    slots.objects.bulk_update(
        locked_slots,
        ["is_blocked", "blocked_at"]
    )

    return True, None




@login_required
def tournamentcheckout(request, session_id):
    PRICE_MAP = {
        "morning": "t_morning_price",
        "afternoon": "t_afternoon_price",
        "evening": "t_evening_price",
        "night": "t_night_price",
    }
    t_session = get_object_or_404(
        tournamentsession,
        id=session_id,
        user=request.user,
    )
    session_key = f"tournament_session:{session_id}"
    if not redis_client.exists(session_key):
        cancel_tournament_booking_session(t_session)
        return redirect("grounds_page")
    reserved_days = (
        reservetournament.objects
        .filter(session=t_session, status="reserved")
        .prefetch_related("blocked_slots")
    )
    if not reserved_days.exists():
        return redirect("tournamentBookingPage", pk=t_session.ground_id)
    total_amount = 0
    slot_ids = []
    for rd in reserved_days:
        shifts_used = (
            rd.blocked_slots
            .values_list("shift", flat=True)
            .distinct()
        )
        for shift in shifts_used:
            price_field = PRICE_MAP.get(shift)
            if price_field:
                total_amount += getattr(t_session.ground, price_field, 0) or 0
        slot_ids.extend(
            rd.blocked_slots.values_list("id", flat=True)
        )
    pay = (
        payment.objects.filter(
            user=request.user,
            tournament_session=t_session,
            status=False
        )
        .order_by("-created_at")
        .first()
    )
    remaining_seconds = 0
    if pay and pay.expires_at:
        remaining_seconds = int((pay.expires_at - timezone.now()).total_seconds())
    if pay and remaining_seconds <= 0:
        cancel_tournament_booking_session(t_session)
        return redirect("grounds_page")
    return render(request, "bookings/tournamentcheckout.html", {
        "session": t_session,
        "reserved": reserved_days,
        "total": total_amount,
        "ground": t_session.ground,
        "payment_status": request.GET.get("payment"),
    })

@login_required
def create_tournament_razorpay_order(request, session_id):
    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "message": "Invalid request"
        }, status=400)
    PRICE_MAP = {
        "morning": "t_morning_price",
        "afternoon": "t_afternoon_price",
        "evening": "t_evening_price",
        "night": "t_night_price",
    }
    t_session = get_object_or_404(
        tournamentsession,
        id=session_id,
        user=request.user,
    )
    reserved_days = (
        reservetournament.objects
        .filter(session=t_session, status="reserved")
        .prefetch_related("blocked_slots")
    )
    if not reserved_days.exists():
        return JsonResponse({
            "success": False,
            "redirect": "/bookings/grounds/",
            "message": "No reserved slots found"
        }, status=400)
    total_amount = 0
    slot_ids = []
    for rd in reserved_days:
        shifts_used = (
            rd.blocked_slots
            .values_list("shift", flat=True)
            .distinct()
        )
        for shift in shifts_used:
            price_field = PRICE_MAP.get(shift)
            if price_field:
                total_amount += getattr(t_session.ground, price_field, 0) or 0
        slot_ids.extend(
            rd.blocked_slots.values_list("id", flat=True)
        )
    existing_payment = (
        payment.objects.filter(
            user=request.user,
            tournament_session=t_session,
            status=False
        ).order_by("-created_at").first())
    if existing_payment:
        remaining_seconds = int((existing_payment.expires_at - timezone.now()).total_seconds())
        if remaining_seconds <= 0:
            cancel_tournament_booking_session(t_session)
            return JsonResponse({
                "success": False,
                "redirect": "/bookings/grounds/",
                "message": "Previous payment expired"
            }, status=400)
        return JsonResponse({
            "success": True,
            "razorpay_order_id": existing_payment.razorpay_order_id,
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "amount": int(existing_payment.amount * 100),
            "ground_name": t_session.ground.name,
        })
    try:
        with transaction.atomic():
            now = timezone.now()
            pay = payment.objects.create(
                user=request.user,
                tournament_session=t_session,
                amount=total_amount,
                status=False,
                expires_at=now + timedelta(minutes=10)
            )
            for reservation in reserved_days:
                for slot in reservation.blocked_slots.all():
                    Orders.objects.create(
                        user=request.user,
                        ground=t_session.ground,
                        tournament_session=t_session,
                        date=reservation.date,
                        slotsbooked_id=slot.id,
                        transaction_id=f"tournament_{pay.id}_{slot.id}",
                        price=float(slot.price or 0),
                        payment_status=False,
                        booked=False,
                        Tournament_or_normal="tournament",
                    )
            ok, message = lock_tournament_order_slots_for_payment(t_session)
            if not ok:
                raise ValueError(message)
    except ValueError as e:
        cancel_tournament_booking_session(t_session)
        return JsonResponse({
            "success": False,
            "redirect": "/bookings/grounds/",
            "message": str(e)
        }, status=400)
    try:
        razorpay_order = (razorpay_client.order.create({
            "amount": int(pay.amount * 100),
            "currency": "INR",
            "receipt": f"tournament_{pay.id}",
            "notes":{
                "payment_id": str(pay.id),
                "session_id": str(t_session.id),
                "user_id": str(request.user.id),
                "slot_ids": json.dumps(slot_ids),
                "type": "tournament",
            },
        }))
    except Exception:
        logger.exception( "Tournament Razorpay order creation failed")
        cancel_tournament_booking_session(t_session)
        return JsonResponse({"success": False, "message": "Payment gateway error" }, status=500)
    pay.razorpay_order_id = razorpay_order.get("id")
    pay.save(update_fields=["razorpay_order_id"])
    return JsonResponse({
        "success": True,
        "razorpay_order_id": razorpay_order.get("id"),
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "amount": int(pay.amount * 100),
        "ground_name": t_session.ground.name,
    })

def finalize_tournament_razorpay_payment(
    pay,
    razorpay_payment_id
):
    with transaction.atomic():
        pay = (
            payment.objects
            .select_for_update()
            .get(id=pay.id)
        )
        if pay.status:
            return pay
        pay.status = True
        pay.razorpay_payment_id = (
            razorpay_payment_id
        )
        pay.save(
            update_fields=[
                "status",
                "razorpay_payment_id"
            ]
        )
        order_qs = Orders.objects.filter(
            tournament_session=
                pay.tournament_session,
            user=pay.user,
            payment_status=False,
            booked=False,
            Tournament_or_normal=
                "tournament",
        )
        slot_ids = list(
            order_qs.values_list(
                "slotsbooked_id",
                flat=True
            )
        )
        order_qs.update(
            payment_status=True,
            booked=True,
            transaction_id=razorpay_payment_id
        )
        slot_objs = list(slots.objects.select_for_update().filter(id__in=slot_ids))
        for slot in slot_objs:
            slot.is_booked = True
            slot.is_blocked = False
            slot.blocked_at = None
        slots.objects.bulk_update(slot_objs, ["is_booked", "is_blocked", "blocked_at"])
        try:
            tournament_session_id = str(pay.tournament_session.id)
            session_key = f"tournament_session:{tournament_session_id}"
            session_slots_key = f"tournament_session_slots:{tournament_session_id}"
            redis_client.delete(session_key)
            redis_client.delete(session_slots_key)
            tournament_orders = (
            Orders.objects.filter(
                tournament_session=
                    pay.tournament_session,
                user=pay.user,
                Tournament_or_normal=
                    "tournament",
            )
            .select_related("ground")
            )
            for order in tournament_orders:
                lock_key = (
                f"lock:slot:"
                f"{order.ground.id}:"
                f"{order.slotsbooked_id}:"
                f"{order.date}"
                )
                redis_client.delete(lock_key)
            reserved_days = (
            reservetournament.objects.filter(
                session=pay.tournament_session
            )
            )
            for rd in reserved_days:
                day_lock_key = (
                    f"tournament_day_lock:"
                    f"{rd.ground.id}:"
                    f"{rd.date}"
                )
                redis_client.delete(day_lock_key)
        except Exception:
            logger.exception("Failed to clear tournament redis locks")
        try:
            send_booking_event({
                "event": "tournament_booking_confirmed",
                "user_id": str(pay.user.id),
                "payment_id": str(pay.id),
                "razorpay_payment_id": razorpay_payment_id,
                "amount": str(pay.amount),
                "ground":str(pay.tournament_session.ground.name),
            })
        except Exception:
            logger.exception("Failed to send tournament booking event")        
    return pay


from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404

razorpay.api_key = settings.RAZORPAY_KEY_ID
razorpay.api_secret = settings.RAZORPAY_SECRET_KEY

from datetime import timedelta
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import reservationsession, reservedslots, payment

def cancel_booking(booking):
    with transaction.atomic():
        booking = Bookings.objects.select_for_update().get(id=booking.id)
        if booking.is_cancelled:
            return
        slot_ids = list(booking.slotsbooked.values_list("id", flat=True))
        slot_objs = list(slots.objects.select_for_update().filter(id__in=slot_ids))
        for slot in slot_objs:
            slot.is_booked = False
            slot.is_blocked = False
            slot.blocked_at = None
        slots.objects.bulk_update(slot_objs, ["is_booked", "is_blocked", "blocked_at"])
        booking.booked = False
        booking.is_cancelled = True
        booking.save(update_fields=["booked", "is_cancelled"])
        if booking.normal_session:
            Orders.objects.filter(
                normal_session=booking.normal_session,
                user=booking.user,
                booked=True,
            ).update(
                booked=False,
                payment_status=False,
            )
        elif booking.tournament_session:
            Orders.objects.filter(
                tournament_session=booking.tournament_session,
                user=booking.user,
                booked=True,
            ).update(
                booked=False,
                payment_status=False,
            )

@login_required
def cancel_booking_view(request, booking_id):
    booking = get_object_or_404(Bookings, id=booking_id, user=request.user)
    cancel_booking(booking)
    return redirect("booking_detail", booking_id=booking.id)

def my_bookings(request):
    bookings = (
        Bookings.objects
        .filter(user=request.user)
        .select_related("ground")
        .order_by("-created_at")
    )
    return render(request, "bookings/my_bookings.html", {
        "bookings": bookings,
    })


def payment_success_page(request):
    return redirect("grounds_page")

def payment_cancel_page(request):
    session_id = request.GET.get("session_id")
    if session_id:
        return redirect("checkout", session_id=session_id)
    return redirect("grounds_page")


def decode_redis_ids(raw_ids):
    return [int(s.decode() if isinstance(s, bytes) else s) for s in raw_ids]


razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_SECRET_KEY)
)

@login_required
def checkoutpage(request, session_id):
    session = get_object_or_404(
        reservationsession,
        id=session_id,
        user=request.user
    )
    pay = (
        payment.objects.filter(
            session=session,
            user=request.user,
            status=False
        )
        .order_by("-created_at")
        .first()
    )
    if pay and pay.expires_at:
        remaining_seconds = int((pay.expires_at - timezone.now()).total_seconds())
        if remaining_seconds <= 0:
            cancel_normal_booking_session(session)
            return redirect("grounds_page")
    session_key = f"session:{session_id}"
    session_slots_key = f"session_slots:{session_id}"
    if not redis_client.exists(session_key):
        cancel_normal_booking_session(session)
        return redirect("grounds_page")
    raw_slot_ids = redis_client.smembers(session_slots_key)
    if not raw_slot_ids:
        cancel_normal_booking_session(session)
        return redirect("grounds_page")
    slot_ids = decode_redis_ids(raw_slot_ids)
    slot_objs = list(
        slots.objects.filter(id__in=slot_ids)
        .only("id", "price", "starttime", "endtime","is_blocked","is_booked")
    )
    total = sum(float(slot.price or 0) for slot in slot_objs)
    return render(request, "bookings/checkoutpage.html", {
        "session": session,
        "slots": slot_objs,
        "total": total,
        "ground": session.ground,
        "payment_status":request.GET.get("payment"),
    })


@login_required
def booking_detail(request, booking_id):
    booking = get_object_or_404(Bookings, id=booking_id, user=request.user)
    slots_booked = booking.slotsbooked.all().order_by("starttime")
    return render(request, "bookings/booking_detail.html", {
        "booking": booking,
        "slots": slots_booked,
    })


@login_required
def create_razorpay_order(request, session_id):
    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "message": "Invalid request"
        }, status=400)
    session = get_object_or_404(
        reservationsession,
        id=session_id,
        user=request.user
    )
    session_key = f"session:{session_id}"
    session_slots_key = f"session_slots:{session_id}"
    if not redis_client.exists(session_key):
        cancel_normal_booking_session(session)
        return JsonResponse({
            "success": False,
            "redirect": "/bookings/grounds/",
            "message": "Session expired"
        }, status=400)
    raw_slot_ids = redis_client.smembers(session_slots_key)
    if not raw_slot_ids:
        cancel_normal_booking_session(session)
        return JsonResponse({
            "success": False,
            "redirect": "/bookings/grounds/",
            "message": "No slots selected"
        }, status=400)
    slot_ids = decode_redis_ids(raw_slot_ids)
    slot_objs = list(
        slots.objects.filter(id__in=slot_ids)
        .only("id", "price", "starttime", "endtime")
    )
    total = sum(float(slot.price or 0) for slot in slot_objs)
    existing_payment = (
        payment.objects.filter(
            session=session,
            user=request.user,
            status=False
        )
        .order_by("-created_at")
        .first()
    )
    if existing_payment:
        remaining_seconds = int((existing_payment.expires_at - timezone.now()).total_seconds())
        if remaining_seconds <= 0:
            cancel_normal_booking_session(session)
            return JsonResponse({
                "success": False,
                "redirect": "/bookings/grounds/",
                "message": "Previous payment expired"
            }, status=400)
        return JsonResponse({
            "success": True,
            "razorpay_order_id":existing_payment.razorpay_order_id,
            "razorpay_key_id":settings.RAZORPAY_KEY_ID,
            "amount": int(existing_payment.amount * 100),
            "ground_name":session.ground.name,
        })
    try:
        with transaction.atomic():
            now = timezone.now()
            pay = payment.objects.create(
            user=request.user,
            session=session,
            amount=total,
            status=False,
            expires_at=now + timedelta(minutes=10)
            )
            for slot in slot_objs:
                Orders.objects.create(
                    user=request.user,
                    ground=session.ground,
                    date=session.date,
                    normal_session=session,
                    slotsbooked_id=slot.id,
                    transaction_id=f"normal_{pay.id}_{slot.id}",
                    price=float(slot.price or 0),
                    payment_status=False,
                    booked=False,
                    Tournament_or_normal="normal",
                )
            ok,message = lock_normal_order_slots_for_payment(session)
            if not ok:
                raise ValueError(message)
    except ValueError as e:
        cancel_normal_booking_session(session)
        return JsonResponse({
            "success": False,
            "message": str(e)
        }, status=409)
    try:
        razorpay_order = razorpay_client.order.create(
            {
                "amount": int(total * 100),
                "currency": "INR",
                "receipt": f"pay_{pay.id}",
                "notes": {
                    "payment_id": str(pay.id),
                    "session_id": str(session.id),
                    "user_id": str(request.user.id),
                    "slot_ids": json.dumps(slot_ids),
                    "type": "normal",
                },
            }
        )
    except Exception:
        logger.exception("Razorpay order creation failed")
        cancel_normal_booking_session(session)
        return JsonResponse(
            {"success": False, "message": "Payment gateway error. Please try again."},
            status=502,
        )
    pay.razorpay_order_id = razorpay_order["id"]
    pay.save(update_fields=["razorpay_order_id"])
    return JsonResponse({
        "success": True,
        "razorpay_order_id": razorpay_order["id"],
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "amount": int(total * 100),
        "ground_name": session.ground.name,
    })


def lock_normal_order_slots_for_payment(session):
    order_objs = list(
        Orders.objects.filter(
            normal_session=session,
            Tournament_or_normal="normal",
            payment_status=False,
            booked=False,
        )
    )
    slot_ids = [o.slotsbooked_id for o in order_objs if o.slotsbooked_id]
    if not slot_ids:
        return False, "No order slots found"
    locked_slots = list(
        slots.objects.select_for_update().filter(id__in=slot_ids)
    )
    if len(locked_slots) != len(slot_ids):
        return False, "Some slots were not found"
    now = timezone.now()
    for slot in locked_slots:
        if slot.is_booked:
            logger.warning("Slot %d is already booked", slot.id)
            return False, "One or more slots are already booked"      
        if slot.is_blocked:
            logger.warning("Slot %d is currently locked", slot.id)
            return False, "Slot currently locked"
        slot.is_blocked = True
        slot.blocked_at = now
    slots.objects.bulk_update(locked_slots, ["is_blocked", "blocked_at"])
    return True, None



from .kafka_producer import send_booking_event


from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
import json


@csrf_exempt
def payment_success_razorpay_webhook(request):
    payload = request.body
    sig = request.META.get("HTTP_X_RAZORPAY_SIGNATURE")
    try:
        razorpay_client.utility.verify_webhook_signature(
            payload.decode(),
            sig,
            settings.RAZORPAY_WEBHOOK_SECRET
        )
    except Exception:
        return HttpResponse(status=400)
    event = json.loads(payload)
    if event.get("event") == "payment.captured":
        payment_entity = event["payload"]["payment"]["entity"]
        razorpay_order_id = payment_entity.get("order_id")
        razorpay_payment_id = payment_entity.get("id")
        try:
            pay = payment.objects.get(razorpay_order_id=razorpay_order_id)
            if pay.session:
               finalize_razorpay_payment(pay, razorpay_payment_id)
            elif pay.tournament_session:
               finalize_tournament_razorpay_payment(pay, razorpay_payment_id)
        except Exception:
            logger.exception("Razorpay webhook finalize failed")
            return HttpResponse(status=500)
    elif event.get("event") == "payment.failed":
        payment_entity = event["payload"]["payment"]["entity"]
        razorpay_order_id = payment_entity.get("order_id")
        try:
            pay = payment.objects.get(razorpay_order_id=razorpay_order_id)
            remaining_seconds = int((pay.expires_at - timezone.now()).total_seconds())
            if remaining_seconds <= 0:
                if pay.session:
                   cancel_normal_booking_session(pay.session)
                if pay.tournament_session:
                   cancel_tournament_booking_session(pay.tournament_session)
                logger.info("Razorpay payment failed for order %s", razorpay_order_id)
        except Exception:
            logger.exception("Razorpay payment failed handler error")
    return HttpResponse(status=200)


@login_required
def payment_waiting_page(request, razorpay_order_id):
    pay = get_object_or_404(payment, razorpay_order_id=razorpay_order_id, user=request.user)
    return render(
        request,
        "bookings/payment_waiting.html",
        {"razorpay_order_id": pay.razorpay_order_id},
    )
    
@login_required
def check_payment_status(request, razorpay_order_id):
    try:
        pay = payment.objects.get(razorpay_order_id=razorpay_order_id, user=request.user)
        if pay.status:
            booking = Bookings.objects.filter(
                user=pay.user,
                normal_session=pay.session,
                tournament_session=pay.tournament_session,
                payment_status=True,
            ).order_by("-created_at").first()
            if not booking:
                return JsonResponse({"status": "pending"})
            return JsonResponse({
                "status": "success",
                "redirect": f"/bookings/booking/{booking.id}/"
            })
        remaining_seconds = int((pay.expires_at - timezone.now()).total_seconds())
        if remaining_seconds <= 0:
            if pay.session:
               cancel_normal_booking_session(pay.session)
            if pay.tournament_session:
               cancel_tournament_booking_session(pay.tournament_session)
            return JsonResponse({"status": "expired", "redirect": "/bookings/grounds/"})
        return JsonResponse({"status": "pending"})
    except payment.DoesNotExist:
        return JsonResponse({"status": "failed", "redirect": "/bookings/grounds/"})
    except Exception:
        logger.exception("check_payment_status error")
        return JsonResponse({"status": "failed", "redirect": "/bookings/grounds/"})

def finalize_razorpay_payment(pay, razorpay_payment_id):
    with transaction.atomic():
        pay = payment.objects.select_for_update().get(id=pay.id)
        if pay.status:
            return pay
        pay.status = True
        pay.razorpay_payment_id = razorpay_payment_id
        pay.save(update_fields=["status", "razorpay_payment_id"])
        slot_ids = list(
            Orders.objects.filter(
                normal_session=pay.session,
                user=pay.user,
                payment_status=False,
                booked=False,
                Tournament_or_normal="normal",
            ).values_list("slotsbooked_id", flat=True)
        )
        Orders.objects.filter(
            normal_session=pay.session,
            user=pay.user,
            payment_status=False,
            booked=False,
            Tournament_or_normal="normal",
        ).update(
            payment_status=True,
            booked=True,
            transaction_id=razorpay_payment_id
        )
        slots.objects.filter(id__in=slot_ids).update(
            is_booked=True,
            is_blocked=False,
            blocked_at=None
        )
    if pay.session:
        redis_client.delete(f"session:{pay.session.id}")
        redis_client.delete(f"session_slots:{pay.session.id}")
    try:
        send_booking_event({
            "event": "payment_success",
            "user_id": str(pay.user.id),
            "payment_id": str(pay.id),
            "razorpay_payment_id": razorpay_payment_id,
            "amount": str(pay.amount),
            "ground": str(pay.session.ground.name),
            "date": str(pay.session.date),
        })
    except Exception:
        logger.exception("Failed to send booking event")
    return pay

@csrf_exempt
@login_required
def payment_success_razorpay(request):
    if request.method != "POST":
        return JsonResponse({"success": False}, status=405)
    data = json.loads(request.body)
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_signature = data.get("razorpay_signature")
    error = data.get("error") 
    if error:
        try:
            pay = payment.objects.get(razorpay_order_id=razorpay_order_id,user=request.user)
            remaining_seconds = int((pay.expires_at - timezone.now()).total_seconds())
            if remaining_seconds > 0:
                if pay.session: 
                    return JsonResponse({
                        "success": False,
                        "redirect": f"/bookings/checkout/{pay.session.id}/?payment=cancel"
                    })
                if pay.tournament_session:
                    return JsonResponse({
                        "success": False,
                        "redirect": f"/bookings/tournamentcheckout/{pay.tournament_session.id}/?payment=cancel"
                    })
            if pay.session:
               cancel_normal_booking_session(pay.session)
            if pay.tournament_session:
               cancel_tournament_booking_session(pay.tournament_session)

        except Exception:
            pass
        return JsonResponse({
            "success": False,
            "redirect": "/bookings/grounds/"
        })
    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
    except Exception:
        return JsonResponse({"success": False, "message": "Invalid signature"})
    try:
        pay = payment.objects.get(razorpay_order_id=razorpay_order_id,user=request.user)
        if pay.session:
           finalize_razorpay_payment(pay, razorpay_payment_id)
        if pay.tournament_session:
            finalize_tournament_razorpay_payment(pay, razorpay_payment_id)
        return JsonResponse({"success": True})
    except Exception:
        logger.exception("Razorpay finalize failed")
        return JsonResponse({"success": False, "message": "Finalization failed"})
       
def get_lat_long(address):
    api_key = "" ###
    url = "https://us1.locationiq.com/v1/search"
    params = {"q": address, "key": api_key, "format": "json"}
    headers = {"User-Agent": "CricStore-App/1.0"}
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    if isinstance(data, list) and data:
        loc = data[0]
        return loc["lat"], loc["lon"]
    return None, None


def getuserlocation(request):
    if request.method == "POST":
        lat=request.POST.get("lat")
        lon=request.POST.get("lon")
        if lat and lon:
            request.session["user_lat"] = float(lat)
            request.session["user_lon"] = float(lon)
            return JsonResponse({
                "success": True,
                "message": "Location updated successfully!"
            })
        return JsonResponse({
            "success": False,
            "message": "Couldn't fetch location. Try again."
        })
    return JsonResponse({"success": False, "message": "Invalid request."})

def handle_ground_info(context):
    ground_name = context.get("ground_or_turf_name") or context.get("ground_name")
    city = context.get("city")
    area = context.get("area")
    if not ground_name:
        return {"message": "Please tell me the ground or turf name."}
    filters = {"name__icontains": ground_name}
    if city:
        filters["city__icontains"] = city
    if area:
        filters["address__icontains"] = area
    ground = Ground.objects.filter(**filters).first()
    if not ground:
        return {"message": f"Sorry, I couldn’t find any ground named {ground_name}."}
    if context.get("intent")=="address":
        return {"message":f"the address the ground is {ground.address}"}
    if context.get("intent") == "ground_status":
        is_open = bool(int.from_bytes(ground.opens, "little")) if ground.opens is not None else False
        if is_open:
            return {"message": f"Yes, {ground.name} is open today!"}
        else:
            return {"message": f" Sorry, {ground.name} is closed today."}
    if context.get("intent") == "ground_facilities":
        facilities = []
        if bool(int.from_bytes(ground.batballprovided, "little")):
            facilities.append("Bat and Ball Provided")
        if bool(int.from_bytes(ground.washroomsavailable, "little")):
            facilities.append("Washrooms Available")
        if ground.Grounddimensions:
            facilities.append(f"Dimensions: {ground.Grounddimensions} meters")

        if not facilities:
            return {"message": f"No specific facility information available for {ground.name}."}
        return {"message": f"{ground.name} offers: {', '.join(facilities)}."}
    is_open = bool(int.from_bytes(ground.opens, "little")) if ground.opens is not None else False
    rating = ground.rating or "N/A"
    price = ground.price or "N/A"
    sport = ground.sporttype.capitalize()
    facilities_list = []
    if bool(int.from_bytes(ground.batballprovided, "little")):
        facilities_list.append("Bat & Ball Provided")
    if bool(int.from_bytes(ground.washroomsavailable, "little")):
        facilities_list.append("Washrooms")
    if ground.Grounddimensions:
        facilities_list.append(f"Dimensions: {ground.Grounddimensions}m")
    facilities_str = ", ".join(facilities_list) if facilities_list else "Basic facilities available"
    response = (
        f"*{ground.name}* ({sport}) — located in {ground.city}.\n"
        f" Average price: ₹{price}\n Rating: {rating}\n"
        f"Facilities: {facilities_str}\n"
        f"Status: {' Open' if is_open else 'Closed'}"
    )
    return {"message": response}

from collections import defaultdict

def detect_booking_type(query):
    keywords = ["tournament", "league"]
    q = query.lower()
    return "tournament" if any(k in q for k in keywords) else "normal_booking"
import re
from datetime import datetime, timedelta
from django.utils import timezone

import re

def normalize_date_text(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\b(on|at|by|the|from|to)\b', ' ', text)
    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text)
    keywords = ["this", "next", "coming", "upcoming", "current"]
    weekdays = [
        "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday"
    ]
    SHIFTS=["morning", "afternoon", "evening", "night"]
    for k in keywords:
        for d in weekdays:
            text = re.sub(rf'\b{k}{d}\b', f"{k} {d}", text)
    text = re.sub(r'\b(this|next)(weekend)\b', r'\1 \2', text)
    for d in weekdays + ["weekend"]:
        for s in SHIFTS:
            text = re.sub(rf'\b{d}{s}\b', f"{d} {s}", text)
    for k in keywords:
        for d in weekdays + ["weekend"]:
            for s in SHIFTS:
                text = re.sub(
                    rf'\b{k}{d}{s}\b',
                    f"{k} {d} {s}",
                    text
                )
    text = re.sub(r'\s+', ' ', text).strip()
    return text
SHIFTS=["morning", "afternoon", "evening", "night"]
def strip_shifts(text):
    if not text:
        return ""
    pattern = r'\b(' + '|'.join(SHIFTS) + r')\b'
    return re.sub(pattern, '', text).strip()


def parse_natural_date_tournament(text):
    WEEKDAYS = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6
    }
    if not text:
        return None
    text = normalize_date_text(text)
    today = timezone.now().date()
    for fmt in (
        "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d",
        "%d %b %Y", "%d %B %Y",
        "%d-%m-%y", "%d/%m/%y"
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    for fmt in ("%d %b", "%d %B"):
        try:
            parsed = datetime.strptime(text, fmt)
            current_year = today.year
            if parsed.month < today.month or (parsed.month == today.month and parsed.day < today.day):
                current_year += 1
            return parsed.replace(year=current_year).date()
        except ValueError:
            pass
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text == "day after tomorrow":
        return today + timedelta(days=2)
    words = text.split()
    current_day = today.weekday()
    if len(words) == 1 and words[0] in WEEKDAYS:
        words = ["this", words[0]]
    if "weekend" in words:
        days_until_sat = (5 - current_day) % 7
        if "next" in words:
            days_until_sat += 7
        return today + timedelta(days=days_until_sat)
    if words[-1] in WEEKDAYS:
        target = WEEKDAYS[words[-1]]
        delta = (target - current_day) % 7
        if delta == 0 :
            if words[0] in ["this", "current"]:
                return today
            elif words[0] in ["next", "upcoming"]:
                delta = 7
        return today + timedelta(days=delta)
    if text.isdigit():
        day = int(text)
        month = today.month
        year = today.year
        if day < today.day:
            month += 1
            if month > 12:
                month = 1
                year += 1
        return datetime(year, month, day).date()
    return None
def parse_date_constraints(start,end,total_days):
    duration_days = int(total_days) if total_days and str(total_days).isdigit() else None
    if start and "weekend" in start.lower():
        today = timezone.now().date()
        current_day = today.weekday()
        days_until_sat = (5 - current_day) % 7
        if "next" in start.lower():
            days_until_sat += 7
        start_date = today + timedelta(days=days_until_sat)
        if not end:
            end_date = start_date + timedelta(days=1)
            return {"success": True, "start": start_date, "end": end_date}
        else:
            end_clean=strip_shifts(end)
            end_date = parse_natural_date_tournament(end_clean)
            if end_date and end_date >= start_date:
                return {"success": True, "start": start_date, "end": end_date}
            else:
                end_date = start_date + timedelta(days=7)
                if end_date >= start_date:
                    return {"success": True, "start": start_date, "end": end_date}
                else:
                    return {"success": False, "message": "End date must be after start date."}
    start_clean = strip_shifts(normalize_date_text(start))
    end_clean = strip_shifts(normalize_date_text(end))
    start_date = parse_natural_date_tournament(start_clean)
    end_date = parse_natural_date_tournament(end_clean)
    today= timezone.now().date()
    if start_date and end_date and start_date <= end_date:
        return {"success": True, "start": start_date, "end": end_date}
    if start_date and end_date and start_date > end_date:
        end_date = end_date + timedelta(days=7)
        return {"success": True, "start": start_date, "end": end_date}
    if start_date and duration_days:
        return {
            "success": True,
            "start": start_date,
            "end": start_date + timedelta(days=duration_days - 1)
        }
    return {
        "success": False,
        "message": "Unable to understand tournament dates. Please specify start and end clearly."
    }

def shifts(allowedshifts, start, end):
    default = ["morning", "afternoon", "evening", "night"]
    result = {}
    constraint = allowedshifts.get("constraint_type") if allowedshifts else ""
    if constraint == "only":
        allowed = allowedshifts.get("start_day", [])
        current = start
        while current <= end:
            result[current] = allowed.copy()
            current += timedelta(days=1)
        return result
    current = start
    dayindex = 0
    totaldays = (end - start).days
    while current <= end:
        if dayindex == 0:
            if allowedshifts and allowedshifts.get("start_day"):
                idx = default.index(allowedshifts["start_day"][0])
                result[current] = default[idx:]
            else:
                result[current] = default.copy()
        elif dayindex == totaldays:
            if allowedshifts and allowedshifts.get("end_day"):
                idx = default.index(allowedshifts["end_day"][0])
                result[current] = default[:idx + 1]
            else:
                result[current] = default.copy()
        else:
            result[current] = default.copy()
        current += timedelta(days=1)
        dayindex += 1
    return result


def calculatematchtimings(overs):
    balltime=1
    inningsbreak=20
    oneover_minutes=4.5 
    return (overs*oneover_minutes) + inningsbreak
SHIFT_DURATION_MINUTES = {
    "morning": 240,     
    "afternoon": 240, 
    "evening": 300,    
    "night": 300,       
}
timings={
    "morning":(time(6,0),time(11,0)),
    "afternoon":(time(11,0),time(15,0)),
    "evening":(time(15,0),time(19,0)),
    "night":(time(19,0),time(23,59))
}

from functools import lru_cache
SHIFT_LIST = ["morning", "afternoon", "evening", "night"]
SHIFT_BIT = {s: 1 << i for i, s in enumerate(SHIFT_LIST)}

def check(ground, start, end, shiftperday, budget, matches, overs, show=False):
    timepermatch = calculatematchtimings(overs)
    matches_per_shift = {
        shift: (SHIFT_DURATION_MINUTES[shift] // timepermatch
                if SHIFT_DURATION_MINUTES[shift] >= timepermatch else 0)
        for shift in SHIFT_LIST
    }
    avail_mask_per_day = {}
    total_possible_matches = 0
    current = start
    while current <= end:
        day_slots = Slot.objects.filter(ground=ground, date=current)
        slotbyshift = {}
        for slot in day_slots:
            slotbyshift.setdefault(slot.shift, []).append(slot)
        day_mask = 0
        for shift in SHIFT_LIST:
            shift_slots = slotbyshift.get(shift, [])
            if not shift_slots:
                continue
            blocked = any(s.is_booked or s.is_blocked for s in shift_slots)
            if not blocked:
                day_mask |= SHIFT_BIT[shift]
                total_possible_matches += matches_per_shift[shift]

        avail_mask_per_day[current] = day_mask
        current += timedelta(days=1)
    if total_possible_matches < matches:
        return {
            "success": False,
            "message": "This tournament cannot be played within the given dates"
        }
    dates = list(avail_mask_per_day.keys())
    max_matches_per_day = sum(matches_per_shift.values())
    @lru_cache(None)
    def dfs(index, currmatches, currbudget):
        if currmatches >= matches:
            return (True, []) if show else (0, [])
        if index == len(dates):
            return (False, None) if show else (float("inf"), None)
        remaining_days = len(dates) - index
        if currmatches + remaining_days * max_matches_per_day < matches:
            return (False, None) if show else (float("inf"), None)
        current_date = dates[index]
        allowed_mask = avail_mask_per_day[current_date]
        user_mask = 0
        for s in shiftperday.get(current_date, []):
            user_mask |= SHIFT_BIT[s]
        valid_mask = allowed_mask & user_mask
        res = dfs(index + 1, currmatches, currbudget)
        if show and res[0]:
            return True, res[1]
        if not show and res[0] < float("inf"):
            return res
        submask = valid_mask
        while submask:
            cost = 0
            gained = 0
            shifts = []
            for shift in SHIFT_LIST:
                if submask & SHIFT_BIT[shift]:
                    price = getattr(ground, f"t_{shift}_price", None)
                    if price is None:
                        break
                    cost += price
                    gained += matches_per_shift[shift]
                    shifts.append(shift)
            else:
                if currbudget + cost <= budget:
                    nxt = dfs(
                        index + 1,
                        currmatches + gained,
                        currbudget + cost
                    )

                    if show and nxt[0]:
                        return True, [(current_date, shifts)] + nxt[1]

                    if not show:
                        total_cost = cost + nxt[0]
                        if total_cost < res[0]:
                            res = (total_cost, [(current_date, shifts)] + nxt[1])
            submask = (submask - 1) & valid_mask
        return res
    result = dfs(0, 0, 0)
    if show:
        return {
            "success": result[0],
            "total_cost": None,
            "schedule": result[1]
        }
    else:
        if result[1] is None:
            return {
                "success": False,
                "total_cost": None,
                "schedule": None,
                "message": "No valid shift combination found within budget"
            }
        return {
            "success": True,
            "total_cost": result[0],
            "schedule": result[1]
        }


def showavailability(grounds, start, end, shiftsperday):
    available_grounds = []
    for ground in grounds:
        is_valid = True
        current = start
        while current <= end:
            day_slots = slots.objects.filter(ground=ground, date=current)
            slotbyshift = {}
            for slot in day_slots:
                slotbyshift.setdefault(slot.shift, []).append(slot)
            for required_shift in shiftsperday.get(current, []):
                shift_slots = slotbyshift.get(required_shift, [])
                if not shift_slots:
                    is_valid = False
                    break
                if any(slot.is_booked or slot.is_blocked for slot in shift_slots):
                    is_valid = False
                    break
            if not is_valid:
                break
            current += timedelta(days=1)
        if is_valid:
            available_grounds.append(ground)
    return available_grounds

from django.db.models import Q, Avg
def price_lte_q(value):
  return (
  Q(morning_price__lte=value) |
  Q(afternoon_price__lte=value) |
  Q(evening_price__lte=value) |
  Q(night_price__lte=value)
  )

def parsehours(hours_text):
    wordtonum={
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10
    }
    if not hours_text:
      return None
    text = str(hours_text).lower()
    digit_match=re.search(r'(\d+)',text)
    if digit_match:
        return int(digit_match.group())
    for word, value in wordtonum.items():
       if word in text:
         return value
    return None
 
    
def price_gte_q(value):
  return (
  Q(morning_price__gte=value) |
  Q(afternoon_price__gte=value) |
  Q(evening_price__gte=value) |
  Q(night_price__gte=value)
  )

from .models import slots as Slot
def userquerychatbot(request):
    if request.method != "POST":
        return JsonResponse({"message": "Use POST for booking agent actions."}, status=405)

    payload = read_chat_payload(request)
    query = str(payload.get("query", "")).strip()
    mode = str(payload.get("mode", "")).strip()
    if not mode:
        return JsonResponse({'message':"Mode parameter is missing."})
    required_fields = normalize_required_fields(payload.get("required_fields"))
    context = get_agent_context(request, mode)
    if query.lower() in {"start over", "reset", "new search", "restart"}:
        reset_agent_context(context, mode)
        request.session.modified = True
        return JsonResponse({"message": "Started a fresh conversation. Tell me what you'd like to do next."})

    if context.get("pending_action"):
        if is_affirmative_reply(query):
            context["confirmation_approved"] = True
            request.session.modified = True
        elif is_negative_reply(query):
            clear_pending_action(context)
            context["stage"] = "collecting_details"
            request.session.modified = True
            return JsonResponse({"message": "Okay, I won't continue with that action. Tell me what you want to change next."})
        elif query:
            clear_pending_action(context)

    if mode=="normal_booking":
      booking_type="normal_booking"
      print("Required fields sent to backend:", required_fields)
      output = interpretgroundquery(query,booking_type,required_fields)
      print("Chatbot Output:",output)
      print("previouscontext:", context)
      if output.get("intent")=="unknown" and "intent" in context:
          output["intent"]=context["intent"]
      raw_intent = (output.get("intent") or "").lower()
      print("raw_intent:", raw_intent)
      INTENT_MAP = {
      "show": "show_ground",
      "find": "show_ground",
      "search": "show_ground",
      "recommend": "show_ground",
      "suggest": "show_ground",
      "view": "show_ground",
      "book": "book",
      "reserve": "book",
      "schedule": "book",
      "cancel": "cancel_booking",
      "change": "cancel_booking",
      "modify": "cancel_booking",
      "reschedule": "reschedule",
      "about": "ground_info",
      "info_ground": "ground_info",
      "tellme": "ground_info",
      }
      if raw_intent in ["show_ground","book","cancel_booking","reschedule","ground_info"]:
          normalized_intent = raw_intent
      else:
         normalized_intent = INTENT_MAP.get(raw_intent, "unknown")
      print("Normalized Intent:", normalized_intent)
      merge_agent_filters(context, output.get("filters", {}))
      print("output context:",output)
      if normalized_intent != "unknown":
        context["intent"] = normalized_intent
      context['booking_type']=output.get('booking_type')
      context["stage"] = "understanding_request"
      request.session.modified = True
      print("Updated Chatbot Context:",context)
      sport_type = (context.get("sporttype") or "").lower().strip()
      ground_or_turf = (context.get("ground_or_turf") or "").lower().strip()
      if not sport_type:
       q = query.lower()
       if "football" in q:
          sport_type = "football"
       elif "cricket" in q:
          sport_type = "cricket"
       elif "hockey" in q:
          sport_type = "hockey"
       elif "badminton" in q:
          sport_type = "badminton"
       elif "tennis" in q:
          sport_type = "tennis"
       elif "volleyball" in q:
          sport_type = "volleyball"
      outdoor_sports = ["cricket", "football", "hockey"]
      if not sport_type:
        return JsonResponse({'message':"Which sport are you looking to book a ground for ?","required_fields":["sport_type"]})
      if sport_type in outdoor_sports:
        if not ground_or_turf:
            response_message = f"For {sport_type.capitalize()}, would you like to book a ground or a turf?,"
            return JsonResponse({
                "message": response_message,"required_fields":["ground_or_turf"],
            })
      else:
        ground_or_turf = "turf"
      context["sporttype"] = sport_type
      context["ground_or_turf"] = ground_or_turf
      request.session.modified = True
      if sport_type:
       grounds = Ground.objects.filter(sporttype__icontains=sport_type)
       print("grounds by sport_type:", grounds)
      if ground_or_turf:
          grounds=grounds.filter(types__icontains=ground_or_turf)
          print("grounds by ground_or_turf:", grounds)
      bookingtype= context.get("booking_type", "").lower().strip()
      if bookingtype=="normal_booking" and context.get("intent") == "show_ground":
         context["stage"] = "showing_options"
         if not context.get("ground_or_turf_name"):
          if context.get("date"):
             parsed_date=parse_natural_date(context["date"])
             if not parsed_date:
              return JsonResponse({
                 "message": "I couldn't understand the date. Please say something like '28 Jan' or 'tomorrow'.",
                 "required_fields": ["date"]
                })
             context["date"]=parsed_date.isoformat()
          if context.get("nearme") and not context.get("radius_km"):
             context["radius_km"] = 15
             if not request.session.get("user_lat") or not request.session.get("user_lon"):
                 html_page=render_to_string("bookings/location-detection.html",request=request)
                 return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})      
             user_lat = float(request.session["user_lat"])
             user_lon = float(request.session["user_lon"])
             print("Finding grounds near user at:", user_lat, user_lon)
             grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
             if isinstance(grounds, list):
                 ground_ids = [g.id for g in grounds]
                 grounds = Ground.objects.filter(id__in=ground_ids)
                 cities= Ground.objects.values_list('city', flat=True).distinct()
                 html_page = render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                 return JsonResponse({"message":"these are the grounds near to you","html": html_page})
          if not context.get("city"):
             if context.get("nearme") and not context.get("radius_km"):
               context["radius_km"] = 15
             if context.get("radius_km"):
               if not request.session.get("user_lat") or not request.session.get("user_lon"):
                 html_page=render_to_string("bookings/location-detection.html",request=request)
                 return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})      
               user_lat = float(request.session["user_lat"])
               user_lon = float(request.session["user_lon"])
               print("Finding grounds near user at:", user_lat, user_lon)
               grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
               if isinstance(grounds, list):
                 ground_ids = [g.id for g in grounds]
                 grounds = Ground.objects.filter(id__in=ground_ids)
                 cities= Ground.objects.values_list('city', flat=True).distinct()
                 html_page = render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                 return JsonResponse({"message":"these are the grounds near to you","html": html_page})
             return JsonResponse({'message': "Please tell me which city you want to search grounds in.","required_fields":["city"]})
         if context.get("city"):
            grounds = grounds.filter(city__icontains=context["city"])
            print("grounds by city:", grounds)
         if context.get("area"):
            grounds = grounds.filter(address__icontains=context["area"])
         if context.get("radius_km"):
            if not request.session.get("user_lat") or not request.session.get("user_lon"):
                html_page=render_to_string("bookings/location-detection.html",request=request)
                return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})
            user_lat = float(request.session["user_lat"])
            user_lon = float(request.session["user_lon"])
            grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
            if isinstance(grounds, list):
              ground_ids = [g.id for g in grounds]
              grounds = Ground.objects.filter(id__in=ground_ids)
         if context.get("rating_min"):
            grounds = grounds.filter(rating__gte=float(context["rating_min"]))
         if context.get("rating_semantic") == "top_rated":
            grounds = grounds.filter(rating__gte=3).order_by('-rating')
         elif context.get("rating_semantic") == "low_rated":
            grounds = grounds.filter(rating__lte=3).order_by('rating')
         if context.get("price_semantic") == "cheaper" and not context.get("price"):
            avg_price = grounds.aggregate(
              avg_morning=Avg("morning_price"),
              avg_afternoon=Avg("afternoon_price"),
              avg_evening=Avg("evening_price"),
              avg_night=Avg("night_price"),
            )
            prices = [
              avg_price["avg_morning"],
              avg_price["avg_afternoon"],
              avg_price["avg_evening"],
              avg_price["avg_night"],
             ]
            prices = [p for p in prices if p is not None]
            if prices:
              overall_avg = sum(prices) / len(prices)
            grounds = grounds.filter(price_lte_q(overall_avg))
         elif context.get("price_semantic") == "expensive" and not context.get("price"):
            avg_price = grounds.aggregate(
              avg_morning=Avg("morning_price"),
              avg_afternoon=Avg("afternoon_price"),
              avg_evening=Avg("evening_price"),
              avg_night=Avg("night_price"),
            )
            prices = [
              avg_price["avg_morning"],
              avg_price["avg_afternoon"],
              avg_price["avg_evening"],
              avg_price["avg_night"],
             ]
            prices = [p for p in prices if p is not None]
            if prices:
               overall_avg = sum(prices) / len(prices)
            grounds = grounds.filter(price_gte_q(overall_avg))
         if context.get("price"):
            max_price = float(context["price"]) + 100
            grounds = grounds.filter(price_lte_q(max_price))
         if context.get("rating"):
            grounds = grounds.filter(rating__gte=float(context["rating"]))
            cities= Ground.objects.values_list('city', flat=True).distinct()
            context["stage"] = "showing_grounds"
            html_page = render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":context.get("city")},request=request)
            return JsonResponse({"message":"these are grounds based on your requirements","html": html_page})
         if context.get("ground_or_turf_name"):
            if not context.get("area"):
                return JsonResponse({'message': "Please tell me which area this ground is in","required_fields":["area"]})
            ground = Ground.objects.filter(
                name__icontains=context["ground_or_turf_name"],
                city__icontains=context["city"],
                address__icontains=context["area"]
            ).first()
            if not ground:
                grounds=Ground.objects.filter(address__icontains=context["area"])
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page= render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({'message': "I found multiple grounds in that area. Please select one from the list below.","html":html_page})
            if context.get("open"):
                if ground.opens:
                    return JsonResponse({'message':"yes it's open"})
                else:
                    return JsonResponse({"message":"sorry today ground is closed "})
            date_str = context.get("date")
            if date_str:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    date_obj = timezone.now().date()
            else:
                date_obj = timezone.now().date()
            date_for_input = date_obj.strftime('%Y-%m-%d')
            today = timezone.now().date().strftime('%Y-%m-%d')
            cities = Ground.objects.values_list('city', flat=True).distinct()
            time_slots = Slot.objects.filter(ground=ground, date=date_obj).order_by('starttime')
            booked = time_slots.filter(is_booked=True)
            reserved = time_slots.filter(is_blocked=True)
            available = time_slots.filter(is_blocked=False, is_booked=False)
            userreservedslots = []
            if request.user.is_authenticated:
                usersession = reservationsession.objects.filter(
                    user=request.user, ground=ground, date=date_obj
                ).first()
                if usersession:
                    userreservedslots = list(
                        reservedslots.objects.filter(session=usersession, status='reserved')
                    )
                    reserved = reserved.exclude(id__in=[s.slot.id for s in userreservedslots])
            context["stage"] = "showing_ground_detail"
            html_page=render_to_string("bookings/groundpage.html",{'ground': ground,'date': date_for_input,'today': today,'cities': cities,'selected_city': ground.city,'reserved': reserved,'booked': booked,'available': available,'all_slots': time_slots,'userreservedslots': userreservedslots},request=request)
            return JsonResponse({"message":"check the ground details and its slot details","html":html_page})
      if bookingtype=="normal_booking" and context.get("intent") == "book":
        context["stage"] = "collecting_booking_details"
        if not context.get("date"):
            return JsonResponse({
               "message": "Please tell me the date you want to book.",
               "required_fields": ["date"]
           })
        date_str = context["date"]
        print("Parsing date from user input:", date_str)
        parsed_date = parse_natural_date(date_str)
        print("Parsed date:", parsed_date)
        if not parsed_date:
         return JsonResponse({
        "message": f"I couldn’t understand the date '{date_str}'. Please specify a date like '28 Jan', 'tomorrow', or '2026-01-28'.",
        "required_fields": ["date"]
        })
        date_obj = parsed_date
        context["date"] = date_obj.isoformat()
        request.session.modified = True
        required_fields = ["ground_or_turf_name", "city", "area", "timings"]
        for field in required_fields:
            if not context.get(field):
                return JsonResponse({'message': f"Please tell me the {field.replace('_', ' ')}.","required_fields":[field]})
        ground = Ground.objects.filter(
            name__icontains=context["ground_or_turf_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        )
        if ground.count() == 1:
            ground = ground.first()
            print(ground)
        elif ground.count() > 1:
           cities = Ground.objects.values_list('city', flat=True).distinct()
           html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
           return JsonResponse({
           "message": "I found multiple grounds in that area. Please select one.",
            "html": html_page
           })
        else:
            cities = Ground.objects.values_list('city', flat=True).distinct()
            grounds=Ground.objects.filter(address__icontains=context["area"])
            html_page=render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
            return JsonResponse({'message': "There is no ground of that name ,I found multiple grounds in that area. Please select one from the list below.","html":html_page})
        try:
            date_obj = datetime.strptime(context["date"], "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'message': "Invalid date format. Please use YYYY-MM-DD."})
        constraint = context.get("constraint_type", "between")
        userslots = timingstoslots(
            context.get("timings"), context.get("sporttype"),context.get("ground_or_turf"), context.get("am_pm"),context.get("shift"),constraint
        )
        if not userslots:
            return JsonResponse({
                 "message": "I couldn’t understand the time. Please specify a time like '5 to 7 evening'.","required_fields":["timings"]
                })
        if len(userslots) > 2 and not context.get("hours"):
            return JsonResponse({'message': f"Among all hours {context['timings']}, how many hours do you want to play?","required_fields":["hours"]})
        if context.get("hours"):
            hrs=parsehours(context.get("hours"))
            if not hrs:
                return JsonResponse({'message': "I couldn't understand the number of hours you want to play. Please specify a number like '2' or 'three'.","required_fields":["hours"]})
            userneedstoplay = hrs
        else:
            userneedstoplay=len(userslots)
        print("User Slots:", userslots)
        summary = (
            f"Please confirm this booking: {ground.name} in {context['city']} on {context['date']} "
            f"for {userneedstoplay} hour(s). Requested window: {context.get('timings') or ', '.join(userslots)}."
        )
        if not context.get("confirmation_approved"):
            set_pending_action(context, "confirm_normal_booking", summary)
            request.session.modified = True
            return JsonResponse({
                "message": summary,
                "options": [
                    {"text": "Confirm booking"},
                    {"text": "Change details"},
                ]
            })
        clear_pending_action(context)
        output_res = chatbot_reserve_slots(request, ground, date_obj, userslots, userneedstoplay)
        if not isinstance(output_res,dict):
            return JsonResponse({'message': 'Error reserving slots. Please try again.'})
        if not output_res.get("success"):
            message=output_res.get("message")
            cities = Ground.objects.values_list('city', flat=True).distinct()
            if output_res.get('alternative_grounds'):
                altgrounds=output_res['alternative_grounds']
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":context.get("city")},request=request)
                return JsonResponse({"message":output_res.get("message"),"html": html_page})
            else:
                return JsonResponse({"message":output_res.get("message")})
        return JsonResponse({"message": "Slots reserved successfully. Redirecting to checkout…","redirect_url": reverse("checkout", args=[output_res.get("session_id")])})
      if bookingtype=="normal_booking" and context.get("intent") in ["ground_info", "ground_facilities", "ground_status"]:
        info_result = handle_ground_info(context)
        return JsonResponse(info_result)   

    if mode == "cancellation":
            if not request.user.is_authenticated:
                return JsonResponse({"message": "Please log in to continue."})
            upcoming_bookings = (
                Bookings.objects
                .filter(
                    user=request.user,
                    is_cancelled=False,
                    booked=True,
                    date__gte=timezone.now().date()
                )
                .select_related("ground")
                .order_by("date")
            )
            if not upcoming_bookings.exists():
                return JsonResponse({"message": "You have no upcoming bookings to cancel."})
            booking_id = request.GET.get("booking_id")
            if not booking_id:
                options = []
                for b in upcoming_bookings:
                    slot_times = ", ".join(
                        str(s.starttime) for s in b.slotsbooked.all()
                    )
                    options.append({
                        "id": str(b.id),
                        "text": f"{b.ground.name} on {b.date} — Slots: {slot_times}"
                    })
                return JsonResponse({
                    "message": "Which booking would you like to cancel?",
                    "options": options
                })
            booking = Bookings.objects.filter(id=booking_id, user=request.user).first()
            if not booking:
                return JsonResponse({"message": "Invalid booking selected."})
            if booking.is_cancelled:
                return JsonResponse({"message": "This booking is already cancelled."})
            if booking.date < timezone.now().date():
                return JsonResponse({"message": "You can't cancel this booking anymore."})
            cancel_booking(booking)
            return JsonResponse({
                "message": f"Your booking is cancelled successfully. Refund of ₹{booking.price} is initiated."
            }) 
    if mode == "reschedule":
      booking_id = payload.get("booking_id") or request.POST.get("booking_id") or context.get("selected_booking_id")
      context["stage"] = "collecting_reschedule_target"
      if not booking_id:
        pastorders = Orders.objects.filter(
            user=request.user,
            date__gt=timezone.now().date(),
            booked=True
        ).order_by("date")
        if not pastorders.exists():
            return JsonResponse({"message": "You have no upcoming bookings to reschedule."})
        options = []
        for order in pastorders:
            slots = format_order_slots(order)
            options.append({
                "id": order.id,
                "text": f"{order.ground.name} on {order.date} — Slots: {slots}"
            })
        return JsonResponse({
            "message": "Which booking would you like to reschedule?",
            "options": options
        })
      booking = Orders.objects.filter(id=booking_id, user=request.user).first()
      if not booking:
        return JsonResponse({"message": "Invalid booking selected."})
      context["selected_booking_id"] = booking.id
      if booking.date < timezone.now().date():
        return JsonResponse({"message": "This booking cannot be rescheduled now."})
      if not context.get("timings") or not context.get("date"):
        return JsonResponse({"message": "Tell me the new date and new timings you want to reschedule to."})
      if booking.Tournament_or_normal == "normal":
        required_fields = ["ground_or_turf_name", "city", "area", "date", "timings"]
        for field in required_fields:
            if not context.get(field):
                return JsonResponse({'message': f"Please tell me the {field.replace('_', ' ')}."})
        ground = Ground.objects.filter(
            name__icontains=context["ground_or_turf_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        ).first()
        if not ground:
            grounds=Ground.objects.filter(address__icontains=context["area"])
            html_page= render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":context.get("city")},request=request)
            return JsonResponse({'message': "I found multiple grounds in that area. Please select one from the list below.","html":html_page})
        try:
            date_obj = datetime.strptime(context["date"], "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'message': "Invalid date format. Please use YYYY-MM-DD."})
        constraint = context.get("constraint_type", "between")
        userslots = timingstoslots(
            context["timings"], context["sporttype"],context["ground_or_turf"], context["am_pm"],context["shift"],constraint
        )
        if not userslots:
            return JsonResponse({
                 "message": "I couldn’t understand the time. Please specify a time like '5 to 7 evening'."
                })
        if len(userslots) > 2 and not context.get("hours"):
            return JsonResponse({'message': f"Among all hours {context['timings']}, how many hours do you want to play?"})
        if context.get("hours"):
            userneedstoplay = int(context.get("hours"))
        else:
            userneedstoplay=len(userslots)
        reserve = chatbot_reserve_slots(request, ground, date_obj,userslots,userneedstoplay)
        if not reserve.get("success"):
            message=reserve.get("message")
            cities = Ground.objects.values_list('city', flat=True).distinct()
            if reserve.get('alternative_grounds'):
                altgrounds=reserve.get('alternative_grounds')
                message=reserve.get("message")
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":context.get("city")},request=request)
                return JsonResponse({"message":message,"html": html_page})
            else:
                return JsonResponse({"message":message})
        with transaction.atomic():
         for s in booking.slotsbooked.all():
            s.is_blocked=False
            s.is_booked=False
            s.blocked_at=None
            s.save()
            booking.booked=False
            booking.status="cancelled"
            booking.save(update_fields=["booked", "status"])
        reserved_ids = reserve['reserved_slots']
        session_id = reserve['session_id']
        total = len(reserved_ids) * float(ground.price)
        pay = payment.objects.create(
          session_id=session_id,
          user=request.user,
          amount=total,
          )
        order_data = {
          "amount": int(total * 100),
          "currency": "INR",
          "receipt": f"order_rcptid_{pay.id}",
          }
        rp_order = client.order.create(order_data)
        pay.order_id = rp_order["id"]
        pay.save()
        session_obj = reservationsession.objects.get(id=session_id)
        reserved_qs = reservedslots.objects.filter(session=session_obj, status="reserved")
        html = render_to_string("bookings/checkoutpage.html", {
          "session": session_obj,
          "reserved": reserved_qs,
          "total": total,
          "razorpay_key": settings.RAZORPAY_KEY_ID,
          "order_id": rp_order["id"],
          "payment_id": pay.id,
          "ground": session_obj.ground
          })
        return JsonResponse({
          "message": "Please complete payment in 15 minutes.",
          "html": html
          })  
      if booking.Tournament_or_normal == "tournament":
        return JsonResponse({
            "message": "Tournament booking rechedule would be added soon sorry.",})
    #############################################################################################################################################   
    if mode=="tournament":
      mode="tournament_booking"
      context = get_agent_context(request, mode)
      booking_type="tournament_booking"
      print("Required fields sent to backend:", required_fields)
      output = interpretgroundquery(query,booking_type,required_fields)  
      print("Chatbot Output:",output)
      print("previouscontext:", context)
      if output.get("intent")=="unknown" and "intent" in context:
          output["intent"]=context["intent"]
      raw_intent = (output.get("intent") or "").lower()
      print("raw_intent:", raw_intent)
      INTENT_MAP = {
      "show": "show_ground",
      "find": "show_ground",
      "search": "show_ground",
      "recommend": "show_ground",
      "suggest": "show_ground",
      "view": "show_ground",
      "book": "book",
      "reserve": "book",
      "schedule": "book",
      "cancel": "cancel_booking",
      "change": "cancel_booking",
      "modify": "cancel_booking",
      "reschedule": "reschedule",
      "about": "ground_info",
      "info_ground": "ground_info",
      "tellme": "ground_info",
      }
      if raw_intent in ["show_ground","book","cancel_booking","reschedule","ground_info"]:
          normalized_intent = raw_intent
      else:
         normalized_intent = INTENT_MAP.get(raw_intent, "unknown")
      print("Normalized Intent:", normalized_intent)
      merge_agent_filters(context, output.get("filters", {}))
      print("output context:",output)
      if normalized_intent != "unknown":
        context["intent"] = normalized_intent
      context['booking_type']=output.get('booking_type')
      context["stage"] = "understanding_request"
      request.session.modified = True
      print("Updated Chatbot Context:",context)
      sport_type = (context.get("sporttype") or "").lower().strip()
      ground_or_turf = (context.get("ground_or_turf") or "").lower().strip()
      if not sport_type:
       q = query.lower()
       if "football" in q:
          sport_type = "football"
       elif "cricket" in q:
          sport_type = "cricket"
       elif "hockey" in q:
          sport_type = "hockey"
       elif "badminton" in q:
          sport_type = "badminton"
       elif "tennis" in q:
          sport_type = "tennis"
       elif "volleyball" in q:
          sport_type = "volleyball"
      outdoor_sports = ["cricket", "football", "hockey"]
      if not sport_type:
        return JsonResponse({'message': "What sport is this tournament for?", "required_fields":["sport_type"]})
      if sport_type in outdoor_sports:
        if not ground_or_turf:
            response_message = f"For {sport_type.capitalize()}, would you like to book a ground or a turf?,"
            return JsonResponse({
                "message": response_message,"required_fields":["ground_or_turf"],
            })
      if not ground_or_turf:
          response_message = f"For tournaments, would you like to book a ground or a turf?"
          return JsonResponse({
             "message": response_message,
             "required_fields": ["ground_or_turf"]
            })
      request.session.modified = True
      if sport_type:
       grounds = Ground.objects.filter(sporttype__icontains=sport_type)
       print("grounds by sport_type:", grounds)
      if ground_or_turf:
          grounds=grounds.filter(types__icontains=ground_or_turf)
          print("grounds by ground_or_turf:", grounds)
      bookingtype= context.get("booking_type", "").lower().strip()
      if booking_type=="tournament_booking" and context.get("intent") == "show_ground":   
        if not context.get("ground_or_turf_name"):
          if context.get("nearme") and not context.get("radius_km"):
              context["radius_km"] = 15
          if context.get("radius_km"):
            if not request.session.get("user_lat") or not request.session.get("user_lon"):
                  html_page=render_to_string("bookings/location-detection.html",request=request)
                  return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})
            user_lat = float(request.session["user_lat"])
            user_lon = float(request.session["user_lon"])
            grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
            if isinstance(grounds, list):
                ground_ids = [g.id for g in grounds]
                grounds = Ground.objects.filter(id__in=ground_ids)
            cities= Ground.objects.values_list('city', flat=True).distinct()
            html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
            return JsonResponse({"message":"these are the grounds near to you","html": html_page})
          if context.get("city"):
               grounds=grounds.filter(city__icontains=context["city"])
          if context.get("area"):
               grounds = grounds.filter(address__icontains=context["area"])
          if context.get("rating_min"):
              grounds = grounds.filter(rating__gte=float(context["rating_min"]))
          if context.get("rating_semantic"):
              if context.get("rating_semantic") in ["top", "high", "good", "top_rated"]:
                  grounds=grounds.filter(rating__gte=3)
              elif context.get("rating_semantic") in ["low", "bad", "poor", "low_rated"]:
                  grounds=grounds.filter(rating__lte=3)
          if context.get("start"):
             dicti = parse_date_constraints(context["start"],context.get("end"),context.get("total_days"))
             print("Parsed date constraints:", dicti)
             if not dicti["success"]:
               return JsonResponse({"message": dicti["message"]})
             start,end=dicti["start"],dicti["end"]
             shiftsperday=shifts(context["shifts"],start,end)
             context["start"]=start.isoformat()
             context["end"]=end.isoformat()
             print("Start:", start, "End:", end, "Shifts per day:", shiftsperday)
          if not context.get("budget"):
                grounds=showavailability(grounds,start,end,shiftsperday)
                if isinstance(grounds, list):
                  grounds = Ground.objects.filter(id__in=[g.id for g in grounds])
                grounds=grounds.order_by('-t_fullday_price') 
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":"these are the grounds near to you","html": html_page})
          if context.get("budget"):
                if not context.get("total_matches"):
                    return JsonResponse({"message":"please provide total no of matches in the tournament","required_fields":["total_matches"]})
                if not context.get("overs_per_match"):
                    return JsonResponse({"message":"please provide total no of overs per match","required_fields":["overs_per_match"]})
                if not context.get("start"):
                    return JsonResponse({"message":"please provided start_date and end_date of tournament","required_fields":["start","end"]})
                valid_grounds=[]
                if context.get("start") and context.get("end"):
                 for g in grounds:
                    result=check(ground=g,
                                 start=context["start"],
                                 end=context["end"],
                                 shiftperday=shiftsperday,
                                 budget=int(context["budget"]),
                                 matches=int(context["total_matches"]) ,
                                 overs=int(context["overs_per_match"]),
                                 show=True
                        )
                    if result["success"]:
                           valid_grounds.append(g)
                if not valid_grounds:
                    grs=Ground.objects.filter(city=context["city"])
                    cities= Ground.objects.values_list('city', flat=True).distinct()
                    html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                    return JsonResponse({
                        "message": "No grounds can host this tournament within your budget you can check in the grounds provided","html":html_page
                        })
                grounds=valid_grounds
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({
                         "message": "These grounds fit your budget and schedule",
                         "html": html_page
                        })
        if context.get("ground_or_turf_name"):
            if not context.get("area") or not context.get("city"):
                return JsonResponse({"message":"please provide city and area of the ground you are looking","required_fields":["area","city"]})
            grounds = Ground.objects.filter(
              name__icontains=context.get("ground_or_turf_name")
             )
            grounds = grounds.filter(city=context["city"])
            grounds = grounds.filter(address__icontains=context["area"])
            cities = Ground.objects.values_list('city', flat=True).distinct()
            if not grounds.exists():
                fallback = Ground.objects.all()
                if context.get("city"):
                  fallback = fallback.filter(city=context["city"])
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": fallback, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({
                     "message": "Requested ground not found. Showing similar grounds.",
                      "html": html_page
                    })
            if len(grounds)>1:
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({
                     "message": "Multiple grounds of same name found. Please be more specific.",
                      "html": html_page
                    })
            ground = grounds.first()
            if not context.get("start"):
              return JsonResponse({"message": "Please provide the start date of your tournament.","required_fields":["start"]})
            dicti = parse_date_constraints(context["start"],context.get("end"),context.get("total_days"))
            if not dicti["success"]:
              return JsonResponse({"message": dicti["message"]})
            start,end=dicti["start"],dicti["end"]
            shiftsperday=shifts(context["shifts"],start,end)
            context["start"]=start.isoformat()
            context["end"]=end.isoformat()
            if not context.get("budget"):
                  today = timezone.now().date().strftime('%Y-%m-%d')
                  date_list=[]
                  for i in range(30):
                    d = timezone.now().date() + timedelta(days=i)
                    day_slots = Slot.objects.filter(ground=ground, date=d)
                    if not day_slots.exists():
                        status = "unavailable"
                    else:
                        all_free = not day_slots.filter(is_booked=True).exists() and \
                        not day_slots.filter(is_blocked=True).exists()
                        status = "available" if all_free else "unavailable"
                    date_list.append({
                        "date": d,
                        "day_num": d.day,
                        "status": status
                    })
                  context={
                        "ground":ground,
                        "datelist":date_list,
                   }
                  html_page=render_to_string("bookings/tournament.html",context,request=request)
                  return JsonResponse({'message':"the availability of 30 days of that ground are", 'html': html_page})
            if context.get("budget"):
                if not context.get("total_matches"):
                    return JsonResponse({"message":"please provide total no of matches in the tournament","required_fields":["total_matches"]})
                if not context.get("overs_per_match"):
                    return JsonResponse({"message":"please provide total no of overs per match","required_fields":["overs_per_match"]})
                result=check(ground=ground,
                                 start=context["start"],
                                 end=context["end"],
                                 shiftperday=shiftsperday,
                                 budget=int(context["budget"]),
                                 matches=int(context["total_matches"]) ,
                                 overs=int(context["overs_per_match"]),
                                 show=True
                        )
                if result["success"]:
                        message="yes you can book this ground with your budget"
                        today = timezone.now().date().strftime('%Y-%m-%d')
                        date_list=[]
                        for i in range(30):
                          d = timezone.now().date() + timedelta(days=i)
                          day_slots = Slot.objects.filter(ground=ground, date=d)
                          if not day_slots.exists():
                            status = "unavailable"
                          else:
                           all_free = (not day_slots.filter(is_booked=True).exists() and not day_slots.filter(is_blocked=True).exists())
                           status = "available" if all_free else "unavailable"
                          date_list.append({
                            "date": d,
                            "day_num": d.day,
                            "status": status
                           })
                        context={
                        "ground":ground,
                        "datelist":date_list,
                        }
                        html_page=render_to_string("bookings/tournament.html",context,request=request)
                        return JsonResponse({'message':"the availability of 30 days of that ground are", 'html': html_page})
                else:
                        grounds=Ground.objects.filter(city=context["city"])
                        valid_grounds=[]
                        for g in grounds:
                            result=check(ground=g,
                                 start=context["start"],
                                 end=context["end"],
                                 shiftperday=shiftsperday,
                                 budget=int(context["budget"]),
                                 matches=int(context["total_matches"]) ,
                                 overs=int(context["overs_per_match"]),
                                 show=True
                            )
                            if result["success"]:
                              valid_grounds.append(g)
                        if not valid_grounds:
                          grs=Ground.objects.filter(city=context["city"])
                          cities= Ground.objects.values_list('city', flat=True).distinct()
                          html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grs, "cities": cities, "selected_city":""},request=request)
                          return JsonResponse({
                            "message": "No grounds can host this tournament within your budget,the grounds of your city are provided below you can check them out",
                            "html": html_page
                           })
                        grounds=valid_grounds
                        html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                        return JsonResponse({
                         "message": "These grounds fit your budget and schedule",
                         "html": html_page
                        })       
##################################################################################################################################################
      if output.get("booking_type") == "tournament_booking" and output.get("intent") in ["book", "reserve", "schedule"]:
        context["stage"] = "collecting_tournament_details"
        if not context.get("ground_or_turf_name"):
            return JsonResponse({"message":"please provide ground_or_turf_name and city and area of the ground you are looking","required_fields":["ground_or_turf_name"]})
        if not context.get("area"):
            return JsonResponse({"message":"please provide area of the ground you are looking","required_fields":["area"]})
        if not context.get("city"):
            return JsonResponse({"message":"please provide area of the ground you are looking","required_fields":["city"]})
        ground = Ground.objects.filter(
            name__icontains=context["ground_or_turf_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        ).first()
        if not ground:
            grounds=Ground.objects.filter(address__icontains=context["area"])
            html_page= render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
            return JsonResponse({'message': "I found multiple grounds in that area. Please select one from the list below.","html":html_page})
        if not context.get("start"):
              return JsonResponse({"message": "Please provide the start date of your tournament.","required_fields":["start"]})
        dicti = parse_date_constraints(context["start"],context.get("end"),context.get("total_days"))
        if not dicti["success"]:
            return JsonResponse({"message": dicti["message"]})
        start, end = dicti["start"], dicti["end"]
        shiftsperday = shifts(context["shifts"], start,end)
        context["start"]=start.isoformat()
        context["end"]=end.isoformat()
        tournament_summary = (
            f"Please confirm this tournament booking: {ground.name} in {context['city']} "
            f"from {context['start']} to {context['end']}."
        )
        if context.get("budget"):
            tournament_summary += f" Budget: {context['budget']}."
        if not context.get("confirmation_approved"):
            set_pending_action(context, "confirm_tournament_booking", tournament_summary)
            request.session.modified = True
            return JsonResponse({
                "message": tournament_summary,
                "options": [
                    {"text": "Confirm booking"},
                    {"text": "Change details"},
                ]
            })
        clear_pending_action(context)
        if not context.get("budget"):
            dicti_no_budget=checkwithoutbudget(ground,start,end,shiftsperday)
            print("Check without budget result:", dicti_no_budget)
            if dicti_no_budget["success"]:
                plan=build_plan_from_shifts(shiftsperday)
                print(plan)
                success,session_id=booktournament(request.user,ground,plan)
                print("Booking result:", success, session_id)
                if not success:
                    return JsonResponse({"message": "cannot book someone else booked some shifts"})
                else:
                    context["stage"] = "awaiting_payment"
                    return JsonResponse({"message": "Tournament slots reserved. Please complete payment within 15 minutes.","redirect_url": reverse("tournamentcheckout", args=[session_id])})
            else:
                grounds=Ground.objects.filter(city=context["city"])
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page = render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":"these are the grounds near to you","html": html_page})
        if context.get("budget"):
            if not context.get("total_matches"):
                return JsonResponse({"message":"please provide total no of matches in the tournament","required_fields":["total_matches"]})
            if not context.get("overs_per_match"):
                return JsonResponse({"message":"please provide total no of overs per match","required_fields":["overs_per_match"]})
            dicti=check(ground=ground,
                        start=context["start"],
                        end=context["end"],
                        shiftperday=shiftsperday,
                        budget=context["budget"],
                        matches=context["total_matches"] ,
                        overs=context["overs_per_match"],
                        show=False)
            if not dicti.get("success"):
                grounds=Ground.objects.filter(city=context["city"])
                valid_grounds=[]
                for g in grounds:
                            result=check(ground=g,
                                 start=context["start"],
                                 end=context["end"],
                                 shiftperday=shiftsperday,
                                 budget=context["budget"],
                                 matches=context["total_matches"] ,
                                 overs=context["overs_per_match"],
                                 show=True
                            )
                            if result["success"] and result["schedule"]:
                              valid_grounds.append(g)
                if not valid_grounds:
                    return JsonResponse({
                            "message": "No grounds can host this tournament within your budget"
                           })
                html_page = render_to_string(
                          "partials/partialcheckpage.html",
                           {"grounds": valid_grounds, "cities": cities, "selected_city":""},
                           request=request
                           )
                return JsonResponse({
                         "message": "These grounds fit your budget and schedule",
                         "html": html_page
                        })
            else:
                if not dicti.get("schedule"):
                    return JsonResponse({
                        "message": "No valid schedule found for the tournament within your budget."
                    })
                success, session_id = booktournament(
                  user=request.user,
                  ground=ground,
                  plan=dicti["schedule"]
                )
                if not success:
                  return JsonResponse({
                      "message": "Unable to reserve tournament slots"
                    })
                else:
                    context["stage"] = "awaiting_payment"
                    return JsonResponse({"message": "Tournament slots reserved. Please complete payment within 15 minutes.","redirect_url": reverse("tournamentcheckout", args=[session_id])})
def build_plan_from_shifts(shiftsperday):
    plan = {}
    for date, shifts in shiftsperday.items():
        if shifts:
            plan[date] = shifts
    return plan
             
def checkwithoutbudget(ground, start, end, shiftperday):
    availableshiftperday = {}
    current = start
    while current <= end:
        availableshiftperday[current] = {}
        day_slots = Slot.objects.filter(ground=ground, date=current)
        slotbyshift = {}
        for slot in day_slots:
            slotbyshift.setdefault(slot.shift, []).append(slot)
        for shift in ["morning", "afternoon", "evening", "night"]:
            shift_slots = slotbyshift.get(shift, [])
            if not shift_slots:
                availableshiftperday[current][shift] = False
                continue
            is_unavailable = any(slot.is_booked or slot.is_blocked for slot in shift_slots)
            availableshiftperday[current][shift] = not is_unavailable
        required_shifts = shiftperday.get(current, [])
        for shift in required_shifts:
           if not availableshiftperday[current].get(shift, False):
             return {
            "success": False,
            "message": f"{shift} shift on {current} is not available"
             }
        current += timedelta(days=1)
    return {"success":True}

def booktournament(user, ground, plan):
    with transaction.atomic():
        session = tournamentsession.objects.create(
            user=user,
            ground=ground,
            start_date=min(plan.keys()),
            end_date=max(plan.keys()),
            expires_at=timezone.now() + timedelta(minutes=15)
        )
        for date, shift in plan.items():
            shifts_to_filter = shift if isinstance(shift, (list, tuple)) else [shift]
            locked_slots = Slot.objects.select_for_update().filter(
                ground=ground,
                date=date,
                shift__in=shifts_to_filter,
                is_booked=False,
                is_blocked=False
            )
            if not locked_slots.exists():
                raise Exception(f"No slots available for {date}")
            reserve = reservetournament.objects.create(
                session=session,
                ground=ground,
                date=date,
                status="reserved"
            )
            reserve.blocked_slots.set(locked_slots)
            locked_slots.update(
                is_blocked=True,
                blocked_at=timezone.now()
            )
            date_str = str(date)
            session_id = str(session.id)
            slot_id_list = list(locked_slots.values_list("id", flat=True))
            ground_date_key = f"ground_slots:{ground.id}:{date_str}"
            redis_client.sadd(ground_date_key, *slot_id_list)
            redis_client.expire(ground_date_key, TOURNAMENT_SESSION_TTL_SECONDS)
            for sid in slot_id_list:
                lock_key = f"lock:slot:{ground.id}:{sid}:{date_str}"
                redis_client.set(lock_key, session_id, nx=True, ex=TOURNAMENT_SESSION_TTL_SECONDS)
            for s in shifts_to_filter:
                redis_client.set(
                    f"lock:shift:{ground.id}:{date_str}:{s}",
                    session_id,
                    ex=TOURNAMENT_SESSION_TTL_SECONDS
                )
        redis_client.set(
            f"tournament_session:{session.id}",
            json.dumps({
                "user_id": user.id,
                "ground_id": ground.id,
            }),
            ex=TOURNAMENT_SESSION_TTL_SECONDS
        )
    return True, session.id
            
from django.db import transaction
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from django.utils import timezone

def chatbot_reserve_slots(request, ground, date_obj, userslots, userneedstoplay):
    logger.info(
        "chatbot_reserve_slots called user=%s ground=%s date=%s requested_slots=%s need=%s",
        request.user.id if request.user.is_authenticated else None,
        ground.id,
        date_obj,
        len(userslots),
        userneedstoplay
    )
    if not request.user.is_authenticated:
        return {'success': False, 'message': 'Please log in to continue booking.'}
    user = request.user
    try:
        parsed_user_slots = []
        for slot_str in userslots:
            try:
                start_str, end_str = slot_str.split(" - ")
                start_time = datetime.strptime(start_str.strip(), "%I:%M %p").time()
                end_time = datetime.strptime(end_str.strip(), "%I:%M %p").time()
                parsed_user_slots.append((start_time, end_time, slot_str))
            except ValueError:
                return {'success': False, 'message': f"Invalid slot format: {slot_str}"}
        parsed_user_slots.sort(key=lambda x: x[0])
        ground_date_key = f"ground_slots:{ground.id}:{date_obj}"
        redis_locked_ids = redis_client.smembers(ground_date_key)
        availableslots = list(
            Slot.objects.filter(
                ground=ground,
                date=date_obj,
                is_booked=False,
                is_blocked=False,
            ).exclude(id__in=[int(x) for x in redis_locked_ids])
        )
        if not availableslots:
            return {'success': False, 'message': 'No slots available.'}
        slotmap = {(s.starttime, s.endtime): s for s in availableslots}
        availability = []
        prices = []
        slot_objs = []
        for start_time, end_time, slot_str in parsed_user_slots:
            slot_obj = slotmap.get((start_time, end_time))
            if slot_obj:
                availability.append(True)
                prices.append(slot_obj.price)
                slot_objs.append(slot_obj)
            else:
                availability.append(False)
                prices.append(0)
                slot_objs.append(None)
        if userneedstoplay > len(parsed_user_slots):
            userneedstoplay = len(parsed_user_slots)
        l = 0
        curr_price = 0
        min_price = float('inf')
        best_window = None
        for r in range(len(availability)):
            if not availability[r]:
                l = r + 1
                curr_price = 0
                continue
            curr_price += prices[r]
            while (r - l + 1) > userneedstoplay:
                curr_price -= prices[l]
                l += 1
            if (r - l + 1) == userneedstoplay and curr_price < min_price:
                min_price = curr_price
                best_window = (l, r)
        if not best_window:
            alternative_grounds = list(
                    Ground.objects.filter(
                        city=ground.city,
                        sporttype=ground.sporttype,
                        types=ground.types
                    ).exclude(id=ground.id)
                )
            available_alternatives = []
            for alt in alternative_grounds:
                alt_locked = redis_client.smembers(f"ground_slots:{alt.id}:{date_obj}")
                alt_slots = Slot.objects.filter(
                    ground=alt,
                    date=date_obj,
                    is_booked=False
                ).exclude(id__in=[int(x) for x in alt_locked])
                if alt_slots.exists():
                    available_alternatives.append(alt)
            return {
              'success': False,
              'message': 'No continuous slots available at this ground. Here are alternatives.',
              'alternative_grounds': available_alternatives
            }
        matchslots = [slot_objs[i] for i in range(best_window[0], best_window[1] + 1)]
        session = reservationsession.objects.filter(
            user=user,
            ground=ground,
            date=date_obj,
        ).first()
        if session:
            existing_session_key = f"session:{session.id}"
            if not redis_client.exists(existing_session_key):
                cancel_normal_booking_session(session)
                session = reservationsession.objects.create(
                    user=user,
                    ground=ground,
                    date=date_obj,
                )
        else:
            session = reservationsession.objects.create(
                user=user,
                ground=ground,
                date=date_obj,
            )
        session_id = str(session.id)
        session_key = f"session:{session_id}"
        session_slots_key = f"session_slots:{session_id}"
        ttl = redis_client.ttl(session_key)
        if ttl is None or ttl <= 0:
            redis_client.set(
                session_key,
                json.dumps({
                    "user_id": user.id,
                    "ground_id": ground.id,
                    "date": str(date_obj)
                }),
                ex=SESSION_TTL_SECONDS
            )
            remaining_seconds = SESSION_TTL_SECONDS
        else:
            remaining_seconds = ttl
        redis_client.expire(session_slots_key, remaining_seconds)
        locked_slot_ids = []
        for slot in matchslots:
            lock_key = f"lock:slot:{ground.id}:{slot.id}:{date_obj}"
            acquired = redis_client.set(lock_key, session_id, nx=True, ex=remaining_seconds)
            if not acquired:
                for sid in locked_slot_ids:
                    redis_client.delete(f"lock:slot:{ground.id}:{sid}:{date_obj}")
                    redis_client.srem(session_slots_key, str(sid))
                return {'success': False, 'message': 'Some slots were just taken. Please try again.'}
            locked_slot_ids.append(slot.id)
            redis_client.sadd(session_slots_key, str(slot.id))
        return {
            'success': True,
            'message': 'Slots reserved successfully.',
            'session_id': session.id
        }
    except Exception as e:
        logger.exception("chatbot_reserve_slots failed: %s", e)
        return {'success': False, 'message': str(e)}
