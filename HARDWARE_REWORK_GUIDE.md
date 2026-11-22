# I.R.I.S. v2.5 — Complete Hardware Circuit Rework & Wiring Guide
**Engineered for Assistive Computing & Motor-Disabled Persons**

---

## 1. Executive Summary & Circuit Architecture

This guide provides the complete hardware rebuild instructions for the **I.R.I.S. (Intelligent Real-time Interface System) v2.5** physical telemetry controller.

The hardware module interfaces with your PC via **USB Serial at 115200 baud (COM5)** and integrates:
1. **ESP32 DevKit V1** (30-pin or 36-pin Microcontroller)
2. **GY-521 MPU-6050** (6-DOF IMU — 3-axis Accelerometer & 3-axis Gyroscope via I2C)
3. **HC-SR04 Ultrasonic Distance Sensor** (Sonar radar measuring user distance)
4. **6 Status LEDs** (2x Red for Disarmed, 2x Green for Armed, 2x Blue for Proximity/Assistive Alert)
5. **2 Tactile Push Buttons** (ARM on GPIO 16, DISARM on GPIO 17 with internal pullups)

---

## 2. LED Polarity Guide (When Legs Have Been Cut)

If your LED leads were cut short, you **cannot** use lead length to identify the positive terminal. Use the following visual indicators inside and outside the epoxy lens:

```
       ROUND RIM            FLAT RIM (Notch)
          │                      │
          │      ┌────────┐      │
          │     /  LED     \     │
          │    │   LENS     │    │
          │    │            │    │
          │    │ ┌──┐       │    │
          │    │ │  │ ┌───┐ │    │
          │    │ │  │ │   │ │    │
          │    │ │  │ │   │ │    │
          │    └─┴──┴─┴───┴─┘    │
          │      │      │        │
          └──────┼──────┴────────┘
                 │      │
               ANODE  CATHODE
                (+)     (-)
               SMALL   LARGE "ANVIL/FLAG"
              CONTACT  CONTACT
                 │      │
             To Resistor To GND
              & GPIO     Rail
```

1. **Look Inside the Transparent Dome (Most Reliable)**:
   - **Anode (+)**: The smaller, slender wire post inside the epoxy dome. This connects through a 220Ω resistor to the ESP32 GPIO.
   - **Cathode (-)**: The much larger, triangular or anvil-shaped flag electrode. This connects to the breadboard **GND rail**.
2. **Look at the Plastic Base Rim**:
   - Standard 5mm and 3mm LEDs have a distinct **flat notch** along the circular lip at the base.
   - The pin closest to the **flat notch** is **ALWAYS the Cathode (- / GND)**.
3. **Quick 3V Battery Test**:
   - Take a CR2032 button cell (or touch momentarily to ESP32 3.3V and GND). The side touching the battery (+) is your Anode.

---

## 3. Complete Master Pinout & Connection Table

| Component | Component Pin | ESP32 Pin | Purpose / Function | Voltage Level |
| :--- | :--- | :--- | :--- | :--- |
| **HC-SR04** | VCC | **VIN (or 5V)** | Ultrasonic Transducer Power | **5.0V (USB)** |
| **HC-SR04** | GND | **GND** | Ground Reference | 0V |
| **HC-SR04** | TRIG | **GPIO 18** | 10µs Ultrasonic Trigger Pulse | 3.3V Logic |
| **HC-SR04** | ECHO | **GPIO 19** *(via divider)* | Echo pulse timing (<450cm) | **~3.0V** *(stepped down)* |
| **GY-521 MPU-6050**| VCC | **3V3** | Sensor Core & Gyroscope Power | 3.3V |
| **GY-521 MPU-6050**| GND | **GND** | Ground Reference | 0V |
| **GY-521 MPU-6050**| SCL | **GPIO 22** | I2C Clock Line | 3.3V |
| **GY-521 MPU-6050**| SDA | **GPIO 21** | I2C Data Line | 3.3V |
| **GY-521 MPU-6050**| AD0 | **GND** | Locks I2C Address to `0x68` | 0V |
| **Red LED 1** | Anode (+) | **GPIO 25** *(via 220Ω)* | DISARMED State Indicator | 3.3V |
| **Red LED 1** | Cathode (-) | **GND** | Ground Rail | 0V |
| **Red LED 2** | Anode (+) | **GPIO 26** *(via 220Ω)* | DISARMED State Indicator | 3.3V |
| **Red LED 2** | Cathode (-) | **GND** | Ground Rail | 0V |
| **Green LED 1** | Anode (+) | **GPIO 27** *(via 220Ω)* | ARMED State Indicator | 3.3V |
| **Green LED 1** | Cathode (-) | **GND** | Ground Rail | 0V |
| **Green LED 2** | Anode (+) | **GPIO 32** *(via 220Ω)* | ARMED State Indicator | 3.3V |
| **Green LED 2** | Cathode (-) | **GND** | Ground Rail | 0V |
| **Blue LED 1** | Anode (+) | **GPIO 33** *(via 220Ω)* | Assistive / Proximity Alert (<30cm) | 3.3V |
| **Blue LED 1** | Cathode (-) | **GND** | Ground Rail | 0V |
| **Blue LED 2** | Anode (+) | **GPIO 23** *(via 220Ω)* | Assistive / Proximity Alert (<30cm) | 3.3V |
| **Blue LED 2** | Cathode (-) | **GND** | Ground Rail | 0V |
| **ARM Button** | Terminal 1 | **GPIO 16** | Active-LOW Arm Trigger (`INPUT_PULLUP`) | 3.3V |
| **ARM Button** | Terminal 2 | **GND** | Ground Rail | 0V |
| **DISARM Button**| Terminal 1 | **GPIO 17** | Active-LOW Disarm Trigger (`INPUT_PULLUP`)| 3.3V |
| **DISARM Button**| Terminal 2 | **GND** | Ground Rail | 0V |

---

## 4. Voltage Divider for HC-SR04 ECHO Pin

The HC-SR04 **ECHO** pin outputs a **5V logic pulse**. Connecting 5V directly to an ESP32 GPIO pin (rated for 3.3V maximum) can damage the pin over time. Use two standard resistors to divide the voltage safely.

```
HC-SR04 ECHO Pin (5V Pulse)
          │
          ▼
      ┌───────┐
      │  R1   │  2.2kΩ (or 1kΩ)
      └───────┘
          │
          ├──────────────────────────► To ESP32 GPIO 19 (~3.0V Safe)
          │
      ┌───────┐
      │  R2   │  3.3kΩ (or 2kΩ)
      └───────┘
          │
          ▼
     Breadboard GND Rail
```

- Formula: $V_{out} = 5.0\text{V} \times \frac{3300\Omega}{2200\Omega + 3300\Omega} = 5.0\text{V} \times 0.60 = 3.0\text{V}$ (Ideal logic HIGH for ESP32).

---

## 5. Breadboard Step-by-Step Wiring Sequence

### Step A: Power Rails & Split-Rail Check
1. Connect ESP32 **GND** pin to the **blue/black (-) power rail** on your breadboard.
2. Connect ESP32 **3V3** pin to the **red (+) power rail** on the upper half.
3. Connect ESP32 **VIN** pin directly to HC-SR04 **VCC** (VIN provides 5V from the USB port).
4. **Check for split power rails**: Many 830-tie-point breadboards have a break in the middle of the long power rails. If your board has a break, add a jumper wire connecting the left and right halves of the (-) and (+) rails.

### Step B: Wire the 6 LEDs (Pins 25, 26, 27, 32, 33, 23)
1. Place the 6 LEDs along the breadboard with Cathodes (-) facing the ground rail.
2. Connect a **220Ω or 330Ω resistor** in series with each LED (between the ESP32 GPIO and the LED Anode (+)).
3. Connect the LED Cathode (-) to the **GND rail**.
   - **Red 1**: ESP32 GPIO 25 -> 220Ω -> Red LED 1 Anode -> Cathode to GND
   - **Red 2**: ESP32 GPIO 26 -> 220Ω -> Red LED 2 Anode -> Cathode to GND
   - **Green 1**: ESP32 GPIO 27 -> 220Ω -> Green LED 1 Anode -> Cathode to GND
   - **Green 2**: ESP32 GPIO 32 -> 220Ω -> Green LED 2 Anode -> Cathode to GND
   - **Blue 1**: ESP32 GPIO 33 -> 220Ω -> Blue LED 1 Anode -> Cathode to GND
   - **Blue 2**: ESP32 GPIO 23 -> 220Ω -> Blue LED 2 Anode -> Cathode to GND

### Step C: Wire the 2 Tactile Buttons (Pins 16, 17) & Orientation Warning
> [!WARNING]
> **4-Pin Tactile Switch Orientation**:
> Inside a standard 4-pin push button, pairs of pins on the same side are **permanently connected together**.
> - If you rotate the button by 90 degrees, the internal bridge will **permanently short GPIO 17 to GND**, causing the ESP32 to immediately disarm itself!
> - **How to orient properly**: Straddle the center trench/divider of the breadboard so the pins point across the trench. Connect one leg to the GPIO pin, and the **diagonally opposite leg** to the GND rail.
1. Push buttons use the ESP32's internal pull-up resistor (`INPUT_PULLUP`). **No external resistors are required.**
2. Place **ARM Button**: One pin connects to ESP32 **GPIO 16**, the diagonally opposite pin connects to **GND rail**.
3. Place **DISARM Button**: One pin connects to ESP32 **GPIO 17**, the diagonally opposite pin connects to **GND rail**.

### Step D: Wire the GY-521 MPU-6050
1. Connect MPU-6050 **VCC** to ESP32 **3V3**.
2. Connect MPU-6050 **GND** to breadboard **GND rail**.
3. Connect MPU-6050 **SCL** to ESP32 **GPIO 22**.
4. Connect MPU-6050 **SDA** to ESP32 **GPIO 21**.
5. Connect MPU-6050 **AD0** to breadboard **GND rail** (fixes I2C address to `0x68`).

### Step E: Wire the HC-SR04 Ultrasonic Sensor
1. Connect HC-SR04 **VCC** to ESP32 **VIN** (5V).
2. Connect HC-SR04 **GND** to breadboard **GND rail**.
3. Connect HC-SR04 **TRIG** to ESP32 **GPIO 18**.
4. Connect HC-SR04 **ECHO** to **R1 (2.2kΩ)**.
5. Connect the junction between **R1** and **R2 (3.3kΩ)** to ESP32 **GPIO 19**.
6. Connect the other end of **R2** to breadboard **GND rail**.

---

## 6. Testing & Interactive Diagnostics

Run the interactive hardware diagnostic script from PowerShell or double-click `run_hardware_test.bat`:
```bash
python test_hardware_interactive.py
```
- Press **[1]**: Sequential 6-LED ignition test.
- Press **[2]**: Arm system (turns on Green LEDs).
- Press **[3]**: Disarm system (turns on Red LEDs).
- Press **[4]**: Full component diagnostic (ESP32 chip, ultrasonic, MPU-6050, buttons).
- Press **[5]**: Continuous radar distance & motion telemetry stream.

---

## 7. Troubleshooting: Why the Board Was Disarming Itself & How It Is Solved

If your ESP32 was arming and then immediately disarming itself within a second, here is exactly why it happened and how the updated code resolves it:

### 1. Level-Triggered vs. Edge-Triggered Button Logic (SOLVED)
- **Previous Issue**: The previous firmware checked `if (disarmReading == LOW)`. If a button pin stayed LOW or had contact bounce, the condition remained continuously true. Whenever the software armed the board, the next loop cycle immediately forced it back to DISARMED!
- **The Solution**: The firmware now uses **falling-edge detection**. The button triggers **ONLY ONCE** on the exact moment it transitions from `HIGH` (released) to `LOW` (pressed down). Even if the button is held down or shorted, it will **NEVER** continuously force a disarm.

### 2. Button Rotation on Breadboard
- In standard 4-pin tactile buttons, the two pins on the same side are internally connected together.
- If you plug the button in turned 90 degrees, the internal bridge connects GPIO 17 directly to GND, holding the pin permanently LOW.
- **Check**: Open the Arduino Serial Monitor at 115200 baud on boot. The firmware now prints:
  `PIN_BTN_DISARM (D17) Level: HIGH (OK - Open)`
  If it says `LOW (WARNING: SHORTED TO GND)`, unplug the button or rotate it 90 degrees across the breadboard trench.

### 3. I2C Bus Hang & Watchdog Reboot (SOLVED)
- If the MPU-6050 had loose wires or an unstable clock line during repeated-start (`Wire.endTransmission(false)`), the I2C bus would hang, causing the ESP32 Task Watchdog Timer to reboot the chip after 3 seconds.
- On reboot, the ESP32 starts in the default `DISARMED` state.
- **The Solution**: We added `Wire.setTimeOut(50)` and clean bus release `Wire.endTransmission(true)` so I2C reads never block or reboot the ESP32.

### 4. Clear Diagnostic Reason Output
Whenever the board changes state, it now explicitly prints the exact cause to Serial:
- `INFO: State -> DISARMED [Trigger: PHYSICAL_BUTTON_D17]`
- `INFO: State -> DISARMED [Trigger: SERIAL_CMD]`
- `INFO: State -> ARMED [Trigger: PHYSICAL_BUTTON_D16]`
- `INFO: State -> ARMED [Trigger: SERIAL_CMD]`
You can now immediately see in the Serial Monitor what triggered the state change!
