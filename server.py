"""درگاه کنترل یک ربات در شبکهٔ خصوصی، با کتابخانهٔ استاندارد پایتون."""
from __future__ import annotations

from talk_channel import TalkChannel
from project_control import ProjectControl
from face_protocol import robot_mode

import argparse
import hashlib
import hmac
import json
import logging
import mimetypes
import secrets
import socket
import threading
import time
from collections import deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("timo")
# مهلت کوتاه برای کنترل، فرمان و تازگی رسانه.
LEASE_SECONDS = 1.8
AGENT_SECONDS = 5.0
COMMAND_SECONDS = 1.2
FRAME_SECONDS = 2.0
AUDIO_SECONDS = 0.8
SESSION_SECONDS = 8 * 3600
MAX_BODY = 524288


class Fault(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 350000).hex()


def new_config(password: str, port: int = 8765) -> dict:
    salt = secrets.token_hex(16)
    return {
        "password_salt": salt,
        "password_hash": password_hash(password, salt),
        "agent_token": secrets.token_urlsafe(32),
        "allowed_origins": [f"http://127.0.0.1:{port}", f"http://localhost:{port}"],
        "port": port,
    }


class Gateway:
    def __init__(self, config: dict, clock=time.monotonic):
        self.maintenance=False
        self.config, self.clock = config, clock
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.sessions: dict[str, dict] = {}
        self.failures: dict[str, deque] = {}
        self.queue: deque[dict] = deque()
        self.results: deque[dict] = deque(maxlen=25)
        self.inflight: dict[str, dict] = {}
        self.instance = ""
        self.agent_seen: float | None = None
        self.caps: dict = {}
        self.diagnostics: list[str] = []
        self.camera_error = ""
        self.owner: str | None = None
        self.control_token = ""
        self.lease_deadline = 0.0
        self.frame: bytes | None = None
        self.frame_seen = 0.0
        self.talk=TalkChannel(self.clock)
        self.audio = deque(maxlen=8)
        self.audio_sequence = 0
        self.drive_epoch = 0
        self.sequence = 0
        self.head_next_at = 0.0
        self.arm_range = {}
        self.drive_block = ""
        self.head_notice = "نوع کنترل سر هنوز گزارش نشده است."
        self.shutdown_event = threading.Event()
        self.project = ProjectControl(self, config, Fault)

    def online(self) -> bool:
        return self.agent_seen is not None and self.clock() - self.agent_seen < AGENT_SECONDS

    def login(self, password: str, peer: str, secure: bool) -> tuple[str, dict]:
        with self.lock:
            attempts = self.failures.setdefault(peer, deque())
            while attempts and self.clock() - attempts[0] > 60:
                attempts.popleft()
            if len(attempts) >= 5:
                raise Fault(429, "ورود موقتاً محدود شده؛ یک دقیقه بعد دوباره امتحان کنید.")
            attempts.append(self.clock())
        candidate = password_hash(password, self.config["password_salt"])
        if not hmac.compare_digest(candidate, self.config["password_hash"]):
            raise Fault(401, "رمز ورود درست نیست.")
        with self.lock:
            self.failures.pop(peer, None)
            # نشست منقضی همراه با مجوز کنترلش پاک می‌شود.
            self.tick()
            sid = secrets.token_urlsafe(32)
            session = {"csrf": secrets.token_urlsafe(24), "deadline": self.clock() + SESSION_SECONDS, "secure": secure}
            self.sessions[sid] = session
            return sid, session

    def local_operator(self):
        """In-process desktop access; deliberately has no HTTP endpoint."""
        with self.lock:
            self.tick()
            sid=secrets.token_urlsafe(32)
            session={"csrf":secrets.token_urlsafe(24),"deadline":self.clock()+SESSION_SECONDS,"secure":False}
            self.sessions[sid]=session
            return sid,dict(session)

    def session(self, sid: str) -> dict:
        with self.lock:
            self.tick()
            session = self.sessions.get(sid)
            if not session:
                raise Fault(401, "ابتدا وارد حساب شوید.")
            return dict(session)

    def logout(self, sid: str):
        with self.lock:
            if self.owner == sid:
                self.stop("logout")
            self.sessions.pop(sid, None)

    def tick(self):
        """انقضای مالکیت، فرمان و رسانه را زیر قفل مشترک بررسی می‌کند."""
        now = self.clock()
        self.talk.tick()
        for sid, session in list(self.sessions.items()):
            if session["deadline"] <= now:
                if self.owner == sid:
                    self.stop("session_expired")
                self.sessions.pop(sid, None)
        if self.owner and (now >= self.lease_deadline or not self.online() or not self.caps.get("sdk")):
            self.stop("connection_or_lease_expired")
        while self.queue and self.queue[0]["deadline"] <= now:
            dropped = self.queue.popleft()
            self.record(dropped["id"], dropped["kind"], "expired", "فرمان منقضی شد و اجرا نشد.")
        for cid, command in list(self.inflight.items()):
            if now - command["delivered_at"] > 5:
                self.record(cid, command["kind"], "unknown", "تأیید اجرای فرمان دریافت نشد.")
                self.inflight.pop(cid, None)
        if self.frame and now - self.frame_seen > FRAME_SECONDS:
            self.frame = None
        while self.audio and now-self.audio[0][2] >= AUDIO_SECONDS:
            self.audio.popleft()

    def record(self, cid: str, kind: str, status: str, detail: str):
        self.project.receipt(cid, status)
        self.results.append({"id": cid, "kind": kind, "status": status, "detail": detail, "time": time.time()})

    def enqueue(self, kind: str, args: dict | None = None) -> dict:
        self.sequence += 1
        item = {"id": secrets.token_hex(12), "seq": self.sequence, "kind": kind,
                "args": args or {}, "deadline": self.clock() + COMMAND_SECONDS}
        self.queue.append(item)
        self.condition.notify_all()
        return item

    def stop(self, reason: str = "operator") -> dict:
        # پیش از صف‌کردن توقف، تمام حرکت‌های در انتظار و مجوز قبلی را باطل می‌کنیم.
        self.owner = None
        self.talk.stop()
        self.project.stopped()
        self.frame = None
        self.audio.clear()
        self.control_token = ""
        self.lease_deadline = 0
        for command in self.queue:
            self.record(command["id"], command["kind"], "cancelled", "فرمان با درخواست توقف لغو شد.")
        self.queue.clear()
        return self.enqueue("stop", {"reason": reason})

    def acquire(self, sid: str, control_token: str = "") -> dict:
        with self.lock:
            self.session(sid)
            self.tick()
            if self.maintenance:raise Fault(409,'تنظیم اتصال ربات در حال انجام است؛ کمی صبر کن.')
            if not self.online():
                raise Fault(409, "ربات متصل نیست.")
            if not self.caps.get("sdk"):
                raise Fault(409, "سرویس SDK ربات متصل نیست.")
            if self.owner and (self.owner != sid or not hmac.compare_digest(control_token, self.control_token)):
                raise Fault(409, "کنترل در اختیار دستگاه دیگری است.")
            self.talk.stop()
            self.owner, self.lease_deadline = sid, self.clock() + LEASE_SECONDS
            self.control_token = secrets.token_urlsafe(24)
            self.drive_epoch = 0
            return {"ok": True, "control_token": self.control_token, "drive_epoch": self.drive_epoch}

    def hold(self, sid: str, control_token: str) -> dict:
        with self.lock:
            self.session(sid)
            self.tick()
            if self.owner != sid or not hmac.compare_digest(control_token, self.control_token):
                raise Fault(409, "کنترل غیرفعال شده؛ دوباره آن را فعال کنید.")
            if not self.online() or not self.caps.get("sdk"):
                self.stop("robot_disconnected")
                raise Fault(409, "ارتباط ربات قطع شده است.")
            self.lease_deadline = self.clock() + LEASE_SECONDS
            return {"ok": True}

    def command(self, sid: str, kind: str, args: dict, control_token: str) -> dict:
        with self.lock:
            self.session(sid)
            self.tick()
            if kind in ("nav_room", "speak"):
                raise Fault(400, "از بخش اتاق‌ها یا پخش متن استفاده کن.")
            if kind == "stop":
                cmd = self.stop()
            else:
                if self.owner != sid or not hmac.compare_digest(control_token, self.control_token) or not self.online() or not self.caps.get("sdk"):
                    raise Fault(409, "ابتدا کنترل را فعال کنید و اتصال ربات را بررسی کنید.")
                if kind == "arm_step":
                    raise Fault(409, "کنترل بازو از ریموت غیرفعال است.")
                if kind in ("head_test", "head_step", "head_reset") and self.caps.get("head_arm_rest"):
                    raise Fault(409, "فرمان مشترک سر و بازو غیرفعال است.")
                if kind in ("head_test", "head_step", "head_reset") and not self.caps.get("head"):
                    raise Fault(409, "کنترل سر در دسترس نیست.")
                if kind == "nav_room" and not (self.caps.get("navigation") and self.caps.get("stop")):
                    raise Fault(409, "حرکت به مقصد پس از تأیید فرمان توقف فعال می‌شود.")
                if kind == "brake":
                    self.drive_epoch += 1
                    self.queue = deque(c for c in self.queue if c["kind"] != "drive")
                    cmd = self.enqueue("brake")
                    self.queue.remove(cmd); self.queue.appendleft(cmd)
                    return {"ok": True, "id": cmd["id"], "status":"queued", "drive_epoch":self.drive_epoch}
                if kind == "drive":
                    self.project.manual()
                    if type(args.get("drive_epoch",0)) is not int or args.get("drive_epoch",0) != self.drive_epoch:
                        raise Fault(409, "این فرمان جهت مربوط به قبل از توقف است.")
                    if not (self.caps.get("drive") and self.caps.get("stop")):
                        raise Fault(409, "فرمان‌های حرکت دستی و توقف هنوز تنظیم نشده‌اند.")
                    if args.get("direction") not in ("forward", "backward", "left", "right"):
                        raise Fault(400, "جهت حرکت معتبر نیست.")
                    args = {"direction": args["direction"]}
                elif kind == "face":
                    if not self.caps.get('face'): raise Fault(409, 'اپ ربات را با «اتصال ربات» به نسخهٔ چهره ارتقا بده.')
                    mode=robot_mode(args.get('expression'))
                    if mode is None: raise Fault(400, 'حالت چهره معتبر نیست.')
                    args = {'expression': mode}
                elif kind == "head_step":
                    if args.get("direction") not in ("left", "right", "up", "down"):
                        raise Fault(400, "جهت سر معتبر نیست.")
                    args = {"direction": args["direction"]}
                elif kind == "arm_range":
                    action = args.get("action")
                    if not self.caps.get("arm_range") or (action != "finish" and not self.caps.get("arm_range_ready")):
                        raise Fault(409, "اپ ربات یا وضعیت توقف پایه برای آزمون بازو آماده نیست.")
                    if args.get("confirmed") is not True:
                        raise Fault(400, "ابتدا وضعیت بازوها را تأیید کن.")
                    if action == "finish" and self.arm_range.get("can_finish"):
                        args = {"action": action, "confirmed": True}
                    elif action == "begin" and self.arm_range.get("can_begin"):
                        args = {"action": action, "confirmed": True}
                    elif action in ("move", "rest") and self.arm_range.get("armed") and args.get("side") in ("left", "right"):
                        goal = args.get("goal") if action == "move" else 0
                        if action == "move" and (type(goal) is not int or not 2 <= goal <= 100):
                            raise Fault(400, "هدف بازو باید عدد صحیح بین ۲ و ۱۰۰ باشد.")
                        args = {"action": action, "side": args["side"], "goal": goal, "confirmed": True}
                    else:
                        raise Fault(409, "ابتدا توقف و آماده‌سازی بازوها را انجام بده.")
                    if any(c["kind"] in ("arm_range", "drive", "nav_room", "stop", "brake")
                           for c in (*self.queue, *self.inflight.values())):
                        raise Fault(409, "منتظر نتیجهٔ فرمان قبلی بمان.")
                elif kind in ("head_test", "head_reset", "nav_room", "camera_on", "camera_off", "mic_on", "mic_off"):
                    args = {}
                else:
                    raise Fault(400, "فرمان معتبر نیست.")
                if kind == "mic_on" and not self.caps.get("microphone"):
                    raise Fault(409, "مجوز میکروفون روی ربات داده نشده است.")
                if kind == "camera_on" and not self.caps.get("camera"):
                    raise Fault(409, "دوربین در Android قابل دسترسی نیست یا اجازه دوربین داده نشده.")
                if kind == 'face':
                    self.queue = deque(c for c in self.queue if c['kind'] != 'face')
                if len(self.queue) >= 8:
                    raise Fault(429, "صبر کنید تا فرمان قبلی دریافت شود.")
                if kind in ("head_step", "head_reset"):
                    if self.clock() < self.head_next_at or any(c['kind'] in ('head_step','head_reset') for c in self.queue):
                        raise Fault(429, "برای فرمان بعدی سر، یک لحظه صبر کن.")
                    self.head_next_at = self.clock() + 0.9
                if kind == "drive":
                    # فقط آخرین فرمان جهتِ ارسال‌نشده را نگه می‌داریم تا حرکت‌های قدیمی جمع نشوند.
                    self.queue = deque(c for c in self.queue if c["kind"] != "drive")
                cmd = self.enqueue(kind, args)
            return {"ok": True, "id": cmd["id"], "status": "queued"}

    def poll(self, instance: str, caps: dict, diagnostics: list, camera_error: str, wait: float = 0.65,
             media_notice: str = "", mic_error: str = "", head_notice: str = "", navigation=None, speech=None, arm_range=None,
             drive_block="") -> dict:
        if not isinstance(instance, str) or not 8 <= len(instance) <= 80:
            raise Fault(400, "Invalid agent instance")
        known_caps = {key: caps.get(key) is True for key in ("sdk", "face", "speech", "speaker", "head", "head_arm_rest", "navigation", "drive", "stop", "arm_wave_stop", "arm_range", "arm_range_ready", "camera", "camera_active", "microphone", "mic_active", "moving")}
        if known_caps["head_arm_rest"]:
            known_caps["head"] = False
        with self.condition:
            if self.instance != instance:
                self.talk.stop()
                self.queue.clear()
                self.inflight.clear()
                self.owner, self.lease_deadline = None, 0
                self.control_token = ""
                self.frame = None
                self.audio.clear()
                self.instance = instance
            self.agent_seen, self.caps = self.clock(), known_caps
            if not known_caps.get('camera_active'):self.frame=None
            if not known_caps.get('mic_active'):self.audio.clear()
            self.diagnostics = [str(x)[:200] for x in diagnostics[:100]]
            self.camera_error = camera_error[:240]
            self.media_notice = media_notice[:300]
            self.mic_error = mic_error[:240]
            self.head_notice = head_notice[:300]
            self.drive_block = drive_block if drive_block in ("navigation", "arms") else ""
            self.arm_range = {}
            if known_caps["arm_range"] and isinstance(arm_range, dict):
                if all(type(arm_range.get(side)) is int and 0 <= arm_range[side] <= 100 for side in ("left", "right")):
                    self.arm_range = {"left": arm_range["left"], "right": arm_range["right"],
                                      "armed": arm_range.get("armed") is True, "can_begin": arm_range.get("can_begin") is True,
                                      "can_finish": arm_range.get("can_finish") is True}
            self.project.update(instance, navigation, speech)
            if not self.drive_block and known_caps["sdk"] and not known_caps["drive"]:
                if isinstance(navigation, dict) and navigation.get("busy") is True:
                    self.drive_block = "navigation"
                elif self.arm_range.get("armed") or self.arm_range.get("left") or self.arm_range.get("right"):
                    self.drive_block = "arms"
            self.tick()
            server_wait_ms = 0
            if not self.queue and wait > 0:
                began = time.monotonic()
                # در زمان کنترل فعال، زودتر به ربات پاسخ می‌دهیم تا مهلت محلی به‌موقع تمدید شود.
                self.condition.wait(min(wait, 0.15 if self.owner else 0.65))
                server_wait_ms = min(1000, max(0, int((time.monotonic()-began)*1000)))
            # پاسخِ اپ قبلی نباید فرمانی را از صف اپ تازه بردارد.
            if self.instance != instance:
                raise Fault(409, "Agent replaced")
            self.agent_seen = self.clock()
            self.tick()
            command = self.queue.popleft() if self.queue else None
            wire = None
            if command:
                command["delivered_at"] = self.clock()
                self.inflight[command["id"]] = command
                wire = {key: command[key] for key in ("id", "seq", "kind", "args")}
                wire["valid_for_ms"] = max(0, int((command["deadline"] - self.clock()) * 1000))
            return {"command": wire, "lease_remaining_ms": max(0, int((self.lease_deadline - self.clock()) * 1000)) if self.owner else 0,
                    "server_wait_ms": server_wait_ms}

    def acknowledge(self, instance: str, cid: str, status: str, detail: str):
        with self.lock:
            if instance != self.instance:
                raise Fault(409, "Agent replaced")
            if status not in ("submitted", "rejected", "failed", "expired"):
                raise Fault(400, "Invalid command result")
            command = self.inflight.pop(cid, None)
            if not command:
                raise Fault(404, "Unknown command result")
            self.record(cid, command["kind"], status, detail[:300])

    def talk_owner(self,sid,proof):
        self.session(sid);self.tick()
        if self.owner!=sid or not proof or not hmac.compare_digest(proof,self.control_token):
            raise Fault(409,'ابتدا اختیار کنترل را فعال کن.')
        if not self.caps.get('speaker'):raise Fault(409,'اپ ربات را با اتصال ربات به نسخهٔ جدید ارتقا بده.')

    def talk_start(self,sid,proof):
        with self.lock:
            self.talk_owner(sid,proof)
            return {'stream_id':self.talk.start(),'rate':16000}

    def talk_stop(self,sid,proof,stream):
        with self.lock:
            self.talk_owner(sid,proof)
            if self.talk.stream and stream!=self.talk.stream:raise Fault(409,'این نوبت صحبت پایان یافته است.')
            self.talk.stop();return {'ok':True}

    def talk_push(self,sid,proof,stream,sequence,data):
        with self.lock:
            self.talk_owner(sid,proof)
            try:self.talk.push(stream,sequence,data)
            except ValueError as error:raise Fault(409,str(error))

    def talk_read(self,instance,stream,after):
        with self.lock:
            self.tick()
            if instance!=self.instance:raise Fault(409,'Agent replaced')
            if not self.owner or not self.online():return '',None
            return self.talk.read(stream,after)

    def set_frame(self, instance: str, data: bytes):
        if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
            raise Fault(400, "Expected a JPEG frame")
        with self.lock:
            self.tick()
            if instance != self.instance:
                raise Fault(409, "Agent replaced")
            if not self.online() or not self.owner or not self.caps.get("camera_active"):
                raise Fault(409, "Camera is not active")
            self.frame, self.frame_seen = data, self.clock()

    def set_audio(self, instance: str, data: bytes):
        if not data or len(data) > 16000 or len(data) % 2:
            raise Fault(400, "Expected PCM16 mono audio")
        with self.lock:
            self.tick()
            if instance != self.instance or not self.online() or not self.owner or not self.caps.get('mic_active'):
                raise Fault(409, "Microphone is not active")
            self.audio_sequence += 1
            self.audio.append((self.audio_sequence, data, self.clock()))

    def media(self, sid: str, proof: str, after: int = -1):
        with self.lock:
            self.session(sid)
            self.tick()
            if self.owner != sid or not proof or not hmac.compare_digest(proof, self.control_token):
                raise Fault(409, 'ابتدا اختیار کنترل را فعال کنید.')
            if after < 0:
                if not self.frame:raise Fault(404, 'تصویر تازه دریافت نشده است.')
                return self.frame
            recent = [p for p in self.audio if p[0] > after and self.clock()-p[2] < AUDIO_SECONDS]
            # بعد از اتصال مجدد، پخش را از صدای تازه ادامه می‌دهیم.
            if not recent:raise Fault(404, 'No fresh audio')
            return recent[-1] if len(recent) > 3 else recent[0]

    def status(self, sid: str, control_token: str = "") -> dict:
        with self.lock:
            self.session(sid)
            self.tick()
            owned = self.owner == sid and bool(control_token) and hmac.compare_digest(control_token, self.control_token)
            return {"talk_active":bool(self.talk.stream),"talk_uploaded":self.talk.uploaded,"talk_delivered":self.talk.delivered,"online": self.online(), "capabilities": self.caps if self.online() else {},
                    "control_owned": owned, "drive_epoch": self.drive_epoch if owned else None, "control_busy": bool(self.owner and not owned),
                    "camera_live": bool(self.frame), "camera_age_ms": int((self.clock() - self.frame_seen) * 1000) if self.frame else None,
                    "mic_live": bool(self.audio and self.clock()-self.audio[-1][2] < AUDIO_SECONDS),
                    "camera_error": self.camera_error, "mic_error": getattr(self, "mic_error", ""),
                    "media_notice": getattr(self, "media_notice", ""),
                    "head_notice": self.head_notice,
                    "drive_block": self.drive_block if self.online() else "",
                    "arm_range": self.arm_range if self.online() else {},
                    "diagnostics": self.diagnostics, "results": list(self.results)}

    def watchdog(self):
        while not self.shutdown_event.wait(0.1):
            with self.lock:
                self.tick()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def gateway(self) -> Gateway:
        return self.server.gateway

    def log_message(self, *_args):
        # متن درخواست، تصویر، کوکی و اطلاعات ورود وارد لاگ نمی‌شوند.
        pass

    def reply(self, status: int, data: bytes, mime="application/json; charset=utf-8", extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def json_reply(self, value: dict, status=200, extra: dict | None = None):
        self.reply(status, json.dumps(value, ensure_ascii=False).encode(), extra=extra)

    def body(self) -> bytes:
        if self.headers.get("Transfer-Encoding"):
            raise Fault(400, "Chunked requests are not supported")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise Fault(400, "Invalid Content-Length")
        if not 0 <= length <= MAX_BODY:
            self.close_connection = True
            raise Fault(413, "Request too large")
        value = self.rfile.read(length)
        if len(value) != length:
            raise Fault(400, "Incomplete request")
        return value

    def json_body(self) -> dict:
        if self.headers.get_content_type() != "application/json":
            raise Fault(415, "Expected JSON")
        try:
            data = json.loads(self.body())
        except (UnicodeDecodeError, ValueError):
            raise Fault(400, "Invalid JSON")
        if not isinstance(data, dict):
            raise Fault(400, "Expected a JSON object")
        return data

    def sid(self) -> str:
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except Exception:
            return ""
        cookie = cookies.get("timo_session")
        return cookie.value if cookie else ""

    def origin(self) -> str:
        origin = self.headers.get("Origin", "")
        if origin not in self.gateway.config["allowed_origins"]:
            raise Fault(403, "آدرس پنل در allowed_origins تنظیم نشده یا درخواست از مبدأ دیگری ارسال شده.")
        return origin

    def auth(self, mutation=False) -> tuple[str, dict]:
        sid = self.sid()
        session = self.gateway.session(sid)
        if mutation:
            self.origin()
            if not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
                raise Fault(403, "درخواست معتبر نیست؛ دوباره وارد شوید.")
        return sid, session

    def agent_auth(self):
        expected = "Bearer " + self.gateway.config["agent_token"]
        if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            raise Fault(401, "Invalid robot token")

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path in ('/faces/normal.svg','/faces/happy.svg','/faces/sad.svg','/faces/angry.svg','/faces/upset.svg','/faces/surprised.svg'):
                self.reply(200,(ROOT/'face-preview'/path.rsplit('/',1)[-1]).read_bytes(),'image/svg+xml')
            elif path.startswith('/api/agent/speech/'):
                self.agent_auth()
                data, mime = self.gateway.project.audio_file(self.headers.get('X-Agent-Instance',''), path.rsplit('/',1)[-1])
                self.reply(200, data, mime)
            elif path == '/api/project/state':
                sid, _ = self.auth()
                self.json_reply(self.gateway.project.state(sid))
            elif path == '/api/agent/talk':
                self.agent_auth()
                try:after=int(parse_qs(urlsplit(self.path).query).get('after',['0'])[0])
                except ValueError:raise Fault(400,'Invalid talk cursor')
                if after<0:raise Fault(400,'Invalid talk cursor')
                stream,packet=self.gateway.talk_read(self.headers.get('X-Agent-Instance',''),self.headers.get('X-Talk-Stream',''),after)
                extra={'X-Talk-Stream':stream,'X-Talk-Active':'1' if stream else '0'}
                if packet:
                    seq,data,at=packet
                    extra.update({'X-Audio-Sequence':str(seq),'X-Audio-Age-Ms':str(max(0,int((self.gateway.clock()-at)*1000)))})
                    self.reply(200,data,'application/octet-stream',extra)
                else:self.reply(204,b'','application/octet-stream',extra)
            elif path == "/api/session":
                try:
                    _, session = self.auth()
                    self.json_reply({"authenticated": True, "csrf": session["csrf"]})
                except Fault as error:
                    if error.status != 401:
                        raise
                    self.json_reply({"authenticated": False})
            elif path == "/api/status":
                sid, _ = self.auth()
                self.json_reply(self.gateway.status(sid, self.headers.get("X-Control-Token", "")))
            elif path == "/api/frame":
                sid, _ = self.auth()
                frame = self.gateway.media(sid, self.headers.get('X-Control-Token',''))
                self.reply(200, frame, "image/jpeg")
            elif path == '/api/audio':
                sid, _ = self.auth()
                try:after = int(parse_qs(urlsplit(self.path).query).get('after',['0'])[0])
                except ValueError:raise Fault(400,'Invalid audio cursor')
                if after < 0:raise Fault(400,'Invalid audio cursor')
                sequence, data, _ = self.gateway.media(sid,self.headers.get('X-Control-Token',''),after)
                self.reply(200,data,'application/octet-stream',{'X-Audio-Sequence':str(sequence),'X-Audio-Rate':'16000'})
            elif path in ("/", "/index.html", "/app.js", "/talk-worklet.js", "/project.js", "/face-control.js", "/style.css", "/manifest.webmanifest", "/sw.js", "/icon.svg", "/icon-192.png", "/icon-512.png"):
                filename = "index.html" if path == "/" else path[1:]
                source = ROOT / "web" / filename
                if not source.is_file():
                    raise Fault(404, "File not found")
                mime = {".js": "text/javascript", ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml"}.get(source.suffix, mimetypes.guess_type(source.name)[0] or "application/octet-stream")
                self.reply(200, source.read_bytes(), mime)
            else:
                raise Fault(404, "Not found")
        except Fault as error:
            self.json_reply({"error": error.message}, error.status)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            if path.startswith("/api/agent/"):
                self.agent_auth()
                if path == '/api/agent/audio':
                    if self.headers.get_content_type() != 'application/octet-stream':raise Fault(415,'Expected PCM audio')
                    self.gateway.set_audio(self.headers.get('X-Agent-Instance',''),self.body())
                    self.json_reply({'ok':True});return
                if path == "/api/agent/frame":
                    if self.headers.get_content_type() != "image/jpeg":
                        raise Fault(415, "Expected JPEG")
                    self.gateway.set_frame(self.headers.get("X-Agent-Instance", ""), self.body())
                    self.json_reply({"ok": True})
                    return
                body = self.json_body()
                if path == "/api/agent/poll":
                    caps, diagnostics = body.get("capabilities", {}), body.get("diagnostics", [])
                    if not isinstance(caps, dict) or not isinstance(diagnostics, list):
                        raise Fault(400, "Invalid capabilities")
                    self.json_reply(self.gateway.poll(body.get("instance", ""), caps, diagnostics, str(body.get("camera_error", "")),
                                                     media_notice=str(body.get("media_notice", "")), mic_error=str(body.get("mic_error", "")),
                                                     head_notice=str(body.get("head_notice", "")), navigation=body.get("navigation"), speech=body.get("speech"),
                                                     arm_range=body.get("arm_range"), drive_block=body.get("drive_block")))
                elif path == '/api/agent/navigation/validate':
                    self.json_reply(self.gateway.project.validate_navigation(self.headers.get('X-Agent-Instance',''), str(body.get('command_id',''))))
                elif path == "/api/agent/result":
                    self.gateway.acknowledge(str(body.get("instance", "")), str(body.get("id", "")), str(body.get("status", "")), str(body.get("detail", "")))
                    self.json_reply({"ok": True})
                else:
                    raise Fault(404, "Not found")
                return
            if path == "/api/login":
                origin = self.origin()
                body = self.json_body()
                password = body.get("password", "")
                if not isinstance(password, str) or len(password) > 512:
                    raise Fault(400, "Invalid password")
                # درخواست‌های پراکسی محلی ممکن است همگی با یک IP دیده شوند.
                sid, session = self.gateway.login(password, self.client_address[0], origin.startswith("https://"))
                cookie = f"timo_session={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}"
                if session["secure"]:
                    cookie += "; Secure"
                self.json_reply({"ok": True, "csrf": session["csrf"]}, extra={"Set-Cookie": cookie})
                return
            sid, session = self.auth(mutation=True)
            if path == '/api/talk/audio':
                if self.headers.get_content_type()!='application/octet-stream':raise Fault(415,'Expected PCM')
                try:seq=int(self.headers.get('X-Audio-Sequence','0'))
                except ValueError:raise Fault(400,'Invalid audio sequence')
                self.gateway.talk_push(sid,self.headers.get('X-Control-Token',''),self.headers.get('X-Talk-Stream',''),seq,self.body())
                self.json_reply({'ok':True});return
            body = self.json_body()
            if path == '/api/project/chat':
                self.json_reply(self.gateway.project.chat(sid, self.headers.get('X-Control-Token',''), body.get('request_id'), body.get('text'), body.get('new_session') is True))
            elif path == '/api/project/say':
                self.json_reply(self.gateway.project.say(sid, self.headers.get('X-Control-Token',''), body.get('request_id'), body.get('text')))
            elif path == '/api/project/navigate':
                self.json_reply(self.gateway.project.navigate(sid, self.headers.get('X-Control-Token',''), body.get('request_id'), body.get('room_id')))
            elif path == '/api/talk/start':
                self.json_reply(self.gateway.talk_start(sid,self.headers.get('X-Control-Token','')))
            elif path == '/api/talk/stop':
                self.json_reply(self.gateway.talk_stop(sid,self.headers.get('X-Control-Token',''),body.get('stream_id','')))
            elif path == "/api/logout":
                self.gateway.logout(sid)
                cookie = "timo_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0" + ("; Secure" if session["secure"] else "")
                self.json_reply({"ok": True}, extra={"Set-Cookie": cookie})
            elif path == "/api/control/acquire":
                self.json_reply(self.gateway.acquire(sid, self.headers.get("X-Control-Token", "")))
            elif path == "/api/control/hold":
                self.json_reply(self.gateway.hold(sid, self.headers.get("X-Control-Token", "")))
            elif path == "/api/command":
                kind, args = body.get("kind", ""), body.get("args", {})
                if not isinstance(kind, str) or not isinstance(args, dict):
                    raise Fault(400, "Invalid command")
                self.json_reply(self.gateway.command(sid, kind, args, self.headers.get("X-Control-Token", "")))
            else:
                raise Fault(404, "Not found")
        except Fault as error:
            # با بستن اتصال، بدنهٔ باقی‌ماندهٔ درخواست نامعتبر دوباره تفسیر نمی‌شود.
            self.close_connection = True
            self.json_reply({"error": error.message}, error.status)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        except Exception:
            LOG.exception("Request failed")
            self.close_connection = True
            self.json_reply({"error": "خطای سرویس کنترل"}, 500)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple, gateway: Gateway):
        super().__init__(address, Handler)
        self.gateway = gateway
        self.slots = threading.BoundedSemaphore(40)

    def get_request(self):
        client, address = super().get_request()
        client.settimeout(5)
        return client, address

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    if not args.config.exists():
        parser.error("Run python setup.py first to create your private config.json")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    gateway = Gateway(config)
    server = Server((args.host, int(config["port"])), gateway)
    threading.Thread(target=gateway.watchdog, daemon=True).start()
    print(f"Timo gateway: http://{args.host}:{server.server_port} (private network only)", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        gateway.shutdown_event.set()
        with gateway.lock:
            gateway.stop("server_shutdown")
        server.server_close()
        # اگر درگاه قطع شود، تایمر مستقل اپ ربات مسئول درخواست توقف است.


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
