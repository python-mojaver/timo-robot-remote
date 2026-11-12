"""تب‌های گفتگو و ناوبری. کارهای طولانی روی صف تمدید کنترل اجرا نمی‌شوند."""
import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk, messagebox
import tkinter as tk


class ProjectPanes:
    def __init__(self, remote, notebook):
        self.remote=remote;self.root=remote.root;self.pool=ThreadPoolExecutor(max_workers=2)
        self.busy=set();self.view={};self.new_session=True
        self.chat_tab=ttk.Frame(notebook,padding=18);self.rooms_tab=ttk.Frame(notebook,padding=18)
        notebook.add(self.chat_tab,text='گفتگو و صدای پاسخ');notebook.add(self.rooms_tab,text='اتاق‌ها و مسیر')
        for tab in (self.chat_tab,self.rooms_tab):
            ttk.Button(tab,text='اتصال پروژهٔ اصلی',command=self.configure).pack(anchor='e',pady=4)
        self.info=tk.StringVar(value='سرور پروژهٔ اصلی را روی پورت ۸۰۰۰ روشن کن؛ سپس اتصال پروژه را تنظیم کن.')
        ttk.Label(self.chat_tab,textvariable=self.info,wraplength=850,justify='right').pack(fill='x',pady=8)
        self.history=tk.Text(self.chat_tab,height=13,wrap='word',state='disabled',font=('Tahoma',11));self.history.pack(fill='both',expand=True)
        self.input=tk.Text(self.chat_tab,height=4,wrap='word',font=('Tahoma',11));self.input.pack(fill='x',pady=10)
        self.input.bind('<Control-Return>',lambda event:self.send_chat())
        bar=ttk.Frame(self.chat_tab);bar.pack(fill='x')
        self.send=ttk.Button(bar,text='ارسال به چت',command=self.send_chat);self.send.pack(side='right',padx=5)
        self.say=ttk.Button(bar,text='فقط پخش همین متن از ربات',command=self.say_input);self.say.pack(side='right',padx=5)
        self.auto_speech=tk.BooleanVar(value=True)
        ttk.Checkbutton(bar,text='پاسخ از ربات خوانده شود',variable=self.auto_speech).pack(side='right',padx=8)
        ttk.Button(bar,text='گفتگوی جدید',command=self.clear).pack(side='left')
        self.speech_note=tk.StringVar(value='متن چت به همان LangGraph و حافظهٔ پروژه فرستاده می‌شود.')
        ttk.Label(self.chat_tab,textvariable=self.speech_note,wraplength=850).pack(fill='x',pady=8)
        self.map=tk.StringVar(value='نقشهٔ مشترک: در انتظار اتصال')
        ttk.Label(self.rooms_tab,textvariable=self.map,font=('Tahoma',13)).pack(fill='x',pady=8)
        ttk.Button(self.rooms_tab,text='تازه‌سازی اتاق‌ها',command=self.refresh).pack(anchor='e')
        self.rooms=ttk.Treeview(self.rooms_tab,columns=('name','map'),show='headings',height=10,selectmode='browse')
        self.rooms.heading('name',text='مقصد');self.rooms.heading('map',text='نقشه / وضعیت')
        self.rooms.column('name',width=350,anchor='e');self.rooms.column('map',width=250,anchor='e');self.rooms.pack(fill='both',expand=True,pady=10)
        self.room_note=tk.StringVar(value='اتاق‌ها فقط از پایگاه دادهٔ پروژه خوانده می‌شوند.')
        ttk.Label(self.rooms_tab,textvariable=self.room_note,wraplength=850,font=('Tahoma',11)).pack(fill='x',pady=10)
        actions=ttk.Frame(self.rooms_tab);actions.pack(fill='x')
        self.go=ttk.Button(actions,text='حرکت به مقصد انتخاب‌شده',command=self.navigate);self.go.pack(side='right',padx=5)
        ttk.Button(actions,text='لغو مسیر و توقف',command=remote.stop).pack(side='right',padx=5)
        ttk.Label(self.rooms_tab,text='رسیدن فقط با پیام پایان مسیر و بررسی بیکار SDK تأیید می‌شود. قطع کنترل، درخواست لغو می‌فرستد.',wraplength=850).pack(fill='x',pady=12)
        self.controls();self.root.after(1000,self.poll)

    def job(self,name,call,done=None,failed=None):
        if name in self.busy or self.remote.closing:return
        self.busy.add(name);self.controls()
        future=self.pool.submit(call)
        def finish(f):
            try:value=f.result();error=None
            except Exception as exc:value=None;error=str(exc)
            def apply():
                self.busy.discard(name)
                if self.remote.closing:return
                if error:
                    self.info.set(error);self.speech_note.set(error)
                    if name=='state':self.view={'error':error};self.room_note.set(error)
                    if failed:failed(error)
                elif done:done(value)
                self.controls()
            if not self.remote.closing:
                try:self.root.after(0,apply)
                except RuntimeError:pass
        future.add_done_callback(finish)

    def controls(self):
        can=self.remote.owned and bool(self.remote.client.proof)
        self.send['state']='normal' if can and 'chat' not in self.busy else 'disabled'
        self.say['state']='normal' if can and 'say' not in self.busy and self.remote.caps.get('speech') else 'disabled'
        nav=self.view.get('navigation',{})
        self.go['state']='normal' if can and nav.get('ready') and not nav.get('busy') and not self.view.get('error') and 'navigate' not in self.busy else 'disabled'

    def append(self,label,text):
        self.history.configure(state='normal');self.history.insert('end',label+'\n'+text+'\n\n');self.history.see('end');self.history.configure(state='disabled')

    def clear(self):
        if 'chat' in self.busy:return
        self.new_session=True;self.history.configure(state='normal');self.history.delete('1.0','end');self.history.configure(state='disabled')

    def send_chat(self):
        text=self.input.get('1.0','end').strip()
        if not text or not self.remote.owned or 'chat' in self.busy:return
        proof=self.remote.client.proof;new=self.new_session;rid=secrets.token_hex(16)
        self.append('شما',text);self.input.delete('1.0','end');self.info.set('در حال دریافت پاسخ از پروژه…')
        def done(value):
            if proof!=self.remote.client.proof:return
            if value.get('error'):self.append('خطا',value['error']);return
            self.new_session=False;self.append('تیمو',value.get('response',''))
            if value.get('notice'):self.append('وضعیت',value['notice'])
            self.info.set('پاسخ دریافت شد.')
            if value.get('stopped'):self.remote.release_local()
            elif self.auto_speech.get() and value.get('response'):self.speak(value['response'])
            self.refresh()
        self.job('chat',lambda:self.remote.client.request('/api/project/chat',{'request_id':rid,'text':text,'new_session':new},timeout=50,control_proof=proof),done)

    def say_input(self):
        self.speak(self.input.get('1.0','end').strip())

    def speak(self,text):
        if not text or not self.remote.owned or 'say' in self.busy:return
        proof=self.remote.client.proof;rid=secrets.token_hex(16);self.speech_note.set('در حال تولید صدا با سرویس فعلی پروژه…')
        def done(value):
            if proof==self.remote.client.proof:self.speech_note.set(value.get('error') or 'درخواست پخش به ربات ارسال شد؛ منتظر وضعیت پخش.')
        self.job('say',lambda:self.remote.client.request('/api/project/say',{'request_id':rid,'text':text},timeout=50,control_proof=proof),done)

    def navigate(self):
        selected=self.rooms.selection()
        if not selected or not self.remote.owned:return
        room_id=int(selected[0]);room=next((r for r in self.view.get('rooms',[]) if r['id']==room_id),None)
        if not room or not room['available']:self.room_note.set('این مقصد با نقشهٔ مشترک تطابق ندارد.');return
        proof=self.remote.client.proof;rid=secrets.token_hex(16);self.room_note.set('در حال بررسی مقصد…')
        def done(value):self.room_note.set(value.get('error') or 'درخواست حرکت ثبت شد؛ وضعیت SDK را منتظر بمان.');self.refresh()
        self.job('navigate',lambda:self.remote.client.request('/api/project/navigate',{'request_id':rid,'room_id':room_id},timeout=5,control_proof=proof),done)

    def refresh(self):
        if not self.remote.logged:return
        def done(value):
            self.view=value;self.map.set('نقشهٔ مشترک: '+(value.get('map_name') or 'تنظیم نشده'))
            self.info.set(value.get('error') or 'پروژه متصل است؛ برای ارسال، کنترل ربات را فعال نگه دار.')
            selected=self.rooms.selection();self.rooms.delete(*self.rooms.get_children())
            for room in value.get('rooms',[]):self.rooms.insert('', 'end',iid=str(room['id']),values=(room['name'],room['map_name'] if room['available'] else 'نقشه نامطابق / غیرفعال'))
            if selected and self.rooms.exists(selected[0]):self.rooms.selection_set(selected[0])
            nav=value.get('navigation',{});self.room_note.set(nav.get('message') or nav.get('state','در انتظار وضعیت SDK'))
            speech=value.get('speech',{})
            if speech.get('message') and 'say' not in self.busy:self.speech_note.set(speech['message'])
        self.job('state',lambda:self.remote.client.request('/api/project/state',timeout=5),done)

    def poll(self):
        if self.remote.closing:return
        if self.remote.config.get('project_key'):self.refresh()
        self.root.after(1800,self.poll)

    def configure(self):
        panel=tk.Toplevel(self.root);panel.title('اتصال به پروژهٔ اصلی');panel.geometry('620x300');panel.transient(self.root)
        ttk.Label(panel,text='سرور فعلی FastAPI و کلید مدیر ایجنت؛ کلید Groq لازم نیست.',padding=12).pack()
        ttk.Label(panel,text='آدرس سرویس').pack();url=ttk.Entry(panel,width=65);url.insert(0,self.remote.config.get('project_url','http://127.0.0.1:8000'));url.pack(pady=6)
        ttk.Label(panel,text='کلید مدیر ایجنت (X-Agent-Key)').pack();key=ttk.Entry(panel,width=65,show='*');key.insert(0,self.remote.config.get('project_key',''));key.pack(pady=6)
        note=tk.StringVar();ttk.Label(panel,textvariable=note,wraplength=550).pack(pady=8)
        def save():
            config=dict(self.remote.config,project_url=url.get().strip(),project_key=key.get().strip());note.set('در حال بررسی اتصال…')
            def done(value):
                self.remote.config.update(project_url=config['project_url'],project_key=config['project_key'])
                self.remote.save_config();panel.destroy();self.refresh()
            self.job('configure',lambda:self.remote.gateway.project.configure(config),done,note.set)
        ttk.Button(panel,text='بررسی و ذخیرهٔ اتصال',command=save).pack(pady=8)

    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)
