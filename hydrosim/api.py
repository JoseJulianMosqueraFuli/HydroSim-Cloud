from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from hydrosim.engine import run_engine
from hydrosim.repository import ScenarioRepository
from hydrosim.service import InvalidScenarioError, ScenarioService

MAX_REQUEST_BYTES = 65_536
SCENARIO_ID_PATTERN = re.compile(r"^[0-9a-f-]{36}$")


def create_service(database_path: str | None = None) -> ScenarioService:
    path = database_path or os.environ.get(
        "HYDROSIM_DB_PATH", "./data/scenarios.sqlite3"
    )
    max_workers = int(os.environ.get("HYDROSIM_MAX_WORKERS", "1"))
    if max_workers < 1 or max_workers > 4:
        raise ValueError("HYDROSIM_MAX_WORKERS must be between 1 and 4.")
    return ScenarioService(
        repository=ScenarioRepository(path),
        executor=ThreadPoolExecutor(max_workers=max_workers),
        engine_runner=run_engine,
    )


class ScenarioRequestHandler(BaseHTTPRequestHandler):
    service: ScenarioService

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return

        prefix = "/scenarios/"
        if self.path.startswith(prefix):
            scenario_id = self.path[len(prefix) :]
            if not SCENARIO_ID_PATTERN.fullmatch(scenario_id):
                self._send_json(400, {"error": "Invalid scenario id."})
                return
            scenario = self.service.get(scenario_id)
            if scenario is None:
                self._send_json(404, {"error": "Scenario not found."})
                return
            self._send_json(200, scenario)
            return

        self._send_json(404, {"error": "Route not found."})

    def do_POST(self) -> None:
        if self.path != "/scenarios":
            self._send_json(404, {"error": "Route not found."})
            return

        content_length = self.headers.get("Content-Length")
        if content_length is None or not content_length.isdecimal():
            self._send_json(400, {"error": "Content-Length is required."})
            return
        if int(content_length) > MAX_REQUEST_BYTES:
            self._send_json(413, {"error": "Request body is too large."})
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json(415, {"error": "Content-Type must be application/json."})
            return

        try:
            payload: Any = json.loads(self.rfile.read(int(content_length)))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "Request body must contain valid JSON."})
            return

        try:
            scenario = self.service.submit(payload)
        except InvalidScenarioError as error:
            self._send_json(400, {"error": str(error)})
            return
        except RuntimeError as error:
            self._send_json(503, {"error": str(error)})
            return

        self._send_json(202, scenario)

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), format % args))


def serve() -> None:
    host = os.environ.get("HYDROSIM_HOST", "127.0.0.1")
    port = int(os.environ.get("HYDROSIM_PORT", "8080"))
    service = create_service()
    handler = type(
        "ConfiguredScenarioRequestHandler",
        (ScenarioRequestHandler,),
        {"service": service},
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"HydroSim API listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down HydroSim API.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
