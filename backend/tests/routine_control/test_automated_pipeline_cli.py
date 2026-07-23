from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from app.routine_control.cli.automated_pipeline import main


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _App:
    def app_context(self):
        return _Context()


class _Result:
    def __init__(self, succeeded: bool) -> None:
        self.succeeded = succeeded
        self.status = "SUCCESS" if succeeded else "FAILED"
        self.error_code = None if succeeded else "TEST_FAILED"

    def to_dict(self):
        return {
            "error_code": self.error_code,
            "status": self.status,
            "succeeded": self.succeeded,
        }


class AutomatedPipelineCliTestCase(unittest.TestCase):
    ARGS = [
        "--date-from",
        "2026-07-01",
        "--date-to",
        "2026-07-23",
        "--observed-at-utc",
        "2026-07-23T18:00:00Z",
        "--headless",
        "--json",
    ]

    def test_json_success_is_deterministic_and_exit_zero(self) -> None:
        output = StringIO()
        calls = []

        def service(**kwargs):
            calls.append(kwargs)
            return _Result(True)

        with redirect_stdout(output):
            exit_code = main(
                self.ARGS,
                app_factory=_App,
                pipeline_service=service,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["headless"])
        self.assertEqual(
            output.getvalue().strip(),
            '{"error_code":null,"status":"SUCCESS","succeeded":true}',
        )

    def test_failed_result_exits_one(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                self.ARGS,
                app_factory=_App,
                pipeline_service=lambda **_kwargs: _Result(False),
            )
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "FAILED")

    def test_exception_output_does_not_include_exception_message(self) -> None:
        output = StringIO()

        def failing_service(**_kwargs):
            raise RuntimeError("password=secret C:/private")

        with redirect_stdout(output):
            exit_code = main(
                self.ARGS,
                app_factory=_App,
                pipeline_service=failing_service,
            )
        payload = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("RuntimeError", payload)
        self.assertNotIn("password=secret", payload)
        self.assertNotIn("C:/private", payload)


if __name__ == "__main__":
    unittest.main()
