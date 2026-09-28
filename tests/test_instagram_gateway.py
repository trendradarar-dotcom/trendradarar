import importlib.util
import os
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATEWAY_APP = ROOT / "instagram_oauth_gateway" / "app.py"


class GatewayBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["INSTAGRAM_OAUTH_GATEWAY_SECRET"] = "test-gateway-secret"
        os.environ["INSTAGRAM_OAUTH_PUBLIC_ORIGIN"] = "https://trendradar.com.co"
        os.environ["INSTAGRAM_OAUTH_UPSTREAM_URL"] = "https://example.invalid"
        spec = importlib.util.spec_from_file_location("trendradar_instagram_gateway_test", GATEWAY_APP)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.client = cls.module.app.test_client()

    def test_health_is_configured(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["configured"])

    def test_gateway_oauth_is_hard_disabled_fail_closed(self):
        for method, path in (
            ("get", "/oauth/browser/start"),
            ("get", "/oauth/browser/callback"),
            ("get", "/oauth/start"),
            ("post", "/oauth/callback"),
        ):
            response = getattr(self.client, method)(path)
            self.assertEqual(response.status_code, 423)
            self.assertEqual(
                response.get_json()["error"],
                "OAUTH_BROWSER_DISABLED_FAIL_CLOSED",
            )

    def test_security_headers_are_fail_closed(self):
        response = self.client.get("/health")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertIn("default-src 'none'", response.headers.get("Content-Security-Policy", ""))


if __name__ == "__main__":
    unittest.main()
