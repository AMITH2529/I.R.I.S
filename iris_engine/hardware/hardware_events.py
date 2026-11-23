from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, Dict, Any
import time

class HardwareState(Enum):
    OFFLINE = 'OFFLINE'
    CONNECTING = 'CONNECTING'
    DISARMED = 'DISARMED'
    ARMED = 'ARMED'

class AlertType(Enum):
    NONE = 'NONE'
    PROXIMITY = 'PROXIMITY'
    MOTION = 'MOTION'

@dataclass
class HardwareTelemetry:
    is_connected: bool = False
    port: str = 'COM5'
    state: HardwareState = HardwareState.OFFLINE
    distance_cm: float = 0.0
    proximity_alert: bool = False
    motion_alert: bool = False
    motion_values: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    light_state: bool = False
    last_event_text: str = ''
    last_event_time: float = 0.0
    last_heartbeat: float = 0.0

    def get_summary(self) -> Dict[str, Any]:
        return {'connected': self.is_connected, 'port': self.port, 'state': self.state.value, 'distance_cm': round(self.distance_cm, 1), 'proximity_alert': self.proximity_alert, 'motion_alert': self.motion_alert, 'motion_g': [round(v, 2) for v in self.motion_values], 'light': self.light_state, 'last_event': self.last_event_text}
