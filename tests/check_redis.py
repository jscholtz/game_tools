import os
import sys
from pathlib import Path
from uuid import uuid4

import redis
from dotenv import load_dotenv
from redis.exceptions import RedisError

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

required = ("REDIS_USERNAME", "REDIS_PASSWORD")
missing = [name for name in required if not os.environ.get(name)]
if missing:
    sys.exit(f"Missing required .env setting(s): {', '.join(missing)}")

client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "machine-hand-mice-91302.db.redis.io"),
    port=int(os.environ.get("REDIS_PORT", "18224")),
    decode_responses=True,
    username=os.environ["REDIS_USERNAME"],
    password=os.environ["REDIS_PASSWORD"],
    socket_connect_timeout=10,
    socket_timeout=10,
)

try:
    print(f"PING: {client.ping()}")
    key = f"game_helper:redis_check:{uuid4().hex}"
    print(f"SET test key: {client.set(key, 'bar', ex=60)}")
    value = client.get(key)
    print(f"GET test key: {value}")
    if value != "bar":
        sys.exit("Redis connectivity check failed: value did not round-trip.")
    client.delete(key)
except RedisError as error:
    sys.exit(f"Redis connection/check failed: {error}")
