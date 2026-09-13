"""Single-machine SQLite stage ledger. Process adoption and production scheduling are not implemented."""
import json
from pathlib import Path
import sqlite3
import time

from .common import PipelineError, canonical


class StateStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          run_key TEXT PRIMARY KEY, case_id TEXT NOT NULL, manifest TEXT NOT NULL,
          created_s REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (
          run_key TEXT NOT NULL REFERENCES runs(run_key), stage TEXT NOT NULL,
          attempt INTEGER NOT NULL, status TEXT NOT NULL,
          owner TEXT NOT NULL, updated_s REAL NOT NULL, result TEXT,
          PRIMARY KEY (run_key, stage, attempt));
        CREATE UNIQUE INDEX IF NOT EXISTS one_live_attempt
          ON attempts(run_key, stage) WHERE status = 'RUNNING';
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, run_key TEXT NOT NULL,
          stage TEXT NOT NULL, payload TEXT NOT NULL, at_s REAL NOT NULL);
        """)

    def close(self):
        self.db.close()

    def register(self, key, case_id, manifest):
        encoded = canonical(manifest)
        with self.db:
            row = self.db.execute("SELECT manifest FROM runs WHERE run_key=?", (key,)).fetchone()
            if row and row["manifest"] != encoded:
                raise PipelineError("IDENTITY_CONFLICT", "Same run key has different configuration.")
            self.db.execute("INSERT OR IGNORE INTO runs VALUES (?,?,?,?)", (key, case_id, encoded, time.time()))

    def claim(self, key, stage, owner):
        try:
            self.db.execute("BEGIN IMMEDIATE")
            number = self.db.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM attempts WHERE run_key=? AND stage=?", (key, stage)).fetchone()[0]
            self.db.execute("INSERT INTO attempts VALUES (?,?,?,'RUNNING',?,?,NULL)", (key, stage, number, owner, time.time()))
            self.db.commit()
            return number
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            raise PipelineError("STAGE_ALREADY_RUNNING_OR_UNREGISTERED", "Reconcile live process before retrying.") from exc

    def finish(self, key, stage, attempt, owner, status, result):
        if status not in {"PASS", "FAIL", "NEEDS_REVIEW", "INTERRUPTED", "BLOCKED"}:
            raise ValueError("Invalid stage status.")
        # The scaffold must never create a false accepted scientific sample.
        if stage == "PUBLISH" and status == "PASS":
            raise PipelineError("NOT_IMPLEMENTED", "Production acceptance gate is not implemented in v0.1.")
        with self.db:
            cur = self.db.execute("UPDATE attempts SET status=?, result=?, updated_s=? WHERE run_key=? AND stage=? AND attempt=? AND owner=? AND status='RUNNING'",
                                  (status, canonical(result), time.time(), key, stage, attempt, owner))
            if cur.rowcount != 1:
                raise PipelineError("OWNERSHIP_MISMATCH", "Attempt does not belong to this worker or is already finished.")
            self.db.execute("INSERT INTO events(run_key,stage,payload,at_s) VALUES (?,?,?,?)", (key, stage, canonical(result), time.time()))

    def status(self):
        return [dict(row) for row in self.db.execute("SELECT run_key,stage,attempt,status,owner,updated_s FROM attempts ORDER BY run_key,stage,attempt")]
