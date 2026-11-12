import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from quick_connect import Adb, SetupError, connect, PACKAGE, VERSION, local_ip_for_robot
from server import Gateway, new_config

TOKEN='test_connection_token_12345678901234567890'

class FakeAdb:
    def __init__(self,version=VERSION,tunnel=True,configured=True):
        self.calls=[];self.version=version;self.tunnel=tunnel;self.configured=configured
    def devices(self):return ['wireless-robot']
    def run(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        if args[:3]==('shell','dumpsys','package'):return 'versionCode='+str(self.version)
        if args[0]=='install':return 'Success'
        if args[0]=='reverse' and not self.tunnel:raise SetupError('reverse unavailable')
        if args[:3]==('shell','am','broadcast'):return 'Broadcast completed: result='+('1' if self.configured else '0')
        return ''

class QuickConnectTests(unittest.TestCase):
    def pair(self,adb,local='192.168.17.110'):
        with tempfile.TemporaryDirectory() as directory:
            apk=Path(directory)/'apks/TimoRemote-Robot.apk';apk.parent.mkdir();apk.write_bytes(b'test-only')
            origins=[]
            with patch('quick_connect.local_ip_for_robot',return_value=local):
                result=connect({'agent_token':TOKEN},8765,directory,'wireless-robot',allow_origin=origins.append,adb=adb)
            return result,origins
    def test_old_app_is_upgraded_and_only_separate_package_is_configured(self):
        adb=FakeAdb(version=1);result,origins=self.pair(adb)
        self.assertEqual(result['url'],'http://192.168.17.110:8765')
        self.assertEqual(origins,[result['url']])
        self.assertEqual(len([a for a,k in adb.calls if a[0]=='install']),1)
        broadcast=[a for a,k in adb.calls if a[:3]==('shell','am','broadcast')][0]
        self.assertIn(PACKAGE+'/.SetupReceiver',broadcast)
        self.assertIn(TOKEN,broadcast)
        self.assertNotIn('com.htnhome.robotassistant',' '.join(' '.join(a) for a,k in adb.calls))
        self.assertFalse(any('uninstall' in a or 'force-stop' in a for a,k in adb.calls))
    def test_up_to_date_app_does_not_need_install(self):
        adb=FakeAdb();self.pair(adb)
        self.assertFalse(any(a[0]=='install' for a,k in adb.calls))
    def test_version_15_is_upgraded_to_the_bundled_robot_app(self):
        adb=FakeAdb(version=15);self.pair(adb)
        installs=[args for args,_ in adb.calls if args[0]=='install']
        self.assertEqual(len(installs),1)
        self.assertEqual(installs[0][:2],('install','-r'))
        self.assertEqual(Path(installs[0][2]).name,'TimoRemote-Robot.apk')
    def test_tunnel_can_provision_without_detecting_lan_address(self):
        result,_=self.pair(FakeAdb(),local=None)
        self.assertTrue(result['tunnel']);self.assertEqual(result['url'],'http://127.0.0.1:8765')
    def test_lan_can_work_without_adb_reverse(self):
        adb=FakeAdb(tunnel=False);result,_=self.pair(adb)
        self.assertFalse(result['tunnel'])
        broadcast=[a for a,k in adb.calls if a[:3]==('shell','am','broadcast')][0]
        self.assertEqual(broadcast[-1],result['url'])
    def test_no_route_or_tunnel_fails_before_credentials_are_sent(self):
        adb=FakeAdb(tunnel=False)
        with self.assertRaises(SetupError):self.pair(adb,local=None)
        self.assertFalse(any(TOKEN in a for a,k in adb.calls))
    def test_receiver_failure_is_not_reported_as_connected(self):
        with self.assertRaises(SetupError):self.pair(FakeAdb(configured=False))
    def test_no_shell_interpolation_and_private_failure_redacts_secret(self):
        commands=[]
        def runner(command,**kwargs):
            commands.append((command,kwargs))
            return subprocess.CompletedProcess(command,1,'',TOKEN)
        adb=Adb(executable='C:/SDK with spaces/adb.exe',runner=runner)
        with self.assertRaises(SetupError) as error:adb.run('shell','am','broadcast','--es','token',TOKEN,serial='robot',private=True)
        self.assertNotIn(TOKEN,str(error.exception))
        self.assertNotIn('shell',commands[0][1])
        self.assertEqual(commands[0][0][:3],['C:/SDK with spaces/adb.exe','-s','robot'])
    def test_only_authorized_physical_devices_are_listed(self):
        def runner(command,**kwargs):
            return subprocess.CompletedProcess(command,0,'List of devices attached\nrobot device\nlocked unauthorized\nemulator-5554 device\nlost offline\n','')
        self.assertEqual(Adb(executable='adb',runner=runner).devices(),['robot'])
    def test_local_operator_is_separate_from_http_password_login(self):
        gateway=Gateway(new_config('remote-password-123'))
        sid,session=gateway.local_operator()
        self.assertEqual(gateway.session(sid)['csrf'],session['csrf'])
        self.assertTrue(session['csrf'])
    def test_pairing_blocks_new_motion_ownership(self):
        from server import Fault
        gateway=Gateway(new_config('remote-password-123'))
        sid,_=gateway.local_operator()
        gateway.poll('test-robot-123',{'sdk':True,'drive':True,'stop':True},[], '',wait=0)
        gateway.maintenance=True
        with self.assertRaises(Fault):gateway.acquire(sid)
        gateway.maintenance=False
        self.assertTrue(gateway.acquire(sid)['control_token'])

if __name__=='__main__':unittest.main()
