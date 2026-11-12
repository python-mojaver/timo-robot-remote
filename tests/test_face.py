import json
import unittest
from pathlib import Path
import test_gateway as helper
from server import Gateway,Fault

class FaceCommandTests(unittest.TestCase):
    def setUp(self):
        self.clock=helper.Clock();self.g=Gateway(helper.CONFIG,self.clock)
        self.caps=dict(helper.CAPS,face=True)
        self.g.poll(helper.INSTANCE,self.caps,[],'',wait=0)
        self.sid,_=self.g.login(helper.PASSWORD,'127.0.0.1',False)
        self.proof=self.g.acquire(self.sid)['control_token']
    def send(self,value,**extra):return self.g.command(self.sid,'face',dict(expression=value,**extra),self.proof)
    def test_face_selection_is_bounded_and_never_becomes_a_motor_command(self):
        for mode in ('normal','happy','sad','angry','surprised','upset'):
            self.send(mode,pose={'x':999},msg_id='motor',angle=180)
            item=self.g.poll(helper.INSTANCE,self.caps,[],'',wait=0)['command']
            wire='upset' if mode=='angry' else 'sad' if mode=='upset' else mode
            self.assertEqual((item['kind'],item['args']),('face',{'expression':wire}))
        for invalid in ('unknown',None,12,{},"normal');alert(1)//"):
            with self.subTest(invalid=invalid),self.assertRaises(Fault):self.send(invalid)
    def test_pending_faces_coalesce_without_dropping_other_commands(self):
        self.g.command(self.sid,'head_test',{},self.proof)
        self.send('sad');self.send('happy')
        self.assertEqual([x['kind'] for x in self.g.queue],['head_test','face'])
        self.assertEqual(self.g.queue[-1]['args']['expression'],'happy')
    def test_requires_new_app_and_current_control_and_expires(self):
        self.g.poll(helper.INSTANCE,helper.CAPS,[],'',wait=0)
        with self.assertRaises(Fault):self.send('happy')
        self.g.poll(helper.INSTANCE,self.caps,[],'',wait=0)
        with self.assertRaises(Fault):self.g.command(self.sid,'face',{'expression':'sad'},'stale')
        self.send('happy');self.clock.advance(1.3)
        self.assertIsNone(self.g.poll(helper.INSTANCE,self.caps,[],'',wait=0)['command'])
        self.g.command(self.sid,'stop',{},self.proof)
        with self.assertRaises(Fault):self.send('sad')
    def test_stop_removes_pending_faces(self):
        self.send('sad');self.g.command(self.sid,'stop',{},self.proof)
        self.assertEqual([x['kind'] for x in self.g.queue],['stop'])

class FaceHTTPTests(unittest.TestCase):
    setUp=helper.HttpTests.setUp
    tearDown=helper.HttpTests.tearDown
    request=helper.HttpTests.request
    login=helper.HttpTests.login
    def test_authenticated_face_delivery_and_public_static_previews(self):
        caps=dict(helper.CAPS,face=True)
        self.gateway.poll(helper.INSTANCE,caps,[],'',wait=0)
        operator=self.login();_,_,raw=self.request('/api/control/acquire',{},operator)
        operator['X-Control-Token']=json.loads(raw)['control_token']
        body={'kind':'face','args':{'expression':'surprised'}}
        self.assertEqual(self.request('/api/command',body,{'Cookie':operator['Cookie']})[0],403)
        self.assertEqual(self.request('/api/command',body,operator)[0],200)
        agent={'Authorization':'Bearer '+self.config['agent_token']}
        code,_,raw=self.request('/api/agent/poll',{'instance':helper.INSTANCE,'capabilities':caps},agent)
        self.assertEqual(code,200);self.assertEqual(json.loads(raw)['command']['args'],{'expression':'surprised'})
        self.assertEqual(self.request('/faces/normal.svg')[0],200)
        self.assertEqual(self.request('/faces/angry.svg')[0],200)
        self.assertEqual(self.request('/faces/../../config.json')[0],404)
        self.assertEqual(self.request('/face-control.js')[0],200)

if __name__=='__main__':unittest.main()
