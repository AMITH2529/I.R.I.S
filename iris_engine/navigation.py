import time
import math
from typing import Tuple, Optional, Dict, Any, List
import numpy as np
import cv2

class PointerNavigationEngine:
    METHOD_BALLISTICS_RELATIVE = 'ballistics_relative'
    METHOD_HYBRID_GAZE_POSE = 'hybrid_gaze_pose'
    METHOD_ABSOLUTE_ANCHOR = 'absolute_anchor'
    METHOD_VELOCITY_JOYSTICK = 'velocity_joystick'
    ALL_METHODS = [METHOD_BALLISTICS_RELATIVE, METHOD_HYBRID_GAZE_POSE, METHOD_ABSOLUTE_ANCHOR, METHOD_VELOCITY_JOYSTICK]

    def __init__(self, screen_w: int, screen_h: int, default_method: str=METHOD_ABSOLUTE_ANCHOR, base_sensitivity: float=1.0, enable_dwell_click: bool=False, dwell_time: float=0.7, dwell_radius: float=24.0):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.current_method = default_method
        self.sensitivity = base_sensitivity
        self.is_sniper = False
        self.cursor_x = float(screen_w // 2)
        self.cursor_y = float(screen_h // 2)
        self.anchor_laser: Optional[Tuple[float, float]] = None
        self.prev_input_pt: Optional[Tuple[float, float]] = None
        self.prev_time: float = time.time()
        self.enable_dwell_click = enable_dwell_click
        self.dwell_time = dwell_time
        self.dwell_radius = dwell_radius
        self.dwell_start_time: Optional[float] = None
        self.dwell_anchor_pos: Optional[Tuple[float, float]] = None
        self.dwell_progress: float = 0.0
        self.last_dwell_click_time: float = 0.0
        self.dwell_cooldown: float = 1.0
        self.deadzone_inner = 0.8
        self.deadzone_outer = 4.0
        self.ballistic_accel = 2.2
        self.ballistic_v_half = 12.0
        self.is_calibrated = False
        self.affine_matrix: Optional[np.ndarray] = None
        self.calib_step = 0
        self.calib_samples: List[Tuple[float, float]] = []

    def set_method(self, method: str) -> None:
        if method in self.ALL_METHODS:
            self.current_method = method
            self.prev_input_pt = None

    def cycle_method(self) -> str:
        idx = self.ALL_METHODS.index(self.current_method)
        next_idx = (idx + 1) % len(self.ALL_METHODS)
        self.set_method(self.ALL_METHODS[next_idx])
        return self.current_method

    def recenter(self, current_laser: Optional[Tuple[float, float]]=None) -> None:
        self.cursor_x = float(self.screen_w // 2)
        self.cursor_y = float(self.screen_h // 2)
        if current_laser is not None:
            self.anchor_laser = current_laser
            self.prev_input_pt = current_laser
        self.dwell_start_time = None
        self.dwell_progress = 0.0

    def _apply_soft_deadzone(self, dx: float, dy: float) -> Tuple[float, float, float]:
        speed = math.hypot(dx, dy)
        if speed <= self.deadzone_inner:
            return (0.0, 0.0, 0.0)
        elif speed >= self.deadzone_outer:
            factor = 1.0
        else:
            t = (speed - self.deadzone_inner) / (self.deadzone_outer - self.deadzone_inner)
            factor = t * t * (3.0 - 2.0 * t)
        return (dx * factor, dy * factor, speed)

    def _calculate_ballistic_gain(self, speed: float) -> float:
        eff_sens = self.sensitivity * 0.32 if self.is_sniper else self.sensitivity
        gain_mult = 1.0 + self.ballistic_accel * (math.pow(speed, 1.8) / (math.pow(speed, 1.8) + math.pow(self.ballistic_v_half, 1.8)))
        return eff_sens * gain_mult

    def update(self, laser_pt: Tuple[float, float], euler_angles: Tuple[float, float, float], gaze_offset: Tuple[float, float], current_time: float) -> Tuple[float, float, Optional[str]]:
        dt = max(0.0001, current_time - self.prev_time)
        self.prev_time = current_time
        lx, ly = laser_pt
        pitch, yaw, roll = euler_angles
        gx, gy = gaze_offset
        if self.anchor_laser is None:
            self.anchor_laser = (lx, ly)
        if self.prev_input_pt is None:
            self.prev_input_pt = (lx, ly)
        prev_lx, prev_ly = self.prev_input_pt
        raw_dx = lx - prev_lx
        raw_dy = ly - prev_ly
        self.prev_input_pt = (lx, ly)
        if self.current_method == self.METHOD_BALLISTICS_RELATIVE:
            soft_dx, soft_dy, speed = self._apply_soft_deadzone(raw_dx, raw_dy)
            gain = self._calculate_ballistic_gain(speed)
            disp_x = soft_dx * gain * 3.8
            disp_y = soft_dy * gain * 3.8
            self.cursor_x += disp_x
            self.cursor_y += disp_y
        elif self.current_method == self.METHOD_HYBRID_GAZE_POSE:
            soft_dx, soft_dy, speed = self._apply_soft_deadzone(raw_dx, raw_dy)
            gain = self._calculate_ballistic_gain(speed)
            disp_x = soft_dx * gain * 3.6
            disp_y = soft_dy * gain * 3.6
            self.cursor_x += disp_x
            self.cursor_y += disp_y
            trim_scale = 35.0 if not self.is_sniper else 12.0
            iris_trim_x = gx * trim_scale
            iris_trim_y = gy * trim_scale
            eff_x = self.cursor_x + iris_trim_x
            eff_y = self.cursor_y + iris_trim_y
            target_x = float(np.clip(eff_x, 0, self.screen_w - 1))
            target_y = float(np.clip(eff_y, 0, self.screen_h - 1))
            self.cursor_x = np.clip(self.cursor_x, 0, self.screen_w - 1)
            self.cursor_y = np.clip(self.cursor_y, 0, self.screen_h - 1)
            triggered_action = self._update_dwell(target_x, target_y, current_time)
            return (target_x, target_y, triggered_action)
        elif self.current_method == self.METHOD_ABSOLUTE_ANCHOR:
            eff_sens = self.sensitivity * 0.3 if self.is_sniper else self.sensitivity
            ax, ay = self.anchor_laser
            rel_x = (lx - ax) * eff_sens * 0.028
            rel_y = (ly - ay) * eff_sens * 0.032
            raw_dist = math.hypot(rel_x, rel_y)
            d_inner = 0.015
            d_outer = 0.065
            if raw_dist <= d_inner:
                factor = 0.0
            elif raw_dist >= d_outer:
                factor = 1.0
            else:
                t = (raw_dist - d_inner) / (d_outer - d_inner)
                factor = t * t * (3.0 - 2.0 * t)
            rel_x *= factor
            rel_y *= factor
            sign_x = 1.0 if rel_x >= 0 else -1.0
            sign_y = 1.0 if rel_y >= 0 else -1.0
            curved_x = sign_x * math.pow(abs(rel_x), 1.18)
            curved_y = sign_y * math.pow(abs(rel_y), 1.18)
            target_abs_x = self.screen_w / 2.0 + curved_x * (self.screen_w / 2.0)
            target_abs_y = self.screen_h / 2.0 + curved_y * (self.screen_h / 2.0)
            disp = math.hypot(target_abs_x - self.cursor_x, target_abs_y - self.cursor_y)
            speed = disp / max(0.0001, dt)
            speed_ratio = speed * speed / (speed * speed + 1800.0 * 1800.0)
            alpha = 0.4 + 0.48 * speed_ratio
            self.cursor_x = alpha * target_abs_x + (1.0 - alpha) * self.cursor_x
            self.cursor_y = alpha * target_abs_y + (1.0 - alpha) * self.cursor_y
        elif self.current_method == self.METHOD_VELOCITY_JOYSTICK:
            eff_sens = self.sensitivity * 0.35 if self.is_sniper else self.sensitivity
            joy_x = yaw * 0.2
            joy_y = -pitch * 0.25
            soft_jx, soft_jy, j_mag = self._apply_soft_deadzone(joy_x, joy_y)
            if j_mag > 0.0:
                speed_scale = math.pow(j_mag, 1.4) * eff_sens * 350.0
                norm_x = soft_jx / j_mag
                norm_y = soft_jy / j_mag
                self.cursor_x += norm_x * speed_scale * dt
                self.cursor_y += norm_y * speed_scale * dt
        self.cursor_x = float(np.clip(self.cursor_x, 0, self.screen_w - 1))
        self.cursor_y = float(np.clip(self.cursor_y, 0, self.screen_h - 1))
        triggered_action = self._update_dwell(self.cursor_x, self.cursor_y, current_time)
        return (self.cursor_x, self.cursor_y, triggered_action)

    def _update_dwell(self, cur_x: float, cur_y: float, current_time: float) -> Optional[str]:
        if not self.enable_dwell_click:
            self.dwell_progress = 0.0
            self.dwell_start_time = None
            return None
        if self.dwell_anchor_pos is None:
            self.dwell_anchor_pos = (cur_x, cur_y)
            self.dwell_start_time = current_time
            self.dwell_progress = 0.0
            return None
        ax, ay = self.dwell_anchor_pos
        dist = math.hypot(cur_x - ax, cur_y - ay)
        if dist > self.dwell_radius:
            self.dwell_anchor_pos = (cur_x, cur_y)
            self.dwell_start_time = current_time
            self.dwell_progress = 0.0
            return None
        if self.dwell_start_time is None:
            self.dwell_start_time = current_time
        elapsed = current_time - self.dwell_start_time
        self.dwell_progress = min(1.0, elapsed / self.dwell_time)
        if self.dwell_progress >= 1.0:
            if current_time - self.last_dwell_click_time > self.dwell_cooldown:
                self.last_dwell_click_time = current_time
                self.dwell_start_time = current_time
                self.dwell_progress = 0.0
                return 'dwell_click'
        return None

    def get_5point_calibration_targets(self) -> List[Tuple[int, int, str]]:
        w, h = (self.screen_w, self.screen_h)
        return [(w // 2, h // 2, 'CENTER'), (int(w * 0.15), int(h * 0.15), 'TOP-LEFT'), (int(w * 0.85), int(h * 0.15), 'TOP-RIGHT'), (int(w * 0.15), int(h * 0.85), 'BOTTOM-LEFT'), (int(w * 0.85), int(h * 0.85), 'BOTTOM-RIGHT')]

    def solve_affine_calibration(self, recorded_head_pts: List[Tuple[float, float]], target_screen_pts: List[Tuple[float, float]]) -> bool:
        if len(recorded_head_pts) < 3 or len(target_screen_pts) < 3:
            return False
        src = np.array(recorded_head_pts, dtype=np.float32)
        dst = np.array(target_screen_pts, dtype=np.float32)
        matrix, inliers = cv2.estimateAffine2D(src, dst)
        if matrix is not None:
            self.affine_matrix = matrix
            self.is_calibrated = True
            return True
        return False
