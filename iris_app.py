import os
import sys
import time
import math
import queue
from typing import Tuple, Optional, Dict, Any, List
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iris_engine.camera import ThreadedWebcamStream
from iris_engine.preprocessor import LightingCompensator
from iris_engine.tracker import FastFaceMeshTracker
from iris_engine.pose_estimator import HeadPoseEstimator
from iris_engine.iris_detector import IrisGazeDetector
from iris_engine.filters import OneEuroFilter2D
from iris_engine.gesture_engine import GestureEngine
from iris_engine.navigation import PointerNavigationEngine
from iris_engine.controller import WindowsCursorController
from iris_engine.hardware import ESP32Controller, HardwareState
from iris_engine.audio_feedback import AudioFeedbackEngine
from iris_engine.speech_controller import SpeechControlEngine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
YUNET_PATH = os.path.join(BASE_DIR, 'models', 'face_detection_yunet.onnx')
FACEMESH_PATH = os.path.join(BASE_DIR, 'models', 'FaceMesh.onnx')

def draw_circular_gauge(img: np.ndarray, center: Tuple[int, int], radius: int, progress: float, color: Tuple[int, int, int]=(0, 240, 255), thickness: int=3) -> None:
    cx, cy = center
    cv2.circle(img, (cx, cy), radius, (50, 55, 65), thickness, cv2.LINE_AA)
    if progress > 0.0:
        angle = int(360.0 * min(1.0, max(0.0, progress)))
        cv2.ellipse(img, (cx, cy), (radius, radius), -90, 0, angle, color, thickness, cv2.LINE_AA)

def draw_metric_bar(img: np.ndarray, label: str, value: float, max_val: float, pos: Tuple[int, int], width: int=140, height: int=7, fill_color: Tuple[int, int, int]=(0, 240, 255), threshold: Optional[float]=None) -> None:
    x, y = pos
    cv2.putText(img, label, (x, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (180, 195, 210), 1, cv2.LINE_AA)
    cv2.rectangle(img, (x, y), (x + width, y + height), (32, 38, 48), -1)
    pct = min(1.0, max(0.0, value / max_val)) if max_val > 0 else 0.0
    fill_w = int(width * pct)
    if fill_w > 0:
        cv2.rectangle(img, (x, y), (x + fill_w, y + height), fill_color, -1)
    cv2.rectangle(img, (x, y), (x + width, y + height), (55, 65, 80), 1)
    if threshold is not None and max_val > 0:
        tx = int(x + width * min(1.0, max(0.0, threshold / max_val)))
        cv2.line(img, (tx, y - 2), (tx, y + height + 2), (0, 120, 255), 2)

def render_cyber_dashboard(panel: np.ndarray, nav: PointerNavigationEngine, gestures: Dict[str, Any], hw: Any, is_paused: bool, has_face: bool, fps: float, sensor_log: List[Tuple[str, str, Tuple[int, int, int]]], speech_active: bool=False, speech_listening: bool=False) -> None:
    pw, ph = (panel.shape[1], panel.shape[0])
    panel[:] = (12, 16, 24)
    cv2.rectangle(panel, (10, 6), (pw - 10, 38), (20, 26, 38), -1)
    cv2.rectangle(panel, (10, 6), (pw - 10, 38), (40, 52, 72), 1)
    cv2.putText(panel, 'I.R.I.S. v2.5 MASTER HUD', (18, 26), cv2.FONT_HERSHEY_DUPLEX, 0.42, (0, 240, 255), 1, cv2.LINE_AA)
    if is_paused:
        st_text, st_col = ('PAUSED (SPACE)', (0, 140, 255))
    elif not has_face:
        st_text, st_col = ('SEARCHING...', (0, 200, 255))
    else:
        st_text, st_col = ('ONLINE', (0, 255, 120))
    cv2.putText(panel, st_text, (pw - 110, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.33, st_col, 1, cv2.LINE_AA)

    cv2.rectangle(panel, (10, 44), (pw - 10, 108), (18, 23, 33), -1)
    cv2.rectangle(panel, (10, 44), (pw - 10, 108), (35, 46, 64), 1)
    cv2.putText(panel, 'NAVIGATION & MODES', (18, 59), cv2.FONT_HERSHEY_DUPLEX, 0.33, (255, 255, 255), 1, cv2.LINE_AA)
    mode_display = nav.current_method.replace('_', ' ').upper()
    cv2.putText(panel, f'Mode: {mode_display} [M]', (18, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 230, 255), 1, cv2.LINE_AA)
    snp_col = (255, 100, 255) if nav.is_sniper else (80, 90, 105)
    snp_txt = '[SNIPER: ON]' if nav.is_sniper else '[SNIPER (P)]'
    cv2.putText(panel, snp_txt, (18, 89), cv2.FONT_HERSHEY_SIMPLEX, 0.3, snp_col, 1, cv2.LINE_AA)
    dwl_col = (0, 220, 255) if nav.enable_dwell_click else (80, 90, 105)
    dwl_txt = '[DWELL: ON]' if nav.enable_dwell_click else '[DWELL (W)]'
    cv2.putText(panel, dwl_txt, (126, 89), cv2.FONT_HERSHEY_SIMPLEX, 0.3, dwl_col, 1, cv2.LINE_AA)
    if speech_listening:
        voc_col = (0, 240, 255)
        voc_txt = '[VOICE: HEARD]'
    elif speech_active:
        voc_col = (0, 255, 120)
        voc_txt = '[VOICE: ON]'
    else:
        voc_col = (80, 90, 105)
        voc_txt = '[VOICE (V)]'
    cv2.putText(panel, voc_txt, (230, 89), cv2.FONT_HERSHEY_SIMPLEX, 0.3, voc_col, 1, cv2.LINE_AA)
    cv2.putText(panel, f'Sens: {nav.sensitivity:.2f}x (+/-)', (18, 103), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (180, 195, 210), 1, cv2.LINE_AA)
    sens_pct = min(1.0, max(0.0, (nav.sensitivity - 0.4) / 2.6))
    bar_w = 100
    cv2.rectangle(panel, (160, 98), (160 + bar_w, 104), (32, 38, 48), -1)
    cv2.rectangle(panel, (160, 98), (160 + int(bar_w * sens_pct), 104), (0, 240, 255), -1)
    cv2.rectangle(panel, (160, 98), (160 + bar_w, 104), (55, 65, 80), 1)

    cv2.rectangle(panel, (10, 114), (pw - 10, 186), (18, 23, 33), -1)
    cv2.rectangle(panel, (10, 114), (pw - 10, 186), (35, 46, 64), 1)
    cv2.putText(panel, 'BIOMETRIC EYE & MOUTH', (18, 129), cv2.FONT_HERSHEY_DUPLEX, 0.33, (255, 255, 255), 1, cv2.LINE_AA)
    l_ear = gestures.get('left_ear', 0.18)
    r_ear = gestures.get('right_ear', 0.18)
    mar = gestures.get('mar', 0.015)
    closure_l = gestures.get('closure_l', 0.0)
    closure_r = gestures.get('closure_r', 0.0)
    thresh = gestures.get('closure_threshold', 0.25)
    l_col = (0, 120, 255) if closure_l >= thresh else (0, 255, 140)
    r_col = (0, 120, 255) if closure_r >= thresh else (0, 255, 140)
    draw_metric_bar(panel, f'L Close: {closure_l * 100:.0f}% (EAR {l_ear:.2f})', closure_l, 0.6, (18, 143), width=135, fill_color=l_col, threshold=thresh)
    draw_metric_bar(panel, f'R Close: {closure_r * 100:.0f}% (EAR {r_ear:.2f})', closure_r, 0.6, (165, 143), width=135, fill_color=r_col, threshold=thresh)
    draw_metric_bar(panel, f'Mouth MAR: {mar:.3f}', mar, 0.25, (18, 168), width=135, fill_color=(255, 160, 0), threshold=0.15)
    cv2.putText(panel, f'FPS: {fps:3.0f}', (165, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.31, (160, 175, 190), 1, cv2.LINE_AA)
    if gestures.get('is_blinking'):
        sub_str, sub_col = ('[DUAL BLINK: CLICK TRIGGERED]', (255, 100, 255))
    elif gestures.get('is_left_winking'):
        sub_str, sub_col = ('[LEFT WINK: LEFT CLICK]', (0, 255, 120))
    elif gestures.get('is_right_winking'):
        sub_str, sub_col = ('[RIGHT WINK: RIGHT CLICK]', (0, 220, 255))
    elif nav.dwell_progress > 0.0:
        sub_str, sub_col = (f'[DWELL CHARGING: {int(nav.dwell_progress * 100)}%]', (0, 240, 255))
    else:
        sub_str, sub_col = ('Blink/Release [B] | Wink | Dwell [W]', (0, 240, 255))
    cv2.putText(panel, sub_str, (18, 181), cv2.FONT_HERSHEY_SIMPLEX, 0.28, sub_col, 1, cv2.LINE_AA)

    cv2.rectangle(panel, (10, 192), (pw - 10, 362), (18, 23, 33), -1)
    cv2.rectangle(panel, (10, 192), (pw - 10, 362), (35, 46, 64), 1)
    cv2.putText(panel, 'HARDWARE & HOME AUTOMATION', (18, 206), cv2.FONT_HERSHEY_DUPLEX, 0.33, (255, 255, 255), 1, cv2.LINE_AA)
    hw_conn_badge = f'[{hw.port}] ONLINE' if hw.is_connected else '[COM5] OFFLINE'
    hw_conn_col = (0, 255, 120) if hw.is_connected else (100, 110, 130)
    cv2.putText(panel, hw_conn_badge, (pw - 105, 206), cv2.FONT_HERSHEY_SIMPLEX, 0.3, hw_conn_col, 1, cv2.LINE_AA)
    state_col = (0, 255, 120) if hw.state == HardwareState.ARMED else (0, 60, 255) if hw.state == HardwareState.DISARMED else (120, 130, 140)
    cv2.putText(panel, f'State: [{hw.state.value}]', (18, 221), cv2.FONT_HERSHEY_SIMPLEX, 0.31, state_col, 1, cv2.LINE_AA)
    arm_s_bg = (20, 52, 34) if hw.state == HardwareState.ARMED else (22, 28, 38)
    arm_s_bd = (0, 255, 120) if hw.state == HardwareState.ARMED else (70, 85, 100)
    cv2.rectangle(panel, (215, 209), (272, 224), arm_s_bg, -1)
    cv2.rectangle(panel, (215, 209), (272, 224), arm_s_bd, 1)
    cv2.putText(panel, '[ARM]', (226, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.27, arm_s_bd, 1, cv2.LINE_AA)
    drm_s_bg = (45, 20, 26) if hw.state == HardwareState.DISARMED else (22, 28, 38)
    drm_s_bd = (0, 60, 255) if hw.state == HardwareState.DISARMED else (70, 85, 100)
    cv2.rectangle(panel, (278, 209), (345, 224), drm_s_bg, -1)
    cv2.rectangle(panel, (278, 209), (345, 224), drm_s_bd, 1)
    cv2.putText(panel, '[DISARM]', (283, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.27, drm_s_bd, 1, cv2.LINE_AA)

    is_disarmed = hw.state == HardwareState.DISARMED
    is_armed = hw.state == HardwareState.ARMED
    is_prox = hw.proximity_alert and is_armed
    r1_on, r2_on = (is_disarmed, is_disarmed)
    g1_on, g2_on = (is_armed, is_armed)
    b1_on, b2_on = (is_prox, is_prox)
    cv2.putText(panel, 'LEDs:', (18, 236), cv2.FONT_HERSHEY_SIMPLEX, 0.29, (180, 195, 210), 1, cv2.LINE_AA)
    led_defs = [
        ('R1:25', r1_on, (0, 0, 255), (35, 35, 80)),
        ('R2:26', r2_on, (0, 0, 255), (35, 35, 80)),
        ('G1:27', g1_on, (0, 255, 120), (25, 60, 35)),
        ('G2:32', g2_on, (0, 255, 120), (25, 60, 35)),
        ('B1:33', b1_on, (255, 180, 0), (60, 45, 25)),
        ('B2:23', b2_on, (255, 180, 0), (60, 45, 25)),
        ('WL:13', hw.light_state, (255, 255, 255), (45, 45, 55))
    ]
    led_x = 52
    for label, is_on, on_color, off_color in led_defs:
        dot_col = on_color if is_on else off_color
        cv2.circle(panel, (led_x, 234), 4, dot_col, -1, cv2.LINE_AA)
        if is_on:
            cv2.circle(panel, (led_x, 234), 6, on_color, 1, cv2.LINE_AA)
        cv2.putText(panel, label, (led_x - 14, 248), cv2.FONT_HERSHEY_SIMPLEX, 0.24, dot_col if is_on else (120, 130, 140), 1, cv2.LINE_AA)
        led_x += 42

    light_box_y = 252
    cv2.rectangle(panel, (18, light_box_y), (pw - 18, light_box_y + 44), (22, 28, 40), -1)
    cv2.rectangle(panel, (18, light_box_y), (pw - 18, light_box_y + 44), (45, 60, 85), 1)
    lt_status_col = (255, 255, 255) if hw.light_state else (120, 130, 145)
    lt_status_txt = 'HOME LIGHT: [ON] (GPIO 13)' if hw.light_state else 'HOME LIGHT: [OFF] (GPIO 13)'
    cv2.putText(panel, lt_status_txt, (26, light_box_y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.3, lt_status_col, 1, cv2.LINE_AA)

    tog_side_col = (255, 255, 255) if hw.light_state else (80, 95, 115)
    cv2.rectangle(panel, (24, light_box_y + 20), (190, light_box_y + 40), (25, 55, 40) if hw.light_state else (20, 25, 35), -1)
    cv2.rectangle(panel, (24, light_box_y + 20), (190, light_box_y + 40), (0, 255, 120) if hw.light_state else (65, 80, 95), 1)
    cv2.putText(panel, '[TOGGLE (L)]', (55, light_box_y + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.28, tog_side_col, 1, cv2.LINE_AA)

    cv2.rectangle(panel, (205, light_box_y + 20), (265, light_box_y + 40), (20, 48, 32) if hw.light_state else (20, 25, 35), -1)
    cv2.rectangle(panel, (205, light_box_y + 20), (265, light_box_y + 40), (0, 255, 120) if hw.light_state else (65, 80, 95), 1)
    cv2.putText(panel, '[ON]', (223, light_box_y + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (0, 255, 120) if hw.light_state else (100, 115, 130), 1, cv2.LINE_AA)

    cv2.rectangle(panel, (275, light_box_y + 20), (335, light_box_y + 40), (42, 20, 26) if not hw.light_state else (20, 25, 35), -1)
    cv2.rectangle(panel, (275, light_box_y + 20), (335, light_box_y + 40), (0, 60, 255) if not hw.light_state else (65, 80, 95), 1)
    cv2.putText(panel, '[OFF]', (292, light_box_y + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (0, 60, 255) if not hw.light_state else (100, 115, 130), 1, cv2.LINE_AA)

    dist_val = hw.distance_cm
    dist_valid = 0.5 < dist_val < 450.0
    dist_str = f'{dist_val:.1f} cm' if dist_valid else '--'
    dist_col = (0, 60, 255) if hw.proximity_alert else (0, 240, 255) if dist_valid else (140, 150, 160)
    cv2.putText(panel, f'HC-SR04 Radar (D18/D19): {dist_str}', (18, 312), cv2.FONT_HERSHEY_SIMPLEX, 0.3, dist_col, 1, cv2.LINE_AA)
    cv2.rectangle(panel, (18, 317), (pw - 20, 324), (32, 38, 48), -1)
    if dist_valid:
        gauge_pct = min(1.0, max(0.0, dist_val / 100.0))
        gw = int((pw - 38) * gauge_pct)
        g_col = (0, 60, 255) if dist_val < 30.0 else (0, 220, 255) if dist_val < 60.0 else (0, 255, 120)
        cv2.rectangle(panel, (18, 317), (18 + gw, 324), g_col, -1)
    thresh_x = int(18 + (pw - 38) * (30.0 / 100.0))
    cv2.line(panel, (thresh_x, 315), (thresh_x, 326), (0, 60, 255), 2)
    cv2.rectangle(panel, (18, 317), (pw - 20, 324), (55, 65, 80), 1)

    ax, ay, az = hw.motion_values
    mag = math.sqrt(ax * ax + ay * ay + az * az)
    mot_col = (0, 80, 255) if hw.motion_alert else (0, 255, 120)
    mot_str = '[MOTION!]' if hw.motion_alert else '[STABLE]'
    cv2.putText(panel, f'MPU-6050: AX:{ax:+.2f} AY:{ay:+.2f} AZ:{az:+.2f} {mot_str}', (18, 339), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (190, 205, 220), 1, cv2.LINE_AA)

    top_cmds = nav.get_top_commands(3)
    if top_cmds:
        top_str = ' | '.join([f'{k}:{v}' for k, v in top_cmds])
        cv2.putText(panel, f'Top Intent: {top_str}', (18, 355), cv2.FONT_HERSHEY_SIMPLEX, 0.27, (0, 240, 255), 1, cv2.LINE_AA)
    else:
        cv2.putText(panel, 'Adaptive Interaction: Gaze Velocity Tuned', (18, 355), cv2.FONT_HERSHEY_SIMPLEX, 0.27, (130, 145, 160), 1, cv2.LINE_AA)

    cv2.rectangle(panel, (10, 368), (pw - 10, 508), (18, 23, 33), -1)
    cv2.rectangle(panel, (10, 368), (pw - 10, 508), (35, 46, 64), 1)
    cv2.putText(panel, 'HARDWARE & SENSOR ACTIVITY LOG', (18, 384), cv2.FONT_HERSHEY_DUPLEX, 0.33, (255, 255, 255), 1, cv2.LINE_AA)
    log_y = 402
    for t_str, act_text, col in sensor_log[-6:]:
        cv2.putText(panel, f'{t_str} -> {act_text}', (18, log_y), cv2.FONT_HERSHEY_SIMPLEX, 0.29, col, 1, cv2.LINE_AA)
        log_y += 17
    cv2.putText(panel, '[SPACE] Pause | [C] Center | [L] Light | [V] Voice | [K] Calib', (10, 526), cv2.FONT_HERSHEY_SIMPLEX, 0.27, (130, 145, 160), 1, cv2.LINE_AA)

def main():
    print('=' * 72)
    print('  I.R.I.S. (Intelligent Real-time Interface System) v2.5')
    print('  Neural Assistive Controller with Home Automation & Voice Assistant')
    print('=' * 72)
    controller = WindowsCursorController(enable_sound=False)
    audio = AudioFeedbackEngine(enable_chimes=True, enable_speech=True)
    screen_w, screen_h = controller.get_screen_size()
    print(f'[INFO] Display Resolution: {screen_w} x {screen_h}')

    speech_queue: queue.Queue = queue.Queue()
    def on_speech_command(action_name: str, action_data: Dict[str, Any]) -> None:
        speech_queue.put((action_name, action_data))

    speech_engine = SpeechControlEngine(command_callback=on_speech_command)
    speech_enabled = speech_engine.start()
    if speech_enabled:
        audio.speak('I.R.I.S. Assistive Suite Online')

    lighting = LightingCompensator(clip_limit=2.0, tile_grid_size=(8, 8))
    pose_estimator = HeadPoseEstimator()
    iris_detector = IrisGazeDetector()
    gesture_engine = GestureEngine(wink_hold_time=0.2, double_click_hold_time=0.55, click_cooldown=0.3, scroll_pitch_deadzone=8.0, scroll_hold_time=0.15, asymmetry_threshold=0.25, enable_blink_click=True, blink_click_hold_time=0.28, closure_threshold=0.25)
    nav_engine = PointerNavigationEngine(screen_w=screen_w, screen_h=screen_h, default_method=PointerNavigationEngine.METHOD_ABSOLUTE_ANCHOR, base_sensitivity=1.0, enable_dwell_click=False, dwell_time=0.65, dwell_radius=22.0)
    esp32 = ESP32Controller(port='COM5', baudrate=115200)
    esp32.start()
    tracker = FastFaceMeshTracker(model_yunet_path=YUNET_PATH, model_facemesh_path=FACEMESH_PATH, input_size=(640, 480), redetect_interval=90)
    camera = ThreadedWebcamStream(src=0, width=640, height=480, fps=30).start()
    time.sleep(0.4)

    if not camera.stream.isOpened() or camera.read() is None:
        print('[ERROR] Camera could not be opened. Please verify your webcam is connected and not in use.')
        camera.stop()
        return

    window_name = 'I.R.I.S. - Controller & Neural HUD'
    cam_w, cam_h = (640, 540)
    sidebar_w = 370
    total_w = cam_w + sidebar_w
    total_h = cam_h
    center_wx = max(0, int((screen_w - total_w) / 2))
    center_wy = max(0, int((screen_h - total_h) / 2) - 40)

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, total_w, total_h)
    cv2.moveWindow(window_name, center_wx, center_wy)
    try:
        cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass

    def get_window_pos(win_name: str) -> Tuple[int, int]:
        try:
            import ctypes
            hwnd = ctypes.windll.user32.FindWindowW(None, win_name)
            if hwnd:
                rect = (ctypes.c_long * 4)()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                return int(rect[0]), int(rect[1])
        except Exception:
            pass
        return center_wx, center_wy

    def handle_ui_action(action: str) -> Tuple[str, Tuple[int, int, int]]:
        telemetry = esp32.get_telemetry()
        if action == 'light_toggle':
            new_state = not telemetry.light_state
            esp32.set_light(new_state)
            if new_state:
                audio.light_turned_on()
            else:
                audio.light_turned_off()
            nav_engine.record_command('toggle_light')
            return (f"LIGHT {('ON' if new_state else 'OFF')}", (255, 255, 255) if new_state else (180, 180, 180))
        elif action == 'light_on':
            esp32.set_light(True)
            audio.light_turned_on()
            nav_engine.record_command('light_on')
            return ('LIGHT ON', (255, 255, 255))
        elif action == 'light_off':
            esp32.set_light(False)
            audio.light_turned_off()
            nav_engine.record_command('light_off')
            return ('LIGHT OFF', (180, 180, 180))
        elif action == 'arm':
            esp32.arm()
            audio.arm_system()
            nav_engine.record_command('arm')
            return ('SYSTEM ARMED', (0, 255, 120))
        elif action == 'disarm':
            esp32.disarm()
            audio.disarm_system()
            nav_engine.record_command('disarm')
            return ('SYSTEM DISARMED', (0, 60, 255))
        return ('', (0, 255, 120))

    def match_ui_button(rx: float, ry: float) -> Optional[str]:
        if 456 <= ry <= 504:
            if 12 <= rx <= 145:
                return 'arm'
            elif 155 <= rx <= 295:
                return 'disarm'
            elif 340 <= rx <= 495:
                return 'light_toggle'
            elif 505 <= rx <= 560:
                return 'light_on'
            elif 570 <= rx <= 630:
                return 'light_off'
        if show_sidebar:
            if 209 <= ry <= 224:
                if 640 + 215 <= rx <= 640 + 272:
                    return 'arm'
                elif 640 + 278 <= rx <= 640 + 345:
                    return 'disarm'
            elif 250 <= ry <= 295:
                if 640 + 18 <= rx <= 640 + 195:
                    return 'light_toggle'
                elif 640 + 205 <= rx <= 640 + 265:
                    return 'light_on'
                elif 640 + 275 <= rx <= 640 + 340:
                    return 'light_off'
        return None

    def on_mouse_event(event, mx, my, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            act = match_ui_button(mx, my)
            if act is not None:
                handle_ui_action(act)

    cv2.setMouseCallback(window_name, on_mouse_event)

    def check_ui_button_hit(tx: float, ty: float) -> Optional[str]:
        cur_wx, cur_wy = get_window_pos(window_name)
        return match_ui_button(tx - cur_wx, ty - cur_wy)

    t_start = time.time()
    laser_filter = OneEuroFilter2D(t_start, 320.0, 240.0, min_cutoff=0.008, beta=0.006, d_cutoff=1.0)
    neutral_initialized = False
    is_paused = False
    show_sidebar = True
    last_scroll_time = 0.0
    SCROLL_INTERVAL = 0.075
    click_suppress_until = 0.0
    last_prox_audio_time = 0.0
    last_motion_audio_time = 0.0
    last_action_text = ''
    last_action_time = 0.0
    last_action_color = (0, 255, 120)
    sensor_log: List[Tuple[str, str, Tuple[int, int, int]]] = [
        (time.strftime('%H:%M:%S'), 'SYSTEM INITIALIZED', (0, 240, 255)),
        (time.strftime('%H:%M:%S'), 'ESP32 CONTROLLER CONNECTED', (0, 255, 120))
    ]
    ripples: List[Dict[str, Any]] = []
    frame_times: List[float] = []
    fps = 30.0

    face_lost_start = 0.0
    face_lost_notified = False

    print('[READY] I.R.I.S. Engine Online.')
    print('        Controls: [SPACE] Pause | [C] Recenter | [L] Light Toggle | [W] Dwell | [M] Mode | [T] Sidebar | [ESC] Exit\n')

    try:
        while True:
            try:
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    print('[INFO] Pop-up window closed by user.')
                    break
            except Exception:
                pass

            t_frame_start = time.time()
            raw_cam_frame = camera.read()
            if raw_cam_frame is None:
                time.sleep(0.005)
                continue

            raw_cam_frame = cv2.flip(raw_cam_frame, 1)
            frame = np.zeros((cam_h, cam_w, 3), dtype=np.uint8)
            frame[30:510, 0:640] = raw_cam_frame
            img_h, img_w, _ = (480, 640, 3)

            rgb_image = lighting.process(raw_cam_frame)
            landmarks = tracker.detect_and_track(rgb_image)
            current_time = time.time()
            gestures: Dict[str, Any] = {}
            anchor_x, anchor_y = (320.0, 240.0)
            hold_progress = 0.0
            pitch, yaw, roll = (0.0, 0.0, 0.0)
            has_face = landmarks is not None

            if has_face:
                if face_lost_notified:
                    audio.tracking_recovered()
                    face_lost_notified = False
                    nav_engine.clear_failsafe()
                face_lost_start = 0.0
            else:
                if face_lost_start == 0.0:
                    face_lost_start = current_time
                elif current_time - face_lost_start > 1.2 and not face_lost_notified:
                    audio.tracking_lost_alert()
                    face_lost_notified = True
                    nav_engine.trigger_failsafe()

            while not speech_queue.empty():
                s_act, s_data = speech_queue.get_nowait()
                s_resp = s_data.get('verbal_response', '')
                s_raw = s_data.get('raw_text', s_act)
                last_action_text = f'VOICE: {s_raw.upper()}'
                last_action_time = current_time
                last_action_color = (0, 240, 255)
                sensor_log.append((time.strftime('%H:%M:%S'), f'VOICE: {s_raw.upper()}', (0, 240, 255)))
                if len(sensor_log) > 12:
                    sensor_log.pop(0)

                if s_act == 'left_click':
                    controller.left_click()
                    audio.left_click()
                    nav_engine.record_command('left_click')
                    click_suppress_until = current_time + 0.05
                    ripples.append({'x': int(anchor_x), 'y': int(anchor_y) + 30, 'start': current_time, 'color': (0, 255, 120)})
                elif s_act == 'right_click':
                    controller.right_click()
                    audio.right_click()
                    nav_engine.record_command('right_click')
                    click_suppress_until = current_time + 0.05
                    ripples.append({'x': int(anchor_x), 'y': int(anchor_y) + 30, 'start': current_time, 'color': (0, 220, 255)})
                elif s_act == 'double_click':
                    controller.double_click()
                    audio.double_click()
                    nav_engine.record_command('double_click')
                    click_suppress_until = current_time + 0.05
                    ripples.append({'x': int(anchor_x), 'y': int(anchor_y) + 30, 'start': current_time, 'color': (255, 100, 255)})
                elif s_act == 'scroll_up':
                    controller.scroll(6)
                    audio.scroll_up()
                    nav_engine.record_command('scroll_up')
                elif s_act == 'scroll_down':
                    controller.scroll(-6)
                    audio.scroll_down()
                    nav_engine.record_command('scroll_down')
                elif s_act == 'light_on':
                    handle_ui_action('light_on')
                elif s_act == 'light_off':
                    handle_ui_action('light_off')
                elif s_act == 'toggle_light':
                    handle_ui_action('light_toggle')
                elif s_act == 'fan_on':
                    audio.fan_turned_on()
                    nav_engine.record_command('fan_on')
                elif s_act == 'fan_off':
                    audio.fan_turned_off()
                    nav_engine.record_command('fan_off')
                elif s_act == 'voice_error':
                    audio.voice_error('Command not recognized')
                elif s_act == 'recenter':
                    nav_engine.recenter((anchor_x, anchor_y))
                    laser_filter.reset(current_time, anchor_x, anchor_y)
                    controller.move_to(screen_w // 2, screen_h // 2)
                    audio.recenter()
                    if s_resp:
                        audio.speak(s_resp)
                elif s_act == 'pause':
                    is_paused = True
                    audio.pause()
                    if s_resp:
                        audio.speak(s_resp)
                elif s_act == 'resume':
                    is_paused = False
                    audio.resume()
                    if s_resp:
                        audio.speak(s_resp)
                elif s_act == 'toggle_sniper':
                    nav_engine.is_sniper = not nav_engine.is_sniper
                    audio.sniper_toggle(nav_engine.is_sniper)
                    audio.speak('Sniper on' if nav_engine.is_sniper else 'Sniper off')
                elif s_act == 'toggle_dwell':
                    nav_engine.enable_dwell_click = not nav_engine.enable_dwell_click
                    audio.dwell_toggle(nav_engine.enable_dwell_click)
                    audio.speak('Dwell on' if nav_engine.enable_dwell_click else 'Dwell off')
                elif s_act == 'calibrate':
                    if has_face:
                        current_l_ear = gestures.get('left_ear', 0.22)
                        current_r_ear = gestures.get('right_ear', 0.22)
                        current_mar = gestures.get('mar', 0.015)
                        gesture_engine.recalibrate_baseline(current_l_ear, current_r_ear, current_mar)
                    audio.calibrate()
                    if s_resp:
                        audio.speak(s_resp)
                elif s_act == 'arm':
                    esp32.arm()
                    audio.arm_system()
                elif s_act == 'disarm':
                    esp32.disarm()
                    audio.disarm_system()
                elif s_act == 'test_leds':
                    esp32.test_leds()
                    audio.voice_command_recognized('test_leds', s_resp or 'Testing LEDs')
                else:
                    audio.voice_command_recognized(s_act, s_resp)

            if has_face:
                cranial_raw_x = float((landmarks[168][0] + landmarks[6][0] + landmarks[197][0]) / 3.0)
                cranial_raw_y = float((landmarks[168][1] + landmarks[6][1] + landmarks[197][1]) / 3.0)
                anchor_x, anchor_y = laser_filter.filter(current_time, cranial_raw_x, cranial_raw_y)
                if not neutral_initialized:
                    nav_engine.recenter((anchor_x, anchor_y))
                    neutral_initialized = True

                success, proj, rvec, tvec = pose_estimator.estimate_pose(landmarks, img_w, img_h)
                if success and rvec is not None:
                    pitch, yaw, roll = pose_estimator.get_euler_angles(rvec)

                gaze_data = iris_detector.estimate_iris_gaze(raw_cam_frame, landmarks, is_blinking=False)
                gaze_offset = (gaze_data.get('gaze_offset_x', 0.0), gaze_data.get('gaze_offset_y', 0.0))
                gestures = gesture_engine.process_frame(landmarks, current_time, pitch_angle=pitch, tilt_y=0.0, is_mirrored=True)
                hold_progress = gestures.get('hold_progress', 0.0)
                trigger = gestures.get('trigger_action')

                action_fired = False
                target_screen_x, target_screen_y, dwell_action = nav_engine.update(laser_pt=(anchor_x, anchor_y), euler_angles=(pitch, yaw, roll), gaze_offset=gaze_offset, current_time=current_time)

                if not is_paused and trigger is not None:
                    ui_hit = check_ui_button_hit(target_screen_x, target_screen_y)
                    if ui_hit is not None:
                        lbl, col = handle_ui_action(ui_hit)
                        last_action_text = f'EYE-CLICK: {lbl}!'
                        last_action_time = current_time
                        last_action_color = col
                        click_suppress_until = current_time + 0.1
                        action_fired = True
                    elif trigger == 'left_click':
                        controller.left_click()
                        audio.left_click()
                        nav_engine.record_command('left_click')
                        last_action_text = 'LEFT CLICK!'
                        last_action_time = current_time
                        last_action_color = (0, 255, 120)
                        click_suppress_until = current_time + 0.05
                        action_fired = True
                    elif trigger == 'right_click':
                        controller.right_click()
                        audio.right_click()
                        nav_engine.record_command('right_click')
                        last_action_text = 'RIGHT CLICK!'
                        last_action_time = current_time
                        last_action_color = (0, 220, 255)
                        click_suppress_until = current_time + 0.05
                        action_fired = True
                    elif trigger == 'double_click':
                        controller.double_click()
                        audio.double_click()
                        nav_engine.record_command('double_click')
                        last_action_text = 'DOUBLE CLICK!'
                        last_action_time = current_time
                        last_action_color = (255, 100, 255)
                        click_suppress_until = current_time + 0.05
                        action_fired = True
                    elif trigger == 'scroll_up':
                        if current_time - last_scroll_time > SCROLL_INTERVAL:
                            controller.scroll(3)
                            audio.scroll_up()
                            nav_engine.record_command('scroll_up')
                            last_scroll_time = current_time
                            last_action_text = 'SCROLL UP'
                            last_action_time = current_time
                            last_action_color = (0, 240, 255)
                            action_fired = True
                    elif trigger == 'scroll_down':
                        if current_time - last_scroll_time > SCROLL_INTERVAL:
                            controller.scroll(-3)
                            audio.scroll_down()
                            nav_engine.record_command('scroll_down')
                            last_scroll_time = current_time
                            last_action_text = 'SCROLL DOWN'
                            last_action_time = current_time
                            last_action_color = (0, 240, 255)
                            action_fired = True

                if action_fired:
                    sensor_log.append((time.strftime('%H:%M:%S'), last_action_text, last_action_color))
                    if len(sensor_log) > 12:
                        sensor_log.pop(0)
                    ripples.append({'x': int(anchor_x), 'y': int(anchor_y) + 30, 'start': current_time, 'color': last_action_color})

                if not is_paused and current_time >= click_suppress_until:
                    controller.move_to(target_screen_x, target_screen_y)

                if not is_paused and dwell_action == 'dwell_click':
                    ui_hit = check_ui_button_hit(target_screen_x, target_screen_y)
                    if ui_hit is not None:
                        lbl, col = handle_ui_action(ui_hit)
                        last_action_text = f'DWELL: {lbl}!'
                        last_action_color = col
                    else:
                        controller.left_click()
                        audio.left_click()
                        nav_engine.record_command('dwell_click')
                        last_action_text = 'DWELL CLICK!'
                        last_action_color = (0, 240, 255)
                    last_action_time = current_time
                    click_suppress_until = current_time + 0.05
                    sensor_log.append((time.strftime('%H:%M:%S'), last_action_text, last_action_color))
                    ripples.append({'x': int(anchor_x), 'y': int(anchor_y) + 30, 'start': current_time, 'color': last_action_color})

                reticle_pt = (int(anchor_x), int(anchor_y) + 30)
                cv2.circle(frame, reticle_pt, 6, (0, 240, 255), -1, cv2.LINE_AA)
                cv2.circle(frame, reticle_pt, 9, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.drawMarker(frame, reticle_pt, (0, 240, 255), cv2.MARKER_CROSS, 16, 1, cv2.LINE_AA)

                r_eye_indices = [33, 160, 158, 133, 153, 144]
                l_eye_indices = [362, 385, 387, 263, 373, 380]
                closure_thresh = gestures.get('closure_threshold', 0.25)
                r_eye_col = (0, 120, 255) if gestures.get('closure_r', 0.0) >= closure_thresh else (0, 255, 140)
                l_eye_col = (0, 120, 255) if gestures.get('closure_l', 0.0) >= closure_thresh else (0, 255, 140)
                for idx in r_eye_indices:
                    cv2.circle(frame, (int(landmarks[idx][0]), int(landmarks[idx][1]) + 30), 1, r_eye_col, -1)
                for idx in l_eye_indices:
                    cv2.circle(frame, (int(landmarks[idx][0]), int(landmarks[idx][1]) + 30), 1, l_eye_col, -1)
                for idx in [1, 61, 291, 152]:
                    cv2.circle(frame, (int(landmarks[idx][0]), int(landmarks[idx][1]) + 30), 2, (0, 255, 120), -1)

                active_hold = max(hold_progress, nav_engine.dwell_progress if nav_engine.enable_dwell_click else 0.0)
                if active_hold > 0.0:
                    gauge_col = (255, 100, 255) if gestures.get('is_blinking') else (0, 240, 255) if nav_engine.dwell_progress > 0 else (0, 255, 120)
                    draw_circular_gauge(frame, reticle_pt, radius=22, progress=active_hold, color=gauge_col, thickness=3)
            else:
                card_x1 = 110
                card_x2 = cam_w - 110
                card_y1 = 200
                card_y2 = 310
                overlay = frame.copy()
                cv2.rectangle(overlay, (card_x1, card_y1), (card_x2, card_y2), (18, 22, 30), -1)
                cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
                cv2.rectangle(frame, (card_x1, card_y1), (card_x2, card_y2), (0, 220, 255), 2)
                cv2.putText(frame, 'SEARCHING FOR FACE...', (card_x1 + 35, card_y1 + 45), cv2.FONT_HERSHEY_DUPLEX, 0.55, (0, 240, 255), 1, cv2.LINE_AA)
                cv2.putText(frame, 'Position face in view to track', (card_x1 + 40, card_y1 + 80), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 195, 210), 1, cv2.LINE_AA)
                if nav_engine.is_failsafe_active:
                    cv2.putText(frame, '[FAILSAFE ACTIVE: POINTER HELD]', (card_x1 + 25, card_y1 + 100), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 60, 255), 1, cv2.LINE_AA)

            active_ripples = []
            for r in ripples:
                elapsed_r = current_time - r['start']
                if elapsed_r < 0.4:
                    prog_r = elapsed_r / 0.4
                    rad = int(14 + prog_r * 42)
                    thick = max(1, int(3 * (1.0 - prog_r)))
                    cv2.circle(frame, (r['x'], r['y']), rad, r['color'], thick, cv2.LINE_AA)
                    active_ripples.append(r)
            ripples = active_ripples

            hw = esp32.get_telemetry()
            if hw.proximity_alert:
                last_action_text = f'PROXIMITY ALERT ({hw.distance_cm:.1f}cm)!'
                last_action_time = current_time
                last_action_color = (0, 240, 255)
                if current_time - last_prox_audio_time > 2.0:
                    audio.proximity_alert()
                    last_prox_audio_time = current_time
            elif hw.motion_alert:
                last_action_text = 'MOTION / TILT ALERT!'
                last_action_time = current_time
                last_action_color = (0, 140, 255)
                if current_time - last_motion_audio_time > 2.5:
                    audio.motion_alert()
                    last_motion_audio_time = current_time

            if hw.last_event_text and current_time - hw.last_event_time < 0.1:
                event_entry = (time.strftime('%H:%M:%S'), hw.last_event_text, (0, 140, 255) if 'MOTION' in hw.last_event_text else (0, 240, 255))
                if not sensor_log or sensor_log[-1][1] != event_entry[1]:
                    sensor_log.append(event_entry)
                    if len(sensor_log) > 12:
                        sensor_log.pop(0)

            cv2.rectangle(frame, (0, 0), (cam_w, 28), (12, 16, 24), -1)
            cv2.line(frame, (0, 28), (cam_w, 28), (35, 45, 60), 1)
            st_dot_col = (0, 255, 120) if hw.is_connected and hw.state == HardwareState.ARMED else (0, 60, 255) if hw.is_connected else (90, 100, 115)
            cv2.circle(frame, (14, 14), 4, st_dot_col, -1, cv2.LINE_AA)
            esp_label = f'ESP32 [{hw.state.value}]' if hw.is_connected else 'ESP32 [OFFLINE]'
            cv2.putText(frame, esp_label, (24, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.32, st_dot_col, 1, cv2.LINE_AA)
            dist_val = hw.distance_cm
            if 0.5 < dist_val < 450.0:
                dist_txt = f'HC-SR04: {dist_val:.1f}cm'
                dist_radar_col = (0, 60, 255) if hw.proximity_alert else (0, 240, 255)
            else:
                dist_txt = 'HC-SR04: --'
                dist_radar_col = (130, 140, 150)
            cv2.putText(frame, dist_txt, (180, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.32, dist_radar_col, 1, cv2.LINE_AA)

            lt_hud_txt = 'LIGHT: [ON]' if hw.light_state else 'LIGHT: [OFF]'
            lt_hud_col = (255, 255, 255) if hw.light_state else (120, 130, 145)
            cv2.putText(frame, lt_hud_txt, (320, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.32, lt_hud_col, 1, cv2.LINE_AA)

            ax, ay, az = hw.motion_values
            g_mag = math.sqrt(ax * ax + ay * ay + az * az)
            mot_hud_col = (0, 80, 255) if hw.motion_alert else (0, 255, 140)
            mot_hud_txt = f'MPU: {g_mag:.2f}g'
            cv2.putText(frame, mot_hud_txt, (450, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.32, mot_hud_col, 1, cv2.LINE_AA)
            cv2.putText(frame, f'FPS: {fps:.0f}', (cam_w - 75, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 240, 255), 1, cv2.LINE_AA)

            arm_bg = (20, 56, 36) if hw.state == HardwareState.ARMED else (20, 26, 36)
            arm_bd = (0, 255, 120) if hw.state == HardwareState.ARMED else (65, 85, 105)
            cv2.rectangle(frame, (12, 456), (145, 504), arm_bg, -1)
            cv2.rectangle(frame, (12, 456), (145, 504), arm_bd, 2)
            cv2.putText(frame, '[ARM]', (45, 486), cv2.FONT_HERSHEY_DUPLEX, 0.48, arm_bd, 1)

            drm_bg = (48, 20, 26) if hw.state == HardwareState.DISARMED else (20, 26, 36)
            drm_bd = (0, 60, 255) if hw.state == HardwareState.DISARMED else (65, 85, 105)
            cv2.rectangle(frame, (155, 456), (295, 504), drm_bg, -1)
            cv2.rectangle(frame, (155, 456), (295, 504), drm_bd, 2)
            cv2.putText(frame, '[DISARM]', (178, 486), cv2.FONT_HERSHEY_DUPLEX, 0.48, drm_bd, 1)

            tog_bg = (24, 52, 38) if hw.light_state else (20, 26, 36)
            tog_border = (255, 255, 255) if hw.light_state else (55, 75, 95)
            cv2.rectangle(frame, (340, 456), (495, 504), tog_bg, -1)
            cv2.rectangle(frame, (340, 456), (495, 504), tog_border, 2)
            tog_label = '[LIGHT: ON]' if hw.light_state else '[LIGHT: OFF]'
            tog_col = (255, 255, 255) if hw.light_state else (140, 155, 175)
            cv2.putText(frame, tog_label, (352, 485), cv2.FONT_HERSHEY_DUPLEX, 0.44, tog_col, 1)

            btn_on_bg = (20, 48, 32) if hw.light_state else (18, 24, 34)
            btn_on_border = (0, 255, 120) if hw.light_state else (70, 85, 100)
            cv2.rectangle(frame, (505, 456), (560, 504), btn_on_bg, -1)
            cv2.rectangle(frame, (505, 456), (560, 504), btn_on_border, 1)
            cv2.putText(frame, 'ON', (520, 486), cv2.FONT_HERSHEY_SIMPLEX, 0.38, btn_on_border, 1, cv2.LINE_AA)

            btn_off_bg = (42, 20, 26) if not hw.light_state else (18, 24, 34)
            btn_off_border = (0, 60, 255) if not hw.light_state else (70, 85, 100)
            cv2.rectangle(frame, (570, 456), (630, 504), btn_off_bg, -1)
            cv2.rectangle(frame, (570, 456), (630, 504), btn_off_border, 1)
            cv2.putText(frame, 'OFF', (585, 486), cv2.FONT_HERSHEY_SIMPLEX, 0.38, btn_off_border, 1, cv2.LINE_AA)

            cv2.rectangle(frame, (0, 510), (cam_w, cam_h), (12, 16, 24), -1)
            cv2.line(frame, (0, 510), (cam_w, 510), (35, 45, 60), 1)
            cv2.putText(frame, 'LEDS:', (10, 528), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (170, 185, 200), 1, cv2.LINE_AA)
            is_disarmed = hw.state == HardwareState.DISARMED
            is_armed = hw.state == HardwareState.ARMED
            is_prox = hw.proximity_alert and is_armed
            led_mini = [
                ('R1', is_disarmed, (0, 0, 255)),
                ('R2', is_disarmed, (0, 0, 255)),
                ('G1', is_armed, (0, 255, 120)),
                ('G2', is_armed, (0, 255, 120)),
                ('B1', is_prox, (255, 180, 0)),
                ('B2', is_prox, (255, 180, 0)),
                ('WL', hw.light_state, (255, 255, 255))
            ]
            mini_x = 55
            for lbl, lit, col in led_mini:
                dot_c = col if lit else (40, 45, 60)
                cv2.circle(frame, (mini_x, 525), 4, dot_c, -1, cv2.LINE_AA)
                cv2.putText(frame, lbl, (mini_x + 6, 528), cv2.FONT_HERSHEY_SIMPLEX, 0.26, (200, 210, 220) if lit else (100, 110, 120), 1, cv2.LINE_AA)
                mini_x += 38

            cv2.putText(frame, 'KEYS: [A] ARM | [D] DISARM | [L] LIGHT | [X] TEST', (285, 528), cv2.FONT_HERSHEY_SIMPLEX, 0.26, (160, 175, 190), 1, cv2.LINE_AA)

            if hw.proximity_alert:
                cv2.rectangle(frame, (2, 30), (cam_w - 2, 508), (0, 60, 255), 3)
                alert_bar_w = 340
                ax1 = (cam_w - alert_bar_w) // 2
                cv2.rectangle(frame, (ax1, 34), (ax1 + alert_bar_w, 62), (15, 20, 32), -1)
                cv2.rectangle(frame, (ax1, 34), (ax1 + alert_bar_w, 62), (0, 60, 255), 2)
                cv2.putText(frame, f'! PROXIMITY ALERT: {dist_val:.1f} CM < 30 CM !', (ax1 + 14, 53), cv2.FONT_HERSHEY_DUPLEX, 0.42, (0, 60, 255), 1, cv2.LINE_AA)

            if current_time - last_action_time < 0.7 and last_action_text:
                banner_w = 320
                bx1 = (cam_w - banner_w) // 2
                bx2 = bx1 + banner_w
                by1, by2 = (68 if hw.proximity_alert else 36, 108 if hw.proximity_alert else 76)
                b_overlay = frame.copy()
                cv2.rectangle(b_overlay, (bx1, by1), (bx2, by2), (18, 22, 30), -1)
                cv2.addWeighted(b_overlay, 0.88, frame, 0.12, 0, frame)
                cv2.rectangle(frame, (bx1, by1), (bx2, by2), last_action_color, 2)
                cv2.putText(frame, last_action_text, (bx1 + 14, by1 + 26), cv2.FONT_HERSHEY_DUPLEX, 0.5, last_action_color, 1, cv2.LINE_AA)

            t_frame_end = time.time()
            frame_times.append(t_frame_end - t_frame_start)
            if len(frame_times) > 30:
                frame_times.pop(0)
            fps = len(frame_times) / sum(frame_times) if sum(frame_times) > 0 else 30.0

            if show_sidebar:
                panel = np.zeros((cam_h, sidebar_w, 3), dtype=np.uint8)
                render_cyber_dashboard(panel, nav_engine, gestures, hw, is_paused, has_face, fps, sensor_log, speech_active=speech_enabled, speech_listening=speech_engine.is_listening)
                display_canvas = np.hstack([frame, panel])
            else:
                display_canvas = frame

            cv2.imshow(window_name, display_canvas)
            key = cv2.waitKey(1) & 255
            if key == 27:
                print('[INFO] Terminating session cleanly...')
                break
            elif key == ord(' '):
                is_paused = not is_paused
                if is_paused:
                    audio.pause()
                    audio.speak('Paused')
                else:
                    audio.resume()
                    audio.speak('Resumed')
                sensor_log.append((time.strftime('%H:%M:%S'), 'PAUSED' if is_paused else 'RESUMED', (0, 140, 255)))
            elif key in (ord('l'), ord('L')):
                lbl, col = handle_ui_action('light_toggle')
                last_action_text = lbl
                last_action_time = current_time
                last_action_color = col
                sensor_log.append((time.strftime('%H:%M:%S'), lbl, col))
            elif key in (ord('o'), ord('O')):
                lbl, col = handle_ui_action('light_off')
                last_action_text = lbl
                last_action_time = current_time
                last_action_color = col
                sensor_log.append((time.strftime('%H:%M:%S'), lbl, col))
            elif key in (ord('v'), ord('V')):
                speech_enabled = not speech_enabled
                if speech_enabled:
                    speech_engine.start()
                    audio.speak('Voice control active')
                    last_action_text = 'VOICE: ACTIVE'
                else:
                    speech_engine.stop()
                    audio.speak('Voice control disabled')
                    last_action_text = 'VOICE: OFF'
                last_action_time = current_time
                last_action_color = (0, 255, 120) if speech_enabled else (120, 130, 140)
                sensor_log.append((time.strftime('%H:%M:%S'), f"VOICE {('ACTIVE' if speech_enabled else 'OFF')}", last_action_color))
            elif key in (ord('c'), ord('C')):
                nav_engine.recenter((anchor_x, anchor_y))
                laser_filter.reset(current_time, anchor_x, anchor_y)
                controller.move_to(screen_w // 2, screen_h // 2)
                audio.recenter()
                audio.speak('Recentered')
                last_action_text = 'RECENTERED'
                last_action_time = current_time
                last_action_color = (0, 240, 255)
                sensor_log.append((time.strftime('%H:%M:%S'), 'RECENTERED', (0, 240, 255)))
            elif key in (ord('p'), ord('P'), ord('z'), ord('Z')):
                nav_engine.is_sniper = not nav_engine.is_sniper
                audio.sniper_toggle(nav_engine.is_sniper)
                audio.speak('Sniper on' if nav_engine.is_sniper else 'Sniper off')
                last_action_text = f"SNIPER {('ON (0.25x)' if nav_engine.is_sniper else 'OFF')}"
                last_action_time = current_time
                last_action_color = (255, 100, 255)
                sensor_log.append((time.strftime('%H:%M:%S'), last_action_text, last_action_color))
            elif key in (ord('w'), ord('W')):
                nav_engine.enable_dwell_click = not nav_engine.enable_dwell_click
                audio.dwell_toggle(nav_engine.enable_dwell_click)
                audio.speak('Dwell on' if nav_engine.enable_dwell_click else 'Dwell off')
                last_action_text = f"DWELL CLICK {('ON' if nav_engine.enable_dwell_click else 'OFF')}"
                last_action_time = current_time
                last_action_color = (0, 240, 255)
                sensor_log.append((time.strftime('%H:%M:%S'), last_action_text, last_action_color))
            elif key in (ord('k'), ord('K')):
                if has_face:
                    current_l_ear = gestures.get('left_ear', 0.22)
                    current_r_ear = gestures.get('right_ear', 0.22)
                    current_mar = gestures.get('mar', 0.015)
                    gesture_engine.recalibrate_baseline(current_l_ear, current_r_ear, current_mar)
                    last_action_text = f'CALIBRATED (L:{current_l_ear:.2f} R:{current_r_ear:.2f})'
                    last_action_time = current_time
                    last_action_color = (0, 255, 120)
                    audio.calibrate()
                    audio.speak('Calibrated')
                    sensor_log.append((time.strftime('%H:%M:%S'), f'CALIB L:{current_l_ear:.2f} R:{current_r_ear:.2f}', (0, 255, 120)))
            elif key in (ord('b'), ord('B')):
                gesture_engine.enable_blink_click = not gesture_engine.enable_blink_click
                b_state = 'ON (0.28s)' if gesture_engine.enable_blink_click else 'OFF'
                last_action_text = f'BLINK CLICK {b_state}'
                last_action_time = current_time
                last_action_color = (255, 100, 255)
                sensor_log.append((time.strftime('%H:%M:%S'), f'BLINK CLICK {b_state}', (255, 100, 255)))
            elif key == ord('['):
                gesture_engine.closure_threshold = max(0.15, gesture_engine.closure_threshold - 0.02)
                last_action_text = f'CLICK SENS: {gesture_engine.closure_threshold * 100:.0f}%'
                last_action_time = current_time
                last_action_color = (0, 240, 255)
                sensor_log.append((time.strftime('%H:%M:%S'), f'CLICK SENS {gesture_engine.closure_threshold * 100:.0f}%', (0, 240, 255)))
            elif key == ord(']'):
                gesture_engine.closure_threshold = min(0.45, gesture_engine.closure_threshold + 0.02)
                last_action_text = f'CLICK SENS: {gesture_engine.closure_threshold * 100:.0f}%'
                last_action_time = current_time
                last_action_color = (0, 240, 255)
                sensor_log.append((time.strftime('%H:%M:%S'), f'CLICK SENS {gesture_engine.closure_threshold * 100:.0f}%', (0, 240, 255)))
            elif key in (ord('m'), ord('M')):
                new_mode = nav_engine.cycle_method()
                last_action_text = f'MODE: {new_mode[:12].upper()}'
                last_action_time = current_time
                last_action_color = (0, 255, 120)
                sensor_log.append((time.strftime('%H:%M:%S'), f'MODE: {new_mode}', (0, 255, 120)))
            elif key in (ord('+'), ord('=')):
                nav_engine.sensitivity = min(3.0, nav_engine.sensitivity + 0.1)
                last_action_text = f'SENS: {nav_engine.sensitivity:.2f}x'
                last_action_time = current_time
                last_action_color = (0, 240, 255)
            elif key in (ord('-'), ord('_')):
                nav_engine.sensitivity = max(0.4, nav_engine.sensitivity - 0.1)
                last_action_text = f'SENS: {nav_engine.sensitivity:.2f}x'
                last_action_time = current_time
                last_action_color = (0, 240, 255)
            elif key in (ord('t'), ord('T')):
                show_sidebar = not show_sidebar
                new_w = cam_w + sidebar_w if show_sidebar else cam_w
                cv2.resizeWindow(window_name, new_w, total_h)
            elif key in (ord('a'), ord('A')):
                esp32.arm()
                audio.arm_system()
                last_action_text = 'CMD: ARM SENT'
                last_action_time = current_time
                last_action_color = (0, 255, 120)
                sensor_log.append((time.strftime('%H:%M:%S'), 'CMD: ARM SENT', (0, 255, 120)))
            elif key in (ord('d'), ord('D')):
                esp32.disarm()
                audio.disarm_system()
                last_action_text = 'CMD: DISARM SENT'
                last_action_time = current_time
                last_action_color = (0, 60, 255)
                sensor_log.append((time.strftime('%H:%M:%S'), 'CMD: DISARM SENT', (0, 60, 255)))
            elif key in (ord('x'), ord('X')):
                esp32.test_leds()
                last_action_text = 'CMD: TEST LEDS'
                last_action_time = current_time
                last_action_color = (0, 240, 255)
                sensor_log.append((time.strftime('%H:%M:%S'), 'CMD: TEST LEDS', (0, 240, 255)))
    finally:
        speech_engine.stop()
        esp32.stop()
        camera.stop()
        cv2.destroyAllWindows()
        print('[INFO] I.R.I.S. Session Terminated Cleanly.')

if __name__ == '__main__':
    main()
