const int LED_PINS[6] = {25, 26, 27, 32, 33, 23};
const char* LED_NAMES[6] = {
  "RED 1   (GPIO 25)",
  "RED 2   (GPIO 26)",
  "GREEN 1 (GPIO 27)",
  "GREEN 2 (GPIO 32)",
  "BLUE 1  (GPIO 33)",
  "BLUE 2  (GPIO 23)"
};

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n==========================================");
  Serial.println("  I.R.I.S. LED & POWER DIAGNOSTIC TEST   ");
  Serial.println("==========================================");

  for (int i = 0; i < 6; i++) {
    pinMode(LED_PINS[i], OUTPUT);
    digitalWrite(LED_PINS[i], LOW);
  }
  Serial.println("[INFO] GPIO pins configured as OUTPUT.");
}

void loop() {

  Serial.println("\n>> PHASE 1: Turning ALL 6 LEDs ON for 3 seconds...");
  for (int i = 0; i < 6; i++) {
    digitalWrite(LED_PINS[i], HIGH);
  }
  delay(3000);

  Serial.println(">> PHASE 2: Turning ALL 6 LEDs OFF for 1 second...");
  for (int i = 0; i < 6; i++) {
    digitalWrite(LED_PINS[i], LOW);
  }
  delay(1000);

  Serial.println(">> PHASE 3: Cycling through LEDs individually...");
  for (int i = 0; i < 6; i++) {
    Serial.print("   -> Testing pin: ");
    Serial.println(LED_NAMES[i]);
    digitalWrite(LED_PINS[i], HIGH);
    delay(700);
    digitalWrite(LED_PINS[i], LOW);
    delay(300);
  }

  Serial.println("[CYCLE COMPLETE] Repeating test in 2 seconds...");
  delay(2000);
}
