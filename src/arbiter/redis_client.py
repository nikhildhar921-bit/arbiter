import redis.asyncio as redis

from arbiter.config import settings

# Shared Redis connection
redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    decode_responses=True,  # get back str instead of bytes
)
