import array
import json
import math
import threading
import unittest
from unittest.mock import patch
from test_gateway import CAPS,CONFIG,INSTANCE,PASSWORD,Clock,Fault
from server import Gateway
from talk_channel import TalkChannel
from talk_input import PcmChunker,LiveMicrophone,mono_pcm
import test_gateway as helpers

class TalkTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.g=Gateway(CONFIG,self.clock)
        self.sid,_=self.g.login(PASSWORD,'127.0.0.1',False)
        self.caps=dict(CAPS,speaker=True)
        self.g.poll(INSTANCE,self.caps,[],'',wait=0)
        self.proof=self.g.acquire(self.sid)['control_token']
    def start(self):return self.g.talk_start(self.sid,self.proof)['stream_id']
    def push(self,stream,seq=1,data=b'\x01\x00'*1600):self.g.talk_push(self.sid,self.proof,stream,seq,data)
    def test_owner_and_new_robot_capability_required(self):
        with self.assertRaises(Fault):self.g.talk_start(self.sid,'')
        self.g.poll(INSTANCE,dict(self.caps,speaker=False),[],'',wait=0)
        with self.assertRaises(Fault):self.start()
    def test_pcm_roundtrip_and_cursor(self):
        stream=self.start();pcm=b'\xff\x7f'*1600;self.push(stream,data=pcm)
        out,packet=self.g.talk_read(INSTANCE,'',0)
        self.assertEqual(out,stream);self.assertEqual(packet[:2],(1,pcm))
        self.assertIsNone(self.g.talk_read(INSTANCE,stream,1)[1])
    def test_old_stream_cannot_write_or_stop_new_stream(self):
        old=self.start();new=self.start()
        with self.assertRaises(Fault):self.push(old)
        with self.assertRaises(Fault):self.g.talk_stop(self.sid,self.proof,old)
        self.assertEqual(self.g.talk.stream,new)
    def test_stop_rejects_late_packet_without_releasing_body_control(self):
        stream=self.start();self.push(stream)
        self.g.talk_stop(self.sid,self.proof,stream)
        self.assertTrue(self.g.status(self.sid,self.proof)['control_owned'])
        with self.assertRaises(Fault):self.push(stream,2)
        self.assertEqual(self.g.talk_read(INSTANCE,stream,0),('',None))
    def test_global_stop_lease_loss_logout_and_agent_replace_drop_audio(self):
        for reason in ('stop','lease','logout','replace'):
            self.setUp();stream=self.start();self.push(stream)
            if reason=='stop':self.g.command(self.sid,'stop',{},self.proof)
            elif reason=='lease':self.clock.advance(2);self.g.status(self.sid,self.proof)
            elif reason=='logout':self.g.logout(self.sid)
            else:self.g.poll('different-agent',self.caps,[],'',wait=0)
            self.assertFalse(self.g.talk.stream);self.assertFalse(self.g.talk.frames)
    def test_bad_pcm_duplicate_sequence_and_other_agent_rejected(self):
        stream=self.start();self.push(stream)
        for seq,data in [(1,b'00'),(0,b'00'),(2,b'x'),(2,b''),(2,b'00'*3201)]:
            with self.assertRaises(Fault):self.push(stream,seq,data)
        with self.assertRaises(Fault):self.g.talk_read('other-agent',stream,0)
    def test_freshness_idle_expiry_and_bounded_backlog(self):
        stream=self.start()
        for seq in range(1,12):self.push(stream,seq)
        self.assertEqual(len(self.g.talk.frames),5)
        self.assertEqual(self.g.talk_read(INSTANCE,stream,0)[1][0],11)
        self.clock.advance(.6)
        self.assertIsNone(self.g.talk_read(INSTANCE,stream,0)[1])
        self.assertEqual(self.g.talk.stream,stream)
        self.clock.advance(.5)
        self.assertEqual(self.g.talk_read(INSTANCE,stream,0),('',None))

class TalkHTTPTests(unittest.TestCase):
    setUp=helpers.HttpTests.setUp
    tearDown=helpers.HttpTests.tearDown
    request=helpers.HttpTests.request
    login=helpers.HttpTests.login
    def test_microphone_policy_and_worklet_are_available_on_same_origin(self):
        status,headers,_=self.request('/')
        self.assertEqual(status,200);self.assertIn('microphone=(self)',headers['Permissions-Policy'])
        self.assertEqual(self.request('/talk-worklet.js')[0],200)

    def test_authenticated_binary_talk_route_and_stop(self):
        robot={'Authorization':'Bearer '+self.config['agent_token'],'X-Agent-Instance':INSTANCE}
        self.request('/api/agent/poll',{'instance':INSTANCE,'capabilities':dict(CAPS,speaker=True)},robot)
        owner=self.login();_,_,raw=self.request('/api/control/acquire',{},owner)
        owner['X-Control-Token']=json.loads(raw)['control_token']
        status,_,raw=self.request('/api/talk/start',{},owner);self.assertEqual(status,200)
        stream=json.loads(raw)['stream_id']
        import urllib.request,urllib.error
        headers=dict(owner,**{'Origin':self.base,'Content-Type':'application/octet-stream','X-Talk-Stream':stream,'X-Audio-Sequence':'1'})
        req=urllib.request.Request(self.base+'/api/talk/audio',b'\x01\x00'*1600,headers)
        with urllib.request.urlopen(req) as result:self.assertEqual(result.status,200)
        req=urllib.request.Request(self.base+'/api/agent/talk?after=0',headers=robot)
        with urllib.request.urlopen(req) as result:
            self.assertEqual(result.status,200);self.assertEqual(result.read(),b'\x01\x00'*1600)
            self.assertEqual(result.headers['X-Talk-Stream'],stream)
        status,_,_=self.request('/api/talk/stop',{'stream_id':stream},owner);self.assertEqual(status,200)
        req=urllib.request.Request(self.base+'/api/agent/talk?after=1',headers=robot)
        with urllib.request.urlopen(req) as result:self.assertEqual(result.status,204);self.assertEqual(result.headers['X-Talk-Active'],'0')
        self.assertEqual(self.request('/api/talk/start',{},headers={'Cookie':owner['Cookie']})[0],403)

class MicrophoneTests(unittest.TestCase):
    def test_stereo_is_downmixed_with_signed_pcm_values(self):
        raw=array.array('h',[1000,3000,-32768,32767,-1000,-3000]).tobytes()
        self.assertEqual(mono_pcm(raw,2),array.array('h',[2000,0,-2000]).tobytes())
        with self.assertRaises(ValueError):mono_pcm(b'00',2)

    def test_resampling_is_continuous_across_callback_boundaries(self):
        samples=array.array('h',[round(15000*math.sin(2*math.pi*440*i/48000)) for i in range(48001)])
        whole=PcmChunker(48000).feed(samples.tobytes())
        chunker=PcmChunker(48000);split=[]
        for start in range(0,len(samples),137):split.extend(chunker.feed(samples[start:start+137].tobytes()))
        self.assertEqual(whole,split);self.assertEqual(len(whole),10)
        self.assertTrue(all(len(x)==3200 for x in whole))
    def test_capture_errors_visible_and_pre_cancel_does_not_start_recording(self):
        errors=[];done=threading.Event()
        class Backend:
            def query_devices(self,**kwargs):raise RuntimeError('No input device')
        mic=LiveMicrophone(lambda *x:None,lambda e:(errors.append(e),done.set()),Backend())
        mic.start();self.assertTrue(done.wait(2));self.assertIn('No input device',errors[0])
    def test_native_capture_sends_pcm_once_then_stops_and_closes(self):
        sent=[];closed=threading.Event();errors=[]
        class Stream:
            active=True
            def __init__(self,**kwargs):self.callback=kwargs['callback']
            def start(self):self.callback(array.array('h',[1234]*4801).tobytes(),4801,None,None)
            def abort(self):self.active=False
            def close(self):closed.set()
        class Backend:
            RawInputStream=Stream
            def query_devices(self,**kw):return {'default_samplerate':48000,'max_input_channels':1}
            def check_input_settings(self,**kw):pass
        def send(pcm,seq):sent.append((pcm,seq));mic.stop()
        mic=LiveMicrophone(send,errors.append,Backend());mic.start()
        self.assertTrue(closed.wait(2));self.assertFalse(errors)
        self.assertEqual(sent,[(array.array('h',[1234]*1600).tobytes(),1)])

    def test_stop_during_device_open_closes_without_capture(self):
        entered=threading.Event();resume=threading.Event();closed=threading.Event();started=[]
        class Stream:
            def __init__(self,**kwargs):entered.set();resume.wait(2)
            def start(self):started.append(True)
            def abort(self):pass
            def close(self):closed.set()
        class Backend:
            RawInputStream=Stream
            def query_devices(self,**kw):return {'default_samplerate':48000,'max_input_channels':1}
            def check_input_settings(self,**kw):pass
        mic=LiveMicrophone(lambda *x:None,lambda e:None,Backend()).start()
        self.assertTrue(entered.wait(2));mic.stop();resume.set();self.assertTrue(closed.wait(2));self.assertFalse(started)

if __name__=='__main__':unittest.main()
