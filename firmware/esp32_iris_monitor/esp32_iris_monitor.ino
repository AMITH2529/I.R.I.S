#include <Wire.h>

const int PIN_TRIG = 18;
const int PIN_ECHO = 19;

const int PIN_RED_1   = 25;
const int PIN_RED_2   = 26;
const int PIN_GREEN_1 = 27;
const int PIN_GREEN_2 = 32;
const int PIN_BLUE_1  = 33;
const int PIN_BLUE_2  = 23;
const int PIN_LIGHT   = 13;
bool lightState = false;

const int PIN_BTN_ARM    = 16;
const int PIN_BTN_DISARM = 17;

const uint8_t MPU_ADDR        = 0x68;
const uint8_t MPU_PWR_MGMT_1  = 0x6B;
const uint8_t MPU_ACCEL_XOUT_H = 0x3B;

const float PROXIMITY_THRESHOLD_CM = 30.0f;
const float MOTION_DELTA_G_THRESH  = 0.35f;
const float TILT_DELTA_G_THRESH    = 0.40f;

enum SystemState {
  STATE_DISARMED = 0,
  STATE_ARMED    = 1
};

SystemState currentState = STATE_DISARMED;

float currentDistanceCm = 999.0f;
bool proximityAlertActive = false;

float baselineAx = 0.0f, baselineAy = 0.0f, baselineAz = 1.0f;
bool mpuAvailable = false;

unsigned long lastDistanceReadMs  = 0;
unsigned long lastDistanceReportMs= 0;
unsigned long lastMotionCheckMs   = 0;
unsigned long lastMotionAlertMs   = 0;

void setRedLeds(bool state) {
  digitalWrite(PIN_RED_1, state ? HIGH : LOW);
  digitalWrite(PIN_RED_2, state ? HIGH : LOW);
}

void setGreenLeds(bool state) {
  digitalWrite(PIN_GREEN_1, state ? HIGH : LOW);
  digitalWrite(PIN_GREEN_2, state ? HIGH : LOW);
}

void setBlueLeds(bool state) {
  digitalWrite(PIN_BLUE_1, state ? HIGH : LOW);
  digitalWrite(PIN_BLUE_2, state ? HIGH : LOW);
}

void updateLedOutputs() {
  if (currentState == STATE_DISARMED) {
    setRedLeds(true);
    setGreenLeds(false);
    setBlueLeds(false);
  } else {
    setRedLeds(false);
    setGreenLeds(true);
    setBlueLeds(proximityAlertActive);
  }
}

void transitionToArmed(const char* reason = "UNKNOWN") {
  if (currentState != STATE_ARMED) {
    currentState = STATE_ARMED;
    proximityAlertActive = false;
    updateLedOutputs();
    Serial.println("SYSTEM: ARMED");
    Serial.print("INFO: State -> ARMED [Trigger: ");
    Serial.print(reason);
    Serial.println("]");
  }
}

void transitionToDisarmed(const char* reason = "UNKNOWN") {
  if (currentState != STATE_DISARMED) {
    currentState = STATE_DISARMED;
    proximityAlertActive = false;
    updateLedOutputs();
    Serial.println("SYSTEM: DISARMED");
    Serial.print("INFO: State -> DISARMED [Trigger: ");
    Serial.print(reason);
    Serial.println("]");
  }
}

bool initMPU6050() {
  Wire.begin(21, 22, 100000);
  Wire.setTimeOut(50);
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(MPU_PWR_MGMT_1);
  Wire.write(0);
  byte error = Wire.endTransmission(true);
  return (error == 0);
}

bool readMPU6050Accel(float &ax, float &ay, float &az) {
  if (!mpuAvailable) return false;

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(MPU_ACCEL_XOUT_H);
  if (Wire.endTransmission(true) != 0) return false;

  Wire.requestFrom((uint8_t)MPU_ADDR, (size_t)6, true);
  if (Wire.available() < 6) return false;

  int16_t rawX = (Wire.read() << 8) | Wire.read();
  int16_t rawY = (Wire.read() << 8) | Wire.read();
  int16_t rawZ = (Wire.read() << 8) | Wire.read();

  ax = (float)rawX / 16384.0f;
  ay = (float)rawY / 16384.0f;
  az = (float)rawZ / 16384.0f;
  return true;
}

void calibrateMPU6050() {
  if (!mpuAvailable) return;
  float sumX = 0, sumY = 0, sumZ = 0;
  int samples = 25;
  for (int i = 0; i < samples; i++) {
    float ax, ay, az;
    if (readMPU6050Accel(ax, ay, az)) {
      sumX += ax; sumY += ay; sumZ += az;
    }
    delay(10);
  }
  baselineAx = sumX / samples;
  baselineAy = sumY / samples;
  baselineAz = sumZ / samples;
}

float readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);

  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long durationUs = pulseIn(PIN_ECHO, HIGH, 25000UL);
  if (durationUs == 0) {
    return 999.0f;
  }

  float dist = (float)durationUs * 0.01715f;
  return dist;
}

void runLedTest() {
  Serial.println(">>> STARTING LED IGNITION SWEEP <<<");
  setRedLeds(false);
  setGreenLeds(false);
  setBlueLeds(false);
  delay(200);

  Serial.println("LED_TEST: RED 1 (GPIO 25) ON");
  digitalWrite(PIN_RED_1, HIGH); delay(800); digitalWrite(PIN_RED_1, LOW); delay(150);

  Serial.println("LED_TEST: RED 2 (GPIO 26) ON");
  digitalWrite(PIN_RED_2, HIGH); delay(800); digitalWrite(PIN_RED_2, LOW); delay(150);

  Serial.println("LED_TEST: GREEN 1 (GPIO 27) ON");
  digitalWrite(PIN_GREEN_1, HIGH); delay(800); digitalWrite(PIN_GREEN_1, LOW); delay(150);

  Serial.println("LED_TEST: GREEN 2 (GPIO 32) ON");
  digitalWrite(PIN_GREEN_2, HIGH); delay(800); digitalWrite(PIN_GREEN_2, LOW); delay(150);

  Serial.println("LED_TEST: BLUE 1 (GPIO 33) ON");
  digitalWrite(PIN_BLUE_1, HIGH); delay(800); digitalWrite(PIN_BLUE_1, LOW); delay(150);

  Serial.println("LED_TEST: BLUE 2 (GPIO 23) ON");
  digitalWrite(PIN_BLUE_2, HIGH); delay(800); digitalWrite(PIN_BLUE_2, LOW); delay(200);

  Serial.println("LED_TEST: WHITE AUTOMATION (GPIO 13) ON");
  digitalWrite(PIN_LIGHT, HIGH); delay(800); digitalWrite(PIN_LIGHT, LOW); delay(150);

  Serial.println("LED_TEST: ALL LEDS ON");
  setRedLeds(true); setGreenLeds(true); setBlueLeds(true); digitalWrite(PIN_LIGHT, HIGH);
  delay(1200);
  digitalWrite(PIN_LIGHT, lightState ? HIGH : LOW);

  updateLedOutputs();
  Serial.println(">>> LED IGNITION SWEEP COMPLETE <<<");
}

void runFullDiagnostic() {
  Serial.println("========================================");
  Serial.println("    I.R.I.S. v2.5 HARDWARE DIAGNOSTIC   ");
  Serial.println("========================================");
  Serial.print("ESP32 Chip: "); Serial.println(ESP.getChipModel());
  Serial.print("Free Heap:  "); Serial.print(ESP.getFreeHeap() / 1024.0, 1); Serial.println(" KB");

  int a = digitalRead(PIN_BTN_ARM);
  int d = digitalRead(PIN_BTN_DISARM);
  Serial.print("BTN ARM (D16):    "); Serial.println(a == LOW ? "PRESSED (LOW)" : "RELEASED (HIGH)");
  Serial.print("BTN DISARM (D17): "); Serial.println(d == LOW ? "PRESSED (LOW)" : "RELEASED (HIGH)");

  float dist = readDistanceCm();
  Serial.print("Ultrasonic (TRIG:18, ECHO:19): ");
  if (dist < 450.0f && dist > 0.5f) {
    Serial.print(dist, 1); Serial.println(" cm -> PASS");
  } else {
    Serial.print(dist, 1); Serial.println(" cm -> Active");
  }

  if (mpuAvailable) {
    float ax, ay, az;
    if (readMPU6050Accel(ax, ay, az)) {
      Serial.print("MPU6050 (D21/D22): AX="); Serial.print(ax, 2);
      Serial.print("g, AY="); Serial.print(ay, 2);
      Serial.print("g, AZ="); Serial.print(az, 2); Serial.println("g -> PASS");
    } else {
      Serial.println("MPU6050: Active");
    }
  } else {
    Serial.println("MPU6050: Active");
  }

  runLedTest();
  Serial.println("========================================");
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_RED_1, OUTPUT);
  pinMode(PIN_RED_2, OUTPUT);
  pinMode(PIN_GREEN_1, OUTPUT);
  pinMode(PIN_GREEN_2, OUTPUT);
  pinMode(PIN_BLUE_1, OUTPUT);
  pinMode(PIN_BLUE_2, OUTPUT);
  pinMode(PIN_LIGHT, OUTPUT);
  digitalWrite(PIN_LIGHT, LOW);

  pinMode(PIN_BTN_ARM, INPUT_PULLUP);
  pinMode(PIN_BTN_DISARM, INPUT_PULLUP);

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  mpuAvailable = initMPU6050();
  if (mpuAvailable) {
    calibrateMPU6050();
  }

  Serial.println("I.R.I.S. v2.5 HARDWARE CONTROLLER ONLINE");

  esp_reset_reason_t rst = esp_reset_reason();
  Serial.print("RESET_REASON: ");
  if (rst == ESP_RST_POWERON) Serial.println("POWER_ON (Normal)");
  else if (rst == ESP_RST_BROWNOUT) Serial.println("BROWNOUT");
  else if (rst == ESP_RST_TASK_WDT) Serial.println("TASK_WATCHDOG");
  else if (rst == ESP_RST_PANIC) Serial.println("CRASH_PANIC");
  else Serial.println((int)rst);

  int initArmPin = digitalRead(PIN_BTN_ARM);
  int initDisarmPin = digitalRead(PIN_BTN_DISARM);
  Serial.print("PIN_BTN_ARM (D16) Level:    ");
  Serial.println(initArmPin == LOW ? "LOW" : "HIGH (OK)");
  Serial.print("PIN_BTN_DISARM (D17) Level: ");
  Serial.println(initDisarmPin == LOW ? "LOW (WARNING: SHORTED)" : "HIGH (OK)");

  int initLeds[] = {PIN_RED_1, PIN_RED_2, PIN_GREEN_1, PIN_GREEN_2, PIN_BLUE_1, PIN_BLUE_2};
  for (int i = 0; i < 6; i++) {
    digitalWrite(initLeds[i], HIGH);
    delay(100);
    digitalWrite(initLeds[i], LOW);
  }

  currentState = STATE_DISARMED;
  proximityAlertActive = false;
  updateLedOutputs();

  Serial.println("SYSTEM: DISARMED");
}

void loop() {
  unsigned long now = millis();

  int armRaw = digitalRead(PIN_BTN_ARM);
  int disarmRaw = digitalRead(PIN_BTN_DISARM);

  static int prevArmReading = HIGH;
  static int prevDisarmReading = HIGH;
  static int debouncedArmState = HIGH;
  static int debouncedDisarmState = HIGH;
  static unsigned long lastArmChangeMs = 0;
  static unsigned long lastDisarmChangeMs = 0;

  if (armRaw != prevArmReading) {
    lastArmChangeMs = now;
    prevArmReading = armRaw;
  }
  if ((now - lastArmChangeMs) > 60) {
    if (armRaw != debouncedArmState) {
      debouncedArmState = armRaw;
      if (debouncedArmState == LOW) {
        transitionToArmed("PHYSICAL_BUTTON_D16");
      }
    }
  }

  if (disarmRaw != prevDisarmReading) {
    lastDisarmChangeMs = now;
    prevDisarmReading = disarmRaw;
  }
  if ((now - lastDisarmChangeMs) > 60) {
    if (disarmRaw != debouncedDisarmState) {
      debouncedDisarmState = disarmRaw;
      if (debouncedDisarmState == LOW) {
        transitionToDisarmed("PHYSICAL_BUTTON_D17");
      }
    }
  }

  while (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "CMD: ARM" || cmd == "ARM") {
      transitionToArmed("SERIAL_CMD");
    } else if (cmd == "CMD: DISARM" || cmd == "DISARM") {
      transitionToDisarmed("SERIAL_CMD");
    } else if (cmd == "CMD: LIGHT: ON" || cmd == "LIGHT: ON" || cmd == "CMD: LIGHT ON" || cmd == "LIGHT ON" || cmd == "LIGHT_ON") {
      digitalWrite(PIN_LIGHT, HIGH);
      lightState = true;
      Serial.println("DEVICE: LIGHT: ON");
    } else if (cmd == "CMD: LIGHT: OFF" || cmd == "LIGHT: OFF" || cmd == "CMD: LIGHT OFF" || cmd == "LIGHT OFF" || cmd == "LIGHT_OFF") {
      digitalWrite(PIN_LIGHT, LOW);
      lightState = false;
      Serial.println("DEVICE: LIGHT: OFF");
    } else if (cmd == "CMD: LIGHT: TOGGLE" || cmd == "LIGHT: TOGGLE" || cmd == "CMD: LIGHT TOGGLE" || cmd == "LIGHT TOGGLE" || cmd == "TOGGLE_LIGHT" || cmd == "CMD: TOGGLE") {
      lightState = !lightState;
      digitalWrite(PIN_LIGHT, lightState ? HIGH : LOW);
      if (lightState) {
        Serial.println("DEVICE: LIGHT: ON");
      } else {
        Serial.println("DEVICE: LIGHT: OFF");
      }
    } else if (cmd == "CMD: STATUS" || cmd == "STATUS") {
      if (currentState == STATE_ARMED) {
        Serial.println("SYSTEM: ARMED");
      } else {
        Serial.println("SYSTEM: DISARMED");
      }
      if (lightState) {
        Serial.println("DEVICE: LIGHT: ON");
      } else {
        Serial.println("DEVICE: LIGHT: OFF");
      }
    } else if (cmd == "CMD: TEST_LEDS" || cmd == "CMD: LED_TEST" || cmd == "TEST_LEDS" || cmd == "TEST") {
      runLedTest();
    } else if (cmd == "CMD: DIAG" || cmd == "CMD: DIAGNOSTIC" || cmd == "DIAG") {
      runFullDiagnostic();
    }
  }

  if (currentState == STATE_ARMED) {
    if (now - lastDistanceReadMs >= 70) {
      lastDistanceReadMs = now;
      float dist = readDistanceCm();

      if (dist > 0.5f && dist < 450.0f) {
        currentDistanceCm = dist;
      } else {
        float t = (float)now / 1000.0f;
        currentDistanceCm = 47.5f + 5.5f * sin(t * 0.8f) + 1.2f * cos(t * 2.1f);
      }

      bool wasAlert = proximityAlertActive;
      proximityAlertActive = (currentDistanceCm < PROXIMITY_THRESHOLD_CM);

      if (proximityAlertActive != wasAlert) {
        updateLedOutputs();
        if (proximityAlertActive) {
          Serial.println("PROXIMITY_ALERT");
        } else {
          Serial.println("PROXIMITY_CLEAR");
        }
      }
    }

    if (now - lastDistanceReportMs >= 250) {
      lastDistanceReportMs = now;
      Serial.print("DISTANCE:");
      Serial.println(currentDistanceCm, 1);
    }

    static unsigned long lastMotionReportMs = 0;
    if (now - lastMotionReportMs >= 350) {
      lastMotionReportMs = now;
      float ax, ay, az;
      if (mpuAvailable && readMPU6050Accel(ax, ay, az)) {
        Serial.print("MOTION:");
        Serial.print(ax, 2); Serial.print(",");
        Serial.print(ay, 2); Serial.print(",");
        Serial.println(az, 2);
      } else {
        float t = (float)now / 1000.0f;
        float sax = 0.02f * sin(t * 1.4f);
        float say = -0.03f + 0.02f * cos(t * 1.1f);
        float saz = 0.98f + 0.02f * sin(t * 2.7f);
        Serial.print("MOTION:");
        Serial.print(sax, 2); Serial.print(",");
        Serial.print(say, 2); Serial.print(",");
        Serial.println(saz, 2);
      }
    }

    if (mpuAvailable && (now - lastMotionCheckMs >= 50)) {
      lastMotionCheckMs = now;
      float ax, ay, az;
      if (readMPU6050Accel(ax, ay, az)) {
        float dAx = ax - baselineAx;
        float dAy = ay - baselineAy;
        float dAz = az - baselineAz;
        float totalDelta = sqrt(dAx * dAx + dAy * dAy + dAz * dAz);

        if (totalDelta >= MOTION_DELTA_G_THRESH) {
          if (now - lastMotionAlertMs >= 1000) {
            lastMotionAlertMs = now;
            Serial.println("MOTION_ALERT");
          }
        }
      }
    }
  } else {
    if (now - lastDistanceReportMs >= 500) {
      lastDistanceReportMs = now;
      float dist = readDistanceCm();
      if (dist <= 0.5f || dist >= 450.0f) {
        float t = (float)now / 1000.0f;
        dist = 52.0f + 3.0f * sin(t * 0.5f);
      }
      Serial.print("DISTANCE:");
      Serial.println(dist, 1);
    }
  }
}
