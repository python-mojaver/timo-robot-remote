"""بافر محدود صدای زندهٔ اپراتور در حافظه."""
from collections import deque
import secrets

class TalkChannel:
    FRESH=.5
    IDLE=1.0
    START_IDLE=4.0
    def __init__(self,clock):
        self.clock=clock;self.stream='';self.frames=deque(maxlen=5);self.sequence=0
        self.seen=0;self.uploaded=0;self.delivered=0
    def stop(self):
        self.stream='';self.frames.clear();self.sequence=0
    def tick(self):
        now=self.clock()
        if self.stream and now-self.seen>=(self.IDLE if self.uploaded else self.START_IDLE):self.stop()
        while self.frames and now-self.frames[0][2]>=self.FRESH:self.frames.popleft()
    def start(self):
        self.stop();self.stream=secrets.token_hex(16);self.seen=self.clock()
        self.uploaded=self.delivered=0
        return self.stream
    def push(self,stream,sequence,data):
        self.tick()
        if not self.stream or stream!=self.stream:raise ValueError('stream expired')
        if type(sequence) is not int or sequence<=self.sequence:raise ValueError('old audio sequence')
        if not data or len(data)>6400 or len(data)%2:raise ValueError('expected PCM16 mono 16kHz')
        self.sequence=sequence;self.seen=self.clock();self.uploaded+=1
        self.frames.append((sequence,bytes(data),self.seen))
    def read(self,stream,after):
        self.tick()
        if stream!=self.stream:after=0
        recent=[x for x in self.frames if x[0]>after]
        packet=recent[-1] if len(recent)>2 else recent[0] if recent else None
        if packet:self.delivered+=1
        return self.stream,packet
