from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ScenarioRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scenarios (
                    scenario_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                UPDATE scenarios
                SET status = 'FAILED',
                    error = 'Local worker stopped before the scenario completed.',
                    updated_at = ?
                WHERE status IN ('QUEUED', 'RUNNING')
                """,
                (utc_now(),),
            )

    def create(self, scenario: dict[str, Any]) -> None:
        now = utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO scenarios (
                    scenario_id, name, engine, status, parameters_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'QUEUED', ?, ?, ?)
                """,
                (
                    scenario["scenario_id"],
                    scenario["name"],
                    scenario["engine"],
                    json.dumps(scenario["parameters"]),
                    now,
                    now,
                ),
            )

    def set_running(self, scenario_id: str) -> None:
        self._update_status(scenario_id, "RUNNING")

    def set_succeeded(self, scenario_id: str, result: dict[str, Any]) -> None:
        now = utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE scenarios
                SET status = 'SUCCEEDED', result_json = ?, error = NULL,
                    updated_at = ?
                WHERE scenario_id = ?
                """,
                (json.dumps(result), now, scenario_id),
            )

    def set_failed(self, scenario_id: str, error: str) -> None:
        now = utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE scenarios
                SET status = 'FAILED', error = ?, updated_at = ?
                WHERE scenario_id = ?
                """,
                (error, now, scenario_id),
            )

    def get(self, scenario_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM scenarios WHERE scenario_id = ?",
                (scenario_id,),
            ).fetchone()

        if row is None:
            return None

        scenario = dict(row)
        scenario["parameters"] = json.loads(scenario.pop("parameters_json"))
        result_json = scenario.pop("result_json")
        scenario["result"] = json.loads(result_json) if result_json else None
        return scenario

    def _update_status(self, scenario_id: str, status: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE scenarios SET status = ?, updated_at = ? WHERE scenario_id = ?",
                (status, utc_now(), scenario_id),
            )
