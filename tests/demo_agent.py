"""ربات شبیه‌سازی‌شده برای دموی محلی پنل."""
import io
import math
import struct
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Fault, Gateway, Server, new_config

def start_agent(gateway):
    caps=dict(sdk=True,drive=True,stop=True,head=True,camera=True,camera_active=False,microphone=True,mic_active=False)
    def agent():
        from PIL import Image,ImageDraw
        image=Image.new('RGB',(640,480),(30,65,78));draw=ImageDraw.Draw(image)
        draw.rectangle((70,100,570,360),outline=(97,217,191),width=5)
        draw.text((130,215),'SIMULATED ROBOT CAMERA / TEST ONLY',fill='white')
        stream=io.BytesIO();image.save(stream,format='JPEG');frame=stream.getvalue()
        audio=struct.pack('<1600h',*[int(1800*math.sin(2*math.pi*440*i/16000)) for i in range(1600)])
        while not gateway.shutdown_event.is_set():
            response=gateway.poll('demo-agent-instance',caps,['SIMULATED TEST AGENT'], '',wait=.04,head_notice='هر کلیک یک فرمان سر — شبیه‌ساز بدون موتور')
            command=response['command']
            if command:
                kind=command['kind']
                if kind in ('camera_on','camera_off'):caps['camera_active']=kind=='camera_on'
                if kind in ('mic_on','mic_off'):caps['mic_active']=kind=='mic_on'
                if kind=='stop':caps['camera_active']=caps['mic_active']=False
                gateway.acknowledge('demo-agent-instance',command['id'],'submitted','SIMULATED — no hardware')
            if response['lease_remaining_ms']>0:
                try:
                    if caps['camera_active']:gateway.set_frame('demo-agent-instance',frame)
                    if caps['mic_active']:gateway.set_audio('demo-agent-instance',audio)
                except Fault: pass  # وضعیت تازهٔ حسگر با درخواست بعدی اعلام می‌شود.
            time.sleep(.06)
    threading.Thread(target=agent,daemon=True).start()

def main():
    config=new_config('local-test-password',18765)
    gateway=Gateway(config)
    server=Server(('127.0.0.1',18765),gateway)
    start_agent(gateway)
    threading.Thread(target=gateway.watchdog,daemon=True).start()
    print('UI fixture: http://127.0.0.1:18765 / local-test-password',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
