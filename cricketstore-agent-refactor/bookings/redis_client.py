import redis
from django.conf import settings

redis_client = redis.from_url(
    settings.REDIS_URL,
    db=getattr(settings, "REDIS_LOCK_DB", 0),
    decode_responses=False
)
