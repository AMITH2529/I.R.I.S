import unittest
import time
from iris_engine.hardware.hardware_events import HardwareState, HardwareTelemetry
from iris_engine.hardware.esp32_controller import ESP32Controller

class TestHardwareIntegration(unittest.TestCase):

    def test_initial_telemetry_defaults(self):
        ctrl = ESP32Controller(port='COM5')
        t = ctrl.get_telemetry()
        self.assertFalse(t.is_connected)
        self.assertEqual(t.state, HardwareState.OFFLINE)
        self.assertFalse(t.proximity_alert)
        self.assertFalse(t.motion_alert)

    def test_state_change_packet_parsing(self):
        ctrl = ESP32Controller(port='COM5')
        ctrl._handle_connection_change(True, 'Connected')
        t1 = ctrl.get_telemetry()
        self.assertTrue(t1.is_connected)
        self.assertEqual(t1.state, HardwareState.DISARMED)
        ctrl._parse_line('SYSTEM: ARMED')
        t2 = ctrl.get_telemetry()
        self.assertEqual(t2.state, HardwareState.ARMED)
        ctrl._parse_line('SYSTEM: DISARMED')
        t3 = ctrl.get_telemetry()
        self.assertEqual(t3.state, HardwareState.DISARMED)

    def test_distance_and_proximity_alert_parsing(self):
        ctrl = ESP32Controller(port='COM5', alert_hold_duration=0.2)
        ctrl._handle_connection_change(True, 'Connected')
        ctrl._parse_line('SYSTEM: ARMED')
        ctrl._parse_line('DISTANCE:24.5')
        t = ctrl.get_telemetry()
        self.assertAlmostEqual(t.distance_cm, 24.5)
        ctrl._parse_line('PROXIMITY_ALERT')
        t_alert = ctrl.get_telemetry()
        self.assertTrue(t_alert.proximity_alert)
        ctrl._parse_line('PROXIMITY_CLEAR')
        self.assertTrue(ctrl.get_telemetry().proximity_alert)
        time.sleep(0.25)
        self.assertFalse(ctrl.get_telemetry().proximity_alert)

    def test_motion_alert_and_values_parsing(self):
        ctrl = ESP32Controller(port='COM5', alert_hold_duration=0.2)
        ctrl._handle_connection_change(True, 'Connected')
        ctrl._parse_line('MOTION:0.12,-0.05,0.98')
        t = ctrl.get_telemetry()
        self.assertEqual(t.motion_values, (0.12, -0.05, 0.98))
        ctrl._parse_line('MOTION_ALERT')
        t_alert = ctrl.get_telemetry()
        self.assertTrue(t_alert.motion_alert)
if __name__ == '__main__':
    unittest.main()
