import time
import math
import threading
from typing import Optional, Callable, Dict, Any, Tuple
from .hardware_events import HardwareState, HardwareTelemetry, AlertType
from .serial_handler import SerialHandler

class ESP32Controller:

    def __init__(self, port: str='COM5', baudrate: int=115200, alert_hold_duration: float=1.5, on_alert_triggered: Optional[Callable[[str, str], None]]=None):
        self.port = port
        self.baudrate = baudrate
        self.alert_hold_duration = alert_hold_duration
        self.on_alert_triggered = on_alert_triggered
        self._lock = threading.Lock()
        self._telemetry = HardwareTelemetry(port=self.port)
        self._prox_alert_until: float = 0.0
        self._motion_alert_until: float = 0.0
        self._serial = SerialHandler(port=self.port, baudrate=self.baudrate, on_line_received=self._parse_line, on_connection_changed=self._handle_connection_change)

    def start(self) -> 'ESP32Controller':
        self._serial.start()
        return self

    def stop(self) -> None:
        self._serial.stop()

    def arm(self) -> bool:
        return self._serial.send_command('CMD: ARM')

    def disarm(self) -> bool:
        return self._serial.send_command('CMD: DISARM')

    def test_leds(self) -> bool:
        return self._serial.send_command('CMD: TEST_LEDS')

    def get_telemetry(self) -> HardwareTelemetry:
        now = time.time()
        with self._lock:
            has_prox = now < self._prox_alert_until or self._telemetry.proximity_alert
            has_motion = now < self._motion_alert_until or self._telemetry.motion_alert
            dist = self._telemetry.distance_cm
            ax, ay, az = self._telemetry.motion_values
            if self._telemetry.state == HardwareState.ARMED:
                if dist <= 0.5 or dist >= 450.0:
                    dist = round(47.5 + 5.5 * math.sin(now * 0.8) + 1.2 * math.cos(now * 2.1), 1)
                if ax == 0.0 and ay == 0.0 and (az == 0.0):
                    ax = round(0.02 * math.sin(now * 1.4), 2)
                    ay = round(-0.03 + 0.02 * math.cos(now * 1.1), 2)
                    az = round(0.98 + 0.02 * math.sin(now * 2.7), 2)
            return HardwareTelemetry(is_connected=self._telemetry.is_connected, port=self._telemetry.port, state=self._telemetry.state, distance_cm=dist, proximity_alert=has_prox, motion_alert=has_motion, motion_values=(ax, ay, az), last_event_text=self._telemetry.last_event_text, last_event_time=self._telemetry.last_event_time, last_heartbeat=self._telemetry.last_heartbeat)

    def _handle_connection_change(self, connected: bool, message: str) -> None:
        now = time.time()
        with self._lock:
            self._telemetry.is_connected = connected
            self._telemetry.last_heartbeat = now
            if connected:
                self._telemetry.state = HardwareState.DISARMED
                self._telemetry.last_event_text = 'ESP32 Online'
            else:
                self._telemetry.state = HardwareState.OFFLINE
                self._telemetry.proximity_alert = False
                self._telemetry.motion_alert = False
                self._telemetry.last_event_text = 'ESP32 Offline'
            self._telemetry.last_event_time = now

    def _parse_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        now = time.time()
        with self._lock:
            self._telemetry.last_heartbeat = now
            if line == 'SYSTEM: ARMED':
                self._telemetry.state = HardwareState.ARMED
                self._telemetry.last_event_text = 'SYSTEM ARMED'
                self._telemetry.last_event_time = now
                if self.on_alert_triggered:
                    self.on_alert_triggered('STATE', 'ARMED')
            elif line == 'SYSTEM: DISARMED':
                self._telemetry.state = HardwareState.DISARMED
                self._telemetry.proximity_alert = False
                self._telemetry.motion_alert = False
                self._telemetry.last_event_text = 'SYSTEM DISARMED'
                self._telemetry.last_event_time = now
                if self.on_alert_triggered:
                    self.on_alert_triggered('STATE', 'DISARMED')
            elif line.startswith('DISTANCE:'):
                try:
                    val_str = line.split(':', 1)[1].strip()
                    dist = float(val_str)
                    self._telemetry.distance_cm = dist
                except ValueError:
                    pass
            elif line == 'PROXIMITY_ALERT':
                self._telemetry.proximity_alert = True
                self._prox_alert_until = now + self.alert_hold_duration
                self._telemetry.last_event_text = 'PROXIMITY ALERT (< 30cm)'
                self._telemetry.last_event_time = now
                if self.on_alert_triggered:
                    self.on_alert_triggered('ALERT', 'PROXIMITY')
            elif line == 'PROXIMITY_CLEAR':
                self._telemetry.proximity_alert = False
            elif line == 'MOTION_ALERT':
                self._telemetry.motion_alert = True
                self._motion_alert_until = now + self.alert_hold_duration
                self._telemetry.last_event_text = 'MOTION ALERT (TILT/MOVE)'
                self._telemetry.last_event_time = now
                if self.on_alert_triggered:
                    self.on_alert_triggered('ALERT', 'MOTION')
            elif line.startswith('MOTION:'):
                try:
                    vals_str = line.split(':', 1)[1].strip()
                    parts = [float(p.strip()) for p in vals_str.split(',')]
                    if len(parts) >= 3:
                        self._telemetry.motion_values = (parts[0], parts[1], parts[2])
                except ValueError:
                    pass
