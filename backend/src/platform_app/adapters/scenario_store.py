from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
import sqlite3

from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import SavedScenario


@dataclass(frozen=True)
class SaveOutcome:
    scenario: SavedScenario
    replayed: bool


class ScenarioStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(self._connect()) as connection, connection:
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS scenarios(
                scenario_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                title TEXT NOT NULL, created_at TEXT NOT NULL, payload_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS idempotency(
                project_id TEXT NOT NULL, operation TEXT NOT NULL, request_key TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL, scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                PRIMARY KEY(project_id,operation,request_key));
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _lookup(connection, project: str, key: str, fingerprint: str) -> SaveOutcome | None:
        row = connection.execute("""SELECT i.payload_fingerprint,s.payload_json
            FROM idempotency i JOIN scenarios s ON i.scenario_id=s.scenario_id
            WHERE i.project_id=? AND i.operation='save' AND i.request_key=?""",(project,key)).fetchone()
        if row is None:
            return None
        if row[0] != fingerprint:
            raise DomainConflict("idempotency_conflict", "此保存请求已用于其他参数或名称，请重新保存。")
        return SaveOutcome(SavedScenario.model_validate_json(row[1]), True)

    def find_request(self, project: str, key: str, fingerprint: str) -> SaveOutcome | None:
        connection = self._connect()
        try:
            return self._lookup(connection, project, key, fingerprint)
        finally:
            connection.close()

    def save(self, scenario: SavedScenario, key: str, fingerprint: str) -> SaveOutcome:
        connection = self._connect()
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                cached = self._lookup(connection, scenario.project_id, key, fingerprint)
                if cached is not None:
                    return cached
                connection.execute("INSERT INTO scenarios VALUES(?,?,?,?,?)",(scenario.scenario_id,
                    scenario.project_id,scenario.title,scenario.created_at.isoformat(),scenario.model_dump_json()))
                connection.execute("INSERT INTO idempotency VALUES(?,'save',?,?,?)",
                    (scenario.project_id,key,fingerprint,scenario.scenario_id))
            return SaveOutcome(scenario,False)
        finally:
            connection.close()

    def get(self, scenario_id: str, project_id: str = "local") -> SavedScenario:
        connection = self._connect()
        try:
            row = connection.execute("SELECT payload_json FROM scenarios WHERE scenario_id=? AND project_id=?",
                                     (scenario_id,project_id)).fetchone()
            if row is None:
                raise KeyError(scenario_id)
            return SavedScenario.model_validate_json(row[0])
        finally:
            connection.close()

    def list(self, project_id: str = "local") -> tuple[SavedScenario, ...]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT payload_json FROM scenarios WHERE project_id=? ORDER BY created_at DESC,scenario_id",
                                      (project_id,)).fetchall()
            return tuple(SavedScenario.model_validate_json(row[0]) for row in rows)
        finally:
            connection.close()
