"""دریافت PCM از میکروفون ویندوز هنگام نگه‌داشتن دکمهٔ صحبت."""
import array
import queue
import sys
import threading
import time

def mono_pcm(data,channels):
    if channels==1:return bytes(data)
    samples=array.array('h');samples.frombytes(data)
    if sys.byteorder!='little':samples.byteswap()
    if len(samples)%channels:raise ValueError('Incomplete audio frame')
    mixed=array.array('h',(round(sum(samples[i:i+channels])/channels) for i in range(0,len(samples),channels)))
    if sys.byteorder!='little':mixed.byteswap()
    return mixed.tobytes()

class PcmChunker:
    def __init__(self,rate):
        if not 8000<=rate<=192000:raise ValueError('Unsupported input rate')
        self.step=rate/16000;self.position=0.;self.samples=[];self.output=array.array('h')
    def feed(self,data):
        incoming=array.array('h');incoming.frombytes(data)
        if sys.byteorder!='little':incoming.byteswap()
        self.samples.extend(incoming);result=[]
        while self.position+1<len(self.samples):
            i=int(self.position);f=self.position-i
            self.output.append(round(self.samples[i]*(1-f)+self.samples[i+1]*f));self.position+=self.step
            if len(self.output)==1600:
                if sys.byteorder!='little':self.output.byteswap()
                result.append(self.output.tobytes());self.output=array.array('h')
        consumed=min(int(self.position),max(0,len(self.samples)-1))
        self.samples=self.samples[consumed:];self.position-=consumed
        return result

class LiveMicrophone:
    def __init__(self,send,on_error,backend=None):
        self.send=send;self.on_error=on_error;self.backend=backend
        self.closed=threading.Event();self.stream=None;self.pending=queue.Queue(maxsize=2)
    def start(self):
        threading.Thread(target=self._run,daemon=True,name='TimoTalkInput').start();return self
    def stop(self):
        self.closed.set();stream=self.stream
        if stream is not None:
            try:stream.abort()
            except Exception:pass
    def _run(self):
        stream=None
        try:
            if self.backend is None:import sounddevice as sd
            else:sd=self.backend
            info=sd.query_devices(kind='input');rate=round(float(info['default_samplerate']))
            if int(info['max_input_channels'])<1:raise RuntimeError('میکروفون لپ‌تاپ پیدا نشد.')
            channels=1
            try:sd.check_input_settings(samplerate=rate,channels=channels,dtype='int16')
            except Exception:
                if int(info['max_input_channels'])<2:raise
                channels=2;sd.check_input_settings(samplerate=rate,channels=channels,dtype='int16')
            chunker=PcmChunker(rate)
            def callback(data,frames,at,status):
                if self.closed.is_set():return
                try:
                    for pcm in chunker.feed(mono_pcm(data,channels)):
                        item=(time.monotonic(),pcm)
                        try:self.pending.put_nowait(item)
                        except queue.Full:
                            try:self.pending.get_nowait()
                            except queue.Empty:pass
                            self.pending.put_nowait(item)
                except Exception as exc:self.on_error(str(exc));self.closed.set()
            stream=sd.RawInputStream(samplerate=rate,channels=channels,dtype='int16',blocksize=max(1,rate//50),callback=callback)
            self.stream=stream
            if self.closed.is_set():return
            stream.start();seq=0
            while not self.closed.is_set():
                if not stream.active:raise RuntimeError('میکروفون قطع شده است.')
                try:at,pcm=self.pending.get(timeout=.1)
                except queue.Empty:continue
                if time.monotonic()-at>.3:continue
                if self.closed.is_set():break
                seq+=1;self.send(pcm,seq)
        except Exception as exc:
            if not self.closed.is_set():self.on_error(str(exc))
        finally:
            self.closed.set();self.stream=None
            if stream is not None:
                try:stream.abort()
                except Exception:pass
                try:stream.close()
                except Exception:pass
