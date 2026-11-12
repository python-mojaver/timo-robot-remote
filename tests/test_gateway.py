import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import COMMAND_SECONDS, FRAME_SECONDS, LEASE_SECONDS, Fault, Gateway, Server, new_config

PASSWORD = "unit-test-password-only"
INSTANCE = "test-agent-instance"
CAPS = {"sdk": True, "head": True, "navigation": True, "drive": True, "stop": True, "camera": True, "camera_active": True}
CONFIG = new_config(PASSWORD)


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now
    def advance(self, value): self.now += value


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.gateway = Gateway(CONFIG, self.clock)
        self.sid, self.session = self.gateway.login(PASSWORD, "127.0.0.1", False)
        self.gateway.poll(INSTANCE, CAPS, [], "", wait=0)
        self.proof = ""

    def acquire(self):
        response = self.gateway.acquire(self.sid)
        self.proof = response["control_token"]
        return response

    def transport_navigation(self):
        # Exercise transport/expiry here; project destination authorization has its own tests.
        with self.gateway.lock:return self.gateway.enqueue('nav_room', {})

    def command(self, kind, args):
        return self.gateway.command(self.sid, kind, args, self.proof)

    def test_offline_robot_cannot_be_acquired(self):
        self.clock.advance(6)
        with self.assertRaises(Fault) as caught: self.acquire()
        self.assertEqual(caught.exception.status, 409)

    def test_only_one_operator_can_control(self):
        other, _ = self.gateway.login(PASSWORD, "other", False)
        self.acquire()
        with self.assertRaises(Fault): self.gateway.acquire(other)
        with self.assertRaises(Fault): self.gateway.command(other, "head_test", {}, "")

    def test_second_tab_cannot_inherit_control_from_shared_cookie(self):
        self.acquire()
        with self.assertRaises(Fault): self.gateway.acquire(self.sid)
        with self.assertRaises(Fault): self.gateway.hold(self.sid, "")
        with self.assertRaises(Fault): self.gateway.command(self.sid, "head_test", {}, "")
        self.assertTrue(self.gateway.status(self.sid)["control_busy"])
        self.assertFalse(self.gateway.status(self.sid)["control_owned"])
        self.assertTrue(self.gateway.status(self.sid, self.proof)["control_owned"])

    def test_late_command_from_old_lease_cannot_start_new_movement(self):
        self.acquire()
        old_proof = self.proof
        self.command("stop", {})
        self.gateway.poll(INSTANCE, CAPS, [], "", wait=0)
        self.acquire()
        with self.assertRaises(Fault): self.gateway.command(self.sid, "drive", {"direction": "forward"}, old_proof)
        with self.assertRaises(Fault): self.gateway.hold(self.sid, old_proof)
        self.assertFalse(self.gateway.queue)

    def test_unknown_commands_are_not_forwarded(self):
        self.acquire()
        with self.assertRaises(Fault): self.command("raw_json", {"msg_id": "something"})
        self.assertFalse(self.gateway.queue)

    def test_navigation_requires_reported_stop_support(self):
        caps = dict(CAPS, navigation=False, stop=False, drive=False)
        self.gateway.poll(INSTANCE, caps, [], "", wait=0)
        self.acquire()
        with self.assertRaises(Fault): self.command('nav_room', {})
        with self.assertRaises(Fault): self.command("drive", {"direction": "forward"})
        self.assertTrue(self.command("head_test", {})["ok"])

    def test_stop_is_required_even_with_inconsistent_capabilities(self):
        self.gateway.poll(INSTANCE, dict(CAPS, stop=False), [], "", wait=0)
        self.acquire()
        with self.assertRaises(Fault): self.command('nav_room', {})
        with self.assertRaises(Fault): self.command("drive", {"direction": "forward"})

    def test_sdk_disconnect_revokes_active_control(self):
        self.acquire()
        response = self.gateway.poll(INSTANCE, dict(CAPS, sdk=False), [], "", wait=0)
        self.assertIsNone(self.gateway.owner)
        self.assertEqual(response["command"]["kind"], "stop")

    def test_lease_expiry_cancels_navigation_and_queues_stop(self):
        self.acquire()
        self.transport_navigation()
        self.clock.advance(LEASE_SECONDS + .01)
        with self.gateway.lock: self.gateway.tick()
        self.assertIsNone(self.gateway.owner)
        self.assertEqual([c["kind"] for c in self.gateway.queue], ["stop"])

    def test_expired_commands_never_replay(self):
        self.acquire()
        self.command("head_test", {})
        self.clock.advance(COMMAND_SECONDS + .01)
        response = self.gateway.poll(INSTANCE, CAPS, [], "", wait=0)
        self.assertIsNone(response["command"])
        self.assertEqual(self.gateway.results[-1]["status"], "expired")

    def test_stop_preempts_queued_movement(self):
        self.acquire()
        self.transport_navigation()
        self.command("drive", {"direction": "forward"})
        self.command("stop", {})
        command = self.gateway.poll(INSTANCE, CAPS, [], "", wait=0)["command"]
        self.assertEqual(command["kind"], "stop")
        self.assertFalse(self.gateway.queue)

    def test_drive_commands_are_coalesced(self):
        self.acquire()
        self.command("drive", {"direction": "forward"})
        self.command("drive", {"direction": "left"})
        self.assertEqual(len(self.gateway.queue), 1)
        self.assertEqual(self.gateway.queue[0]["args"]["direction"], "left")

    def test_restarting_agent_drops_old_control_and_commands(self):
        self.acquire()
        self.command("head_test", {})
        response = self.gateway.poll("replacement-instance", CAPS, [], "", wait=0)
        self.assertIsNone(response["command"])
        self.assertIsNone(self.gateway.owner)

    def test_ack_is_transport_submission_not_physical_arrival(self):
        self.acquire()
        queued = self.transport_navigation()
        self.gateway.poll(INSTANCE, CAPS, [], "", wait=0)
        self.gateway.acknowledge(INSTANCE, queued["id"], "submitted", "SDK accepted")
        self.assertEqual(self.gateway.results[-1]["status"], "submitted")
        with self.assertRaises(Fault): self.gateway.acknowledge(INSTANCE, queued["id"], "arrived", "fake arrival")

    def test_logout_revokes_control(self):
        self.acquire()
        self.gateway.logout(self.sid)
        self.assertIsNone(self.gateway.owner)
        self.assertEqual(self.gateway.queue[0]["kind"], "stop")

    def test_frames_expire_and_are_bound_to_agent_instance(self):
        self.acquire()
        frame = b"\xff\xd8example-jpeg-bytes\xff\xd9"
        self.gateway.set_frame(INSTANCE, frame)
        self.assertTrue(self.gateway.status(self.sid)["camera_live"])
        self.clock.advance(FRAME_SECONDS + .01)
        self.assertFalse(self.gateway.status(self.sid)["camera_live"])
        with self.assertRaises(Fault): self.gateway.set_frame("different-instance", frame)
        with self.assertRaises(Fault): self.gateway.set_frame(INSTANCE, b"not-jpeg")


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(CONFIG)
        self.gateway = Gateway(self.config)
        self.server = Server(("127.0.0.1", 0), self.gateway)
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.config["allowed_origins"] = [self.base]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, path, body=None, headers=None):
        args = dict(headers or {})
        if body is not None:
            args.setdefault("Content-Type", "application/json")
            args.setdefault("Origin", self.base)
            raw = json.dumps(body).encode()
        else: raw = None
        request = urllib.request.Request(self.base + path, data=raw, headers=args)
        try: response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error: response = error
        with response: return response.status, response.headers, response.read()

    def login(self):
        status, headers, raw = self.request("/api/login", {"password": PASSWORD})
        self.assertEqual(status, 200)
        return {"Cookie": headers["Set-Cookie"].split(";")[0], "X-CSRF-Token": json.loads(raw)["csrf"]}

    def test_auth_and_csrf_boundaries(self):
        self.assertEqual(self.request("/api/status")[0], 401)
        self.assertEqual(self.request("/api/agent/poll", {"instance": INSTANCE})[0], 401)
        self.assertEqual(self.request("/api/login", {"password": PASSWORD}, {"Origin": "https://evil.example"})[0], 403)
        headers = self.login()
        self.assertEqual(self.request("/api/status", headers=headers)[0], 200)
        no_csrf = {"Cookie": headers["Cookie"]}
        self.assertEqual(self.request("/api/command", {"kind": "stop"}, no_csrf)[0], 403)
        self.assertEqual(self.request("/api/command", {"kind": "stop"}, dict(headers, Origin="https://evil.example"))[0], 403)
        self.assertEqual(self.request("/api/command", {"kind": "stop"}, headers)[0], 200)

    def test_whole_command_delivery_and_ack_path(self):
        operator = self.login()
        agent = {"Authorization": "Bearer " + self.config["agent_token"]}
        status, _, _ = self.request("/api/agent/poll", {"instance": INSTANCE, "capabilities": CAPS}, agent)
        self.assertEqual(status, 200)
        status, _, raw = self.request("/api/control/acquire", {}, operator)
        self.assertEqual(status, 200)
        operator["X-Control-Token"] = json.loads(raw)["control_token"]
        status, _, raw = self.request("/api/command", {"kind": "head_test"}, operator)
        queued = json.loads(raw)
        self.assertEqual(status, 200)
        status, _, raw = self.request("/api/agent/poll", {"instance": INSTANCE, "capabilities": CAPS}, agent)
        command = json.loads(raw)["command"]
        self.assertEqual(command["id"], queued["id"])
        self.assertEqual(command["kind"], "head_test")
        self.assertGreater(command["valid_for_ms"], 0)
        self.assertEqual(self.request("/api/agent/result", {"instance": INSTANCE, "id": command["id"], "status": "submitted", "detail": "SDK submitted"}, agent)[0], 200)
        status, _, raw = self.request("/api/status", headers=operator)
        self.assertEqual(json.loads(raw)["results"][-1]["status"], "submitted")

    def test_private_files_and_frames_are_not_public(self):
        for path in ("/config.json", "/robot/MainActivity.kt", "/../../server.py", "/api/frame"):
            self.assertIn(self.request(path)[0], (401, 404))
        status, headers, _ = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_login_rate_limit(self):
        for _ in range(5): self.assertEqual(self.request("/api/login", {"password": "wrong"})[0], 401)
        self.assertEqual(self.request("/api/login", {"password": PASSWORD})[0], 429)


if __name__ == "__main__":
    unittest.main(verbosity=2)
