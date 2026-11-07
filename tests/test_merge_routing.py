import queue
import unittest
from unittest.mock import Mock, patch
import omg3q_tool as tool

class RestoredSkillRoutingTests(unittest.TestCase):
    def test_daily_task_keeps_original_device_and_control_after_target_changes(self):
        app = tool.App.__new__(tool.App)
        app.sessions = tool.SessionRegistry()
        app.adb = 'adb-A'
        current = ['A']
        app.serial = Mock()
        app.serial.get.side_effect = lambda: current[0]
        app.events = queue.Queue()
        app._worker = Mock()
        skill_type = Mock()
        action = Mock()
        original = app.sessions.device('adb-A', 'A')
        app._run_daily_action(action, skill_type)
        work = app._worker.call_args.args[0]
        app.adb, current[0] = 'adb-B', 'B'
        with patch.object(tool, 'connect') as connect, patch.object(tool, 'foreground_package', return_value=tool.PACKAGE), patch.object(tool, 'AdbDevice') as device:
            work()
        connect.assert_called_once_with('adb-A', 'A')
        self.assertEqual(device.call_args.args[:2], ('adb-A', 'A'))
        self.assertIs(skill_type.call_args.kwargs['stop'], original.control.cancelled)
        self.assertEqual(skill_type.call_args.kwargs['clock'], original.control.clock)
        self.assertFalse(device.call_args.kwargs['capture_options']['dismiss_hints'])
        action.assert_called_once_with(skill_type.return_value)
