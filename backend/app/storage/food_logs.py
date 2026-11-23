import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.schemas.food_logs import FoodLog, FoodLogCreate, FoodLogDraft
from app.services.food_reference_binding import bind_draft_items, validate_bindings_for_confirmation

# Append ordered, transactional migrations. Never edit a released migration.
MIGRATIONS = (
    (
        """
        CREATE TABLE food_logs (
            id TEXT PRIMARY KEY NOT NULL,
            consumed_on TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'confirmed')),
            revision INTEGER NOT NULL CHECK (revision >= 1),
            document TEXT NOT NULL CHECK (json_valid(document))
        )
        """,
        "CREATE INDEX food_logs_by_date ON food_logs (consumed_on, id)",
    ),
)


class FoodLogStorageUnavailable(Exception):
    pass


class FoodLogNotFound(Exception):
    pass


class FoodLogConflict(Exception):
    pass


class FoodLogStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if write or version != len(MIGRATIONS):
                    db.execute("BEGIN IMMEDIATE")
                    # Recheck with the write lock in case another process migrated first.
                    version = db.execute("PRAGMA user_version").fetchone()[0]
                    if version > len(MIGRATIONS):
                        raise FoodLogStorageUnavailable
                    for next_version, statements in enumerate(MIGRATIONS[version:], start=version + 1):
                        for statement in statements:
                            db.execute(statement)
                        db.execute(f"PRAGMA user_version = {next_version}")
                yield db
        except (OSError, sqlite3.Error, ValidationError):
            raise FoodLogStorageUnavailable from None

    @staticmethod
    def _read(db: sqlite3.Connection, log_id: UUID) -> FoodLog:
        row = db.execute("SELECT document FROM food_logs WHERE id = ?", (str(log_id),)).fetchone()
        if row is None:
            raise FoodLogNotFound
        return FoodLog.model_validate_json(row[0])

    @staticmethod
    def _values(log: FoodLog) -> tuple[str, str, int, str, str]:
        return (
            log.consumed_at.date().isoformat(), log.status, log.revision,
            log.model_dump_json(), str(log.id),
        )

    @staticmethod
    def _save(db: sqlite3.Connection, log: FoodLog) -> None:
        db.execute(
            "UPDATE food_logs SET consumed_on = ?, status = ?, revision = ?, document = ? WHERE id = ?",
            FoodLogStore._values(log),
        )

    def create(self, payload: FoodLogCreate) -> FoodLog:
        now = datetime.now(timezone.utc)
        log = FoodLog(
            **payload.model_dump(exclude={"items"}), items=bind_draft_items(payload.items, now, payload.description),
            recognition_weight_review=payload.source != "manual_text" or any(item.recognition_evidence for item in payload.items),
            id=uuid4(), status="draft", revision=1, created_at=now, updated_at=now,
        )
        with self.connection(write=True) as db:
            db.execute(
                "INSERT INTO food_logs (consumed_on, status, revision, document, id) VALUES (?, ?, ?, ?, ?)",
                self._values(log),
            )
        return log

    def list_by_date(self, consumed_on: date) -> list[FoodLog]:
        with self.connection() as db:
            rows = db.execute("SELECT document FROM food_logs WHERE consumed_on = ?", (consumed_on.isoformat(),))
            logs = [FoodLog.model_validate_json(row[0]) for row in rows]
        return sorted(logs, key=lambda log: (log.consumed_at, log.id))

    def list_confirmed_by_date(self, consumed_on: date) -> list[FoodLog]:
        # Reporting never uses connection(), which can create or migrate the database.
        try:
            self.path.stat()
        except FileNotFoundError:
            return []
        except OSError:
            raise FoodLogStorageUnavailable from None

        try:
            database_uri = self.path.absolute().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(database_uri, uri=True, timeout=5)) as db:
                db.execute("BEGIN")
                if db.execute("PRAGMA user_version").fetchone()[0] != len(MIGRATIONS):
                    raise FoodLogStorageUnavailable
                rows = db.execute(
                    "SELECT id, document FROM food_logs WHERE consumed_on = ? AND status = 'confirmed'",
                    (consumed_on.isoformat(),),
                )
                logs = []
                for log_id, document in rows:
                    log = FoodLog.model_validate_json(document)
                    if str(log.id) != log_id or log.status != "confirmed" or log.consumed_at.date() != consumed_on:
                        raise FoodLogStorageUnavailable
                    logs.append(log)
        except (OSError, sqlite3.Error, ValidationError):
            raise FoodLogStorageUnavailable from None
        return sorted(logs, key=lambda log: (log.consumed_at, log.id))

    def update(
        self, log_id: UUID, payload: FoodLogDraft, expected_revision: int, *, recognition_applied: bool = False,
    ) -> FoodLog:
        with self.connection(write=True) as db:
            log = self._read(db, log_id)
            if log.status != "draft" or log.revision != expected_revision:
                raise FoodLogConflict
            now = datetime.now(timezone.utc)
            log = log.model_copy(update={
                **payload.model_dump(exclude={"items"}), "items": bind_draft_items(payload.items, now, payload.description),
                "recognition_weight_review": (
                    log.recognition_weight_review or log.source != "manual_text" or recognition_applied
                    or any(item.recognition_evidence for item in payload.items)
                ),
                "revision": log.revision + 1, "updated_at": now,
            })
            self._save(db, log)
        return log

    def confirm(self, log_id: UUID, expected_revision: int) -> FoodLog:
        with self.connection(write=True) as db:
            log = self._read(db, log_id)
            if log.status == "confirmed" and expected_revision in (log.revision - 1, log.revision):
                return log
            if log.status != "draft" or log.revision != expected_revision:
                raise FoodLogConflict
            validate_bindings_for_confirmation(log.items)
            log = log.model_copy(update={
                "status": "confirmed", "revision": log.revision + 1, "updated_at": datetime.now(timezone.utc),
            })
            self._save(db, log)
        return log

    def delete(self, log_id: UUID, expected_revision: int) -> None:
        with self.connection(write=True) as db:
            log = self._read(db, log_id)
            if log.revision != expected_revision:
                raise FoodLogConflict
            db.execute("DELETE FROM food_logs WHERE id = ?", (str(log_id),))
