import unittest
from unittest.mock import patch
from test_gateway import CAPS, CONFIG, INSTANCE, PASSWORD, Clock
from server import Gateway


class ControlTimingTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.gateway = Gateway(CONFIG, self.clock)
        self.sid, _ = self.gateway.login(PASSWORD, '127.0.0.1', False)
        self.gateway.poll(INSTANCE, CAPS, [], '', wait=0)

    def test_wait_is_reported_at_reply_without_consuming_it_twice(self):
        self.gateway.acquire(self.sid)
        def waited(seconds):
            self.assertEqual(seconds, .15)
            self.clock.advance(.15)
        with patch.object(self.gateway.condition, 'wait', side_effect=waited), \
                patch('server.time.monotonic', side_effect=[10.0, 10.15]):
            result = self.gateway.poll(INSTANCE, CAPS, [], '')
        self.assertAlmostEqual(result['server_wait_ms'], 150, delta=1)
        self.assertAlmostEqual(result['lease_remaining_ms'], 1650, delta=1)

    def test_idle_without_owner_keeps_longer_poll_and_zero_lease(self):
        with patch.object(self.gateway.condition, 'wait') as wait:
            result = self.gateway.poll(INSTANCE, CAPS, [], '')
        wait.assert_called_once_with(.65)
        self.assertEqual(result['lease_remaining_ms'], 0)

    def test_queued_stop_bypasses_wait(self):
        proof = self.gateway.acquire(self.sid)['control_token']
        self.gateway.command(self.sid, 'stop', {}, proof)
        with patch.object(self.gateway.condition, 'wait') as wait:
            result = self.gateway.poll(INSTANCE, CAPS, [], '')
        wait.assert_not_called()
        self.assertEqual(result['command']['kind'], 'stop')
        self.assertEqual(result['lease_remaining_ms'], 0)
        self.assertEqual(result['server_wait_ms'], 0)

    def test_sensor_failure_reasons_are_visible_without_changing_ownership(self):
        proof = self.gateway.acquire(self.sid)['control_token']
        self.gateway.poll(INSTANCE, CAPS, [], 'Camera error 1', wait=0,
                          media_notice='lease expired', mic_error='Microphone read -3')
        result = self.gateway.status(self.sid, proof)
        self.assertTrue(result['control_owned'])
        self.assertEqual(result['media_notice'], 'lease expired')
        self.assertEqual(result['mic_error'], 'Microphone read -3')
        self.assertEqual(result['camera_error'], 'Camera error 1')


if __name__ == '__main__': unittest.main()
