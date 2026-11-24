"""Where each report stands, kept in SQLite so a restart loses nothing.

    NEW -> AWAITING_ANSWERS -> ROOM_OPEN -> FIXED
    NEW -> ANSWERED     (a question, a feature request, or still unclear)
    NEW -> DUPLICATE    (already known; the reporter gets the existing link)

AWAITING_ANSWERS can be entered once per report, which is how the "at most
two questions" rule is enforced in code rather than in the prompt.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Stage(str, Enum):
    NEW = "new"
    AWAITING_ANSWERS = "awaiting_answers"
    ROOM_OPEN = "room_open"
    FIXED = "fixed"
    ANSWERED = "answered"
    DUPLICATE = "duplicate"


TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.NEW: {Stage.AWAITING_ANSWERS, Stage.ROOM_OPEN, Stage.ANSWERED, Stage.DUPLICATE},
    Stage.AWAITING_ANSWERS: {Stage.ROOM_OPEN, Stage.ANSWERED, Stage.DUPLICATE},
    Stage.ROOM_OPEN: {Stage.FIXED},
    Stage.FIXED: set(),
    Stage.ANSWERED: set(),
    Stage.DUPLICATE: set(),
}

MAX_QUESTIONS = 2


def can_move(current: Stage, target: Stage) -> bool:
    return target in TRANSITIONS[current]


class InvalidTransition(Exception):
    pass


@dataclass
class Report:
    thread_id: str
    intake_room_id: str
    reporter: str
    messages: list[str] = field(default_factory=list)
    stage: Stage = Stage.NEW
    slug: str | None = None
    summary: str | None = None
    work_room_id: str | None = None
    pr_url: str | None = None

    @property
    def questions_allowed(self) -> bool:
        return self.stage is Stage.NEW


_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    thread_id      TEXT PRIMARY KEY,
    intake_room_id TEXT NOT NULL,
    reporter       TEXT NOT NULL,
    messages       TEXT NOT NULL,
    stage          TEXT NOT NULL,
    slug           TEXT,
    summary        TEXT,
    work_room_id   TEXT,
    pr_url         TEXT,
    updated_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS reports_work_room ON reports(work_room_id);
CREATE TABLE IF NOT EXISTS handled (message_id TEXT PRIMARY KEY);
"""

_SEP = "\x1e"  # record separator between a report's messages


class Store:
    def __init__(self, path: Path | str = ":memory:"):
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    # -- reports --------------------------------------------------------------

    def get(self, thread_id: str) -> Report | None:
        row = self._db.execute("SELECT * FROM reports WHERE thread_id = ?", (thread_id,)).fetchone()
        return _report(row) if row else None

    def by_work_room(self, room_id: str) -> Report | None:
        row = self._db.execute(
            "SELECT * FROM reports WHERE work_room_id = ?", (room_id,)
        ).fetchone()
        return _report(row) if row else None

    def save(self, report: Report) -> None:
        self._db.execute(
            """INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(thread_id) DO UPDATE SET
                 messages=excluded.messages, stage=excluded.stage, slug=excluded.slug,
                 summary=excluded.summary, work_room_id=excluded.work_room_id,
                 pr_url=excluded.pr_url, updated_at=excluded.updated_at""",
            (
                report.thread_id, report.intake_room_id, report.reporter,
                _SEP.join(report.messages), report.stage.value, report.slug,
                report.summary, report.work_room_id, report.pr_url, time.time(),
            ),
        )
        self._db.commit()

    def move(self, report: Report, target: Stage, **fields: object) -> Report:
        if not can_move(report.stage, target):
            raise InvalidTransition(f"{report.stage.value} -> {target.value}")
        report.stage = target
        for name, value in fields.items():
            setattr(report, name, value)
        self.save(report)
        return report

    # -- replayed events ------------------------------------------------------

    def first_time(self, message_id: str) -> bool:
        """True the first time a message id is seen, so a resumed stream can't act twice."""
        cursor = self._db.execute(
            "INSERT OR IGNORE INTO handled (message_id) VALUES (?)", (message_id,)
        )
        self._db.commit()
        return cursor.rowcount == 1


def _report(row: sqlite3.Row) -> Report:
    return Report(
        thread_id=row["thread_id"],
        intake_room_id=row["intake_room_id"],
        reporter=row["reporter"],
        messages=row["messages"].split(_SEP) if row["messages"] else [],
        stage=Stage(row["stage"]),
        slug=row["slug"],
        summary=row["summary"],
        work_room_id=row["work_room_id"],
        pr_url=row["pr_url"],
    )
