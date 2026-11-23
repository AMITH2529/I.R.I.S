# 📖 I.R.I.S. System & Hardware Architecture Guide

A concise breakdown of how the **I.R.I.S. v2.5** assistive computing platform, home automation engine, and physical hardware components function.

---

## 🖥️ 1. How the Software Works

### A. Computer Vision & Landmark Extraction
- **Optical Input**: Standard RGB webcam captures video frames at up to 60 FPS.
- **Lighting Compensation**: Dynamic CLAHE (Contrast Limited Adaptive Histogram Equalization) normalizes luminance ($Y$ channel in YCrCb) to resist lighting changes and room flicker.
- **Hybrid Tracking**:
  - **OpenCV YuNet**: Rapid face detector initializes and re-acquires facial bounds upon tracking loss.
  - **MediaPipe FaceMesh (ONNX Runtime)**: Extracts 468 dense 3D facial landmarks directly on CPU in under 1.8 ms (~550 FPS).
  - **Temporal ROI Tracking**: Tracks the face bounding box across consecutive frames without re-running heavy detection every frame.

### B. Pointer Kinematics & Motion Smoothing
- **Rigid Cranial Anchor**: Uses rigid facial landmarks (forehead and nose bridge) to compute head pose and gaze vectors via Perspective-n-Point (`solvePnP`), preventing Gimbal Lock.
- **Dual-Eye Iris Gaze**: Tracks dark pupil centroids relative to eye canthi in sub-millisecond time for fine gaze trimming.
- **1-Euro Filter**: An adaptive low-pass filter that eliminates high-frequency tremor when stationary while providing zero lag during fast head movements.
- **Continuous Cubic Hermite Deadzone**: Removes jump discontinuities and laddering artifacts near zero velocity.
- **Fitts' Law Ballistics**: Non-linear sigmoid velocity transfer curve provides sub-pixel accuracy during slow adjustments and full-screen reach with subtle 2° head turns.
- **OS Kernel Cursor Dispatch**: Directly injects cursor events into the Windows OS via `SendInput` / `ctypes` user32 API without external dependencies.

### C. Gesture & Click Detection Engine
- **Eye Aspect Ratio (EAR)**: Continuously monitors the vertical-to-horizontal eye opening ratio for both eyes.
- **Voluntary Blink-and-Release**: Differentiates between involuntary physiological blinks (short) and intentional clicks (150ms–480ms closure followed by reopen), triggering a native left-click upon release.
- **Independent Eye Winking**: Calculates relative asymmetry between left and right eyes to fire dedicated Left Click (left wink) or Right Click (right wink).
- **Extended Blink-Hold**: Holding eyes closed past 500ms charges and executes a native Double-Click.
- **Mouth Open Scrolling**: Opening the mouth combined with vertical head tilt initiates continuous, smooth vertical scrolling.
- **Hands-Free Fixation Dwell**: Rest the pointer inside a target radius for 650ms to auto-click without facial gestures.

### D. Eye-Controlled Home Automation
- **Interactive On-Screen Light Controls**: The floating HUD displays interactive `[LIGHT ON]` and `[LIGHT OFF]` widgets.
- **Eye-Click Execution**: Directing gaze/pointer to the Light control and eye-clicking (or dwelling) sends explicit serial commands (`CMD: LIGHT: ON` / `CMD: LIGHT: OFF`).
- **Hardware Acknowledgement**: The ESP32 switches GPIO 13 and returns `DEVICE: LIGHT: ON` / `DEVICE: LIGHT: OFF`.
- **Auditory Confirmation**: The voice assistant immediately announces **"The light is now ON"** or **"The light is now OFF"** with distinct acoustic chimes.

### E. Voice Assistant with Audio Feedback
- **Voice Commands**: Microphone capture with background speech recognition handles verbal light control ("light on", "light off", "toggle light"), fan control ("fan on", "fan off"), navigation, and application launching.
- **Voice Announcements**: Spoken confirmation announces completed actions ("The light is now ON", "The light is now OFF", "The fan is now ON", "The fan is now OFF").
- **Voice Error Alerts**: Audio voice alerts notify users when an unrecognized command is spoken or if hardware disconnects.

### F. Adaptive Gaze Interaction & Intelligent Fail-Safe
- **Adaptive Dwell Thresholds**: The system monitors gaze fixation velocity; steady fixations shorten dwell times for responsive intent execution, while rapid saccades increase dwell times to eliminate unintended clicks.
- **Command Prioritization**: Tracks a frequency histogram of user interactions to prioritize top intents.
- **Intelligent Fail-Safe Safeguard**: When face tracking is lost, pointer movement is immediately frozen, dwell timers are zeroed out, and a voice alert ("Tracking lost") notifies the user to prevent accidental clicks.

---

## ⚡ 2. How the Hardware Works

The hardware monitoring and automation unit runs on an **ESP32 DevKit V1** microcontroller connected via USB UART Serial (`COM5` at 115200 baud).

### A. ESP32 DevKit V1 Microcontroller
- **Dual-Core 32-bit Xtensa Processor @ 240 MHz**: Manages sensor polling, debouncing, serial JSON/text packet streaming, and LED matrices without blocking execution.
- **UART Serial Communication**: Exchanges real-time bi-directional telemetry and command packets (`CMD: ARM`, `CMD: DISARM`, `CMD: LIGHT: ON`, `CMD: LIGHT: OFF`, `DISTANCE:xx.x`, `MOTION:x,y,z`) with the Python host software.
- **Hardware State Machine**:
  - `STATE_DISARMED`: Tracking paused, Red LEDs active.
  - `STATE_ARMED`: Tracking active, Green LEDs active, real-time sensor radar engaged.

### B. Push Buttons (Hardware Arm / Disarm)
- **ARM Button (GPIO 16)**: Configured with internal pull-up (`INPUT_PULLUP`). Falling-edge triggers transition to `ARMED` state.
- **DISARM Button (GPIO 17)**: Configured with internal pull-up (`INPUT_PULLUP`). Falling-edge instantly safety-disarms the system.
- **Software Debouncing**: Integrated 60ms edge validation prevents mechanical contact bounce from causing false state triggers.

### C. HC-SR04 Ultrasonic Distance Sensor
- **Trigger Pin (GPIO 18)**: Sends a 10µs ultrasonic pulse train at 40 kHz.
- **Echo Pin (GPIO 19)**: Measures pulse echo duration via a calibrated voltage divider (converting 5V echo to 3.3V logic).
- **Distance Calculation**: Converts echo travel time to distance ($\text{cm} = \frac{\text{duration} \times 0.0343}{2}$).
- **Proximity Radar Alert**: When user distance drops below 30 cm (`DISTANCE < 30.0 cm`), the ESP32 dispatches `PROXIMITY_ALERT`.

### D. GY-521 MPU-6050 Motion / Accelerometer Sensor
- **I2C Bus Communication**: Connects to ESP32 hardware I2C pins (SDA on GPIO 21, SCL on GPIO 22) with 50ms bus timeout protection.
- **3-Axis Acceleration Sensing**: Reads $A_x, A_y, A_z$ vectors at 16-bit resolution ($\pm 2g$ scale).
- **Motion & Tilt Detection**: Evaluates dynamic acceleration deviations from baseline gravity ($1.0g$).

### E. 6-LED Status Indicator Matrix
- **Red LEDs (GPIO 25 & GPIO 26)**: Illuminate when system is in `DISARMED` state.
- **Green LEDs (GPIO 27 & GPIO 32)**: Illuminate steadily when system is `ARMED` and actively tracking.
- **Blue LEDs (GPIO 33 & GPIO 23)**: Flash during serial communication handshakes and pulse during proximity warnings (<30 cm).

### F. 7th Eye-Controlled Automation LED (GPIO 13)
- **Hardware Wiring**: Anode connected via dedicated 220Ω resistor to ESP32 **GPIO 13**; Cathode connected to common **GND**.
- **Independent Operation**: Driven exclusively by explicit serial commands (`CMD: LIGHT: ON` and `CMD: LIGHT: OFF`).
- **Initial Boot State**: Defaults to OFF (`LOW`) on power-up.
- **Full Isolation**: Operates independently without altering the state machine of the 6 status LEDs or interfering with sensors.
