import json
import urllib.request
import test_gateway as helper
import unittest

class MediaHTTPTests(unittest.TestCase):
    setUp=helper.HttpTests.setUp
    tearDown=helper.HttpTests.tearDown
    request=helper.HttpTests.request
    login=helper.HttpTests.login

    def test_binary_media_round_trip_and_owner_boundary(self):
        caps=dict(helper.CAPS,microphone=True,mic_active=True)
        agent={'Authorization':'Bearer '+self.config['agent_token'],'X-Agent-Instance':helper.INSTANCE}
        self.gateway.poll(helper.INSTANCE,caps,[], '',wait=0)
        operator=self.login()
        _,_,data=self.request('/api/control/acquire',{},operator)
        operator['X-Control-Token']=json.loads(data)['control_token']
        pcm=b'\x23\x01'*1600
        req=urllib.request.Request(self.base+'/api/agent/audio',data=pcm,
            headers=dict(agent,**{'Content-Type':'application/octet-stream'}))
        with urllib.request.urlopen(req,timeout=2) as response:self.assertEqual(response.status,200)
        status,headers,body=self.request('/api/audio?after=0',headers=operator)
        self.assertEqual(status,200);self.assertEqual(body,pcm)
        self.assertEqual(headers['X-Audio-Rate'],'16000')
        self.assertEqual(self.request('/api/audio?after=0',headers={'Cookie':operator['Cookie']})[0],409)
        self.request('/api/command',{'kind':'stop'},operator)
        self.assertEqual(self.request('/api/audio?after=0',headers=operator)[0],409)

    def test_desktop_client_auth_and_stale_proof(self):
        # Pillow must be installed; bundled Windows launcher installs it.
        from desktop import Client
        client=Client(self.base);client.request('/api/login',{'password':helper.PASSWORD})
        self.gateway.poll(helper.INSTANCE,helper.CAPS,[], '',wait=0)
        lease=client.request('/api/control/acquire',{})
        client.proof=lease['control_token'];old=client.proof
        client.request('/api/command',{'kind':'drive','args':{'direction':'forward','drive_epoch':0}})
        client.request('/api/command',{'kind':'stop'})
        client.proof=client.request('/api/control/acquire',{})['control_token']
        with self.assertRaises(RuntimeError):
            client.request('/api/command',{'kind':'drive','args':{'direction':'forward','drive_epoch':0}},control_proof=old)

    def test_local_desktop_session_uses_normal_http_auth(self):
        from desktop import Client
        sid,session=self.gateway.local_operator()
        client=Client(self.base);client.cookie='timo_session='+sid;client.csrf=session['csrf']
        self.gateway.poll(helper.INSTANCE,helper.CAPS,[], '',wait=0)
        self.assertTrue(client.request('/api/status')['online'])
        client.proof=client.request('/api/control/acquire',{})['control_token']
        self.assertTrue(client.request('/api/command',{'kind':'stop'})['ok'])
        self.assertEqual(self.request('/api/local_operator',{})[0],401)

if __name__=='__main__':unittest.main()
