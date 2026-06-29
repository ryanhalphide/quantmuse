import json
import unittest
from datetime import datetime
from unittest.mock import patch

from data_service.api import (
    APIManager, APIEndpoint, APIResponse,
    APIDocumentation, APITesting, APITestCase, APIGateway,
)


def make_endpoint(name="quotes", url="https://example.com/quotes", method="GET"):
    return APIEndpoint(name=name, url=url, method=method, headers={},
                       params={"symbol": "AAPL"}, rate_limit=60)


def fake_response(status=200, data=None, endpoint="quotes"):
    return APIResponse(status_code=status, data=data or {"price": 100},
                       headers={}, timestamp=datetime.now(),
                       endpoint=endpoint, response_time=0.01)


class TestAPIDocumentation(unittest.TestCase):
    def setUp(self):
        self.mgr = APIManager()
        self.mgr.register_endpoint("quotes", make_endpoint())

    def test_markdown_lists_endpoint(self):
        md = APIDocumentation(self.mgr).generate_markdown()
        self.assertIn("`quotes`", md)
        self.assertIn("https://example.com/quotes", md)
        self.assertIn("GET", md)

    def test_markdown_empty(self):
        md = APIDocumentation(APIManager()).generate_markdown()
        self.assertIn("No endpoints registered", md)

    def test_openapi_structure(self):
        spec = APIDocumentation(self.mgr).generate_openapi()
        self.assertEqual(spec["openapi"], "3.0.0")
        self.assertIn("https://example.com/quotes", spec["paths"])
        self.assertIn("get", spec["paths"]["https://example.com/quotes"])

    def test_export_markdown(self):
        import tempfile, os
        f = tempfile.NamedTemporaryFile(suffix=".md", delete=False)
        f.close()
        try:
            self.assertTrue(APIDocumentation(self.mgr).export(f.name, "markdown"))
            with open(f.name) as fh:
                self.assertIn("quotes", fh.read())
        finally:
            os.unlink(f.name)


class TestAPITesting(unittest.TestCase):
    def setUp(self):
        self.mgr = APIManager()
        self.mgr.register_endpoint("quotes", make_endpoint())
        self.tester = APITesting(self.mgr)

    def test_passing_test(self):
        self.tester.register_test(APITestCase("ok", "quotes", expected_status=200))
        with patch.object(self.mgr, "make_request", return_value=fake_response(200)):
            result = self.tester.run_test("ok")
        self.assertTrue(result.passed)

    def test_status_mismatch_fails(self):
        self.tester.register_test(APITestCase("bad", "quotes", expected_status=200))
        with patch.object(self.mgr, "make_request", return_value=fake_response(500)):
            result = self.tester.run_test("bad")
        self.assertFalse(result.passed)
        self.assertIn("expected status", result.message)

    def test_validator(self):
        self.tester.register_test(APITestCase(
            "validated", "quotes",
            validator=lambda r: r.data.get("price", 0) > 50,
        ))
        with patch.object(self.mgr, "make_request",
                          return_value=fake_response(200, {"price": 100})):
            self.assertTrue(self.tester.run_test("validated").passed)
        with patch.object(self.mgr, "make_request",
                          return_value=fake_response(200, {"price": 10})):
            self.assertFalse(self.tester.run_test("validated").passed)

    def test_unknown_endpoint(self):
        self.tester.register_test(APITestCase("x", "nope"))
        self.assertFalse(self.tester.run_test("x").passed)

    def test_report(self):
        self.tester.register_test(APITestCase("ok", "quotes"))
        with patch.object(self.mgr, "make_request", return_value=fake_response(200)):
            report = self.tester.generate_report()
        self.assertIn("API TEST REPORT", report)
        self.assertIn("PASS", report)


class TestAPIGateway(unittest.TestCase):
    def setUp(self):
        self.mgr = APIManager()
        self.mgr.register_endpoint("quotes", make_endpoint())
        self.gw = APIGateway(self.mgr)

    def test_route_passes_through(self):
        with patch.object(self.mgr, "make_request", return_value=fake_response(200)) as mr:
            resp = self.gw.route("quotes", {"symbol": "MSFT"})
        self.assertEqual(resp.status_code, 200)
        mr.assert_called_once()

    def test_request_middleware_modifies_params(self):
        captured = {}

        def inject_token(name, params):
            params["token"] = "secret"
            return params

        def capture(name, params, **kw):
            captured.update(params)
            return fake_response(200)

        self.gw.add_middleware(inject_token)
        with patch.object(self.mgr, "make_request", side_effect=capture):
            self.gw.route("quotes", {"symbol": "AAPL"})
        self.assertEqual(captured.get("token"), "secret")

    def test_middleware_rejection_returns_none(self):
        def reject(name, params):
            raise PermissionError("blocked")

        self.gw.add_middleware(reject)
        with patch.object(self.mgr, "make_request", return_value=fake_response(200)) as mr:
            resp = self.gw.route("quotes")
        self.assertIsNone(resp)
        mr.assert_not_called()

    def test_response_middleware_transforms(self):
        def tag(resp):
            resp.data["tagged"] = True
            return resp

        self.gw.add_response_middleware(tag)
        with patch.object(self.mgr, "make_request", return_value=fake_response(200)):
            resp = self.gw.route("quotes")
        self.assertTrue(resp.data["tagged"])

    def test_rate_limit_override(self):
        self.gw.add_rate_limit("quotes", 10)
        self.assertEqual(self.mgr.endpoints["quotes"].rate_limit, 10)


if __name__ == "__main__":
    unittest.main()
