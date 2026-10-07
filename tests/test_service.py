from __future__ import annotations

import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from hydrosim.engine import run_engine
from hydrosim.repository import ScenarioRepository
from hydrosim.service import InvalidScenarioError, ScenarioService


class ScenarioServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repository = ScenarioRepository(
            str(Path(self.temp_dir.name) / "scenarios.sqlite3")
        )
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.addCleanup(self.executor.shutdown, wait=True)
        self.service = ScenarioService(self.repository, self.executor, run_engine)

    def _wait_for_terminal_status(self, scenario_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            scenario = self.service.get(scenario_id)
            if scenario and scenario["status"] in {"SUCCEEDED", "FAILED"}:
                return scenario
            time.sleep(0.01)
        self.fail("Scenario did not reach a terminal status.")

    def test_demo_scenario_completes_with_explicitly_synthetic_result(self) -> None:
        submitted = self.service.submit(
            {"name": "small-demo", "parameters": {"flow": 10}}
        )
        self.assertIn(submitted["status"], {"QUEUED", "RUNNING", "SUCCEEDED"})

        completed = self._wait_for_terminal_status(submitted["scenario_id"])
        self.assertEqual(completed["status"], "SUCCEEDED")
        self.assertFalse(completed["result"]["is_engineering_result"])
        self.assertEqual(completed["result"]["received_parameters"], {"flow": 10})

    def test_hecras_fails_clearly_until_engine_is_configured(self) -> None:
        submitted = self.service.submit(
            {"name": "hecras-not-configured", "engine": "hec-ras"}
        )

        failed = self._wait_for_terminal_status(submitted["scenario_id"])
        self.assertEqual(failed["status"], "FAILED")
        self.assertIn("HEC-RAS execution is not configured", failed["error"])

    def test_invalid_payloads_are_rejected(self) -> None:
        invalid_payloads = [
            None,
            {"name": ""},
            {"name": "bad-engine", "engine": "unknown"},
            {"name": "bad-engine-type", "engine": ["demo"]},
            {"name": "bad-parameters", "parameters": []},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(InvalidScenarioError):
                    self.service.submit(payload)

    def test_created_scenario_survives_repository_reopen(self) -> None:
        submitted = self.service.submit({"name": "persistent-demo"})
        self._wait_for_terminal_status(submitted["scenario_id"])

        reopened = ScenarioRepository(self.repository.database_path)
        persisted = reopened.get(submitted["scenario_id"])
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["name"], "persistent-demo")
        self.assertEqual(persisted["status"], "SUCCEEDED")


if __name__ == "__main__":
    unittest.main()
