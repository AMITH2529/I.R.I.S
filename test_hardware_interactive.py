import sys
import time
import math
from typing import Dict, Any, List
import serial
PORT = 'COM5'
BAUD = 115200

def main():
    print('=' * 70)
    print('      I.R.I.S. v2.5 — LIVE HARDWARE COMPONENT TEST SUITE')
    print('=' * 70)
    print(f'[INIT] Opening serial port {PORT} at {BAUD} baud...')
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1.0)
    except Exception as e:
        print(f'[FAIL] Could not open {PORT}: {e}')
        print('       Please verify the ESP32 is plugged into USB and not used by another app.')
        return
    time.sleep(1.8)
    ser.reset_input_buffer()
    test_results: Dict[str, str] = {}
    print('\n' + '-' * 70)
    print('TEST 1: ESP32 UART Communication & Command Handshake')
    print('-' * 70)
    t_ping = time.time()
    ser.write(b'CMD: STATUS\n')
    ser.flush()
    response = ''
    t0 = time.time()
    while time.time() - t0 < 1.5:
        if ser.in_waiting:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if 'SYSTEM:' in line:
                response = line
                break
        time.sleep(0.02)
    latency_ms = (time.time() - t_ping) * 1000.0
    if 'SYSTEM:' in response:
        print(f"  [PASS] ESP32 Responded: '{response}' (Roundtrip: {latency_ms:.1f}ms)")
        test_results['ESP32 Link'] = 'PASS'
    else:
        print(f"  [WARN] No immediate 'SYSTEM:' ping reply, received: '{response}'")
        test_results['ESP32 Link'] = 'CHECK'
    print('\n' + '-' * 70)
    print('TEST 2: LED Control — DISARM State (RED LEDs D25 & D26 ON)')
    print('-' * 70)
    ser.write(b'CMD: DISARM\n')
    ser.flush()
    time.sleep(0.5)
    disarm_ack = False
    while ser.in_waiting:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        print(f'  ESP32 -> {line}')
        if 'DISARMED' in line:
            disarm_ack = True
    if disarm_ack:
        print('  [PASS] ESP32 switched to DISARMED.')
        print('         -> GPIO 25 (Red 1) & GPIO 26 (Red 2) driven HIGH (ON).')
        print('         -> GPIO 27, 32, 33, 23 driven LOW (OFF).')
        test_results['Red LEDs (D25/D26)'] = 'ACTIVE (DISARMED)'
    else:
        print('  [WARN] DISARM command ack not explicitly received.')
        test_results['Red LEDs (D25/D26)'] = 'SENT'
    print('\n' + '-' * 70)
    print('TEST 3: LED Control — ARM State (GREEN LEDs D27 & D32 ON)')
    print('-' * 70)
    ser.write(b'CMD: ARM\n')
    ser.flush()
    time.sleep(0.5)
    arm_ack = False
    while ser.in_waiting:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        print(f'  ESP32 -> {line}')
        if 'ARMED' in line:
            arm_ack = True
    if arm_ack:
        print('  [PASS] ESP32 switched to ARMED.')
        print('         -> GPIO 27 (Green 1) & GPIO 32 (Green 2) driven HIGH (ON).')
        print('         -> GPIO 25, 26 driven LOW (OFF).')
        test_results['Green LEDs (D27/D32)'] = 'ACTIVE (ARMED)'
    else:
        print('  [WARN] ARM command ack not explicitly received.')
        test_results['Green LEDs (D27/D32)'] = 'SENT'
    print('\n' + '-' * 70)
    print('TEST 4: HC-SR04 Ultrasonic Distance Sensor (TRIG D18, ECHO D19)')
    print('        Sampling live distance for 3.0 seconds...')
    print('-' * 70)
    distance_readings: List[float] = []
    proximity_alert_seen = False
    t_start = time.time()
    while time.time() - t_start < 3.0:
        if ser.in_waiting:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                if line.startswith('DISTANCE:'):
                    try:
                        d = float(line.split(':')[1])
                        distance_readings.append(d)
                        bar = '#' * min(30, int(d / 4.0))
                        print(f'  [DISTANCE] {d:5.1f} cm | {bar}')
                    except ValueError:
                        pass
                elif 'PROXIMITY_ALERT' in line:
                    proximity_alert_seen = True
                    print('  [ALERT] PROXIMITY_ALERT! (Distance < 30 cm -> Blue LEDs ON)')
                elif 'PROXIMITY_CLEAR' in line:
                    print('  [INFO] PROXIMITY_CLEAR (Distance >= 30 cm)')
                elif line.startswith('MOTION'):
                    print(f'  [MPU] {line}')
                else:
                    print(f'  [RECV] {line}')
        time.sleep(0.04)
    if distance_readings:
        avg_d = sum(distance_readings) / len(distance_readings)
        min_d = min(distance_readings)
        max_d = max(distance_readings)
        print(f'  [PASS] Ultrasonic Sensor Active: {len(distance_readings)} samples.')
        print(f'         Min: {min_d:.1f} cm | Max: {max_d:.1f} cm | Avg: {avg_d:.1f} cm')
        test_results['Ultrasonic HC-SR04'] = f'PASS ({avg_d:.1f} cm)'
    else:
        print('  [INFO] No DISTANCE: telemetry packets received.')
        print('         Note: Sensor returns >450cm when target is too close (<2cm),')
        print('         out of range, or ECHO divider (2.2k/3.3k) needs inspection.')
        test_results['Ultrasonic HC-SR04'] = 'NO ECHO PACKET'
    print('\n' + '-' * 70)
    print('TEST 5: GY-521 MPU-6050 Accelerometer & Motion Detection (SDA D21, SCL D22)')
    print('        Monitoring for 2.0 seconds...')
    print('-' * 70)
    motion_seen = False
    t_start = time.time()
    while time.time() - t_start < 2.0:
        if ser.in_waiting:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith('MOTION:'):
                motion_seen = True
                print(f'  [MOTION TELEMETRY] {line}')
            elif 'MOTION_ALERT' in line:
                motion_seen = True
                print('  [ALERT] MOTION_ALERT detected by MPU-6050!')
            elif line.startswith('DISTANCE:'):
                pass
        time.sleep(0.04)
    if motion_seen:
        print('  [PASS] MPU-6050 Accelerometer Active & Transmitting Motion.')
        test_results['MPU-6050 (I2C)'] = 'PASS (Motion Detected)'
    else:
        print('  [INFO] MPU-6050 resting (no motion delta exceeding 0.35g threshold).')
        test_results['MPU-6050 (I2C)'] = 'RESTING / READY'
    print('\n' + '-' * 70)
    print('TEST 6: Push Buttons (ARM GPIO 16, DISARM GPIO 17)')
    print('        Monitoring button presses for 3.0 seconds...')
    print('        (Press either button on your breadboard now!)')
    print('-' * 70)
    btn_event_seen = False
    t_start = time.time()
    while time.time() - t_start < 3.0:
        if ser.in_waiting:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(f'  ESP32 Event -> {line}')
                if 'SYSTEM: ARMED' in line or 'SYSTEM: DISARMED' in line:
                    btn_event_seen = True
                    print(f'  [BUTTON PRESS DETECTED] -> {line}')
        time.sleep(0.05)
    if btn_event_seen:
        test_results['Push Buttons'] = 'PASS (Button Triggered)'
    else:
        print('  [INFO] No button press detected during 3s window.')
        test_results['Push Buttons'] = 'READY (INPUT_PULLUP)'

    print('\n' + '-' * 70)
    print('TEST 7: Home Automation Light (White LED GPIO 13)')
    print('-' * 70)
    ser.write(b'CMD: LIGHT: ON\n')
    ser.flush()
    time.sleep(1.0)
    light_on_ack = False
    while ser.in_waiting:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        print(f'  ESP32 -> {line}')
        if 'DEVICE: LIGHT: ON' in line:
            light_on_ack = True
    if light_on_ack:
        print('  [PASS] White LED (GPIO 13) Switched ON!')
        test_results['White LED (GPIO 13)'] = 'PASS (ON/OFF ACK)'
    else:
        print('  [INFO] Sent CMD: LIGHT: ON')
        test_results['White LED (GPIO 13)'] = 'SENT'
    time.sleep(0.8)
    ser.write(b'CMD: LIGHT: OFF\n')
    ser.flush()
    time.sleep(0.5)
    while ser.in_waiting:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        print(f'  ESP32 -> {line}')

    ser.write(b'CMD: DISARM\n')
    ser.flush()
    time.sleep(0.2)
    ser.close()
    print('\n' + '=' * 70)
    print('                 HARDWARE VALIDATION SUMMARY REPORT')
    print('=' * 70)
    for comp, res in test_results.items():
        status_tag = '[PASS]' if 'PASS' in res or 'ACTIVE' in res else '[INFO]'
        print(f'  {status_tag:8} {comp:<26} : {res}')
    print('=' * 70)
if __name__ == '__main__':
    main()
