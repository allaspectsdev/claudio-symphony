import http.client
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import webui
import preset_store

HERE = Path(__file__).resolve().parent.parent


class SafePathTests(unittest.TestCase):
    def test_safe_child_rejects_parent_traversal(self):
        self.assertIsNone(webui.safe_child(HERE / "web", "../event.py"))
        self.assertIsNone(webui.safe_child(HERE / "web", "%2e%2e/event.py"))

    def test_preset_names_cannot_traverse(self):
        self.assertIsNone(webui.preset_path("../../tmp"))
        self.assertIsNone(webui.load_preset("../../tmp"))

    def test_persisted_html_fields_are_escaped(self):
        source = (HERE / "web" / "app.js").read_text()
        self.assertIn("esc(s.cwd || s.id)", source)
        self.assertIn("esc(s.base)", source)
        self.assertIn("esc(r.pattern)", source)
        self.assertIn("esc(p.description || '')", source)


class WebHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = webui.ThreadingHTTPServer(("127.0.0.1", 0), webui.Handler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        conn.close()
        return result

    def auth_cookie(self):
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0]

    def json_headers(self, cookie):
        return {
            "Cookie": cookie, "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
        }

    def test_root_sets_strict_cookie_and_security_headers(self):
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertNotIn("script-src 'self' 'unsafe-inline'", headers["Content-Security-Policy"])

    def test_static_traversal_is_rejected(self):
        for path in ("/static/../event.py", "/static/%2e%2e/event.py"):
            status, _, body = self.request("GET", path)
            self.assertEqual(status, 404, body)

    def test_valid_static_asset_is_served(self):
        status, _, body = self.request("GET", "/static/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"Claudio Symphony", body)

    def test_api_requires_authentication(self):
        status, _, _ = self.request("GET", "/api/state")
        self.assertEqual(status, 403)

    def test_host_header_must_be_loopback(self):
        status, _, _ = self.request("GET", "/", headers={"Host": "attacker.example"})
        self.assertEqual(status, 421)

    def test_plain_text_post_is_rejected(self):
        cookie = self.auth_cookie()
        status, _, _ = self.request("POST", "/api/mute", '{"muted":true}', {
            "Cookie": cookie, "Content-Type": "text/plain",
            "Origin": f"http://127.0.0.1:{self.port}",
        })
        self.assertEqual(status, 415)

    def test_cross_origin_post_is_rejected(self):
        cookie = self.auth_cookie()
        status, _, _ = self.request("POST", "/api/mute", '{"muted":true}', {
            "Cookie": cookie, "Content-Type": "application/json",
            "Origin": "https://attacker.example",
        })
        self.assertEqual(status, 403)

    def test_oversized_json_body_is_rejected_before_reading(self):
        cookie = self.auth_cookie()
        status, _, _ = self.request("POST", "/api/mute", b"", {
            "Cookie": cookie, "Content-Type": "application/json",
            "Content-Length": str(webui.MAX_JSON_BODY + 1),
            "Origin": f"http://127.0.0.1:{self.port}",
        })
        self.assertEqual(status, 413)

    def test_authenticated_same_origin_post_succeeds(self):
        cookie = self.auth_cookie()
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(webui, "CONFIG", Path(td) / "config.json"):
            status, _, body = self.request("POST", "/api/mute", '{"muted":true}', {
                "Cookie": cookie, "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
            })
            self.assertEqual(status, 200, body)
            self.assertTrue(json.loads(body)["muted"])
            self.assertTrue(json.loads(webui.CONFIG.read_text())["muted"])

    def test_preset_import_export_and_history_are_authenticated(self):
        cookie = self.auth_cookie()
        name = "web-import-test"
        try:
            preset = dict(preset_store.load("meadow"))
            preset["name"] = name
            preset["description"] = "web import one"
            body = json.dumps({"name": name, "preset": preset})
            status, _, data = self.request(
                "POST", "/api/preset/import", body, self.json_headers(cookie)
            )
            self.assertEqual(status, 200, data)
            self.assertTrue(json.loads(data)["ok"])

            preset["description"] = "web import two"
            status, _, _ = self.request(
                "POST", "/api/preset/import",
                json.dumps({"name": name, "preset": preset}), self.json_headers(cookie),
            )
            self.assertEqual(status, 200)

            status, _, data = self.request(
                "GET", f"/api/preset/export?name={name}", headers={"Cookie": cookie}
            )
            exported = json.loads(data)
            self.assertEqual(status, 200)
            self.assertEqual(exported["preset"]["description"], "web import two")

            status, _, data = self.request(
                "GET", f"/api/preset/history?name={name}", headers={"Cookie": cookie}
            )
            self.assertEqual(status, 200)
            self.assertGreaterEqual(len(json.loads(data)["history"]), 1)
        finally:
            shutil.rmtree(preset_store.user_dir(name), ignore_errors=True)
            shutil.rmtree(preset_store._history_dir(name), ignore_errors=True)

    def test_import_rejects_future_schema_and_cache_limit_is_bounded(self):
        cookie = self.auth_cookie()
        preset = dict(preset_store.load("meadow"))
        preset["schema_version"] = 999
        status, _, _ = self.request(
            "POST", "/api/preset/import",
            json.dumps({"name": "future-test", "preset": preset}), self.json_headers(cookie),
        )
        self.assertEqual(status, 400)
        status, _, data = self.request("GET", "/api/cache", headers={"Cookie": cookie})
        self.assertEqual(status, 200, data)
        self.assertIn("total_bytes", json.loads(data))
        status, _, _ = self.request(
            "POST", "/api/cache/limit", '{"mb":1}', self.json_headers(cookie)
        )
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
