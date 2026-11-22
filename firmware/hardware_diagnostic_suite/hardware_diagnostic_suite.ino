#include <Wire.h>

const int PIN_RED_1   = 25;
const int PIN_RED_2   = 26;
const int PIN_GREEN_1 = 27;
const int PIN_GREEN_2 = 32;
const int PIN_BLUE_1  = 33;
const int PIN_BLUE_2  = 23;

const int PIN_BTN_ARM    = 16;
const int PIN_BTN_DISARM = 17;

const int PIN_TRIG = 18;
const int PIN_ECHO = 19;

const uint8_t MPU_ADDR = 0x68;

bool mpuConnected = false;
unsigned long lastLoopReportMs = 0;
int ledCycleStep = 0;

void printDivider() {
  Serial.println("======================================================================");
}

void setup() {
  Serial.begin(115200);
  delay(1200);

  printDivider();
  Serial.println("         I.R.I.S. v2.5 — HARDWARE COMPONENT DIAGNOSTIC SUITE          ");
  printDivider();

  Serial.println("\n[1/5] ESP32 CHIP & SYSTEM INFORMATION:");
  Serial.print("  - Chip Model:       "); Serial.println(ESP.getChipModel());
  Serial.print("  - Chip Revision:    v"); Serial.println(ESP.getChipRevision());
  Serial.print("  - CPU Cores / Freq: 2 Cores @ "); Serial.print(ESP.getCpuFreqMHz()); Serial.println(" MHz");
  Serial.print("  - Free Heap Memory: "); Serial.print(ESP.getFreeHeap() / 1024.0, 1); Serial.println(" KB");
  Serial.print("  - Flash Memory:     "); Serial.print(ESP.getFlashChipSize() / (1024 * 1024)); Serial.println(" MB");
  Serial.println("  -> [PASS] ESP32 Core Online & Functioning.");

  pinMode(PIN_RED_1, OUTPUT);
  pinMode(PIN_RED_2, OUTPUT);
  pinMode(PIN_GREEN_1, OUTPUT);
  pinMode(PIN_GREEN_2, OUTPUT);
  pinMode(PIN_BLUE_1, OUTPUT);
  pinMode(PIN_BLUE_2, OUTPUT);

  pinMode(PIN_BTN_ARM, INPUT_PULLUP);
  pinMode(PIN_BTN_DISARM, INPUT_PULLUP);

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  Serial.println("\n[2/5] I2C BUS SCAN & MPU-6050 (SDA: GPIO 21, SCL: GPIO 22):");
  Wire.begin(21, 22, 100000);

  byte error, address;
  int devicesFound = 0;
  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();
    if (error == 0) {
      Serial.print("  - I2C Device detected at 0x");
      if (address < 16) Serial.print("0");
      Serial.print(address, HEX);
      if (address == 0x68) {
        Serial.println(" -> MPU-6050 Gyro/Accel (Default Address)");
        mpuConnected = true;
      } else if (address == 0x69) {
        Serial.println(" -> MPU-6050 Gyro/Accel (AD0 High Address)");
        mpuConnected = true;
      } else {
        Serial.println();
      }
      devicesFound++;
    }
  }

  if (devicesFound == 0) {
    Serial.println("  [WARN] No I2C devices detected on GPIO 21/22.");
    Serial.println("         Check MPU-6050: VCC->3.3V, GND->GND, SDA->D21, SCL->D22.");
  } else {

    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x6B);
    Wire.write(0x00);
    Wire.endTransmission();
    Serial.println("  -> [PASS] MPU-6050 Initialized & Woken Up.");
  }

  Serial.println("\n[3/5] PUSH BUTTONS INITIAL READ (Internal Pull-Up Active):");
  int armState = digitalRead(PIN_BTN_ARM);
  int disarmState = digitalRead(PIN_BTN_DISARM);
  Serial.print("  - ARM Button (GPIO 16):    ");
  Serial.println(armState == HIGH ? "RELEASED (HIGH - 3.3V) [PASS]" : "PRESSED (LOW - 0V)");
  Serial.print("  - DISARM Button (GPIO 17): ");
  Serial.println(disarmState == HIGH ? "RELEASED (HIGH - 3.3V) [PASS]" : "PRESSED (LOW - 0V)");

  Serial.println("\n[4/5] HC-SR04 ULTRASONIC SENSOR INITIALIZATION (TRIG:18, ECHO:19):");
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long duration = pulseIn(PIN_ECHO, HIGH, 30000UL);
  if (duration > 0) {
    float dist = (float)duration * 0.01715f;
    Serial.print("  - Echo Pulse Duration: "); Serial.print(duration); Serial.println(" us");
    Serial.print("  - Measured Distance:   "); Serial.print(dist, 1); Serial.println(" cm");
    Serial.println("  -> [PASS] HC-SR04 Ultrasonic Sensor Operational.");
  } else {
    Serial.println("  - Echo Pulse: Timeout (0 us)");
    Serial.println("  [INFO] Verify HC-SR04: VCC->5V (VIN), GND->GND, TRIG->D18, ECHO->2.2k/3.3k Divider->D19.");
  }

  Serial.println("\n[5/5] 6-LED SEQUENTIAL HARDWARE IGNITION SWEEP:");
  Serial.println("  Watch each LED light up in order on your breadboard:\n");

  const int leds[] = {PIN_RED_1, PIN_RED_2, PIN_GREEN_1, PIN_GREEN_2, PIN_BLUE_1, PIN_BLUE_2};
  const char* ledNames[] = {
    "RED 1   (GPIO 25)",
    "RED 2   (GPIO 26)",
    "GREEN 1 (GPIO 27)",
    "GREEN 2 (GPIO 32)",
    "BLUE 1  (GPIO 33)",
    "BLUE 2  (GPIO 23)"
  };

  for (int i = 0; i < 6; i++) digitalWrite(leds[i], LOW);
  delay(300);

  for (int i = 0; i < 6; i++) {
    Serial.print("  -> Lighting "); Serial.print(ledNames[i]); Serial.println(" [ON] ...");
    digitalWrite(leds[i], HIGH);
    delay(700);
    digitalWrite(leds[i], LOW);
    delay(150);
  }

  Serial.println("  -> Lighting ALL 6 LEDs Simultaneously [ALL ON] ...");
  for (int i = 0; i < 6; i++) digitalWrite(leds[i], HIGH);
  delay(1200);
  for (int i = 0; i < 6; i++) digitalWrite(leds[i], LOW);
  Serial.println("  -> [PASS] LED Ignition Sweep Complete.");

  printDivider();
  Serial.println("  DIAGNOSTIC SETUP COMPLETE -> ENTERING CONTINUOUS MONITOR MODE  ");
  Serial.println("  Press buttons or wave hand in front of ultrasonic sensor now!  ");
  printDivider();
}

void loop() {
  unsigned long now = millis();

  if (now - lastLoopReportMs >= 400) {
    lastLoopReportMs = now;

    bool armPressed = (digitalRead(PIN_BTN_ARM) == LOW);
    bool disarmPressed = (digitalRead(PIN_BTN_DISARM) == LOW);

    digitalWrite(PIN_TRIG, LOW);
    delayMicroseconds(2);
    digitalWrite(PIN_TRIG, HIGH);
    delayMicroseconds(10);
    digitalWrite(PIN_TRIG, LOW);
    unsigned long duration = pulseIn(PIN_ECHO, HIGH, 25000UL);
    float dist = (duration > 0) ? ((float)duration * 0.01715f) : 999.0f;

    float ax = 0, ay = 0, az = 0, mag = 0;
    if (mpuConnected) {
      Wire.beginTransmission(MPU_ADDR);
      Wire.write(0x3B);
      if (Wire.endTransmission(false) == 0) {
        Wire.requestFrom((uint8_t)MPU_ADDR, (size_t)6, true);
        if (Wire.available() >= 6) {
          int16_t rx = (Wire.read() << 8) | Wire.read();
          int16_t ry = (Wire.read() << 8) | Wire.read();
          int16_t rz = (Wire.read() << 8) | Wire.read();
          ax = (float)rx / 16384.0f;
          ay = (float)ry / 16384.0f;
          az = (float)rz / 16384.0f;
          mag = sqrt(ax * ax + ay * ay + az * az);
        }
      }
    }

    Serial.print("[STATUS] ");

    if (dist < 450.0f) {
      Serial.print("DIST: "); Serial.print(dist, 1); Serial.print("cm ");
      if (dist < 30.0f) Serial.print("<PROX!> ");
    } else {
      Serial.print("DIST: -- ");
    }

    if (mpuConnected) {
      Serial.print("| MPU: (");
      Serial.print(ax, 2); Serial.print(", ");
      Serial.print(ay, 2); Serial.print(", ");
      Serial.print(az, 2); Serial.print(") |Mag: ");
      Serial.print(mag, 2); Serial.print("g ");
    }

    Serial.print("| BTN: ");
    if (armPressed) Serial.print("[ARM PRESSED!] ");
    else if (disarmPressed) Serial.print("[DISARM PRESSED!] ");
    else Serial.print("[RESTING] ");

    Serial.println();

    bool prox = (dist < 30.0f);
    digitalWrite(PIN_BLUE_1, prox ? HIGH : LOW);
    digitalWrite(PIN_BLUE_2, prox ? HIGH : LOW);

    if (armPressed) {
      digitalWrite(PIN_GREEN_1, HIGH);
      digitalWrite(PIN_GREEN_2, HIGH);
    } else if (!prox) {
      digitalWrite(PIN_GREEN_1, LOW);
      digitalWrite(PIN_GREEN_2, LOW);
    }

    if (disarmPressed) {
      digitalWrite(PIN_RED_1, HIGH);
      digitalWrite(PIN_RED_2, HIGH);
    } else if (!prox) {
      digitalWrite(PIN_RED_1, LOW);
      digitalWrite(PIN_RED_2, LOW);
    }
  }
}
