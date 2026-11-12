import unittest

from test_gateway import CAPS, CONFIG, INSTANCE, Clock, Fault, Gateway


class ArmCommandBlockTests(unittest.TestCase):
    def test_finish_restores_arm_mode_without_needing_navigation_readiness(self):
        gateway = Gateway(CONFIG, Clock())
        sid, _ = gateway.local_operator()
        caps = dict(CAPS, arm_range=True, arm_range_ready=False, drive=False)
        state = {'armed': False, 'left': 2, 'right': 0, 'can_finish': True}
        gateway.poll(INSTANCE, caps, [], '', wait=0, arm_range=state)
        proof = gateway.acquire(sid)['control_token']
        self.assertEqual(gateway.status(sid, proof)['drive_block'], 'arms')
        with self.assertRaises(Fault):
            gateway.command(sid, 'arm_range', {'action': 'finish', 'confirmed': False}, proof)
        gateway.command(sid, 'arm_range', {'action': 'finish', 'confirmed': True}, proof)
        wire = gateway.poll(INSTANCE, caps, [], '', wait=0, arm_range=state)['command']
        self.assertEqual(wire['args'], {'action': 'finish', 'confirmed': True})

    def test_range_requires_owner_and_confirmation_and_is_cancelled_on_stop(self):
        gateway = Gateway(CONFIG, Clock())
        sid, _ = gateway.local_operator()
        caps = dict(CAPS, arm_range=True, arm_range_ready=True)
        state = {'armed': True, 'left': 0, 'right': 2}
        gateway.poll(INSTANCE, caps, [], '', wait=0, arm_range=state)
        proof = gateway.acquire(sid)['control_token']
        args = {'action': 'move', 'side': 'right', 'goal': 100, 'confirmed': True, 'packet': 'invalid'}
        for bad in ({'goal': 1}, {'goal': 101}, {'goal': True}, {'confirmed': False}):
            with self.assertRaises(Fault):
                gateway.command(sid, 'arm_range', {**args, **bad}, proof)
        with self.assertRaises(Fault):
            gateway.command(sid, 'arm_range', args, '')
        gateway.command(sid, 'arm_range', args, proof)
        self.assertNotIn('packet', gateway.queue[0]['args'])
        with self.assertRaises(Fault):
            gateway.command(sid, 'arm_range', args, proof)
        gateway.command(sid, 'stop', {}, proof)
        self.assertEqual(gateway.poll(INSTANCE, caps, [], '', wait=0)['command']['kind'], 'stop')
        self.assertFalse(gateway.queue)

    def test_legacy_arm_commands_never_reach_robot_and_base_stop_still_queues(self):
        gateway = Gateway(CONFIG, Clock())
        sid, _ = gateway.local_operator()
        legacy = dict(CAPS, arms=True, arms_idle=True, head_arm_rest=True)
        gateway.poll(INSTANCE, legacy, [], '', wait=0)
        proof = gateway.acquire(sid)['control_token']
        self.assertFalse(gateway.status(sid, proof)['capabilities']['arm_wave_stop'])

        for action in ('rest', 'right_up', 'left_up', 'lower'):
            with self.assertRaises(Fault) as error:
                gateway.command(sid, 'arm_step', {'action': action, 'confirmed': True}, proof)
            self.assertEqual(error.exception.status, 409)
        self.assertIsNone(gateway.poll(INSTANCE, legacy, [], '', wait=0)['command'])

        gateway.command(sid, 'stop', {}, proof)
        capable = dict(legacy, arm_wave_stop=True)
        stop = gateway.poll(INSTANCE, capable, [], '', wait=0)['command']
        self.assertEqual((stop['kind'], stop['args']), ('stop', {'reason': 'operator'}))
        self.assertTrue(gateway.status(sid)['capabilities']['arm_wave_stop'])
        self.assertFalse(gateway.status(sid, proof)['control_owned'])
