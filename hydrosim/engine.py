from __future__ import annotations

from typing import Any


class EngineNotConfiguredError(RuntimeError):
    """Raised when a real simulation engine has not been configured."""


def run_demo_engine(parameters: dict[str, Any]) -> dict[str, Any]:
    """Return a synthetic result for exercising the API workflow only."""
    return {
        "engine": "demo",
        "is_engineering_result": False,
        "message": "Synthetic output only; this is not a hydraulic calculation.",
        "received_parameters": parameters,
    }


def run_hecras_engine(parameters: dict[str, Any]) -> dict[str, Any]:
    del parameters
    raise EngineNotConfiguredError(
        "HEC-RAS execution is not configured. Install and validate the licensed "
        "engine and its automation interface before enabling this worker."
    )


def run_engine(engine: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if engine == "demo":
        return run_demo_engine(parameters)
    if engine == "hec-ras":
        return run_hecras_engine(parameters)
    raise ValueError(f"Unsupported simulation engine: {engine}")
