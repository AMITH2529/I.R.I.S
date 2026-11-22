# 📖 I.R.I.S. System & Hardware Architecture Guide

A concise breakdown of how the **I.R.I.S. v2.5** assistive computing platform and its physical hardware components function.

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

### D. Multimodal Speech & Audio Navigation
- **Voice Commands**: Real-time microphone capture with background speech recognition allows verbal launching of applications ("open browser", "open notepad", "open terminal"), navigation ("click", "scroll up", "scroll down"), and system control ("arm", "disarm", "recenter").
- **Acoustic Feedback**: Low-latency synthesized audio chimes acknowledge arm/disarm actions, clicks, and proximity alerts for motor-disabled users.
- **Always-on-Top Floating HUD**: Compact camera viewport floats persistently over any active application without minimizing.

---

## ⚡ 2. How the Hardware Works

The hardware monitoring unit runs on an **ESP32 DevKit V1** microcontroller connected via USB UART Serial (`COM5` at 115200 baud).

### A. ESP32 DevKit V1 Microcontroller
- **Dual-Core 32-bit Xtensa Processor @ 240 MHz**: Manages sensor polling, debouncing, serial JSON/text packet streaming, and LED matrices without blocking execution.
- **UART Serial Communication**: Exchanges real-time bi-directional telemetry and command packets (`CMD: ARM`, `CMD: DISARM`, `SYSTEM: ARMED`, `DISTANCE:xx.x`, `ACCEL:x,y,z`) with the Python host software.
- **Hardware State Machine**:
  - `STATE_DISARMED`: Tracking paused, Red LEDs active.
  - `STATE_ARMED`: Tracking active, Green LEDs active, real-time sensor radar engaged.

### B. Push Buttons (Hardware Arm / Disarm)
- **ARM Button (GPIO 16)**: Configured with internal pull-up (`INPUT_PULLUP`). Pressing pulls the pin LOW, triggering an immediate hardware interrupt to transition the system to `ARMED` state.
- **DISARM Button (GPIO 17)**: Configured with internal pull-up (`INPUT_PULLUP`). Pressing pulls the pin LOW, instantly safety-disarming the system and halting cursor movement.
- **Software Debouncing**: Integrated 50ms edge validation prevents mechanical contact bounce from causing false state triggers.

### C. HC-SR04 Ultrasonic Distance Sensor
- **Trigger Pin (GPIO 18)**: Sends a 10µs ultrasonic pulse train at 40 kHz.
- **Echo Pin (GPIO 19)**: Measures pulse echo duration via a calibrated voltage divider (converting 5V echo to 3.3V logic).
- **Distance Calculation**: Converts echo travel time to distance ($\text{cm} = \frac{\text{duration} \times 0.0343}{2}$).
- **Proximity Radar Alert**: When user distance drops below the 30 cm safety threshold (`DISTANCE < 30.0 cm`), the ESP32 dispatches `PROXIMITY_ALERT` to trigger visual and audio warnings in the host interface.

### D. GY-521 MPU-6050 Motion / Accelerometer Sensor
- **I2C Bus Communication**: Connects to ESP32 hardware I2C pins (SDA on GPIO 21, SCL on GPIO 22) with a 50ms bus timeout protection.
- **3-Axis Acceleration Sensing**: Reads $A_x, A_y, A_z$ vectors at 16-bit resolution ($\pm 2g$ scale).
- **Motion & Tilt Detection**: Evaluates dynamic acceleration deviations from baseline gravity ($1.0g$). Sudden head or desk impact triggers immediate motion alert packets.

### E. 6-LED Status Indicator Matrix
- **Red LEDs (GPIO 25 & GPIO 26)**: Illuminate when system is in `DISARMED` state or when an alert occurs.
- **Green LEDs (GPIO 27 & GPIO 32)**: Illuminate steadily when the system is `ARMED` and actively tracking.
- **Blue LEDs (GPIO 33 & GPIO 23)**:
  - Flash rapidly during USB serial data synchronization and hardware command handshakes.
  - Pulse to signal user proximity warnings when an obstacle is within 30 cm.
