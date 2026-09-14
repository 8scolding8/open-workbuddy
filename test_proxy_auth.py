"""Regression tests for the optional local Python proxy key."""

import httpx
import unittest
from unittest.mock import patch

import proxy_server


class ProxyAuthTests(unittest.TestCase):
    @staticmethod
    def request(authorization: str | None = None) -> httpx.Request:
        headers = {}
        if authorization is not None:
            headers["authorization"] = authorization
        return httpx.Request("GET", "http://127.0.0.1/v1/models", headers=headers)

    def test_optional_key_accepts_only_exact_bearer_value(self):
        with patch.object(proxy_server.config, "PROXY_API_KEY", "local-secret"):
            self.assertFalse(proxy_server.proxy_auth_allowed(self.request()))
            self.assertFalse(proxy_server.proxy_auth_allowed(self.request("Bearer wrong")))
            self.assertTrue(proxy_server.proxy_auth_allowed(self.request("Bearer local-secret")))

    def test_local_key_is_not_forwarded_as_upstream_key(self):
        request = self.request("Bearer local-secret")
        with (
            patch.object(proxy_server.config, "PROXY_API_KEY", "local-secret"),
            patch.object(proxy_server.config, "DEFAULT_API_KEY", ""),
            patch.object(proxy_server.config, "load_saved_key", return_value=""),
        ):
            self.assertEqual(proxy_server.get_auth_token(request), "")

    def test_configured_upstream_key_takes_precedence(self):
        request = self.request("Bearer local-secret")
        with (
            patch.object(proxy_server.config, "PROXY_API_KEY", "local-secret"),
            patch.object(proxy_server.config, "DEFAULT_API_KEY", "upstream-secret"),
        ):
            self.assertEqual(proxy_server.get_auth_token(request), "Bearer upstream-secret")


class DashboardConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_config_reports_only_whether_local_key_is_configured(self):
        transport = httpx.ASGITransport(app=proxy_server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            with patch.object(proxy_server.config, "PROXY_API_KEY", "local-secret"):
                response = await client.get("/proxy/config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["proxy_api_key_configured"])
        self.assertNotIn("local-secret", response.text)


if __name__ == "__main__":
    unittest.main()
