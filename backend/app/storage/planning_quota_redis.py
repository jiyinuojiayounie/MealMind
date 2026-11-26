"""Atomic quota reservations against the dedicated Upstash Redis database."""

import re
from datetime import datetime
from uuid import uuid4

import requests

from app.storage.planning_quota import MAX_QUOTAS, QuotaExceeded, QuotaUnavailable, quota_windows

NAMESPACE = "{mealmind:planning:v1}"
LEDGER_KEY = f"{NAMESPACE}:provider"
VERIFY_LEDGER = f"{NAMESPACE}:cloud-verification"
VERIFY_USED = f"{NAMESPACE}:cloud-verification-used"

# Keep the existing provider ledger and its persistent initialization marker.
RESERVE_SCRIPT = """
if ARGV[12] == 'mock' then
    redis.call('ZADD', KEYS[1], 'NX', -1, 'initialized')
    redis.call('EXPIRE', KEYS[1], 172800)
end
if ARGV[12] == 'once' and redis.call('EXISTS', KEYS[2]) == 1 then return -1 end
if redis.call('ZSCORE', KEYS[1], 'initialized') ~= '-1' then return -1 end
local clock = tonumber(ARGV[1])
local oldest = clock
for i = 3, 9, 3 do
    local start = ARGV[i]
    oldest = math.min(oldest, tonumber(start))
    if redis.call('ZCOUNT', KEYS[1], start, '+inf') >= tonumber(ARGV[i+1]) then
        local reset = tonumber(ARGV[i+2])
        if reset == 0 then
            local first = redis.call('ZRANGEBYSCORE', KEYS[1], start, '+inf',
                'WITHSCORES', 'LIMIT', 0, 1)
            reset = tonumber(first[2]) + 60
        end
        return math.max(1, reset - clock)
    end
end
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, oldest - 1)
if ARGV[12] == 'once' then redis.call('SET', KEYS[2], 'used') end
redis.call('ZADD', KEYS[1], clock, ARGV[2])
return 0
"""


def reserve_redis(url: str, token: str, now: datetime, *, limits=MAX_QUOTAS, verification: str = "") -> None:
    # Only use the official HTTPS REST endpoint. Never follow redirects with credentials.
    if not re.fullmatch(r"https://[a-z0-9-]+\.upstash\.io/?", url) or not token.strip():
        raise QuotaUnavailable
    windows = quota_windows(now, limits)
    timestamp = int(now.timestamp())
    latest_reset = max(end for _, _, end in windows if end is not None)
    keys = [VERIFY_LEDGER if verification in {"mock", "missing"} else LEDGER_KEY]
    if verification == "missing":
        keys = [f"{VERIFY_LEDGER}:missing:{uuid4().hex}"]
    if verification == "once":
        keys.append(VERIFY_USED)
    command = ["EVAL", RESERVE_SCRIPT, len(keys), *keys, timestamp, uuid4().hex]
    for start, limit, end in windows:
        command.extend([start, limit, end or 0])
    command.append(verification)
    try:
        response = requests.post(
            url, json=[str(arg) for arg in command], headers={"Authorization": f"Bearer {token}"},
            timeout=(2, 2), allow_redirects=False,
        )
        if response.status_code != 200:
            raise QuotaUnavailable
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise QuotaUnavailable from exc
    result = payload.get("result") if isinstance(payload, dict) and "error" not in payload else None
    if type(result) is not int or result < 0 or result > latest_reset - timestamp:
        raise QuotaUnavailable
    if result:
        raise QuotaExceeded("global_quota", result)
