"""Atomic quota reservations against the dedicated Upstash Redis database."""

import re
from datetime import datetime
from uuid import uuid4

import requests

from app.storage.planning_quota import QuotaExceeded, QuotaUnavailable, quota_windows

NAMESPACE = "{mealmind:planning:v1}"
LEDGER_KEY = f"{NAMESPACE}:provider"

# Each event set contains at most one month's provider attempts or one day's
# requests for an IP. The persistent marker makes a missing ledger fail closed.
RESERVE_SCRIPT = """
if redis.call('ZSCORE', KEYS[1], 'initialized') ~= '-1' then return -1 end
local clock = tonumber(ARGV[1])
for i = 3, 8, 3 do
    local start = ARGV[i]
    if redis.call('ZCOUNT', KEYS[2], start, '+inf') >= tonumber(ARGV[i+1]) then
        local reset = tonumber(ARGV[i+2])
        if reset == 0 then
            local first = redis.call('ZRANGEBYSCORE', KEYS[2], start, '+inf',
                'WITHSCORES', 'LIMIT', 0, 1)
            reset = tonumber(first[2]) + 60
        end
        return math.max(1, reset - clock)
    end
end
redis.call('ZREMRANGEBYSCORE', KEYS[2], 0,
    math.min(tonumber(ARGV[3]), tonumber(ARGV[6])) - 1)
redis.call('ZADD', KEYS[2], clock, ARGV[2])
if KEYS[1] ~= KEYS[2] then redis.call('EXPIREAT', KEYS[2], ARGV[9]) end
return 0
"""


def reserve_redis(url: str, token: str, subject: str, now: datetime, *, provider: bool = False) -> None:
    # Only use the official HTTPS REST endpoint. Never follow redirects with credentials.
    if not re.fullmatch(r"https://[a-z0-9-]+\.upstash\.io/?", url) or not token.strip():
        raise QuotaUnavailable
    windows = quota_windows(now, provider)
    timestamp = int(now.timestamp())
    expires_at = max(end for _, _, end, _ in windows if end is not None)
    if not provider:
        expires_at = max(expires_at, timestamp + 60)
    command = [
        "EVAL", RESERVE_SCRIPT, 2, LEDGER_KEY, f"{NAMESPACE}:{subject}",
        timestamp, uuid4().hex,
    ]
    for start, limit, end, _ in windows:
        command.extend([start, limit, end or 0])
    command.append(expires_at)
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
    if type(result) is not int or result < 0 or result > expires_at - timestamp:
        raise QuotaUnavailable
    if result:
        raise QuotaExceeded(windows[0][3], result)
