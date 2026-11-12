import unittest
from test_gateway import CAPS, INSTANCE, CONFIG, PASSWORD, Clock, Fault, LEASE_SECONDS
from server import Gateway


class RemoteMediaTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.gateway = Gateway(CONFIG, self.clock)
        self.sid, _ = self.gateway.login(PASSWORD, '127.0.0.1', False)
        self.caps = dict(CAPS, microphone=True, mic_active=True)
        self.gateway.poll(INSTANCE, self.caps, [], '', wait=0)
        self.proof = self.gateway.acquire(self.sid)['control_token']

    def command(self, kind, args):
        return self.gateway.command(self.sid,kind,args,self.proof)

    def test_brake_retains_owner_and_rejects_late_drive(self):
        self.command('drive', {'direction': 'forward', 'drive_epoch': 0})
        result = self.command('brake', {})
        self.assertEqual(result['drive_epoch'], 1)
        self.assertEqual(self.gateway.owner, self.sid)
        self.assertEqual([c['kind'] for c in self.gateway.queue], ['brake'])
        with self.assertRaises(Fault):
            self.command('drive', {'direction':'forward', 'drive_epoch':0})
        self.command('drive', {'direction':'right', 'drive_epoch':1})
        self.assertEqual([c['kind'] for c in self.gateway.queue], ['brake','drive'])

    def test_media_requires_current_owner_proof(self):
        self.gateway.set_frame(INSTANCE, b'\xff\xd8frame\xff\xd9')
        self.gateway.set_audio(INSTANCE, b'\x01\x00'*1600)
        with self.assertRaises(Fault): self.gateway.media(self.sid, '')
        with self.assertRaises(Fault): self.gateway.media(self.sid, '', 0)
        self.assertEqual(len(self.gateway.media(self.sid,self.proof,0)[1]),3200)
        self.command('stop',{})
        self.assertFalse(self.gateway.audio)
        self.assertIsNone(self.gateway.frame)
        with self.assertRaises(Fault): self.gateway.media(self.sid,self.proof,0)

    def test_pcm_validation_and_instance_binding(self):
        for data in (b'',b'x',b'x'*16002):
            with self.assertRaises(Fault): self.gateway.set_audio(INSTANCE,data)
        with self.assertRaises(Fault): self.gateway.set_audio('other-instance',b'\0\0')

    def test_audio_cursor_backlog_and_expiry(self):
        for n in range(12): self.gateway.set_audio(INSTANCE, bytes([n,0])*1600)
        self.assertEqual(len(self.gateway.audio),8)
        seq,data,_ = self.gateway.media(self.sid,self.proof,0)
        self.assertEqual(seq,12)
        self.assertEqual(data[:2],b'\x0b\0')
        with self.assertRaises(Fault): self.gateway.media(self.sid,self.proof,seq)
        self.clock.advance(.81)
        with self.assertRaises(Fault): self.gateway.media(self.sid,self.proof,0)

    def test_media_read_expires_control_without_watchdog(self):
        self.gateway.set_frame(INSTANCE,b'\xff\xd8frame\xff\xd9')
        self.clock.advance(LEASE_SECONDS+.01)
        with self.assertRaises(Fault): self.gateway.media(self.sid,self.proof)
        self.assertIsNone(self.gateway.owner)

    def test_capture_capability_denial(self):
        self.gateway.poll(INSTANCE,dict(self.caps,microphone=False,mic_active=False),[], '',wait=0)
        with self.assertRaises(Fault): self.command('mic_on',{})
        with self.assertRaises(Fault): self.gateway.set_audio(INSTANCE,b'\0\0')


if __name__ == '__main__': unittest.main()
