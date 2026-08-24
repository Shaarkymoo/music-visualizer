/*
 * main.cpp — ESP32 LED Matrix Receiver
 *
 * Two modes:
 *   CALIBRATION_MODE = true  → infinite rainbow sweep (data-path test)
 *   CALIBRATION_MODE = false → connects WiFi, prints IP, blinks onboard LED
 *
 * Step 3: Set CALIBRATION_MODE = true, flash, watch for the rainbow.
 *         If LEDs light up, the data path (ESP32 → level shifter → boards)
 *         is proven. Switch to false later for normal operation.
 */

#include <WiFi.h>
#include <FastLED.h>

// ============================================================
// USER CONFIG — change these before flashing
// ============================================================

#define CALIBRATION_MODE true

const char* WIFI_SSID     = "YourWiFiSSID";
const char* WIFI_PASSWORD = "YourWiFiPassword";

// ============================================================
// LED MATRIX CONFIG
// D4 = GPIO4 (confirmed by board silkscreen)
// ============================================================

#define LED_PIN       4
#define MATRIX_COLS   32
#define MATRIX_ROWS   16
#define NUM_LEDS      (MATRIX_COLS * MATRIX_ROWS)  // 512 (full wall)
#define LED_TYPE      WS2812B
#define COLOR_ORDER   GRB
#define BRIGHTNESS    100

CRGB leds[NUM_LEDS];

// ============================================================
// FORWARD DECLARATIONS
// ============================================================

void connectWiFi();
void runRainbowSweep();
void blinkBuiltin();

// ============================================================
// SETUP
// ============================================================

void setup() {
  Serial.begin(115200);

  delay(500);
  Serial.println();
  Serial.println("==================================");
  Serial.println("  ESP32 LED Matrix Receiver");
  Serial.println("==================================");

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  FastLED.addLeds<LED_TYPE, LED_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.setBrightness(BRIGHTNESS);
  FastLED.clear();
  FastLED.show();

  if (CALIBRATION_MODE) {
    Serial.println("MODE: Calibration — infinite rainbow sweep");
    Serial.println("Starting in 5 seconds...");
    for (int i = 5; i > 0; i--) {
      Serial.print(i);
      Serial.print("... ");
      delay(1000);
    }
    Serial.println("GO");
  } else {
    Serial.println("MODE: Normal — connecting WiFi");
    connectWiFi();
  }
}

// ============================================================
// LOOP
// ============================================================

void loop() {
  if (CALIBRATION_MODE) {
    runRainbowSweep();
    return;
  }

  // Normal mode: blink the onboard LED and report WiFi status
  blinkBuiltin();

  static unsigned long last_report = 0;
  unsigned long now = millis();
  if (now - last_report > 10000) {
    last_report = now;
    Serial.print("[heartbeat] WiFi: ");
    Serial.print(WiFi.status() == WL_CONNECTED ? "connected" : "disconnected");
    Serial.print(" | RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.print(" dBm | IP: ");
    Serial.println(WiFi.localIP());
  }
}

// ============================================================
// RAINBOW SWEEP — runs forever, loops back after 255 hues
// ============================================================

void runRainbowSweep() {
  static uint8_t hue = 0;

  fill_rainbow(leds, NUM_LEDS, hue, 1);
  FastLED.show();

  hue++;          // advance hue each frame
  delay(30);      // ~33 fps, full cycle every ~7.7s
}

// ============================================================
// WIFI CONNECTION
// ============================================================

void connectWiFi() {
  Serial.print("Connecting to ");
  Serial.print(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;

    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
  }

  digitalWrite(LED_BUILTIN, LOW);

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("WiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("WiFi FAILED — check SSID/password");
  }
}

// ============================================================
// BUILT-IN LED BLINK (alive indicator, normal mode only)
// ============================================================

void blinkBuiltin() {
  static unsigned long last_toggle = 0;
  static bool state = false;
  unsigned long now = millis();

  if (now - last_toggle > 500) {
    last_toggle = now;
    state = !state;
    digitalWrite(LED_BUILTIN, state);
  }
}
