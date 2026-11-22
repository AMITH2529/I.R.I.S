import numpy as np
import time
from typing import Tuple, Optional, Dict, Any, List

class GestureEngine:

    def __init__(self, wink_hold_time: float=0.18, double_click_hold_time: float=0.3, click_cooldown: float=0.3, scroll_pitch_deadzone: float=8.0, scroll_hold_time: float=0.0, asymmetry_threshold: float=0.25, enable_blink_click: bool=False, blink_click_hold_time: float=0.25, closure_threshold: float=0.2, **kwargs):
        self.wink_hold_time = wink_hold_time
        self.double_click_hold_time = double_click_hold_time
        self.click_cooldown = click_cooldown
        self.scroll_pitch_deadzone = scroll_pitch_deadzone
        self.scroll_hold_time = scroll_hold_time
        self.asymmetry_threshold = asymmetry_threshold
        self.enable_blink_click = enable_blink_click
        self.blink_click_hold_time = blink_click_hold_time
        self.closure_threshold = closure_threshold
        self.EYE_SCREEN_LEFT = [33, 160, 158, 133, 153, 144, 159, 145]
        self.EYE_SCREEN_RIGHT = [362, 385, 387, 263, 373, 380, 386, 374]
        self.EYE_RIGHT_ANATOMIC = self.EYE_SCREEN_LEFT
        self.EYE_LEFT_ANATOMIC = self.EYE_SCREEN_RIGHT
        self.MOUTH_INDICES = [13, 14, 78, 308]
        self.baseline_l_ear = 0.22
        self.baseline_r_ear = 0.22
        self.baseline_mar = 0.015
        self.calibration_samples: List[Tuple[float, float, float]] = []
        self.is_calibrated = False
        self.last_click_time: float = 0.0
        self.blink_start_time: Optional[float] = None
        self.blink_left_clicked: bool = False
        self.blink_double_clicked: bool = False
        self.left_wink_start_time: Optional[float] = None
        self.left_wink_clicked: bool = False
        self.right_wink_start_time: Optional[float] = None
        self.right_wink_clicked: bool = False
        self.is_blinking = False
        self.is_left_winking = False
        self.is_right_winking = False
        self.mouth_opened = False
        self.mouth_open_start_time: Optional[float] = None

    @staticmethod
    def calculate_ear(eye_indices: list, landmarks: np.ndarray) -> float:
        pts = [landmarks[idx][:2] for idx in eye_indices[:6]]
        v1 = np.linalg.norm(pts[1] - pts[5])
        v2 = np.linalg.norm(pts[2] - pts[4])
        h1 = np.linalg.norm(pts[0] - pts[3])
        if len(eye_indices) >= 8:
            p_top = landmarks[eye_indices[6]][:2]
            p_bot = landmarks[eye_indices[7]][:2]
            v_mid = np.linalg.norm(p_top - p_bot)
            if v_mid > 1.0 and h1 > 1e-06:
                return float((v_mid + 0.5 * v1 + 0.5 * v2) / (2.0 * h1))
        return float((v1 + v2) / (2.0 * h1)) if h1 > 1e-06 else 0.0

    @staticmethod
    def calculate_mar(mouth_indices: list, landmarks: np.ndarray) -> float:
        p_upper = landmarks[mouth_indices[0]][:2]
        p_lower = landmarks[mouth_indices[1]][:2]
        p_left = landmarks[mouth_indices[2]][:2]
        p_right = landmarks[mouth_indices[3]][:2]
        vert = np.linalg.norm(p_upper - p_lower)
        horiz = np.linalg.norm(p_left - p_right)
        return float(vert / horiz) if horiz > 1e-06 else 0.0

    def update_baseline(self, l_ear: float, r_ear: float, mar: float) -> None:
        if not self.is_calibrated:
            if l_ear > 0.16 and r_ear > 0.16:
                self.calibration_samples.append((l_ear, r_ear, mar))
                if len(self.calibration_samples) >= 12:
                    self.baseline_l_ear = float(np.mean([s[0] for s in self.calibration_samples]))
                    self.baseline_r_ear = float(np.mean([s[1] for s in self.calibration_samples]))
                    self.baseline_mar = float(np.mean([s[2] for s in self.calibration_samples]))
                    self.is_calibrated = True
            return
        if not self.is_blinking and (not self.is_left_winking) and (not self.is_right_winking):
            if l_ear > 0.14 and r_ear > 0.14:
                self.baseline_l_ear = 0.99 * self.baseline_l_ear + 0.01 * l_ear
                self.baseline_r_ear = 0.99 * self.baseline_r_ear + 0.01 * r_ear
            if 0.005 < mar < 0.035:
                self.baseline_mar = 0.99 * self.baseline_mar + 0.01 * mar

    def recalibrate_baseline(self, l_ear: Optional[float]=None, r_ear: Optional[float]=None, mar: Optional[float]=None) -> None:
        if l_ear is not None and l_ear > 0.1:
            self.baseline_l_ear = float(l_ear)
        if r_ear is not None and r_ear > 0.1:
            self.baseline_r_ear = float(r_ear)
        if mar is not None and mar > 0.005:
            self.baseline_mar = float(mar)
        self.calibration_samples.clear()
        self.is_calibrated = True

    def process_frame(self, landmarks: np.ndarray, current_time: float, pitch_angle: float=0.0, tilt_y: float=0.0, is_mirrored: bool=False, **kwargs) -> Dict[str, Any]:
        if is_mirrored:
            l_indices = self.EYE_SCREEN_LEFT
            r_indices = self.EYE_SCREEN_RIGHT
        else:
            l_indices = self.EYE_LEFT_ANATOMIC
            r_indices = self.EYE_RIGHT_ANATOMIC
        l_ear = self.calculate_ear(l_indices, landmarks)
        r_ear = self.calculate_ear(r_indices, landmarks)
        mar = self.calculate_mar(self.MOUTH_INDICES, landmarks)
        self.update_baseline(l_ear, r_ear, mar)
        drop_l = max(0.0, (self.baseline_l_ear - l_ear) / max(self.baseline_l_ear, 0.0001))
        drop_r = max(0.0, (self.baseline_r_ear - r_ear) / max(self.baseline_r_ear, 0.0001))
        trigger_action: Optional[str] = None
        hold_progress = 0.0
        inner_lip_px = abs(float(landmarks[14][1] - landmarks[13][1]))
        is_inner_open = inner_lip_px >= 8.0
        is_mar_high = mar >= 0.15 or mar >= max(0.12, self.baseline_mar * 3.5)
        self.mouth_opened = bool(is_inner_open and is_mar_high)
        if self.mouth_opened:
            if self.mouth_open_start_time is None:
                self.mouth_open_start_time = current_time
        else:
            self.mouth_open_start_time = None
        mouth_hold_elapsed = current_time - self.mouth_open_start_time if self.mouth_open_start_time else 0.0
        if self.mouth_opened and mouth_hold_elapsed >= self.scroll_hold_time:
            if pitch_angle > max(7.0, self.scroll_pitch_deadzone):
                trigger_action = 'scroll_up'
            elif pitch_angle < -max(7.0, self.scroll_pitch_deadzone):
                trigger_action = 'scroll_down'
        is_dual_blink = drop_l >= self.closure_threshold and drop_r >= self.closure_threshold
        is_left_wink = not is_dual_blink and drop_l >= self.closure_threshold and (drop_r < self.closure_threshold) and (drop_l - drop_r >= 0.12)
        is_right_wink = not is_dual_blink and drop_r >= self.closure_threshold and (drop_l < self.closure_threshold) and (drop_r - drop_l >= 0.12)
        if is_dual_blink:
            self.is_blinking = True
            self.is_left_winking = False
            self.is_right_winking = False
            self.left_wink_start_time = None
            self.right_wink_start_time = None
            if self.blink_start_time is None:
                self.blink_start_time = current_time
                self.blink_left_clicked = False
                self.blink_double_clicked = False
            elapsed = current_time - self.blink_start_time
            if self.enable_blink_click:
                if not self.blink_left_clicked:
                    hold_progress = min(1.0, elapsed / self.blink_click_hold_time)
                    if elapsed >= self.blink_click_hold_time:
                        if current_time - self.last_click_time > self.click_cooldown:
                            trigger_action = 'left_click'
                            self.last_click_time = current_time
                            self.blink_left_clicked = True
                else:
                    double_dur = max(0.1, self.double_click_hold_time - self.blink_click_hold_time)
                    hold_progress = min(1.0, (elapsed - self.blink_click_hold_time) / double_dur)
                    if elapsed >= self.double_click_hold_time and (not self.blink_double_clicked):
                        if current_time - self.last_click_time > self.click_cooldown:
                            trigger_action = 'double_click'
                            self.last_click_time = current_time
                            self.blink_double_clicked = True
            else:
                hold_progress = min(1.0, elapsed / self.double_click_hold_time)
                if elapsed >= self.double_click_hold_time:
                    if current_time - self.last_click_time > self.click_cooldown:
                        trigger_action = 'double_click'
                        self.last_click_time = current_time
                        self.blink_start_time = None
        else:
            if self.enable_blink_click and self.blink_start_time is not None:
                closed_dur = current_time - self.blink_start_time
                if not self.blink_left_clicked and 0.15 <= closed_dur <= 0.48:
                    if current_time - self.last_click_time > self.click_cooldown:
                        trigger_action = 'left_click'
                        self.last_click_time = current_time
            self.is_blinking = False
            self.blink_start_time = None
            self.blink_left_clicked = False
            self.blink_double_clicked = False
        if is_left_wink and (not is_dual_blink):
            self.is_left_winking = True
            self.is_right_winking = False
            self.right_wink_start_time = None
            if self.left_wink_start_time is None:
                self.left_wink_start_time = current_time
                self.left_wink_clicked = False
            elapsed = current_time - self.left_wink_start_time
            hold_progress = max(hold_progress, min(1.0, elapsed / self.wink_hold_time))
            if elapsed >= self.wink_hold_time and (not self.left_wink_clicked):
                if current_time - self.last_click_time > self.click_cooldown:
                    trigger_action = 'left_click'
                    self.last_click_time = current_time
                    self.left_wink_clicked = True
        elif not self.is_blinking:
            if self.left_wink_start_time is not None and (not self.left_wink_clicked):
                wink_dur = current_time - self.left_wink_start_time
                if 0.1 <= wink_dur <= 0.4:
                    if current_time - self.last_click_time > self.click_cooldown:
                        trigger_action = 'left_click'
                        self.last_click_time = current_time
            self.is_left_winking = False
            self.left_wink_start_time = None
            self.left_wink_clicked = False
        if is_right_wink and (not is_dual_blink):
            self.is_right_winking = True
            self.is_left_winking = False
            self.left_wink_start_time = None
            if self.right_wink_start_time is None:
                self.right_wink_start_time = current_time
                self.right_wink_clicked = False
            elapsed = current_time - self.right_wink_start_time
            hold_progress = max(hold_progress, min(1.0, elapsed / self.wink_hold_time))
            if elapsed >= self.wink_hold_time and (not self.right_wink_clicked):
                if current_time - self.last_click_time > self.click_cooldown:
                    trigger_action = 'right_click'
                    self.last_click_time = current_time
                    self.right_wink_clicked = True
        elif not self.is_blinking:
            if self.right_wink_start_time is not None and (not self.right_wink_clicked):
                wink_dur = current_time - self.right_wink_start_time
                if 0.1 <= wink_dur <= 0.4:
                    if current_time - self.last_click_time > self.click_cooldown:
                        trigger_action = 'right_click'
                        self.last_click_time = current_time
            self.is_right_winking = False
            self.right_wink_start_time = None
            self.right_wink_clicked = False
        return {'left_ear': l_ear, 'right_ear': r_ear, 'drop_l': drop_l, 'drop_r': drop_r, 'closure_l': drop_l, 'closure_r': drop_r, 'closure_threshold': self.closure_threshold, 'baseline_l_ear': self.baseline_l_ear, 'baseline_r_ear': self.baseline_r_ear, 'mar': mar, 'mouth_opened': self.mouth_opened, 'is_blinking': self.is_blinking, 'is_left_winking': self.is_left_winking, 'is_right_winking': self.is_right_winking, 'trigger_action': trigger_action, 'hold_progress': hold_progress}

    def should_suppress_cursor(self) -> bool:
        return self.is_left_winking or self.is_right_winking or self.is_blinking or self.mouth_opened
