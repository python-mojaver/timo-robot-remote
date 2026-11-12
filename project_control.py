"""مدیریت فرمان‌های پروژه با بررسی مالکیت قبل و بعد از درخواست شبکه."""
import hashlib
import hmac
import json
import re
import secrets
import time
from collections import OrderedDict

from project_link import ProjectLink, ProjectError, normalize, STOPS


class ProjectControl:
    def __init__(self, gateway, config, fault):
        self.fault = fault
        self.g = gateway
        self.link = ProjectLink(config)
        self.operations = OrderedDict()
        self.sessions = {}
        self.audio = OrderedDict()
        self.nav = {'state': 'checking', 'busy': False, 'ready': False, 'message': 'منتظر بررسی وضعیت ناوبری SDK'}
        self.speech = {}
        self.pending = None
        self.manual_until = 0

    def fail(self, code, message):
        raise self.fault(code, message)

    def owner(self, sid, proof):
        self.g.session(sid); self.g.tick()
        if not proof or self.g.owner != sid or not hmac.compare_digest(proof, self.g.control_token):
            self.fail(409, 'ابتدا کنترل ربات را فعال کن.')

    def operation(self, sid, proof, request_id, kind, value):
        self.owner(sid, proof)
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', request_id): self.fail(400, 'شناسهٔ درخواست معتبر نیست.')
        # شناسهٔ یکسان با محتوای متفاوت رد می‌شود.
        signature = hashlib.sha256(json.dumps([sid, kind, value], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        old = self.operations.get(request_id)
        if old:
            if old['signature'] != signature: self.fail(409, 'شناسهٔ درخواست تکراری است.')
            if old['result'] is None: self.fail(409, 'درخواست قبلی هنوز در حال بررسی است؛ خودکار تکرار نمی‌شود.')
            return old['result'], signature
        while len(self.operations) >= 100:
            key = next((k for k, v in self.operations.items() if v['result'] is not None), None)
            if key is None: self.fail(429, 'درخواست‌های قبلی هنوز پایان نیافته‌اند.')
            self.operations.pop(key)
        self.operations[request_id] = {'signature': signature, 'result': None}
        return None, signature

    def finish(self, request_id, result):
        with self.g.lock:
            if request_id in self.operations: self.operations[request_id]['result'] = result
        return result

    def configure(self, config):
        link = ProjectLink(config)
        view, _ = link.state()  # اعتبار اتصال تازه پیش از جایگزینی بررسی می‌شود.
        with self.g.lock:
            if self.g.owner or self.pending or self.nav.get('busy'): self.fail(409, 'ابتدا پایان حرکت و آزادبودن کنترل را بررسی کن.')
            self.link = link; self.operations.clear(); self.sessions.clear(); self.audio.clear()
        return view

    def state(self, sid):
        with self.g.lock:
            self.g.session(sid); link = self.link
            nav = dict(self.nav); pending = self.pending
            if pending and nav.get('request_id') != pending['id']:
                nav = {'state': 'queued', 'busy': True, 'ready': False, 'request_id': pending['id'], 'message': 'درخواست مقصد ثبت شد؛ منتظر اپ ربات'}
            info = {'navigation': nav, 'speech': dict(self.speech), 'online': self.g.online(), 'configured': link.configured}
        if not link.configured: return {**info, 'rooms': [], 'map_name': '', 'error': 'در ویندوز «اتصال پروژهٔ اصلی» را تنظیم کن.'}
        try:
            view, _ = link.state()
            return {**view, **info, 'error': ''}
        except ProjectError as exc: return {**info, 'rooms': [], 'map_name': '', 'error': str(exc)}

    def manual(self):
        if self.pending or self.nav.get('busy'):
            self.fail(409, 'ناوبری فعال یا تأییدنشده است؛ ابتدا لغو مسیر و تأیید توقف SDK را منتظر بمان.')
        self.manual_until = self.g.clock() + .9

    def navigate(self, sid, proof, request_id, room_id):
        with self.g.lock:
            old, _ = self.operation(sid, proof, request_id, 'navigate', room_id)
            if old is not None: return old
            link = self.link
        try:
            payload, fingerprint = link.destination(room_id)
            with self.g.lock:
                self.owner(sid, proof)
                if self.link is not link: self.fail(409, 'اتصال پروژه تغییر کرد؛ مقصد را دوباره بررسی کن.')
                if self.pending or self.nav.get('busy') or not self.nav.get('ready') or self.g.clock() < self.manual_until:
                    self.fail(409, 'ربات هنوز برای مقصد آماده نیست؛ پایان حرکت دستی یا بررسی وضعیت SDK را منتظر بمان.')
                if not (self.g.caps.get('navigation') and self.g.caps.get('stop')): self.fail(409, 'اپ مستقل ربات و فرمان توقف SDK باید آماده باشند؛ «اتصال ربات» را بررسی کن.')
                args = dict(payload, project_request=request_id, fingerprint=fingerprint)
                command = self.g.enqueue('nav_room', args)
                self.pending = {'id': request_id, 'command': command['id'], 'instance': self.g.instance,
                                'generation': self.nav.get('generation', 0), 'room_id': room_id, 'fingerprint': fingerprint}
                result = {'ok': True, 'request_id': request_id, 'status': 'queued', 'room_name': payload['name']}
            return self.finish(request_id, result)
        except Exception as exc:
            self.finish(request_id, {'ok': False, 'error': str(exc)})
            if isinstance(exc, ProjectError): self.fail(409, str(exc))
            raise

    def validate_navigation(self, instance, command_id):
        with self.g.lock:
            self.g.tick(); pending = dict(self.pending or {}); link = self.link
            if not pending or instance != self.g.instance or command_id != pending.get('command') or not self.g.owner:
                self.fail(409, 'این فرمان مقصد دیگر فعال نیست.')
            command = self.g.inflight.get(command_id)
            if not command or command['deadline'] <= self.g.clock(): self.fail(409, 'فرمان مقصد منقضی شد.')
            token = self.g.control_token
        # مختصات و نسخهٔ نقشه در لحظهٔ تحویل دوباره از منبع اصلی خوانده می‌شوند.
        try: payload, fingerprint = link.destination(pending['room_id'])
        except ProjectError as exc: self.fail(409, str(exc))
        with self.g.lock:
            self.g.tick()
            if self.pending != pending or self.g.instance != instance or self.g.control_token != token or not self.g.owner or command['deadline'] <= self.g.clock():
                self.fail(409, 'فرمان پیش از اجرا لغو یا منقضی شد.')
            if fingerprint != pending['fingerprint']: self.fail(409, 'نقشه یا مقصد تغییر کرده؛ فرمان قبلی اجرا نمی‌شود.')
        return dict(payload, project_request=pending['id'])

    def chat(self, sid, proof, request_id, text, new_session=False):
        if not isinstance(text, str) or not text.strip() or len(text) > 6000: self.fail(400, 'متن معتبر نیست.')
        with self.g.lock:
            old, _ = self.operation(sid, proof, request_id, 'chat', text)
            if old is not None: return old
            if normalize(text) in STOPS:
                self.g.stop('chat_stop')
                return self.finish(request_id, {'response': 'درخواست توقف ارسال شد؛ تأیید توقف را در وضعیت حرکت بررسی کن.', 'stopped': True})
            if new_session or sid not in self.sessions: self.sessions[sid] = 'remote_' + secrets.token_hex(16)
            session = self.sessions[sid]; link = self.link
        try:
            result = link.chat(text, session)
            if result.get('face') and self.g.caps.get('face'):
                with self.g.lock:
                    self.owner(sid, proof)
                    if self.link is not link: self.fail(409, 'اتصال پروژه عوض شد.')
                    self.g.command(sid, 'face', result['face'], proof)
            if result.get('room_id'):
                try: result['navigation'] = self.navigate(sid, proof, request_id + '_nav', result['room_id'])
                except Exception as exc: result['notice'] = 'فرمان حرکت ارسال نشد: ' + str(exc)
            return self.finish(request_id, result)
        except ProjectError as exc:
            self.finish(request_id, {'ok': False, 'error': str(exc)})
            self.fail(502, str(exc))

    def say(self, sid, proof, request_id, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 6000: self.fail(400, 'متن پخش معتبر نیست.')
        with self.g.lock:
            old, _ = self.operation(sid, proof, request_id, 'say', text)
            if old is not None: return old
            if not self.g.caps.get('speech'): self.fail(409, 'اپ ربات برای پخش پاسخ متنی باید ارتقا یابد.')
            link = self.link
        try:
            data, mime = link.speech(text)
            with self.g.lock:
                self.owner(sid, proof)
                if self.link is not link: self.fail(409, 'اتصال پروژه عوض شد.')
                if self.g.talk.stream: self.fail(409, 'ابتدا دکمهٔ صحبت مستقیم را رها کن.')
                aid = secrets.token_hex(16)
                while len(self.audio) >= 2: self.audio.popitem(last=False)
                self.audio[aid] = (data, mime, self.g.clock() + 45, self.g.instance, self.g.control_token)
                self.g.enqueue('speak', {'audio_id': aid, 'project_request': request_id})
            return self.finish(request_id, {'ok': True, 'status': 'queued', 'request_id': request_id})
        except Exception as exc:
            self.finish(request_id, {'ok': False, 'error': str(exc)})
            if isinstance(exc, ProjectError): self.fail(502, str(exc))
            raise

    def audio_file(self, instance, aid):
        with self.g.lock:
            self.g.tick(); item = self.audio.get(aid)
            if not item or instance != self.g.instance or not self.g.owner or item[2] <= self.g.clock() or item[3] != instance or item[4] != self.g.control_token:
                self.fail(404, 'صدای فعال پیدا نشد.')
            return item[0], item[1]

    def stopped(self):
        self.audio.clear()
        # مقصد معلق تا پایان بررسی وضعیت SDK آزاد نمی‌شود.

    def receipt(self, cid, status):
        if self.pending and cid == self.pending['command'] and status in ('rejected', 'expired', 'failed'):
            self.pending = None

    def update(self, instance, nav, speech):
        states = {'checking', 'ready', 'submitted', 'navigating', 'verifying', 'stopping', 'stopped', 'arrived', 'uncertain', 'rejected'}
        if isinstance(nav, dict) and nav.get('state') in states and type(nav.get('generation')) is int and nav['generation'] >= 0:
            nav = dict(nav, busy=nav.get('busy') is True, ready=nav.get('ready') is True,
                       request_id=str(nav.get('request_id', ''))[:100], message=str(nav.get('message', ''))[:400])
            self.nav = {k: nav[k] for k in ('state', 'busy', 'ready', 'request_id', 'message', 'generation')}
            if self.pending:
                matching = nav.get('request_id') == self.pending['id']
                recovered = (instance != self.pending['instance'] or nav.get('generation', 0) > self.pending['generation'])
                if (matching and nav['state'] in ('arrived', 'stopped', 'rejected')) or (recovered and nav['state'] in ('ready', 'stopped') and nav.get('ready') is True):
                    self.pending = None
        if isinstance(speech, dict):
            self.speech = {k: str(speech[k])[:300] for k in ('state', 'request_id', 'message') if k in speech}
