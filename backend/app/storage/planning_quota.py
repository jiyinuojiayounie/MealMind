"""Persistent counters for the public planner. Contains no meal or account data."""

from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from sqlite3 import Error as SQLiteError, connect


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


def quota_windows(now: datetime, provider: bool):
    timestamp = int(now.timestamp())
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    tomorrow = today + timedelta(days=1)
    next_month = (month + timedelta(days=32)).replace(day=1)

    return (
        [(int(today.timestamp()), 30, int(tomorrow.timestamp()), "global_quota"),
         (int(month.timestamp()), 500, int(next_month.timestamp()), "global_quota")]
        if provider else
        [(timestamp - 59, 3, None, "rate_limit"),
         (int(today.timestamp()), 10, int(tomorrow.timestamp()), "rate_limit")]
    )


def reserve(path: Path, subject: str, now: datetime, *, provider: bool = False) -> None:
    timestamp = int(now.timestamp())
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    windows = quota_windows(now, provider)
    try:
        with closing(connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=1)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            # Date boundaries and rate windows are evaluated in UTC by the caller.
            db.execute("DELETE FROM events WHERE subject = 'provider' AND accepted_at < ?", (int(month.timestamp()),))
            db.execute("DELETE FROM events WHERE subject <> 'provider' AND accepted_at < ?",
                       (min(timestamp - 59, int(today.timestamp())),))
            for start, limit, end, reason in windows:
                count, earliest = db.execute(
                    "SELECT COUNT(*), MIN(accepted_at) FROM events WHERE subject = ? AND accepted_at >= ?",
                    (subject, start),
                ).fetchone()
                if count >= limit:
                    raise QuotaExceeded(reason, max(1, (end if end is not None else earliest + 60) - timestamp))
            db.execute("INSERT INTO events VALUES (?, ?)", (subject, timestamp))
    except (SQLiteError, OSError, ValueError) as exc:
        raise QuotaUnavailable from exc


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Initialize a new public planning quota database.")
    parser.add_argument("path", type=Path)
    initialize_quota(parser.parse_args().path)
