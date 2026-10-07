from __future__ import annotations

import json
from concurrent.futures import Executor
from typing import Any, Callable
from uuid import uuid4

from hydrosim.repository import ScenarioRepository

EngineRunner = Callable[[str, dict[str, Any]], dict[str, Any]]


class InvalidScenarioError(ValueError):
    pass


def normalize_scenario(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InvalidScenarioError("The request body must be a JSON object.")

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise InvalidScenarioError("name must be a non-empty string of at most 120 characters.")

    engine = payload.get("engine", "demo")
    if not isinstance(engine, str) or engine not in {"demo", "hec-ras"}:
        raise InvalidScenarioError("engine must be either 'demo' or 'hec-ras'.")

    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        raise InvalidScenarioError("parameters must be a JSON object.")
    if len(json.dumps(parameters).encode("utf-8")) > 32_768:
        raise InvalidScenarioError("parameters must not exceed 32 KiB.")

    return {
        "name": name.strip(),
        "engine": engine,
        "parameters": parameters,
    }


class ScenarioService:
    def __init__(
        self,
        repository: ScenarioRepository,
        executor: Executor,
        engine_runner: EngineRunner,
    ) -> None:
        self.repository = repository
        self.executor = executor
        self.engine_runner = engine_runner

    def submit(self, payload: Any) -> dict[str, Any]:
        scenario = {
            "scenario_id": str(uuid4()),
            **normalize_scenario(payload),
        }
        self.repository.create(scenario)
        try:
            self.executor.submit(self._execute, scenario)
        except RuntimeError as error:
            self.repository.set_failed(scenario["scenario_id"], "Worker is not available.")
            raise RuntimeError("Worker is not available.") from error

        return self.repository.get(scenario["scenario_id"]) or scenario

    def get(self, scenario_id: str) -> dict[str, Any] | None:
        return self.repository.get(scenario_id)

    def _execute(self, scenario: dict[str, Any]) -> None:
        scenario_id = scenario["scenario_id"]
        self.repository.set_running(scenario_id)
        try:
            result = self.engine_runner(scenario["engine"], scenario["parameters"])
            self.repository.set_succeeded(scenario_id, result)
        except Exception as error:
            self.repository.set_failed(scenario_id, str(error))
