from __future__ import annotations

import base64
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError

from hydrosim.engine import run_engine
from hydrosim.service import InvalidScenarioError, normalize_scenario

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAX_REQUEST_BYTES = 65_536


def _clients():
    import boto3

    return (
        boto3.resource("dynamodb").Table(os.environ["SCENARIOS_TABLE"]),
        boto3.client("stepfunctions"),
    )


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(body),
    }


def _public_scenario(item: dict[str, Any]) -> dict[str, Any]:
    scenario = dict(item)
    scenario["parameters"] = json.loads(scenario["parameters"])
    if "result" in scenario:
        scenario["result"] = json.loads(scenario["result"])
    return scenario


def api_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "")
    if method == "GET" and path == "/health":
        return _response(200, {"status": "ok"})

    if method == "POST" and path == "/scenarios":
        body = event.get("body") or ""
        try:
            if event.get("isBase64Encoded"):
                raw_body = base64.b64decode(body, validate=True)
                body = raw_body.decode("utf-8")
            if len(body.encode("utf-8")) > MAX_REQUEST_BYTES:
                return _response(413, {"error": "Request body is too large."})
            decoded_payload = json.loads(body)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return _response(400, {"error": str(error) or "Request body must be valid JSON."})
        try:
            payload = normalize_scenario(decoded_payload)
        except InvalidScenarioError as error:
            return _response(400, {"error": str(error)})

        scenario_id = str(uuid4())
        now = _timestamp()
        item = {
            "scenario_id": scenario_id,
            **payload,
            "parameters": json.dumps(payload["parameters"]),
            "status": "QUEUED",
            "created_at": now,
            "updated_at": now,
        }
        table, stepfunctions = _clients()
        try:
            table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(scenario_id)",
            )
        except (BotoCoreError, ClientError):
            logger.exception("Unable to persist scenario %s", scenario_id)
            return _response(502, {"error": "Unable to persist scenario."})

        try:
            stepfunctions.start_execution(
                stateMachineArn=os.environ["WORKFLOW_ARN"],
                name=scenario_id,
                input=json.dumps({"scenario_id": scenario_id}),
            )
        except (BotoCoreError, ClientError, KeyError):
            logger.exception("Unable to persist or start scenario %s", scenario_id)
            try:
                table.update_item(
                    Key={"scenario_id": scenario_id},
                    UpdateExpression="SET #status = :status, #error = :error, updated_at = :updated",
                    ExpressionAttributeNames={
                        "#status": "status",
                        "#error": "error",
                    },
                    ExpressionAttributeValues={
                        ":status": "FAILED",
                        ":error": "Unable to start scenario workflow.",
                        ":updated": _timestamp(),
                    },
                )
            except (BotoCoreError, ClientError):
                logger.exception("Unable to mark scenario %s as failed", scenario_id)
            return _response(502, {"error": "Unable to start scenario workflow."})
        return _response(202, _public_scenario(item))

    if method == "GET" and path.startswith("/scenarios/"):
        scenario_id = path.removeprefix("/scenarios/")
        if not _is_uuid(scenario_id):
            return _response(400, {"error": "Invalid scenario id."})
        table, _ = _clients()
        try:
            result = table.get_item(Key={"scenario_id": scenario_id})
        except (BotoCoreError, ClientError):
            logger.exception("Unable to load scenario %s", scenario_id)
            return _response(502, {"error": "Unable to load scenario."})
        item = result.get("Item")
        if item is None:
            return _response(404, {"error": "Scenario not found."})
        return _response(200, _public_scenario(item))

    return _response(404, {"error": "Route not found."})


def worker_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    table, _ = _clients()
    scenario_id = event["scenario_id"]
    response = table.get_item(
        Key={"scenario_id": scenario_id},
        ConsistentRead=True,
    )
    item = response.get("Item")
    if item is None:
        raise ValueError(f"Scenario {scenario_id} does not exist.")
    table.update_item(
        Key={"scenario_id": scenario_id},
        UpdateExpression="SET #status = :status, updated_at = :updated REMOVE #error",
        ExpressionAttributeNames={"#status": "status", "#error": "error"},
        ExpressionAttributeValues={
            ":status": "RUNNING",
            ":updated": _timestamp(),
        },
    )
    try:
        result = run_engine(item["engine"], json.loads(item["parameters"]))
    except Exception as error:
        table.update_item(
            Key={"scenario_id": scenario_id},
            UpdateExpression="SET #status = :status, #error = :error, updated_at = :updated",
            ExpressionAttributeNames={"#status": "status", "#error": "error"},
            ExpressionAttributeValues={
                ":status": "FAILED",
                ":error": str(error),
                ":updated": _timestamp(),
            },
        )
        logger.exception("Scenario %s failed in the configured engine", scenario_id)
        raise

    table.update_item(
        Key={"scenario_id": scenario_id},
        UpdateExpression="SET #status = :status, #result = :result, updated_at = :updated REMOVE #error",
        ExpressionAttributeNames={
            "#status": "status",
            "#result": "result",
            "#error": "error",
        },
        ExpressionAttributeValues={
            ":status": "SUCCEEDED",
            ":result": json.dumps(result),
            ":updated": _timestamp(),
        },
    )
    return {"scenario_id": scenario_id, "status": "SUCCEEDED"}


def _is_uuid(value: str) -> bool:
    try:
        from uuid import UUID

        return str(UUID(value)) == value
    except ValueError:
        return False
