import json
import unittest
import test_gateway as helper
from test_project import FakeLink

class ProjectHTTPTests(unittest.TestCase):
    setUp=helper.HttpTests.setUp
    tearDown=helper.HttpTests.tearDown
    request=helper.HttpTests.request
    login=helper.HttpTests.login

    def ready(self):
        self.gateway.project.link=FakeLink()
        self.nav=dict(state='ready',ready=True,busy=False,generation=1,request_id='')
        self.caps=dict(helper.CAPS,speech=True)
        self.agent={'Authorization':'Bearer '+self.config['agent_token'],'X-Agent-Instance':helper.INSTANCE}
        self.gateway.poll(helper.INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)
        self.owner=self.login()
        _,_,body=self.request('/api/control/acquire',{},self.owner)
        self.owner['X-Control-Token']=json.loads(body)['control_token']

    def test_room_delivery_validate_terminal_and_second_room_without_restart(self):
        self.ready()
        self.assertEqual(self.request('/api/project/state')[0],401)
        body={'request_id':'navigation_001','room_id':1,'pose':{'x':999}}
        self.assertEqual(self.request('/api/project/navigate',body,{'Cookie':self.owner['Cookie']})[0],403)
        self.assertEqual(self.request('/api/project/navigate',body,dict(self.owner,Origin='https://other.invalid'))[0],403)
        self.assertEqual(self.request('/api/project/navigate',body,self.owner)[0],200)
        packet=self.gateway.poll(helper.INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)['command']
        claim={'command_id':packet['id']}
        self.assertEqual(self.request('/api/agent/navigation/validate',claim)[0],401)
        code,_,raw=self.request('/api/agent/navigation/validate',claim,self.agent)
        self.assertEqual(code,200);self.assertEqual(json.loads(raw)['pose']['x'],1)
        nav=dict(self.nav,state='arrived',generation=2,request_id='navigation_001')
        self.gateway.poll(helper.INSTANCE,self.caps,[],'',wait=0,navigation=nav)
        body['request_id']='navigation_002'
        self.assertEqual(self.request('/api/project/navigate',body,self.owner)[0],200)
        self.assertEqual(self.request('/api/command',{'kind':'stop'},self.owner)[0],200)
        self.assertEqual(self.request('/api/agent/navigation/validate',claim,self.agent)[0],409)

    def test_chat_speech_bytes_and_stop_revoke(self):
        self.ready()
        code,_,raw=self.request('/api/project/chat',{'request_id':'chat_001','text':'سلام'},self.owner)
        self.assertEqual(code,200);self.assertEqual(json.loads(raw)['response'],'سلام')
        code,_,raw=self.request('/api/project/say',{'request_id':'speech_001','text':'خیلی عالی بود'},self.owner)
        self.assertEqual(code,200)
        command=self.gateway.poll(helper.INSTANCE,self.caps,[],'',wait=0,navigation=self.nav)['command']
        path='/api/agent/speech/'+command['args']['audio_id']
        self.assertEqual(self.request(path)[0],401)
        code,headers,raw=self.request(path,headers=self.agent)
        self.assertEqual((code,raw),(200,b'ID3-audio'));self.assertEqual(headers['Content-Type'],'audio/mpeg')
        self.request('/api/command',{'kind':'stop'},self.owner)
        self.assertEqual(self.request(path,headers=self.agent)[0],404)

    def test_project_navigation_requires_stop_and_rejects_malformed_status(self):
        self.ready()
        self.gateway.poll(helper.INSTANCE,dict(self.caps,stop=False),[],'',wait=0,navigation=self.nav)
        self.assertEqual(self.request('/api/project/navigate',{'request_id':'navigation_001','room_id':1},self.owner)[0],409)
        self.gateway.poll(helper.INSTANCE,self.caps,[],'',wait=0,navigation=dict(self.nav,generation='invalid'))
        self.assertEqual(self.gateway.project.nav['generation'],1)

if __name__=='__main__':unittest.main()
