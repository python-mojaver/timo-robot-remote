"""رابط ویندوز و درگاه محلی تیمو ریموت."""
from __future__ import annotations
import io
import json
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from PIL import Image, ImageTk
from server import Gateway, Server, new_config
import quick_connect

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

def local_addresses():
    result = {'127.0.0.1'}
    try:
        result.update(x for x in socket.gethostbyname_ex(socket.gethostname())[2] if not x.startswith('127.'))
    except OSError:
        pass
    return sorted(result)

from talk_input import LiveMicrophone
from desktop_project import ProjectPanes
from desktop_face import FacePane

class Client:
    """درخواست‌های رابط ویندوز به درگاه محلی و توکن اختیار کنترل."""

    def __init__(self, base):
        self.base=base;self.cookie='';self.csrf='';self.proof=''
    def request(self, path, body=None, binary=False, timeout=1.2, control_proof=None):
        proof=self.proof if control_proof is None else control_proof
        headers={'Origin':self.base,'Cookie':self.cookie,'X-CSRF-Token':self.csrf,'X-Control-Token':proof}
        raw=None
        if body is not None:
            raw=json.dumps(body).encode();headers['Content-Type']='application/json'
        req=urllib.request.Request(self.base+path,raw,headers)
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:
                data=response.read(600000)
                if binary:return data,dict(response.headers)
                value=json.loads(data)
                if path=='/api/login':
                    self.cookie=response.headers['Set-Cookie'].split(';')[0];self.csrf=value['csrf']
                return value
        except urllib.error.HTTPError as e:
            try:detail=json.loads(e.read()).get('error',str(e))
            except Exception:detail=str(e)
            raise RuntimeError(detail) from e

    def send_pcm(self,stream,seq,pcm,proof):
        req=urllib.request.Request(self.base+'/api/talk/audio',pcm,{
            'Origin':self.base,'Cookie':self.cookie,'X-CSRF-Token':self.csrf,
            'X-Control-Token':proof,'X-Talk-Stream':stream,'X-Audio-Sequence':str(seq),
            'Content-Type':'application/octet-stream'})
        with urllib.request.urlopen(req,timeout=1.0) as response:response.read(1024)

class Desktop:
    def __init__(self, root, config):
        self.root=root;self.config=config
        self.talk_held=False;self.talk_generation=0;self.talk_stream="";self.talk_input=None
        self.gateway=Gateway(config);self.server=Server(('0.0.0.0',int(config['port'])),self.gateway)
        threading.Thread(target=self.gateway.watchdog,daemon=True).start()
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.client=Client('http://127.0.0.1:'+str(self.server.server_port))
        self.pool=ThreadPoolExecutor(max_workers=6);self.logged=False;self.owned=False;self.epoch=0
        self.caps={};self.closing=False;self.driving=None;self.braking=False;self.mic_enabled=False
        self.busy=set();self.image=None;self.audio_stream=None;self.audio_sequence=0;self.setting_up=False;self.diagnostics='';self.head_until=0.0
        self.arm_state={};self.arm_pending='';self.arm_until=0.0
        root.title('Timo Remote 1.9.6 — کنترل مستقل تیمو');root.geometry('1160x960');root.minsize(960,850)
        root.configure(bg='#eff5f8')
        self.status=tk.StringVar(value='برای راه‌اندازی، دکمهٔ اتصال ربات را بزن.')
        self.motion=tk.StringVar(value='کنترل غیرفعال است.')
        self.password=tk.StringVar()
        top=ttk.Frame(root,padding=18);top.pack(fill='x')
        ttk.Label(top,text='TIMO REMOTE  |  کنترل مستقل تیمو',font=('Tahoma',17,'bold')).pack(side='right')
        self.connect_button=ttk.Button(top,text='اتصال ربات',command=self.quick_connect)
        self.connect_button.pack(side='left',padx=6)
        ttk.Button(top,text='تنظیمات پیشرفته',command=self.connection_info).pack(side='left',padx=6)
        ttk.Button(top,text='گزارش وضعیت',command=self.show_diagnostics).pack(side='left',padx=6)
        login=ttk.Frame(root,padding=(18,4));login.pack(fill='x')
        self.password_input=ttk.Entry(login,textvariable=self.password,show='*',width=28);self.password_input.pack(side='right')
        ttk.Button(login,text='ورود به ریموت',command=self.login).pack(side='right',padx=8)
        ttk.Label(login,text='رمز جدید همین برنامه').pack(side='right')
        login.pack_forget()  # رابط ویندوز نشست را از درگاه همین فرایند می‌گیرد.
        ttk.Label(root,textvariable=self.status,padding=14,font=('Tahoma',11)).pack(fill='x')
        self.tabs=ttk.Notebook(root);self.tabs.pack(fill='both',expand=True)
        self.manual_tab=ttk.Frame(self.tabs);self.tabs.add(self.manual_tab,text='ریموت و تصویر زنده')
        body=ttk.Frame(self.manual_tab,padding=18);body.pack(fill='both',expand=True)
        camera_box=ttk.LabelFrame(body,text='دوربین زندهٔ ربات',padding=12);camera_box.pack(side='left',fill='both',expand=True)
        self.camera_label=ttk.Label(camera_box,text='منتظر اتصال دوربین ربات',anchor='center')
        self.camera_label.pack(fill='both',expand=True)
        self.media_status=tk.StringVar()
        ttk.Label(camera_box,textvariable=self.media_status,wraplength=620,justify='right').pack(fill='x',pady=4)
        bar=ttk.Frame(camera_box);bar.pack(fill='x',pady=12)
        self.camera_button=ttk.Button(bar,text='روشن‌کردن دوربین',command=self.camera);self.camera_button.pack(side='right',padx=5)
        self.mic_button=ttk.Button(bar,text='شنیدن صدای محیط ربات',command=self.microphone);self.mic_button.pack(side='left',padx=5)
        talk_box=ttk.LabelFrame(camera_box,text='صحبت از ریموت به ربات',padding=8);talk_box.pack(fill='x',pady=4)
        self.talk_status=tk.StringVar(value='دکمه را نگه دار و با میکروفون این دستگاه صحبت کن.')
        self.talk_button=ttk.Button(talk_box,text='🎙 نگه دار و صحبت کن — F2')
        self.talk_button.pack(fill='x');self.talk_button.bind('<ButtonPress-1>',lambda e:self.talk_begin())
        self.talk_button.bind('<ButtonRelease-1>',lambda e:self.talk_end())
        self.talk_button.bind('<Leave>',lambda e:self.talk_end())
        ttk.Label(talk_box,textvariable=self.talk_status,wraplength=620).pack(fill='x')
        root.bind('<KeyPress-F2>',lambda e:self.talk_begin());root.bind_all('<KeyRelease-F2>',lambda e:self.talk_end(),add='+')
        controls=ttk.Frame(body,padding=(20,4));controls.pack(side='right',fill='y')
        self.acquire_button=ttk.Button(controls,text='فعال‌کردن کنترل',command=self.acquire);self.acquire_button.pack(fill='x',pady=12)
        arrows=ttk.Frame(controls);arrows.pack(pady=15)
        self.buttons={}
        for direction,label,row,col in [('forward','↑ جلو',0,1),('left','← چپ',1,0),('right','راست →',1,2),('backward','↓ عقب',2,1)]:
            button=ttk.Button(arrows,text=label,width=10)
            button.grid(row=row,column=col,padx=4,pady=8,ipady=14)
            button.bind('<ButtonPress-1>',lambda event,d=direction:self.start_drive(d))
            button.bind('<ButtonRelease-1>',lambda event:self.brake())
            self.buttons[direction]=button
        tk.Button(controls,text='■ توقف و آزادکردن کنترل',bg='#af3349',fg='white',font=('Tahoma',11,'bold'),
                  command=self.stop,padx=12,pady=15).pack(fill='x',pady=12)
        ttk.Label(controls,textvariable=self.motion,wraplength=280,justify='right').pack(fill='x',pady=10)
        self.drive_block=''
        self.drive_notice=tk.StringVar()
        ttk.Label(controls,textvariable=self.drive_notice,wraplength=280,justify='right').pack(fill='x')
        ttk.Label(controls,text='فلش را نگه دار؛ با رهاکردن درخواست توقف پایه ارسال می‌شود.\nکلید Space: توقف و آزادکردن کنترل',
                  wraplength=280,justify='right').pack(fill='x',pady=10)
        head_box=ttk.LabelFrame(controls,text='سر و زاویهٔ دوربین',padding=8);head_box.pack(fill='x',pady=6)
        self.head_status=tk.StringVar(value='برای تشخیص کنترل سر، اتصال ربات را بزن.')
        ttk.Label(head_box,textvariable=self.head_status,wraplength=265,justify='right').pack(fill='x')
        head_pad=ttk.Frame(head_box);head_pad.pack(pady=5)
        self.head_buttons=[]
        for direction,label,row,col in [('up','سر بالا',0,1),('left','سر چپ',1,0),('center','روبه‌رو',1,1),('right','سر راست',1,2),('down','سر پایین',2,1)]:
            button=ttk.Button(head_pad,text=label,width=8,command=lambda d=direction:self.head_command(d))
            button.grid(row=row,column=col,padx=2,pady=3);self.head_buttons.append(button)
        self.arm_tab=ttk.Frame(self.tabs,padding=22);self.tabs.add(self.arm_tab,text='کنترل بازوها')
        self.arm_status=tk.StringVar(value='منتظر اتصال اپ ربات')
        self.arm_feedback=tk.StringVar()
        self.arm_side=tk.StringVar(value='راست')
        self.arm_percent=tk.StringVar(value='2')
        self.arm_confirmed=tk.BooleanVar(value=False)
        ttk.Label(self.arm_tab,text='کنترل درصدی بازوهای تیمو',font=('Tahoma',16,'bold')).pack(anchor='e',pady=(0,12))
        ttk.Label(self.arm_tab,text='اول توقف را بزن. پس از بررسی توقف و استراحت بازوها، کنترل را فعال و آماده‌سازی را تأیید کن.',
                  wraplength=730,justify='right').pack(anchor='e',pady=5)
        row=ttk.Frame(self.arm_tab);row.pack(anchor='e',pady=8)
        self.arm_acquire=ttk.Button(row,text='فعال‌کردن کنترل',command=self.acquire)
        self.arm_acquire.pack(side='right',padx=5)
        ttk.Combobox(row,textvariable=self.arm_side,values=('راست','چپ'),state='readonly',width=7).pack(side='right',padx=5)
        ttk.Label(row,text='درصد هدف').pack(side='right',padx=3)
        ttk.Spinbox(row,from_=2,to=100,textvariable=self.arm_percent,width=5).pack(side='right',padx=5)
        ttk.Label(row,text='٪').pack(side='right')
        self.arm_confirm=ttk.Checkbutton(self.arm_tab,variable=self.arm_confirmed,command=self.update_arm_buttons)
        self.arm_confirm.pack(anchor='e',pady=5)
        actions=ttk.Frame(self.arm_tab);actions.pack(anchor='e',pady=5)
        self.arm_actions={}
        for action,label in [('begin','آماده‌سازی'),('move','ارسال یک گام'),('rest','یک گام به استراحت'),
                             ('finish','پایان آزمون بازو')]:
            button=ttk.Button(actions,text=label,command=lambda value=action:self.arm_command(value))
            button.pack(side='right',padx=5)
            self.arm_actions[action]=button
        ttk.Label(self.arm_tab,textvariable=self.arm_status,wraplength=730,justify='right').pack(anchor='e',pady=8)
        ttk.Label(self.arm_tab,textvariable=self.arm_feedback,wraplength=730,justify='right').pack(anchor='e')
        ttk.Button(self.arm_tab,text='توقف و آزادکردن کنترل',command=self.stop).pack(anchor='e',pady=10)
        self.arm_side.trace_add('write',self.arm_goal_changed)
        self.arm_percent.trace_add('write',self.arm_goal_changed)
        self.project_panes=ProjectPanes(self,self.tabs)
        self.face_pane=FacePane(self,self.tabs)
        ttk.Button(top,text='توقف',command=self.stop).pack(side='left',padx=6)
        self.events=tk.Text(root,height=6,state='disabled',font=('Tahoma',10));self.events.pack(fill='x',padx=18,pady=(0,18))
        for key,d in [('Up','forward'),('Down','backward'),('Left','left'),('Right','right')]:
            root.bind('<KeyPress-'+key+'>',lambda e,d=d:self.start_drive(d))
            root.bind('<KeyRelease-'+key+'>',lambda e:self.brake())
        root.bind('<space>',lambda e:self.stop() if not self.text_focus() and self.tabs.select() in (str(self.manual_tab),str(self.arm_tab)) else None)
        root.bind('<FocusOut>',self.focus_out);root.protocol('WM_DELETE_WINDOW',self.close)
        self.update_buttons()
        self.login_local()
        root.after(300,self.refresh);root.after(400,self.hold);root.after(250,self.frame);root.after(80,self.audio)
    def login_local(self):
        sid,session=self.gateway.local_operator()
        self.client.cookie='timo_session='+sid;self.client.csrf=session['csrf'];self.logged=True
    def quick_connect(self):
        if self.setting_up:return
        with self.gateway.lock:
            if self.gateway.owner:
                self.status.set('برای تنظیم دوبارهٔ اتصال، ابتدا کنترل را آزاد کن.');return
            self.gateway.maintenance=True
        self.setting_up=True;self.connect_button['state']='disabled'
        self.update_buttons()
        self.status.set('در حال پیدا کردن ربات در اتصال ADB…')
        self.task('find_robot',lambda:quick_connect.Adb().devices(),self.choose_robot,self.setup_failed)
    def choose_robot(self,devices):
        if not devices:self.setup_failed('ربات به ADB متصل نیست؛ اتصال وایرلس قبلی را برقرار کن.');return
        if len(devices)==1:self.setup_robot(devices[0]);return
        panel=tk.Toplevel(self.root);panel.title('انتخاب ربات');panel.geometry('650x180');panel.transient(self.root)
        ttk.Label(panel,text='بیش از یک دستگاه متصل است؛ ربات موردنظر را انتخاب کن.',padding=15).pack()
        selected=tk.StringVar(value=self.config.get('robot_serial') if self.config.get('robot_serial') in devices else devices[0])
        ttk.Combobox(panel,textvariable=selected,values=devices,state='readonly',width=70).pack(padx=15)
        def proceed():serial=selected.get();panel.destroy();self.setup_robot(serial)
        def cancel():panel.destroy();self.setup_failed('انتخاب ربات لغو شد.')
        ttk.Button(panel,text='اتصال',command=proceed).pack(pady=15);panel.protocol('WM_DELETE_WINDOW',cancel)
    def setup_robot(self,serial):
        self.status.set('تنظیم خودکار ربات؛ کمی صبر کن…')
        def progress(message):
            if not self.closing:self.root.after(0,lambda:self.status.set(message))
        def allow(origin):
            with self.gateway.lock:
                if origin not in self.config['allowed_origins']:self.config['allowed_origins'].append(origin)
        def done(value):
            self.gateway.maintenance=False;self.setting_up=False;self.connect_button['state']='normal';self.config['robot_serial']=value['serial'];self.update_buttons()
            (APP_DIR/'config.json').write_text(json.dumps(self.config,indent=2),encoding='utf-8')
            self.status.set('تنظیمات ارسال شد؛ منتظر اتصال اپ ربات هستیم.'+(' مجوزهای نمایشگر ربات را تأیید کن.' if value['permission_notice'] else ''))
            self.root.after(1200,self.refresh_now)
        self.task('setup_robot',lambda:quick_connect.connect(self.config,self.server.server_port,APP_DIR,serial,progress,allow),done,self.setup_failed)
    def setup_failed(self,message):
        self.gateway.maintenance=False;self.setting_up=False;self.connect_button['state']='normal';self.status.set(message);self.update_buttons()
        messagebox.showinfo('اتصال ربات',message,parent=self.root)
    def task(self, name, call, done=None, failure=None):
        # درخواست شبکه در پس‌زمینه است و تغییر رابط به نخ Tk برمی‌گردد.
        if self.closing or name in self.busy:return
        self.busy.add(name)
        future=self.pool.submit(call)
        def finish(f):
            try:value=f.result();error=None
            except Exception as exc:value=None;error=str(exc)
            def apply():
                self.busy.discard(name)
                if self.closing:return
                if error:
                    if failure:failure(error)
                    else:self.status.set(error)
                elif done:done(value)
            if not self.closing:
                try:self.root.after(0,apply)
                except RuntimeError:pass
        future.add_done_callback(finish)
    def login(self):
        value=self.password.get()
        self.task('login',lambda:self.client.request('/api/login',{'password':value}),
                  lambda _:self.login_done())
    def login_done(self):
        self.password.set('');self.logged=True;self.status.set('ورود انجام شد؛ اپ مستقل ربات را متصل کن.');self.root.focus_set();self.refresh_now()
    def save_config(self):
        (APP_DIR/'config.json').write_text(json.dumps(self.config,indent=2),encoding='utf-8')
    def text_focus(self):
        return isinstance(self.root.focus_get(),(tk.Text,tk.Entry,ttk.Entry,ttk.Combobox))
    def update_buttons(self):
        # فعال‌بودن دوربین و آماده‌بودن موتور پایه وضعیت‌های مستقل‌اند.
        if hasattr(self,'project_panes'):self.project_panes.controls()
        if hasattr(self,'face_pane'):self.face_pane.controls()
        self.talk_button['state']='normal' if self.owned and self.caps.get('speaker') and not self.setting_up else 'disabled'
        for b in self.buttons.values():b['state']='normal' if self.owned and self.caps.get('drive') and not self.braking and not self.setting_up else 'disabled'
        reasons={
            'arms':'آزمون بازو، حرکت پایه را قفل کرده. بعد از استراحت هر دو بازو، «پایان آزمون بازو» را بزن.',
            'navigation':'SDK هنوز بیکار بودن ناوبری را تأیید نکرده. وضعیت را در تب «اتاق‌ها و مسیر» ببین.',
        }
        self.drive_notice.set(reasons.get(self.drive_block,'حرکت پایه فعلاً از طرف اپ ربات آماده نیست.')
                              if self.owned and self.caps.get('sdk') and not self.caps.get('drive') else '')
        self.acquire_button['state']='normal' if self.logged and self.caps.get('sdk') and not self.setting_up else 'disabled'
        self.acquire_button['text']='آزادکردن کنترل' if self.owned else 'فعال‌کردن کنترل'
        self.camera_button['state']='normal' if self.owned and self.caps.get('camera') else 'disabled'
        self.mic_button['state']='normal' if self.owned and self.caps.get('microphone') else 'disabled'
        self.camera_button['text']='خاموش‌کردن دوربین' if self.caps.get('camera_active') else 'روشن‌کردن دوربین'
        self.mic_button['text']='خاموش‌کردن میکروفون' if self.caps.get('mic_active') else 'شنیدن صدای محیط ربات'
        for button in self.head_buttons:
            enabled=self.owned and self.caps.get('sdk') and self.caps.get('head') and not self.caps.get('head_arm_rest') and not self.setting_up and time.monotonic()>=self.head_until
            button['state']='normal' if enabled else 'disabled'

        self.update_arm_buttons()

    def arm_goal_changed(self,*_):
        self.arm_confirmed.set(False)
        self.update_arm_buttons()

    def arm_goal(self):
        try:
            goal=int(self.arm_percent.get())
        except ValueError:
            return None
        return goal if 2<=goal<=100 else None

    def update_arm_buttons(self):
        self.arm_acquire['state']=self.acquire_button['state']
        self.arm_acquire['text']=self.acquire_button['text']
        side='left' if self.arm_side.get()=='چپ' else 'right'
        current=self.arm_state.get(side,0)
        other=self.arm_state.get('right' if side=='left' else 'left',0)
        armed=self.arm_state.get('armed',False)
        can_begin=self.arm_state.get('can_begin',False)
        can_finish=self.arm_state.get('can_finish',False)
        available=self.owned and self.caps.get('arm_range') and not self.arm_pending and not self.setting_up and time.monotonic()>=self.arm_until
        ready=available and self.caps.get('arm_range_ready')
        confirmed=self.arm_confirmed.get()
        self.arm_confirm['text']=('بازو و سر را بررسی کردم و این گام را تأیید می‌کنم.' if armed and not can_finish
                                  else 'توقف را بررسی کردم و هر دو بازو در استراحت‌اند.')
        self.arm_confirm['state']='normal' if (ready and (armed or can_begin)) or (available and can_finish) else 'disabled'
        goal=self.arm_goal()
        if goal is None or goal==current or other:
            self.arm_actions['move']['text']='ارسال یک گام'
        else:
            next_goal=2 if current==0 else max(current-8,min(current+8,goal))
            self.arm_actions['move']['text']=f'ارسال یک گام به {next_goal}٪'
        enabled={'begin':ready and can_begin and confirmed,
                 'move':ready and armed and other==0 and goal is not None and goal!=current and confirmed,
                 'rest':ready and armed and current>0 and confirmed,
                 'finish':available and can_finish and confirmed}
        for action,button in self.arm_actions.items():
            button['state']='normal' if enabled[action] else 'disabled'
        if not self.caps.get('arm_range'):
            status='برای ارسال گام، اپ ربات و اتصال SDK را بررسی کن.'
        elif self.owned and can_finish:
            status='برای برگشت به کنترل پایه، استراحت هر دو بازو را تأیید کن و «پایان آزمون بازو» را بزن.'
        elif not armed and not can_begin:
            status='ابتدا دکمهٔ توقف را بزن و نتیجهٔ ارسال به SDK را بررسی کن.'
        elif not self.owned:
            status='برای آماده‌سازی، کنترل را فعال کن.'
        elif not self.caps.get('arm_range_ready'):
            status='منتظر بیکارشدن ناوبری و توقف پایه.'
        elif not armed:
            status='پس از بررسی روی ربات، آماده‌سازی را تأیید کن.'
        else:
            status=f"آخرین هدف درخواستی · چپ {self.arm_state.get('left',0)}٪ · راست {self.arm_state.get('right',0)}٪"
        self.arm_status.set(status)

    def arm_command(self,action):
        if self.arm_actions[action].instate(('disabled',)) or 'arm' in self.busy:
            return
        args={'action':action,'confirmed':self.arm_confirmed.get()}
        if action in ('move','rest'):
            args['side']='left' if self.arm_side.get()=='چپ' else 'right'
            if action=='move':
                args['goal']=self.arm_goal()
        proof=self.client.proof
        self.arm_confirmed.set(False)
        self.arm_pending='sending'
        self.arm_until=time.monotonic()+1.7
        self.arm_feedback.set('در حال ارسال درخواست…')
        self.update_arm_buttons()
        self.root.after(1750,self.update_arm_buttons)
        def done(value):
            if proof==self.client.proof:
                self.arm_pending=value['id']
                self.arm_feedback.set('درخواست در صف است.')
        def failed(message):
            if proof==self.client.proof:
                self.arm_pending=''
                self.arm_feedback.set(message)
                self.update_arm_buttons()
        self.task('arm',lambda:self.client.request('/api/command',{'kind':'arm_range','args':args},control_proof=proof),done,failed)

    def head_command(self,direction):
        if not self.owned or not self.caps.get('head') or time.monotonic()<self.head_until:return
        if self.caps.get('head_arm_rest'):return
        self.head_until=time.monotonic()+1.2;self.update_buttons();self.root.after(1250,self.update_buttons)
        proof=self.client.proof
        kind='head_reset' if direction=='center' else 'head_step'
        args={} if direction=='center' else {'direction':direction}
        self.task('head',lambda:self.client.request('/api/command',{'kind':kind,'args':args},control_proof=proof),
                  lambda _:self.motion.set('فرمان سر در صف ارسال است؛ نتیجه را پایین پنجره ببین.'))
    def acquire(self):
        if self.owned:self.stop();return
        def done(value):
            self.client.proof=value['control_token'];self.epoch=value.get('drive_epoch',0);self.owned=True;self.motion.set('کنترل در اختیار شماست.');self.update_buttons()
        self.task('acquire',lambda:self.client.request('/api/control/acquire',{}),done)
    def refresh_now(self):
        if not self.logged:return
        if self.setting_up:return
        proof=self.client.proof
        def done(state):
            if self.setting_up:return
            self.caps=state.get('capabilities',{})
            self.drive_block=state.get('drive_block','')
            self.arm_state=state.get('arm_range',{})
            self.head_status.set(state.get('head_notice') or 'کنترل سر هنوز شناسایی نشده است؛ اتصال ربات را بزن.')
            issues=[state.get(key,'') for key in ('media_notice','camera_error','mic_error')]
            self.media_status.set(' | '.join(dict.fromkeys(x for x in issues if x)))
            self.diagnostics='\n'.join([self.media_status.get(),self.head_status.get()]+state.get('diagnostics',[]))
            if proof==self.client.proof and self.owned and not state['control_owned']:self.release_local()
            if proof==self.client.proof and state['control_owned']:self.epoch=max(self.epoch,state.get('drive_epoch') or 0)
            self.status.set(('ربات متصل است' if state['online'] else 'اپ مستقل ربات متصل نیست')+
                            (' · SDK متصل' if self.caps.get('sdk') else ' · SDK قطع')+
                            (' · کنترل با دستگاه دیگر' if state['control_busy'] else ''))
            rows=state.get('results',[])
            result=next((item for item in rows if item['id']==self.arm_pending),None)
            if result:
                self.arm_pending=''
                self.arm_feedback.set(result['detail'])
            rows=rows[-6:]
            self.events.configure(state='normal');self.events.delete('1.0','end')
            for r in reversed(rows):self.events.insert('end',r['kind']+' · '+r['status']+' · '+r['detail']+'\n')
            self.events.configure(state='disabled')
            if not state.get('camera_live'):
                self.image=None;self.camera_label.configure(image='',text=state.get('camera_error') or 'تصویر تازه‌ای دریافت نشده است.')
            self.update_buttons()
        self.task('status',lambda:self.client.request('/api/status'),done,lambda _:self.renew_local_session())
    def renew_local_session(self):
        # نشست محلی را تازه می‌کنیم. اپراتور باید دوباره کنترل حرکت را فعال کند.
        self.release_local();self.login_local()
    def refresh(self):
        self.refresh_now()
        if not self.closing:self.root.after(650,self.refresh)
    def hold(self):
        if self.owned:
            proof=self.client.proof
            self.task('hold',lambda:self.client.request('/api/control/hold',{},timeout=.8,control_proof=proof),
                      failure=lambda _:self.connection_lost() if proof==self.client.proof else None)
        if not self.closing:self.root.after(400,self.hold)
    def start_drive(self,direction):
        if self.driving or self.braking or not self.owned or not self.caps.get('drive') or self.text_focus() or self.tabs.select()!=str(self.manual_tab):return
        self.driving=direction;self.drive_tick()
    def drive_tick(self):
        if not self.driving or not self.owned or self.closing:return
        direction=self.driving;epoch=self.epoch;proof=self.client.proof
        self.task('drive',lambda:self.client.request('/api/command',{'kind':'drive','args':{'direction':direction,'drive_epoch':epoch}},control_proof=proof),
                  failure=lambda _:self.stop() if self.driving==direction else None)
        self.root.after(200,self.drive_tick)
    def brake(self):
        if not self.driving or self.braking:return
        self.driving=None;self.braking=True;self.update_buttons()
        def done(value):self.epoch=value['drive_epoch'];self.braking=False;self.motion.set('درخواست توقف جهت ارسال شد.');self.update_buttons()
        proof=self.client.proof
        self.task('brake',lambda:self.client.request('/api/command',{'kind':'brake','args':{}},control_proof=proof),done,lambda _:self.stop())
    def release_local(self):
        self.talk_end(resume=False)
        self.arm_confirmed.set(False);self.arm_pending='';self.arm_state={}
        self.owned=False;self.driving=None;self.client.proof='';self.braking=False;self.mic_enabled=False
        stream=self.audio_stream;self.audio_stream=None
        if stream:
            self.pool.submit(lambda:self.close_stream(stream))
        self.image=None;self.camera_label.configure(image='',text='کنترل غیرفعال است.');self.update_buttons()
    @staticmethod
    def close_stream(stream):
        try:stream.abort();stream.close()
        except Exception:pass
    def stop(self):
        self.release_local();self.motion.set('درخواست توقف و لغو کنترل؛ توقف فیزیکی هنوز تأیید نشده است.')
        if self.logged:self.task('stop',lambda:self.client.request('/api/command',{'kind':'stop','args':{}}))
    def connection_lost(self):
        self.release_local();self.status.set('ارتباط قطع است؛ پس از اتصال، کنترل را دوباره فعال کن.')
    def talk_begin(self):
        if self.talk_held or not self.owned or not self.caps.get('speaker') or self.setting_up or 'talk_start' in self.busy:return
        self.talk_held=True;self.talk_generation+=1;generation=self.talk_generation;proof=self.client.proof
        self.talk_status.set('در حال بازکردن میکروفون…')
        if self.audio_stream:
            try:self.audio_stream.abort()
            except Exception:pass
        def done(value):
            stream=value['stream_id']
            if generation!=self.talk_generation or not self.talk_held or proof!=self.client.proof:
                self.pool.submit(lambda:self._end_talk_request(stream,proof));return
            self.talk_stream=stream
            def failed(error):self.root.after(0,lambda:self.talk_failed(generation,error))
            def send(pcm,seq):
                self.client.send_pcm(stream,seq,pcm,proof)
                if seq==1:self.root.after(0,lambda:self.talk_sent(generation))
            self.talk_input=LiveMicrophone(send,failed).start()
        self.task('talk_start',lambda:self.client.request('/api/talk/start',{},control_proof=proof),done,
                  lambda error:self.talk_failed(generation,error))
    def talk_sent(self,generation):
        if self.talk_held and generation==self.talk_generation:self.talk_status.set('صدای میکروفون در حال ارسال است؛ برای پایان رها کن.')
    def _end_talk_request(self,stream,proof):
        try:self.client.request('/api/talk/stop',{'stream_id':stream},control_proof=proof)
        except Exception:pass
    def talk_end(self,resume=True):
        was_held=self.talk_held
        self.talk_held=False;self.talk_generation+=1
        capture=self.talk_input;self.talk_input=None
        if capture:capture.stop()
        stream=self.talk_stream;self.talk_stream='';proof=self.client.proof
        if stream:self.pool.submit(lambda:self._end_talk_request(stream,proof))
        if was_held and resume and self.audio_stream and self.owned:
            try:self.audio_stream.start()
            except Exception:pass
        if hasattr(self,'talk_status'):self.talk_status.set('ارسال صدای میکروفون خاموش است.')
    def talk_failed(self,generation,error):
        if generation!=self.talk_generation:return
        self.talk_end();self.talk_status.set('ارسال صدا انجام نشد: '+str(error))

    def camera(self):
        kind='camera_off' if self.caps.get('camera_active') else 'camera_on'
        proof=self.client.proof
        self.task('camera',lambda:self.client.request('/api/command',{'kind':kind,'args':{}},control_proof=proof))
    def microphone(self):
        proof=self.client.proof
        if self.caps.get('mic_active') or self.mic_enabled:
            self.mic_enabled=False
            if self.audio_stream:self.close_stream(self.audio_stream);self.audio_stream=None
            self.task('mic',lambda:self.client.request('/api/command',{'kind':'mic_off','args':{}},control_proof=proof))
        else:
            try:
                import sounddevice as sd
                stream=sd.RawOutputStream(samplerate=16000,channels=1,dtype='int16',blocksize=1600)
                stream.start();self.audio_stream=stream;self.audio_sequence=0;self.mic_enabled=True
            except Exception as e:
                self.status.set('دستگاه پخش صدا باز نشد: '+str(e));return
            self.task('mic',lambda:self.client.request('/api/command',{'kind':'mic_on','args':{}},control_proof=proof),
                      failure=lambda error:self.mic_failed(error))
    def mic_failed(self,error):
        self.mic_enabled=False
        if self.audio_stream:self.close_stream(self.audio_stream);self.audio_stream=None
        self.status.set(error)
    def frame(self):
        if self.owned and self.caps.get('camera_active'):
            proof=self.client.proof
            def done(value):
                if proof!=self.client.proof or not self.owned:return
                try:
                    img=Image.open(io.BytesIO(value[0]));img.thumbnail((680,420))
                    self.image=ImageTk.PhotoImage(img);self.camera_label.configure(image=self.image,text='')
                except Exception:self.camera_label.configure(image='',text='فریم دوربین معتبر نیست.')
            self.task('frame',lambda:self.client.request('/api/frame',binary=True,control_proof=proof),done,lambda _:None)
        if not self.closing:self.root.after(250,self.frame)
    def audio(self):
        if self.owned and self.mic_enabled and self.audio_stream and not self.talk_held:
            cursor=self.audio_sequence;stream=self.audio_stream;proof=self.client.proof
            def receive():
                data,headers=self.client.request('/api/audio?after='+str(cursor),binary=True,control_proof=proof)
                if proof==self.client.proof and stream is self.audio_stream and self.mic_enabled and not self.talk_held:
                    stream.write(data)
                return int(headers.get('X-Audio-Sequence','0'))
            def done(sequence):
                if proof==self.client.proof and stream is self.audio_stream:self.audio_sequence=sequence
            self.task('audio',receive,done,lambda _:None)
        if not self.closing:self.root.after(70,self.audio)
    def connection_info(self):
        panel=tk.Toplevel(self.root);panel.title('تنظیمات پیشرفته');panel.geometry('680x390')
        urls=['http://'+ip+':'+str(self.server.server_port) for ip in local_addresses()]
        ttk.Label(panel,text='آدرس را روی موبایل و ربات وارد کن؛ IP شبکهٔ شرکت را انتخاب کن.',padding=16).pack()
        text=tk.Text(panel,height=4);text.insert('1.0','\n'.join(urls));text.configure(state='disabled');text.pack(fill='x',padx=16)
        ttk.Label(panel,text='Robot Token — فقط داخل اپ Timo Remote Robot وارد شود.',padding=12).pack()
        field=ttk.Entry(panel,show='*');field.insert(0,self.config['agent_token']);field.pack(fill='x',padx=16)
        def copy():panel.clipboard_clear();panel.clipboard_append(self.config['agent_token'])
        ttk.Button(panel,text='کپی Robot Token',command=copy).pack(pady=12)
        ttk.Button(panel,text='تعیین یا تغییر رمز ورود موبایل',command=self.mobile_password).pack(pady=10)
        ttk.Label(panel,text='برای اتصال ویندوز به ربات، فقط دکمهٔ اتصال ربات را بزن.').pack()
    def show_diagnostics(self):
        panel=tk.Toplevel(self.root);panel.title('گزارش وضعیت ربات');panel.geometry('760x380')
        text=tk.Text(panel,wrap='word');text.pack(fill='both',expand=True,padx=12,pady=12)
        value=self.diagnostics or 'هنوز گزارشی از ربات دریافت نشده است.'
        text.insert('1.0',value);text.configure(state='disabled')
        def copy():panel.clipboard_clear();panel.clipboard_append(value)
        ttk.Button(panel,text='کپی گزارش',command=copy).pack(pady=10)
    def mobile_password(self):
        if self.setting_up:return
        with self.gateway.lock:
            if self.gateway.owner:
                messagebox.showinfo('رمز موبایل','ابتدا کنترل ربات را آزاد کن.',parent=self.root);return
        value=simpledialog.askstring('رمز موبایل','یک رمز حداقل ۱۲ نویسه‌ای برای ورود از موبایل انتخاب کن:',show='*',parent=self.root)
        if not value:return
        if len(value)<12:
            messagebox.showinfo('رمز موبایل','رمز باید حداقل ۱۲ نویسه باشد.',parent=self.root);return
        replacement=new_config(value)
        with self.gateway.lock:
            self.gateway.stop('mobile_password_changed');self.gateway.sessions.clear()
            for key in ('password_hash','password_salt'):self.config[key]=replacement[key]
        (APP_DIR/'config.json').write_text(json.dumps(self.config,indent=2),encoding='utf-8')
        self.release_local();self.login_local();messagebox.showinfo('رمز موبایل','رمز موبایل ذخیره شد.',parent=self.root)
    def focus_out(self,event):
        if self.talk_held:self.root.after(30,lambda:self.talk_end() if self.root.focus_displayof() is None else None)
        if self.driving:self.root.after(30,lambda:self.stop() if self.root.focus_displayof() is None else None)
    def close(self):
        self.project_panes.close()
        if self.closing:return
        self.stop();self.closing=True
        self.gateway.shutdown_event.set()
        with self.gateway.lock:self.gateway.stop('desktop_closed')
        threading.Thread(target=self.server.shutdown,daemon=True).start()
        self.server.server_close();self.pool.shutdown(wait=False,cancel_futures=True);self.root.destroy()

def main():
    root=tk.Tk();config_path=APP_DIR/'config.json'
    if config_path.exists():
        config=json.loads(config_path.read_text(encoding='utf-8'))
    else:
        # برای مرورگر و موبایل رمز تصادفی می‌سازیم تا اپراتور از تنظیمات رمز دلخواهش را بگذارد.
        config=new_config(secrets.token_urlsafe(32))
        config_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    for ip in local_addresses():
        origin='http://'+ip+':'+str(config['port'])
        if origin not in config['allowed_origins']:config['allowed_origins'].append(origin)
    config_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    try:Desktop(root,config)
    except OSError as e:messagebox.showerror('اتصال سرویس ریموت','پورت ریموت باز نشد؛ ممکن است برنامهٔ دیگری آن را گرفته باشد.\n'+str(e));root.destroy();return
    root.mainloop()

if __name__=='__main__':main()
