from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import which
from subprocess import Popen, check_output
from time import sleep
from unittest.mock import Mock

import pytest
import requests

from app.storage.planning_quota import QuotaExceeded, QuotaUnavailable
from app.storage.planning_quota_redis import LEDGER_KEY, reserve_redis

URL = "https://fixture.upstash.io"
NOW = datetime(2040, 1, 1, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize("status, data", [
    (302, {"result": 0}), (429, {"result": 0}), (200, {"error": "limit"}),
    (200, {"result": -1}), (200, {"result": False}), (200, {"result": "0"}),
    (200, {"result": 9999999}), (200, []),
])
def test_redis_errors_fail_closed(monkeypatch, status, data):
    post = Mock(return_value=Mock(status_code=status, **{"json.return_value": data}))
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(QuotaUnavailable):
        reserve_redis(URL, "fixture-token", NOW)
    post.assert_called_once()
    assert post.call_args.kwargs["allow_redirects"] is False


def test_transport_error_has_no_retry(monkeypatch):
    post = Mock(side_effect=requests.Timeout)
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(QuotaUnavailable):
        reserve_redis(URL, "fixture-token", NOW)
    post.assert_called_once()


@pytest.fixture
def local_redis(tmp_path):
    server, cli = which("redis-server"), which("redis-cli")
    if not server or not cli:
        pytest.skip("redis-server and redis-cli are required for real Lua integration")
    socket = Path(tmp_path) / "redis.sock"

    def run(*args):
        return check_output([cli, "-s", socket.name, "--raw", *args], text=True, cwd=tmp_path).strip()

    def start():
        proc = Popen([server, "--port", "0", "--unixsocket", socket.name, "--dir", str(tmp_path),
                      "--appendonly", "yes", "--appendfsync", "always"], stdout=-3, stderr=-3, cwd=tmp_path)
        for _ in range(200):
            if socket.exists() and proc.poll() is None:
                return proc
            sleep(0.01)
        proc.terminate()
        proc.wait(timeout=10)
        pytest.fail("Local Redis did not start")

    def stop(proc):
        proc.terminate()
        proc.wait(timeout=10)

    proc = start()

    def restart():
        nonlocal proc
        stop(proc)
        proc = start()

    try:
        yield run, restart
    finally:
        stop(proc)


def test_atomic_redis_windows_and_restart(local_redis, monkeypatch):
    run, restart = local_redis

    def eval_on_redis(_url, *, json, **_kwargs):
        result = run(*json)
        return Mock(status_code=200, **{"json.return_value": {"result": int(result)}})

    monkeypatch.setattr(requests, "post", eval_on_redis)

    def attempt(now):
        try:
            reserve_redis(URL, "fixture-token", now)
        except QuotaExceeded as exc:
            return exc.retry_after
        return None

    with pytest.raises(QuotaUnavailable):
        attempt(NOW)
    assert run("ZADD", LEDGER_KEY, "NX", "-1", "initialized") == "1"
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(attempt, [NOW] * 42))
    assert results.count(None) == 5
    assert results.count(60) == 37
    restart()
    assert attempt(NOW) == 60
    for day in range(17):
        for minute in range(1 if day == 0 else 0, 6 if day < 16 else 4):
            instant = NOW + timedelta(days=day, minutes=minute)
            assert all(attempt(instant) is None for _ in range(5))
        if day == 0:
            assert attempt(NOW + timedelta(minutes=6)) == 22 * 3600 - 360
    assert attempt(NOW + timedelta(days=17)) == 13 * 86400 + 14 * 3600
    assert attempt(NOW + timedelta(days=31)) is None


def test_cloud_once_claim_survives_restart(local_redis, monkeypatch):
    run, restart = local_redis

    def eval_on_redis(_url, *, json, **_kwargs):
        return Mock(status_code=200, **{"json.return_value": {"result": int(run(*json))}})

    monkeypatch.setattr(requests, "post", eval_on_redis)
    assert run("ZADD", LEDGER_KEY, "NX", "-1", "initialized") == "1"
    reserve_redis(URL, "fixture-token", NOW, verification="mock")
    assert run("ZCARD", LEDGER_KEY) == "1"
    with pytest.raises(QuotaUnavailable):
        reserve_redis(URL, "fixture-token", NOW, verification="missing")
    reserve_redis(URL, "fixture-token", NOW, verification="once")
    restart()
    with pytest.raises(QuotaUnavailable):
        reserve_redis(URL, "fixture-token", NOW + timedelta(minutes=1), verification="once")
    assert run("ZCARD", LEDGER_KEY) == "2"
