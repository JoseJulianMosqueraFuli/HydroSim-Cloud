from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from unittest.mock import Mock, patch


class BotoCoreError(Exception):
    pass


class ClientError(Exception):
    pass


botocore_module = types.ModuleType("botocore")
botocore_exceptions = types.ModuleType("botocore.exceptions")
botocore_exceptions.BotoCoreError = BotoCoreError
botocore_exceptions.ClientError = ClientError
botocore_module.exceptions = botocore_exceptions
with patch.dict(
    sys.modules,
    {
        "botocore": botocore_module,
        "botocore.exceptions": botocore_exceptions,
    },
):
    aws_handler = importlib.import_module("hydrosim.aws_handler")


class AwsHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = Mock()
        self.stepfunctions = Mock()
        self.clients = patch.object(
            aws_handler,
            "_clients",
            return_value=(self.table, self.stepfunctions),
        )
        self.clients.start()
        self.addCleanup(self.clients.stop)

    def test_submit_persists_then_starts_workflow_without_scenario_parameters(self) -> None:
        event = {
            "rawPath": "/scenarios",
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps(
                {"name": "demo", "parameters": {"flow_rate_cms": 42.5}}
            ),
        }
        with patch.dict(
            "os.environ",
            {"SCENARIOS_TABLE": "scenarios", "WORKFLOW_ARN": "arn:workflow"},
        ):
            response = aws_handler.api_handler(event, None)

        self.assertEqual(response["statusCode"], 202)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "QUEUED")
        self.table.put_item.assert_called_once()
        started = json.loads(self.stepfunctions.start_execution.call_args.kwargs["input"])
        self.assertEqual(started, {"scenario_id": body["scenario_id"]})

    def test_worker_records_synthetic_success(self) -> None:
        scenario_id = "e13b1527-1b8b-42da-9a9b-18b4d11fa087"
        self.table.get_item.return_value = {
            "Item": {
                "engine": "demo",
                "parameters": json.dumps({"flow": 10}),
            }
        }
        result = aws_handler.worker_handler({"scenario_id": scenario_id}, None)

        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(self.table.update_item.call_count, 2)
        completed_update = self.table.update_item.call_args.kwargs
        stored_result = json.loads(
            completed_update["ExpressionAttributeValues"][":result"]
        )
        self.assertFalse(stored_result["is_engineering_result"])

    def test_invalid_request_does_not_call_aws(self) -> None:
        event = {
            "rawPath": "/scenarios",
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({"name": "bad", "engine": []}),
        }
        response = aws_handler.api_handler(event, None)

        self.assertEqual(response["statusCode"], 400)
        self.table.put_item.assert_not_called()
        self.stepfunctions.start_execution.assert_not_called()


if __name__ == "__main__":
    unittest.main()
