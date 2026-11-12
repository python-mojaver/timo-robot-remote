import copy
import io
import json
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from test_gateway import CONFIG, PASSWORD, Clock, INSTANCE, CAPS
from project_link import ProjectLink, ProjectError, origin
from server import Gateway, Fault


RAW={'motion_config':{'configured':True,'map_name':'HTN Home','revision':'revision_a'},
     'rooms':[{'id':1,'name':'اتاق آقای مجاور','aliases':['اتاق من'],'enabled':True,'map_name':'HTN Home','x':1,'y':2,'z':0,'rotation':.2},
              {'id':2,'name':'wrong map','aliases':[],'enabled':True,'map_name':'other','x':0,'y':0,'z':0,'rotation':0}],
     'memories':[{'body':'private memory'}]}


class FakeLink(ProjectLink):
    def __init__(self):super().__init__({'project_key':'manager-secret'});self.raw=copy.deepcopy(RAW);self.calls=[];self.answer={'response':'سلام','action':None}
    def request(self,path,body=None,timeout=3,binary=False):
        self.calls.append((path,body))
        if path=='/api/agent/state':return copy.deepcopy(self.raw)
        if path=='/api/chat':return copy.deepcopy(self.answer)
        if path=='/api/speak':return {'audio_url':'/generated_audio/test.mp3'}
        if binary:return b'ID3-audio'
        raise AssertionError(path)


class ProjectTests(unittest.TestCase):
    def test_chat_face_metadata_reaches_installed_robot_without_motor_command(self):
        self.caps['face']=True
        self.g.poll(INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)
        for index,mode in enumerate(('normal','happy','sad','angry','surprised','upset')):
            self.link.answer={'response':'باشه، شدم.','face':{'expression':mode,'action':'motor'}}
            result=self.g.project.chat(self.sid,self.proof,'face_chat_'+str(index),'تیمو عصبانی باش')
            expected='sad' if mode=='upset' else mode
            self.assertEqual(result['face'],{'expression':expected})
            item=self.g.poll(INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)['command']
            self.assertEqual(item['kind'],'face')
            self.assertEqual(item['args'],{'expression':'upset' if expected=='angry' else expected})
            self.assertIsNone(result['room_id'])
        self.link.answer={'response':'جواب','face':{'expression':'motor'}}
        result=self.g.project.chat(self.sid,self.proof,'face_chat_invalid','سلام')
        self.assertNotIn('face',result);self.assertFalse(self.g.queue)
    def test_late_face_cannot_use_revoked_control(self):
        self.caps['face']=True;self.g.poll(INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)
        def revoked(*args):
            with self.g.lock:self.g.stop('during_chat')
            return {'response':'باشه','face':{'expression':'angry'}}
        self.link.chat=revoked
        with self.assertRaises(Fault):self.g.project.chat(self.sid,self.proof,'revoked_face_chat','تیمو عصبانی باش')
        self.assertNotIn('face',[item['kind'] for item in self.g.queue])
    def setUp(self):
        self.clock=Clock();self.g=Gateway(CONFIG,self.clock);self.link=FakeLink();self.g.project.link=self.link
        self.nav={'state':'ready','ready':True,'busy':False,'generation':1,'request_id':''}
        self.caps=dict(CAPS,navigation=True,speech=True)
        self.g.poll(INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)
        self.sid,_=self.g.login(PASSWORD,'127.0.0.1',False);self.proof=self.g.acquire(self.sid)['control_token']
    def go(self,rid='navigation_001',room=1):return self.g.project.navigate(self.sid,self.proof,rid,room)
    def test_projection_never_returns_key_memories_or_pose(self):
        value=self.g.project.state(self.sid);s=json.dumps(value)
        self.assertNotIn('manager-secret',s);self.assertNotIn('private memory',s);self.assertNotIn('rotation',s)
        self.assertFalse(value['rooms'][1]['available'])
    def test_room_resolution_idempotence_and_no_coordinate_injection(self):
        first=self.go();self.assertEqual(self.go(),first)
        self.assertEqual(len(self.g.queue),1);self.assertEqual(self.g.queue[0]['args']['pose']['x'],1)
        with self.assertRaises(Fault):self.g.command(self.sid,'nav_room',{'pose':{'x':999}},self.proof)
        with self.assertRaises(Fault):self.g.project.navigate(self.sid,'bad-proof','navigation_002',1)
    def test_map_mismatch_and_invalid_pose_are_rejected(self):
        with self.assertRaises(Fault):self.go(room=2)
        self.link.raw['rooms'][0]['rotation']=999
        with self.assertRaises(Fault):self.go('navigation_003')
        self.assertFalse(self.g.queue)
    def test_map_change_after_enqueue_blocks_native_validation(self):
        self.go();packet=self.g.poll(INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)['command']
        self.link.raw['motion_config']['revision']='revision_b'
        with self.assertRaises(Fault):self.g.project.validate_navigation(INSTANCE,packet['id'])
    def test_validated_pose_and_stop_race(self):
        self.go();packet=self.g.poll(INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)['command']
        result=self.g.project.validate_navigation(INSTANCE,packet['id']);self.assertEqual(result['pose']['x'],1)
        with self.g.lock:self.g.stop('test')
        with self.assertRaises(Fault):self.g.project.validate_navigation(INSTANCE,packet['id'])
    def test_manual_and_navigation_interlock_until_native_terminal_event(self):
        self.go()
        with self.assertRaises(Fault):self.g.command(self.sid,'drive',{'direction':'forward','drive_epoch':0},self.proof)
        self.g.poll(INSTANCE,self.caps,[],'',wait=0,navigation=dict(self.nav,state='verifying',busy=True,ready=False,request_id='navigation_001',generation=2))
        self.assertIsNotNone(self.g.project.pending)
        self.g.poll(INSTANCE,self.caps,[],'',wait=0,navigation=dict(self.nav,state='arrived',request_id='navigation_001',generation=2))
        self.assertIsNone(self.g.project.pending)
        self.g.command(self.sid,'drive',{'direction':'forward','drive_epoch':0},self.proof)
        with self.assertRaises(Fault):self.go('navigation_002')
    def test_no_false_arrival_from_old_ready_snapshot(self):
        self.go();self.g.poll(INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)
        self.assertIsNotNone(self.g.project.pending)
    def test_chat_preserves_response_and_session_but_filters_actions(self):
        self.link.answer={'response':'پاسخ واقعی','action':{'type':'navigate','room_id':1,'pose':{'x':999}}}
        a=self.g.project.chat(self.sid,self.proof,'chat_001','سلام')
        self.assertEqual(a['response'],'پاسخ واقعی');self.assertIsNone(a['room_id']);self.assertFalse(self.g.queue)
        self.g.project.chat(self.sid,self.proof,'chat_002','سلام دوباره')
        calls=[body for path,body in self.link.calls if path=='/api/chat'];self.assertEqual(calls[0]['session_id'],calls[1]['session_id'])
        self.g.project.chat(self.sid,self.proof,'chat_003','سلام',True)
        calls=[body for path,body in self.link.calls if path=='/api/chat'];self.assertNotEqual(calls[-1]['session_id'],calls[0]['session_id'])
    def test_explicit_chat_destination_re_resolves_room_and_ignores_action_pose(self):
        self.link.answer={'response':'درخواست مقصد','action':{'type':'navigate','room_id':1,'pose':{'x':999}}}
        self.g.project.chat(self.sid,self.proof,'chat_001','برو اتاق من')
        self.assertEqual(self.g.queue[0]['args']['pose']['x'],1)
    def test_stop_chat_bypasses_llm_and_releases_control(self):
        r=self.g.project.chat(self.sid,self.proof,'chat_001','توقف')
        self.assertTrue(r['stopped']);self.assertIsNone(self.g.owner);self.assertFalse(self.link.calls)
    def test_speech_is_robot_bound_and_revoked_on_stop(self):
        r=self.g.project.say(self.sid,self.proof,'speech_001','خیلی عالی بود')
        item=self.g.queue[0];data,mime=self.g.project.audio_file(INSTANCE,item['args']['audio_id'])
        self.assertEqual(data,b'ID3-audio');self.assertEqual(mime,'audio/mpeg')
        with self.assertRaises(Fault):self.g.project.audio_file('another_instance',item['args']['audio_id'])
        with self.g.lock:self.g.stop()
        with self.assertRaises(Fault):self.g.project.audio_file(INSTANCE,item['args']['audio_id'])
    def test_generated_audio_url_cannot_escape_upstream_origin(self):
        original=self.link.request
        self.link.request=lambda path,*a,**kw:{'audio_url':'https://other.example/audio.mp3'} if path=='/api/speak' else original(path,*a,**kw)
        with self.assertRaises(ProjectError):self.link.speech('hello')
    def test_origin_rules(self):
        self.assertEqual(origin('http://127.0.0.1:8000/'),'http://127.0.0.1:8000')
        for bad in ['http://example.com','http://0.0.0.0:8000','http://u:p@127.0.0.1','http://127.0.0.1/api','file:///etc/passwd']:
            with self.subTest(bad=bad),self.assertRaises(ProjectError):origin(bad)


class UpstreamHTTPTests(unittest.TestCase):
    def test_actual_http_key_json_audio_and_no_redirect(self):
        seen=[]
        class H(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_GET(self):
                seen.append(self.headers.get('X-Agent-Key'))
                if self.path=='/api/agent/state':raw=json.dumps(RAW).encode();self.send_response(200)
                else:self.send_response(302);self.send_header('Location','http://127.0.0.1:1/');raw=b''
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        http=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            link=ProjectLink({'project_url':'http://127.0.0.1:'+str(http.server_port),'project_key':'private-key'})
            view,_=link.state();self.assertEqual(view['map_name'],'HTN Home');self.assertEqual(seen,['private-key'])
            with self.assertRaises(ProjectError):link.request('/redirect')
        finally:http.shutdown();http.server_close()


if __name__=='__main__':unittest.main()
