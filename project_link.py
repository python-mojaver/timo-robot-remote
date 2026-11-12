"""رابط خواندن نقشه، گفتگو و صوت از بک‌اند FastAPI تیمو با کلید محلی."""
import hashlib
import ipaddress
import json
import math
import re
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class ProjectError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def origin(value):
    value = str(value).strip().rstrip('/')
    u = urlsplit(value)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise ProjectError('آدرس سرویس باید فقط مبدأ باشد؛ مثل http://127.0.0.1:8000')
    try:
        port = u.port
        if port is not None and not 1 <= port <= 65535: raise ValueError()
        if u.scheme == 'http' and u.hostname != 'localhost':
            ip = ipaddress.ip_address(u.hostname)
            if not (ip.is_private or ip.is_loopback) or ip.is_unspecified or ip.is_multicast: raise ValueError()
    except ValueError:
        raise ProjectError('برای HTTP از IP شبکهٔ داخلی یا localhost استفاده کن.')
    return value


def normalize(value):
    text = str(value).replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')
    text = re.sub('[\u064b-\u065f\u0670]', '', text)
    return re.sub(r'\s+', ' ', text).strip(' \n\t؟?!.،')


def target(text):
    m = re.fullmatch(r'(?:لطفا )?(?:(?:برو|حرکت کن)(?: به)?|(?:منو|من را|من رو) ببر(?: به)?|ببرم(?: به)?) (.+)', normalize(text))
    return m.group(1) if m else None


STOPS = {'توقف', 'بایست', 'وایسا', 'حرکت نکن', 'توقف حرکت', 'توقف ربات'}


class ProjectLink:
    def __init__(self, config, opener=None):
        self.base = origin(config.get('project_url') or 'http://127.0.0.1:8000')
        self.key = config.get('project_key', '').strip()
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.chat_slots = threading.BoundedSemaphore(2)
        self.speech_slots = threading.BoundedSemaphore(1)

    @property
    def configured(self):
        return bool(self.key)

    def request(self, path, body=None, timeout=3, binary=False):
        if not self.configured: raise ProjectError('در ویندوز «اتصال پروژهٔ اصلی» را تنظیم کن.')
        if not re.fullmatch(r'[\x21-\x7e]{1,512}', self.key): raise ProjectError('کلید مدیر باید فقط مقدار اصلی با نویسه‌های انگلیسی باشد.')
        headers = {'X-Agent-Key': self.key, 'Accept': 'application/json'}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode(); headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.base + path, data, headers)
        try:
            with self.opener.open(req, timeout=timeout) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024: raise ProjectError('پاسخ پروژه بیش از اندازه بزرگ است.')
                if binary: return raw
                result = json.loads(raw)
                if not isinstance(result, dict): raise ProjectError('قالب پاسخ پروژه شناخته نشد.')
                return result
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403): raise ProjectError('کلید مدیر پروژه صحیح نیست یا مجوز دسترسی ندارد.') from None
            if exc.code == 404: raise ProjectError('API موردنیاز در پروژه پیدا نشد؛ نسخهٔ فعلی پروژه باید بررسی شود.') from None
            raise ProjectError('پروژه درخواست را نپذیرفت؛ HTTP ' + str(exc.code)) from None
        except (OSError, ValueError) as exc:
            raise ProjectError('ارتباط با پروژه برقرار نشد؛ روشن‌بودن سرور پورت ۸۰۰۰ و آدرس را بررسی کن.') from None

    def state(self):
        raw = self.request('/api/agent/state')
        config = raw.get('motion_config')
        if not isinstance(config, dict) or not isinstance(raw.get('rooms'), list):
            raise ProjectError('API نقشهٔ مشترک با این ریموت سازگار نیست.')
        map_name, revision = str(config.get('map_name', '')), str(config.get('revision', ''))
        rooms = []
        for room in raw['rooms']:
            if not isinstance(room, dict) or type(room.get('id')) is not int or not room.get('enabled'): continue
            name = str(room.get('name', ''))[:120]
            aliases = [str(x)[:120] for x in room.get('aliases', [])[:30]] if isinstance(room.get('aliases'), list) else []
            rooms.append({'id': room['id'], 'name': name, 'aliases': aliases,
                          'map_name': str(room.get('map_name', ''))[:120],
                          'available': bool(config.get('configured') and revision and room.get('map_name') == map_name)})
        return {'configured': True, 'map_name': map_name[:120], 'revision': revision[:128], 'rooms': rooms}, raw

    def destination(self, room_id):
        if type(room_id) is not int or room_id <= 0: raise ProjectError('شناسهٔ اتاق معتبر نیست.')
        view, raw = self.state()
        item = next((r for r in view['rooms'] if r['id'] == room_id and r['available']), None)
        if item is None: raise ProjectError('مقصد غیرفعال است یا با نقشهٔ مشترک تطابق ندارد؛ فهرست را تازه کن.')
        room = next(r for r in raw['rooms'] if r['id'] == room_id)
        try:
            pose = {k: float(room[k]) for k in ('x', 'y', 'z', 'rotation')}
            if any(not math.isfinite(v) or abs(v) > (math.pi * 2 if k == 'rotation' else 10000) for k, v in pose.items()): raise ValueError()
        except (KeyError, TypeError, ValueError): raise ProjectError('مختصات اتاق معتبر نیست.')
        payload = {'room_id': room_id, 'name': item['name'], 'map_name': view['map_name'],
                   'map_revision': view['revision'], 'pose': pose}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return payload, fingerprint

    def chat(self, text, session):
        text = str(text).strip()
        if not text or len(text) > 6000: raise ProjectError('متن باید بین ۱ تا ۶۰۰۰ نویسه باشد.')
        if not self.chat_slots.acquire(blocking=False): raise ProjectError('پاسخ قبلی در حال آماده‌شدن است؛ کمی صبر کن.')
        try:
            result = self.request('/api/chat', {'message': text, 'session_id': session, 'input_source': 'text'}, timeout=45)
            answer = result.get('response')
            if not isinstance(answer, str) or len(answer) > 24000: raise ProjectError('پاسخ چت قالب معتبری ندارد.')
            # فقط دستور صریح کاربر با الگوی مشخص می‌تواند یک مقصد پیشنهاد کند.
            action = result.get('action')
            room_id = action.get('room_id') if isinstance(action, dict) and action.get('type') == 'navigate' else None
            chosen = None
            wanted = target(text)
            if wanted and type(room_id) is int:
                view, _ = self.state()
                chosen = next((r['id'] for r in view['rooms'] if r['id'] == room_id and r['available'] and
                               wanted in {normalize(r['name']), *(normalize(a) for a in r['aliases'])}), None)
            from face_protocol import canonical
            raw_face = result.get('face')
            mode = canonical(raw_face.get('expression')) if isinstance(raw_face,dict) else None
            return {'response': answer, 'room_id': chosen,
                    **({'face':{'expression':mode}} if mode else {}),
                    'notice': 'اطلاعات پیشنهادی حافظه در ریموت ذخیره نمی‌شوند؛ از مدیریت پروژه استفاده کن.' if result.get('proposal') or result.get('room_draft') else ''}
        finally: self.chat_slots.release()

    def speech(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 6000: raise ProjectError('متن پخش باید بین ۱ تا ۶۰۰۰ نویسه باشد.')
        if not self.speech_slots.acquire(blocking=False): raise ProjectError('صدای قبلی هنوز در حال تولید است؛ کمی صبر کن.')
        try: return self._speech(text)
        finally: self.speech_slots.release()

    def _speech(self, text):
        result = self.request('/api/speak', {'text': text.strip()}, timeout=30)
        path = result.get('audio_url')
        if not isinstance(path, str) or not re.fullmatch(r'/generated_audio/[A-Za-z0-9_.-]+\.(?:mp3|wav)', path):
            raise ProjectError('پروژه فایل صوتی معتبری تولید نکرد.')
        data = self.request(path, binary=True, timeout=15)
        if not data: raise ProjectError('فایل صوتی پروژه خالی است.')
        return data, 'audio/wav' if path.endswith('.wav') else 'audio/mpeg'
