import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import webui

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
            # muting mirrors `claudio off` (stops drone + players) — keep the test
            # from touching real audio processes on the dev machine
            with mock.patch.object(webui, "stop_drone_now") as stop_drone, \
                 mock.patch.object(webui.audio, "stop_all") as stop_all:
                status, _, body = self.request("POST", "/api/mute", '{"muted":true}', {
                    "Cookie": cookie, "Content-Type": "application/json",
                    "Origin": f"http://127.0.0.1:{self.port}",
                })
            self.assertEqual(status, 200, body)
            self.assertTrue(json.loads(body)["muted"])
            self.assertTrue(json.loads(webui.CONFIG.read_text())["muted"])
            stop_drone.assert_called_once()
            stop_all.assert_called_once()

    def post_json(self, path, raw):
        cookie = self.auth_cookie()
        return self.request("POST", path, raw, {
            "Cookie": cookie, "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
        })

    def test_state_with_corrupt_config_and_sessions_returns_json(self):
        cookie = self.auth_cookie()
        cases = [
            ('{"master_gain": "loud", "drone_gain": "x", "quant": {"bpm": "fast"}}',
             '{"active": {"a": "not-a-dict", "b": {"last_seen": "garbage", "cwd": 7}}}'),
            ('[1, 2, 3]', '{"active": ["nope"]}'),
            ('{not json', '"just a string"'),
        ]
        for cfg_text, sess_text in cases:
            with self.subTest(cfg=cfg_text), tempfile.TemporaryDirectory() as td, \
                 mock.patch.object(webui, "CONFIG", Path(td) / "config.json"), \
                 mock.patch.object(webui, "STATE", Path(td)):
                webui.CONFIG.write_text(cfg_text)
                (Path(td) / "sessions.json").write_text(sess_text)
                status, headers, body = self.request("GET", "/api/state", headers={"Cookie": cookie})
                self.assertIn(status, (200, 500), body)
                self.assertTrue(headers["Content-Type"].startswith("application/json"))
                data = json.loads(body)          # a real JSON reply, not a dropped socket
                if status == 200:
                    self.assertIsInstance(data["master_gain"], float)

    def test_non_numeric_and_nan_gain_are_rejected(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(webui, "CONFIG", Path(td) / "config.json"):
            for raw in ('{"gain": "abc"}', '{"gain": NaN}', '{"gain": Infinity}',
                        '{"gain": null}', '{"gain": [1]}'):
                with self.subTest(body=raw):
                    status, _, body = self.post_json("/api/master", raw)
                    self.assertEqual(status, 400, body)
                    self.assertIn("error", json.loads(body))
            self.assertFalse(webui.CONFIG.exists())      # nothing was written
            status, _, body = self.post_json("/api/master", '{"gain": "0.25"}')
            self.assertEqual(status, 200, body)
            self.assertEqual(json.loads(body)["master_gain"], 0.25)

    def test_recording_range_requests(self):
        cookie = self.auth_cookie()
        data = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(webui, "OUT_DIR", Path(td)):
            (Path(td) / "take one.wav").write_bytes(data)
            url = "/recordings/take%20one.wav"
            status, headers, body = self.request("GET", url, headers={"Cookie": cookie, "Range": "bytes=10-19"})
            self.assertEqual(status, 206)
            self.assertEqual(body, data[10:20])
            self.assertEqual(headers["Content-Range"], f"bytes 10-19/{len(data)}")
            self.assertEqual(headers["Accept-Ranges"], "bytes")
            status, _, body = self.request("GET", url, headers={"Cookie": cookie, "Range": "bytes=-4"})
            self.assertEqual((status, body), (206, data[-4:]))
            status, _, body = self.request("GET", url, headers={"Cookie": cookie, "Range": "bytes=1000-"})
            self.assertEqual((status, body), (206, data[1000:]))
            status, headers, _ = self.request("GET", url, headers={"Cookie": cookie, "Range": "bytes=5000-6000"})
            self.assertEqual(status, 416)
            self.assertEqual(headers["Content-Range"], f"bytes */{len(data)}")
            status, _, body = self.request("GET", url, headers={"Cookie": cookie})
            self.assertEqual((status, body), (200, data))


if __name__ == "__main__":
    unittest.main()
