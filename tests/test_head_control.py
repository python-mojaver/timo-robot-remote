import json
import unittest
from unittest.mock import patch
from test_gateway import CAPS, CONFIG, INSTANCE, PASSWORD, Clock, Fault
from test_quick_connect import FakeAdb
import test_quick_connect as setup_helpers
import test_gateway as gateway_helpers
from server import Gateway
from quick_connect import head_profile, SetupError, VERIFIED_SDK_SHA256


class HeadControlTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.gateway=Gateway(CONFIG,self.clock)
        self.sid,_=self.gateway.login(PASSWORD,'127.0.0.1',False)
        self.gateway.poll(INSTANCE,CAPS,[],'',wait=0,head_notice='click once')
        self.proof=self.gateway.acquire(self.sid)['control_token']

    def head(self,direction='left',**extra):
        return self.gateway.command(self.sid,'head_step',dict(direction=direction,**extra),self.proof)

    def test_requires_owner_and_detected_head_controller(self):
        with self.assertRaises(Fault):self.gateway.command(self.sid,'head_step',{'direction':'left'},'')
        self.gateway.poll(INSTANCE,dict(CAPS,head=False),[],'',wait=0)
        with self.assertRaises(Fault):self.head()

    def test_direction_only_wire_and_cannot_inject_motor_angle_or_speed(self):
        self.head(angle=180,speed=255,part=4)
        command=self.gateway.poll(INSTANCE,CAPS,[],'',wait=0)['command']
        self.assertEqual(command['kind'],'head_step')
        self.assertEqual(command['args'],{'direction':'left'})
        self.assertTrue(0<command['valid_for_ms']<=1200)

    def test_rejects_invalid_direction(self):
        for direction in ('forward','backward','center','LEFT',None,12):
            with self.assertRaises(Fault):self.head(direction)
        self.assertFalse(self.gateway.queue)

    def test_clicks_are_rate_limited_and_pending_heads_do_not_accumulate(self):
        self.head()
        with self.assertRaises(Fault) as caught:self.head('right')
        self.assertEqual(caught.exception.status,429)
        self.clock.advance(1)
        with self.assertRaises(Fault):self.head('right')
        self.assertEqual(len(self.gateway.queue),1)

    def test_global_stop_cancels_queued_head_and_keeps_stop_first(self):
        self.head();self.gateway.command(self.sid,'stop',{},self.proof)
        command=self.gateway.poll(INSTANCE,CAPS,[],'',wait=0)['command']
        self.assertEqual(command['kind'],'stop')
        self.assertFalse(self.gateway.queue)
        with self.assertRaises(Fault):self.head()

    def test_head_does_not_send_body_drive_or_change_drive_epoch(self):
        self.head('up');wire=self.gateway.poll(INSTANCE,CAPS,[],'',wait=0)['command']
        self.assertEqual(self.gateway.drive_epoch,0)
        self.assertEqual(wire['args'],{'direction':'up'})
        self.assertEqual(self.gateway.status(self.sid,self.proof)['head_notice'],'')

    def test_old_lease_cannot_issue_head_on_new_control(self):
        old=self.proof;self.gateway.command(self.sid,'stop',{},old)
        self.gateway.poll(INSTANCE,CAPS,[],'',wait=0)
        self.proof=self.gateway.acquire(self.sid)['control_token']
        with self.assertRaises(Fault):self.gateway.command(self.sid,'head_reset',{},old)

    def test_profile_detection_is_read_only_and_accepts_known_vendor_values(self):
        class Reader(FakeAdb):
            def run(self,*args,**kwargs):
                self.calls.append((args,kwargs));return json.dumps({'robot_action_type':'robot_action_new'})
        adb=Reader();self.assertEqual(head_profile(adb,'wireless-robot'),'robot_action_new')
        self.assertEqual(adb.calls[0][0],('shell','cat','/sdcard/.robot_info/.robot_action_type.txt'))
        self.assertEqual(adb.calls[0][1]['serial'],'wireless-robot')

    def test_missing_malformed_or_unknown_profile_remains_disabled(self):
        for raw in ('','{}','[]','null','bad',json.dumps({'robot_action_type':'unknown'}),'x'*4097):
            with patch.object(FakeAdb,'run',return_value=raw):self.assertEqual(head_profile(FakeAdb(),'robot'),'')
        with patch.object(FakeAdb,'run',side_effect=SetupError('permission denied')):
            self.assertEqual(head_profile(FakeAdb(),'robot'),'')

    def test_empty_profile_uses_default_only_for_exact_installed_sdk(self):
        class Reader(FakeAdb):
            digest=VERIFIED_SDK_SHA256
            def run(self,*args,**kwargs):
                self.calls.append((args,kwargs))
                if args[:2]==('shell','cat'):return ''
                if args[:3]==('shell','pm','path'):return 'package:/data/app/~~abc/pkg/base.apk\n'
                if args[:2]==('shell','sha256sum'):return self.digest+'  /data/app/~~abc/pkg/base.apk'
                raise AssertionError(args)
        adb=Reader();self.assertEqual(head_profile(adb,'robot'),'robot_action_ctrl_x')
        self.assertTrue(all(k['serial']=='robot' for a,k in adb.calls))
        adb.digest='0'*64;self.assertEqual(head_profile(adb,'robot'),'')
        with patch.object(Reader,'run',side_effect=SetupError('file unreadable')):
            self.assertEqual(head_profile(Reader(),'robot'),'')

    def test_combined_controller_is_blocked_even_if_older_apk_advertises_head(self):
        self.gateway.poll(INSTANCE, dict(CAPS, head_arm_rest=True), [], '', wait=0)
        self.assertFalse(self.gateway.status(self.sid, self.proof)['capabilities']['head'])
        for kind in ('head_test', 'head_step', 'head_reset'):
            with self.assertRaises(Fault):
                self.gateway.command(self.sid, kind, {'direction': 'left', 'allow_arm_rest': True}, self.proof)
        self.assertFalse(self.gateway.queue)

    def test_pairing_transfers_profile_only_through_protected_receiver(self):
        class Reader(FakeAdb):
            def run(self,*args,**kwargs):
                if args[:2]==('shell','cat'):return '{"robot_action_type":"robot_action_new"}'
                return super().run(*args,**kwargs)
        adb=Reader();setup_helpers.QuickConnectTests.pair(self,adb)
        args=[a for a,k in adb.calls if a[:3]==('shell','am','broadcast')][0]
        i=args.index('head_profile');self.assertEqual(args[i+1],'robot_action_new')


class HeadHTTPTests(unittest.TestCase):
    setUp=gateway_helpers.HttpTests.setUp
    tearDown=gateway_helpers.HttpTests.tearDown
    request=gateway_helpers.HttpTests.request
    login=gateway_helpers.HttpTests.login

    def test_detected_head_notice_and_command_cross_http_boundary(self):
        headers={'Authorization':'Bearer '+self.config['agent_token']}
        status,_,raw=self.request('/api/agent/poll',{'instance':INSTANCE,'capabilities':CAPS,
            'head_notice':'one click per head target','diagnostics':['profile=robot_action_new']},headers)
        self.assertEqual(status,200)
        owner=self.login()
        _,_,raw=self.request('/api/control/acquire',{},owner)
        owner['X-Control-Token']=json.loads(raw)['control_token']
        status,_,raw=self.request('/api/status',headers=owner)
        self.assertEqual(json.loads(raw)['head_notice'],'one click per head target')
        status,_,raw=self.request('/api/command',{'kind':'head_step','args':{'direction':'left','angle':180}},owner)
        self.assertEqual(status,200)
        _,_,raw=self.request('/api/agent/poll',{'instance':INSTANCE,'capabilities':CAPS},headers)
        self.assertEqual(json.loads(raw)['command']['args'],{'direction':'left'})
        self.assertEqual(self.request('/api/command',{'kind':'head_reset'},headers={'Cookie':owner['Cookie']})[0],403)


if __name__=='__main__':unittest.main()
