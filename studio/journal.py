"""SQLite journal: the single source of truth for traceability and replay.

Three tables: runs (one per brief), generations (one per image or failure),
replays (one per verification of a past generation). All SQL lives in this file
and uses parameterized queries only.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from studio.errors import StudioError
from studio.models import Brief, RunConfig

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    author       TEXT NOT NULL,
    brief_json   TEXT NOT NULL,
    config_json  TEXT NOT NULL,
    optimizer_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS generations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL REFERENCES runs(run_id),
    engine         TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    seed           INTEGER NOT NULL,
    prompt         TEXT NOT NULL,
    params_json    TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    error          TEXT,
    output_path    TEXT,
    output_sha256  TEXT,
    env_json       TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    author         TEXT NOT NULL,
    kept           INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS replays (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id  INTEGER NOT NULL REFERENCES generations(id),
    replayed_at    TEXT NOT NULL,
    author         TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    new_sha256     TEXT NOT NULL,
    identical      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_generations_run ON generations(run_id);
"""


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    created_at: str
    author: str
    brief: dict
    config: dict
    optimizer_id: str


@dataclass(frozen=True)
class GenerationRecord:
    id: int
    run_id: str
    engine: str
    engine_version: str
    seed: int
    prompt: str
    params: dict
    status: str
    error: str | None
    output_path: str | None
    output_sha256: str | None
    env: dict
    created_at: str
    author: str
    kept: bool


@dataclass(frozen=True)
class ReplayRecord:
    id: int
    generation_id: int
    replayed_at: str
    author: str
    engine_version: str
    new_sha256: str
    identical: bool


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


class Journal:
    def __init__(self, db_path: str | Path, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._conn:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ----- runs -----------------------------------------------------------------

    def start_run(self, brief: Brief, config: RunConfig, optimizer_id: str) -> str:
        now = self._clock()
        run_id = f"{now:%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
        with self._conn:
            self._conn.execute(
                "INSERT INTO runs (run_id, created_at, author, brief_json, config_json, optimizer_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, now.isoformat(timespec="seconds"), config.author,
                 _dumps(asdict(brief)), _dumps(asdict(config)), optimizer_id),
            )
        return run_id

    def get_run(self, run_id: str) -> RunRecord:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise StudioError(f"no run with id {run_id}")
        return RunRecord(row["run_id"], row["created_at"], row["author"],
                         json.loads(row["brief_json"]), json.loads(row["config_json"]),
                         row["optimizer_id"])

    def list_runs(self) -> list[RunRecord]:
        rows = self._conn.execute(
            "SELECT run_id FROM runs ORDER BY created_at DESC, rowid DESC").fetchall()
        return [self.get_run(r["run_id"]) for r in rows]

    # ----- generations ----------------------------------------------------------

    def record_generation(
        self, *, run_id: str, engine: str, engine_version: str, seed: int, prompt: str,
        params: dict, status: str, env: dict, author: str, error: str | None = None,
        output_path: str | None = None, output_sha256: str | None = None,
    ) -> GenerationRecord:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO generations (run_id, engine, engine_version, seed, prompt, params_json, "
                "status, error, output_path, output_sha256, env_json, created_at, author) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, engine, engine_version, seed, prompt, _dumps(params), status, error,
                 output_path, output_sha256, _dumps(env),
                 self._clock().isoformat(timespec="seconds"), author),
            )
        return self.get_generation(cursor.lastrowid)

    def get_generation(self, generation_id: int) -> GenerationRecord:
        row = self._conn.execute(
            "SELECT * FROM generations WHERE id = ?", (generation_id,)).fetchone()
        if row is None:
            raise StudioError(f"no generation with id {generation_id}")
        return self._generation(row)

    def list_generations(self, run_id: str) -> list[GenerationRecord]:
        rows = self._conn.execute(
            "SELECT * FROM generations WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        return [self._generation(r) for r in rows]

    def count_generations(self, run_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM generations WHERE run_id = ?", (run_id,)).fetchone()
        return row["n"]

    def mark_kept(self, generation_id: int, kept: bool = True) -> GenerationRecord:
        self.get_generation(generation_id)  # raises a clear error if the id is unknown
        with self._conn:
            self._conn.execute(
                "UPDATE generations SET kept = ? WHERE id = ?", (int(kept), generation_id))
        return self.get_generation(generation_id)

    # ----- replays --------------------------------------------------------------

    def add_replay(self, *, generation_id: int, author: str, engine_version: str,
                   new_sha256: str, identical: bool) -> ReplayRecord:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO replays (generation_id, replayed_at, author, engine_version, "
                "new_sha256, identical) VALUES (?, ?, ?, ?, ?, ?)",
                (generation_id, self._clock().isoformat(timespec="seconds"), author,
                 engine_version, new_sha256, int(identical)),
            )
        row = self._conn.execute(
            "SELECT * FROM replays WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._replay(row)

    def list_replays(self, generation_id: int) -> list[ReplayRecord]:
        rows = self._conn.execute(
            "SELECT * FROM replays WHERE generation_id = ? ORDER BY id", (generation_id,)).fetchall()
        return [self._replay(r) for r in rows]

    # ----- row mapping ----------------------------------------------------------

    @staticmethod
    def _generation(row: sqlite3.Row) -> GenerationRecord:
        return GenerationRecord(
            id=row["id"], run_id=row["run_id"], engine=row["engine"],
            engine_version=row["engine_version"], seed=row["seed"], prompt=row["prompt"],
            params=json.loads(row["params_json"]), status=row["status"], error=row["error"],
            output_path=row["output_path"], output_sha256=row["output_sha256"],
            env=json.loads(row["env_json"]), created_at=row["created_at"],
            author=row["author"], kept=bool(row["kept"]),
        )

    @staticmethod
    def _replay(row: sqlite3.Row) -> ReplayRecord:
        return ReplayRecord(
            id=row["id"], generation_id=row["generation_id"], replayed_at=row["replayed_at"],
            author=row["author"], engine_version=row["engine_version"],
            new_sha256=row["new_sha256"], identical=bool(row["identical"]),
        )
