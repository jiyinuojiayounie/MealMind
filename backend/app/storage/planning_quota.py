"""Persistent counters for the public planner. Contains no meal or account data."""

from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from sqlite3 import Error as SQLiteError, connect
from zoneinfo import ZoneInfo


class QuotaUnavailable(Exception):
    pass


class QuotaExceeded(Exception):
    def __init__(self, reason: str, retry_after: int):
        self.reason = reason
        self.retry_after = retry_after


def initialize_quota(path: Path) -> None:
    # An existing empty file is not a valid quota database. Initialize explicitly.
    with path.open("xb"):
        pass
    with closing(connect(path)) as db, db:
        db.execute("CREATE TABLE events (subject TEXT NOT NULL, accepted_at INTEGER NOT NULL)")
        db.execute("CREATE INDEX events_subject_time ON events(subject, accepted_at)")
        db.execute("CREATE INDEX events_time ON events(accepted_at)")


MAX_QUOTAS = (5, 30, 500)
PACIFIC = ZoneInfo("America/Los_Angeles")


def quota_windows(now: datetime, limits: tuple[int, int, int]):
    timestamp = int(now.timestamp())
    day = now.astimezone(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (month + timedelta(days=32)).replace(day=1)
    return (
        (timestamp - 59, limits[0], None),
        (int(day.timestamp()), limits[1], int((day + timedelta(days=1)).timestamp())),
        (int(month.timestamp()), limits[2], int(next_month.timestamp())),
    )


def reserve(path: Path, now: datetime, *, limits=MAX_QUOTAS) -> None:
    timestamp = int(now.timestamp())
    windows = quota_windows(now, limits)
    try:
        with closing(connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=1)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM events WHERE subject = 'provider' AND accepted_at < ?",
                       (min(start for start, _, _ in windows),))
            for start, limit, end in windows:
                count, earliest = db.execute(
                    "SELECT COUNT(*), MIN(accepted_at) FROM events WHERE subject = 'provider' AND accepted_at >= ?",
                    (start,),
                ).fetchone()
                if count >= limit:
                    raise QuotaExceeded("global_quota", max(1, (end if end is not None else earliest + 60) - timestamp))
            db.execute("INSERT INTO events VALUES ('provider', ?)", (timestamp,))
    except (SQLiteError, OSError, ValueError) as exc:
        raise QuotaUnavailable from exc


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Initialize a new public planning quota database.")
    parser.add_argument("path", type=Path)
    initialize_quota(parser.parse_args().path)
