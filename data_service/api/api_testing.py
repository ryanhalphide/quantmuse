"""
API Testing
Register and run lightweight test cases against an APIManager's endpoints,
then summarize results using the manager's built-in performance metrics.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .api_manager import APIManager, APIResponse


@dataclass
class APITestCase:
    """A single endpoint test case."""
    name: str
    endpoint_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    expected_status: int = 200
    # Optional custom assertion on the APIResponse; returns True when the data is valid.
    validator: Optional[Callable[[APIResponse], bool]] = None


@dataclass
class APITestResult:
    """Outcome of running a test case."""
    name: str
    endpoint_name: str
    passed: bool
    status_code: Optional[int]
    response_time: Optional[float]
    message: str = ""


class APITesting:
    """Run registered test cases against an APIManager."""

    def __init__(self, api_manager: APIManager):
        self.logger = logging.getLogger(__name__)
        self.api_manager = api_manager
        self.test_cases: Dict[str, APITestCase] = {}

    def register_test(self, test_case: APITestCase):
        """Register a test case by name."""
        self.test_cases[test_case.name] = test_case
        self.logger.info(f"Registered API test: {test_case.name}")

    def run_test(self, test_name: str) -> APITestResult:
        """Run a single registered test case."""
        if test_name not in self.test_cases:
            return APITestResult(test_name, "", False, None, None,
                                 "test case not found")
        tc = self.test_cases[test_name]

        if tc.endpoint_name not in self.api_manager.endpoints:
            return APITestResult(tc.name, tc.endpoint_name, False, None, None,
                                 f"endpoint '{tc.endpoint_name}' not registered")

        # Disable cache so each test exercises the real endpoint.
        response = self.api_manager.make_request(
            tc.endpoint_name, params=tc.params, use_cache=False
        )
        if response is None:
            return APITestResult(tc.name, tc.endpoint_name, False, None, None,
                                 "no response (rate-limited or request failed)")

        if response.status_code != tc.expected_status:
            return APITestResult(
                tc.name, tc.endpoint_name, False, response.status_code,
                response.response_time,
                f"expected status {tc.expected_status}, got {response.status_code}",
            )

        if tc.validator is not None:
            try:
                if not tc.validator(response):
                    return APITestResult(
                        tc.name, tc.endpoint_name, False, response.status_code,
                        response.response_time, "validator returned False",
                    )
            except Exception as e:
                return APITestResult(
                    tc.name, tc.endpoint_name, False, response.status_code,
                    response.response_time, f"validator raised: {e}",
                )

        return APITestResult(tc.name, tc.endpoint_name, True, response.status_code,
                             response.response_time, "ok")

    def run_all(self) -> Dict[str, APITestResult]:
        """Run every registered test case."""
        return {name: self.run_test(name) for name in self.test_cases}

    def generate_report(self, results: Optional[Dict[str, APITestResult]] = None) -> str:
        """Render a text report. Runs all tests if results are not supplied."""
        if results is None:
            results = self.run_all()

        total = len(results)
        passed = sum(1 for r in results.values() if r.passed)
        lines = [
            "=" * 50,
            "API TEST REPORT",
            "=" * 50,
            f"Total: {total}  Passed: {passed}  Failed: {total - passed}",
            "",
        ]
        for r in results.values():
            mark = "PASS" if r.passed else "FAIL"
            rt = f"{r.response_time:.3f}s" if r.response_time is not None else "-"
            lines.append(f"[{mark}] {r.name} ({r.endpoint_name}) "
                         f"status={r.status_code} time={rt} :: {r.message}")
        return "\n".join(lines)
