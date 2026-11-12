"""انتخاب حالت چهرهٔ آفلاین ربات از رابط ویندوز."""
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

MODES=(('normal','معمولی'),('happy','شاد'),('sad','غمگین'),('angry','عصبانی'),('surprised','متعجب'))

class FacePane:
    def __init__(self,remote,notebook):
        self.remote=remote;self.selected='normal';self.images={};self.thumbs={};self.buttons=[]
        self.tab=ttk.Frame(notebook,padding=18);notebook.add(self.tab,text='چهرهٔ تیمو')
        ttk.Label(self.tab,text='چهرهٔ نمایشگر ربات',font=('Tahoma',18,'bold')).pack(pady=(4,8))
        ttk.Label(self.tab,text='کنترل را فعال کن و یکی از پنج حالت را انتخاب کن. چهره روی نمایشگر خود ربات تغییر می‌کند.',wraplength=850).pack(pady=6)
        self.note=tk.StringVar(value='حالت شروع: معمولی؛ پس از ارتقا، اپ ربات را باز کن.')
        self.preview=ttk.Label(self.tab,anchor='center');self.preview.pack(fill='both',expand=True,pady=12)
        choices=ttk.Frame(self.tab);choices.pack(pady=12)
        assets=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'face-preview'
        for column,(mode,label) in enumerate(MODES):
            try:
                with Image.open(assets/(mode+'.png')) as source:
                    self.images[mode]=ImageTk.PhotoImage(source.resize((640,384),Image.Resampling.LANCZOS))
                    self.thumbs[mode]=ImageTk.PhotoImage(source.resize((144,86),Image.Resampling.LANCZOS))
            except OSError:pass
            button=ttk.Button(choices,text=label,compound='top',command=lambda value=mode:self.choose(value))
            if mode in self.thumbs:button.configure(image=self.thumbs[mode])
            button.grid(row=0,column=column,padx=5,pady=4);self.buttons.append(button)
        ttk.Label(self.tab,textvariable=self.note,wraplength=850,justify='right').pack(pady=12)
        ttk.Label(self.tab,text='روی ربات: چهره تمام‌صفحه است؛ دکمهٔ کوچک ⚙ تنظیمات اتصال را باز می‌کند.',wraplength=850).pack(pady=6)
        if 'normal' in self.images:self.preview.configure(image=self.images['normal'])
        self.controls()

    def controls(self):
        enabled=self.remote.owned and self.remote.caps.get('face') and not self.remote.setting_up and 'face' not in self.remote.busy
        for button in self.buttons:button['state']='normal' if enabled else 'disabled'

    def choose(self,mode):
        r=self.remote
        if mode not in dict(MODES) or not r.owned or not r.caps.get('face') or 'face' in r.busy:return
        proof=r.client.proof;self.note.set('در حال ارسال حالت چهره…')
        def done(value):
            if proof==r.client.proof:
                self.selected=mode
                if mode in self.images:self.preview.configure(image=self.images[mode])
                self.note.set('حالت درخواستی: '+dict(MODES)[mode]+'؛ نتیجهٔ دریافت فرمان در گزارش پایین پنجره دیده می‌شود.')
            self.controls()
        def failed(message):self.note.set(message);self.controls()
        r.task('face',lambda:r.client.request('/api/command',{'kind':'face','args':{'expression':mode}},control_proof=proof),done,failed)
        self.controls()
