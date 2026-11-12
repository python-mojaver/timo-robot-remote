"""نصب و تنظیم اپ همراه تیمو از طریق اتصال مجاز ADB."""
from __future__ import annotations
import sys
import ipaddress
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path

PACKAGE = 'com.htnhome.timoremote.robot'
VERSION = 16

VERIFIED_SDK_SHA256 = '67bee4b18bd0257cd17c0ef1707899c44f0e45b40d465ecd9ac10afaaf3de4c1'

def verified_empty_profile(adb, serial):
    """برای پروفایل خالی، رفتار ctrl_x فقط روی نسخهٔ بررسی‌شدهٔ SDK تأیید شده است."""
    paths=adb.run('shell','pm','path','com.csjbot.robotsdk.ten',serial=serial,timeout=6)
    for line in paths.splitlines():
        path=line.strip().removeprefix('package:')
        if re.fullmatch(r'/data/app/[A-Za-z0-9_~+=./-]+/base\.apk',path):
            value=adb.run('shell','sha256sum',path,serial=serial,timeout=15).split()
            if value and value[0]==VERIFIED_SDK_SHA256:return 'robot_action_ctrl_x'
    return ''

def head_profile(adb, serial):
    """پروفایل حرکت دستگاه را از فایل تنظیمات سازنده می‌خواند."""
    try:
        import json
        raw=adb.run('shell','cat','/sdcard/.robot_info/.robot_action_type.txt',serial=serial,timeout=6)
        if len(raw)>4096:return ''
        if not raw.strip():return verified_empty_profile(adb,serial)
        value=json.loads(raw).get('robot_action_type','')
        return value if value in ('robot_action_new','robot_action_old','robot_action_ctrl_x') else ''
    except (SetupError,ValueError,AttributeError):return ''

class SetupError(RuntimeError): pass

def find_adb():
    candidates = [Path(os.environ.get('LOCALAPPDATA',''))/'Android/Sdk/platform-tools/adb.exe']
    for key in ('ANDROID_HOME','ANDROID_SDK_ROOT'):
        if os.environ.get(key):candidates.append(Path(os.environ[key])/'platform-tools/adb.exe')
    for candidate in candidates:
        if candidate.is_file():return str(candidate)
    value=shutil.which('adb')
    if value:return value
    raise SetupError('ADB پیدا نشد؛ Android Studio و SDK نصب‌شده را بررسی کن.')

class Adb:
    def __init__(self, executable=None, runner=subprocess.run):
        self.executable=executable or find_adb();self.runner=runner
    def run(self,*args,serial=None,timeout=12,private=False):
        command=[self.executable]+(['-s',serial] if serial else [])+list(args)
        try:
            result=self.runner(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                text=True,encoding='utf-8',errors='replace',timeout=timeout,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.TimeoutExpired):
            raise SetupError('ارتباط ADB پاسخ نداد؛ اتصال وایرلس ربات را بررسی کن.') from None
        if result.returncode:
            # آرگومان اتصال ممکن است توکن داشته باشد. برای خطا، پیام عمومی نشان می‌دهیم.
            if private:raise SetupError('ارسال تنظیمات به اپ ربات انجام نشد؛ دوباره اتصال ربات را بزن.')
            text=(result.stderr or result.stdout).strip()
            raise SetupError('ADB: '+text[:350])
        return result.stdout
    def devices(self):
        output=self.run('devices')
        result=[]
        for line in output.splitlines():
            columns=line.split()
            if len(columns)>=2 and columns[1]=='device' and not columns[0].startswith('emulator-'):
                result.append(columns[0])
        return result

def local_ip_for_robot(adb,serial,route_socket=socket.socket):
    candidates=[]
    # اول IP را از جدول مسیر می‌خوانیم و در صورت نیاز سراغ آدرس رابط می‌رویم.
    for args in [('shell','ip','-4','route'),('shell','ip','-o','-4','addr','show')]:
        try:raw=adb.run(*args,serial=serial)
        except SetupError:continue
        found=re.findall(r'\bsrc\s+(\d+\.\d+\.\d+\.\d+)',raw) if 'route' in args else re.findall(r'\binet\s+(\d+\.\d+\.\d+\.\d+)/',raw)
        for value in found:
            address=ipaddress.ip_address(value)
            if address.is_private and not address.is_loopback and value not in candidates:candidates.append(value)
        if candidates:break
    for address in candidates:
        try:
            with route_socket(socket.AF_INET,socket.SOCK_DGRAM) as route:
                route.connect((address,8765));local=route.getsockname()[0]
            ip=ipaddress.ip_address(local)
            if ip.is_private and not ip.is_loopback:return local
        except OSError:continue
    return None

def connect(config,port,app_dir,serial,progress=lambda _:None,allow_origin=lambda _:None,adb=None):
    adb=adb or Adb()
    if serial not in adb.devices():raise SetupError('ربات انتخاب‌شده به ADB متصل نیست.')
    token=config.get('agent_token','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{24,200}',token):raise SetupError('تنظیمات محلی ریموت معتبر نیست.')
    progress('در حال آماده‌کردن اپ مستقل ربات…')
    raw=adb.run('shell','dumpsys','package',PACKAGE,serial=serial)
    version=re.search(r'\bversionCode=(\d+)',raw)
    if not version or int(version.group(1))<VERSION:
        apk=Path(app_dir)/'apks/TimoRemote-Robot.apk'
        if not apk.is_file() and getattr(sys,'frozen',False):apk=Path(sys._MEIPASS)/'apks/TimoRemote-Robot.apk'
        if not apk.is_file():raise SetupError('اپ اندروید را طبق README بساز و در مسیر apks/TimoRemote-Robot.apk قرار بده.')
        installed=adb.run('install','-r',str(apk),serial=serial,timeout=90)
        if 'Success' not in installed:raise SetupError('به‌روزرسانی اپ مستقل ربات کامل نشد.')
    progress('در حال تنظیم خودکار اتصال…')
    local=local_ip_for_robot(adb,serial)
    lan='http://'+local+':'+str(port) if local else ''
    fallback='http://127.0.0.1:'+str(port)
    tunnel=False
    try:
        adb.run('reverse','tcp:'+str(port),'tcp:'+str(port),serial=serial)
        tunnel=True
    except SetupError:pass
    if not lan and not tunnel:raise SetupError('مسیر ارتباط پیدا نشد؛ اتصال شبکه و ADB ربات را بررسی کن.')
    origin=lan or fallback;allow_origin(origin)
    # گیرندهٔ تنظیمات مجوز DUMP می‌خواهد تا برنامه‌های عادی به آن دسترسی نداشته باشند.
    profile=head_profile(adb,serial)
    output=adb.run('shell','am','broadcast','-f','0x10000020','-a',PACKAGE+'.CONFIGURE',
        '-n',PACKAGE+'/.SetupReceiver','--es','url',origin,'--es','token',token,
        '--es','head_profile',profile or 'unknown','--es','fallback',fallback if tunnel else origin,serial=serial,private=True)
    if not re.search(r'\bresult=1\b',output):
        raise SetupError('اپ ربات تنظیمات را نپذیرفت؛ دوباره اتصال ربات را بزن.')
    permission_notice=False
    for permission in ('android.permission.CAMERA','android.permission.RECORD_AUDIO'):
        try:adb.run('shell','pm','grant',PACKAGE,permission,serial=serial,private=True)
        except SetupError:permission_notice=True
    output=adb.run('shell','am','start','-W','--activity-single-top','-a',PACKAGE+'.RECONNECT',
        '-n',PACKAGE+'/.MainActivity',serial=serial)
    if 'Error:' in output or 'Exception' in output:raise SetupError('اپ ربات باز نشد؛ Timo Remote Robot را روی ربات باز کن.')
    return {'serial':serial,'url':origin,'tunnel':tunnel,'permission_notice':permission_notice,'head_profile':profile}
