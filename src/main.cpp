#include <FastLED.h>

// ============================================================
// MODE CONFIG
// ============================================================
#define CALIBRATION_MODE false
#define MAP_TEST_MODE false
// #define ENABLE_UDP        // UNCOMMENT to enable future UDP broadcast receive

// ============================================================
// LED MATRIX CONFIG
// ============================================================
#define LED_PIN       4
#define MATRIX_COLS   32
#define MATRIX_ROWS   16
#define NUM_LEDS      (MATRIX_COLS * MATRIX_ROWS)  // 512
#define LED_TYPE      WS2812B
#define COLOR_ORDER   GRB
#define BRIGHTNESS    100

// ============================================================
// POWER LIMITER — cap total demand at 25A (30A fuse protection)
// ============================================================
#define MAX_CURRENT_A  25.0f
#define LED_CURRENT_MA 20.0f   // per-LED full-brightness current

CRGB leds[NUM_LEDS];

// ============================================================
// SERIAL FRAME PROTOCOL
// magic(2) + len(2 LE) + seq(2 LE) + 512*3 GRB bytes
// ============================================================
const uint8_t MAGIC0 = 0xAA;
const uint8_t MAGIC1 = 0xAA;
const uint16_t EXPECTED_LEN = 0x0600;  // 1536
const size_t PAYLOAD_LEN = NUM_LEDS * 3;
const size_t FRAME_HEADER_LEN = 4;   // LEN(2) + SEQ(2)
const size_t FRAME_BUF_LEN = FRAME_HEADER_LEN + PAYLOAD_LEN;  // 4 + 1536 = 1540

static uint8_t rxbuf[FRAME_BUF_LEN];
static size_t rxlen = 0;
static bool in_frame = false;
static uint16_t last_seq = 0;
static bool have_seq = false;
// Last byte seen while scanning for magic. File-scope so it can be reset when
// a frame completes: if it were left at 0xAA (the second magic byte), the
// leading 0xAA of the NEXT frame would falsely re-trigger sync one byte
// early, shifting every subsequent frame by one byte.
static uint8_t scan_prev = 0;

// ============================================================
// POWER LIMITER
// ============================================================
void applyCurrentLimiter() {
  float total = 0.0f;
  for (int i = 0; i < NUM_LEDS; i++) {
    total += ((float)(leds[i].r + leds[i].g + leds[i].b) / 255.0f) * LED_CURRENT_MA;
  }
  total /= 1000.0f;  // mA -> A
  if (total > MAX_CURRENT_A) {
    float scale = MAX_CURRENT_A / total;
    for (int i = 0; i < NUM_LEDS; i++) {
      leds[i].r = (uint8_t)((float)leds[i].r * scale);
      leds[i].g = (uint8_t)((float)leds[i].g * scale);
      leds[i].b = (uint8_t)((float)leds[i].b * scale);
    }
  }
}

// ============================================================
// SERIAL FRAME HANDLING
// ============================================================
void processFrame(const uint8_t* payload, uint16_t seq) {
  if (have_seq) {
    uint16_t expected = (uint16_t)(last_seq + 1);
    // Accept exact next, OR a host-restart resync (seq back to 0 after a gap),
    // OR small forward jumps (dropped frames on the host side).
    bool ok = (seq == expected) || (seq == 0) || ((seq > last_seq) && ((uint16_t)(seq - last_seq) <= 8));
    if (!ok) {
      // genuinely stale / out-of-order — drop
      Serial.println("drop stale");
      return;
    }
  }
  last_seq = seq;
  have_seq = true;

  // Payload is GRB order: [G][R][B] per pixel.
  // FastLED CRGB stores .r/.g/.b fields.
  // So: g_byte = payload[i*3+0], r_byte = payload[i*3+1], b_byte = payload[i*3+2].
  for (int i = 0; i < NUM_LEDS; i++) {
    leds[i].g = payload[i*3 + 0];
    leds[i].r = payload[i*3 + 1];
    leds[i].b = payload[i*3 + 2];
  }
  applyCurrentLimiter();
  FastLED.show();
}

bool handleSerial() {
  bool read_any = false;
  while (Serial.available() > 0) {
    read_any = true;
    uint8_t b = Serial.read();

    if (!in_frame) {
      // look for magic bytes
      if (scan_prev == MAGIC0 && b == MAGIC1) {
        in_frame = true;
        rxlen = 0;
      }
      scan_prev = b;
      continue;
    }

    // We have magic. Now read LEN (2), SEQ (2), then payload.
    if (rxlen < 2) {
      // collecting LEN low byte then high byte
      rxbuf[rxlen] = b;
      rxlen++;
      continue;
    }
    if (rxlen >= 2 && rxlen < 4) {
      if (rxlen == 2) {
        // LEN bytes are complete — validate against EXPECTED_LEN
        uint16_t len = ((uint16_t)rxbuf[0]) | (((uint16_t)rxbuf[1]) << 8);
        if (len != EXPECTED_LEN) {
          // bad frame header — resync
          in_frame = false;
          rxlen = 0;
          scan_prev = 0;
          continue;
        }
      }
      rxbuf[rxlen] = b;
      rxlen++;
      continue;
    }

    uint16_t seq = ((uint16_t)rxbuf[2]) | (((uint16_t)rxbuf[3]) << 8);
    if (rxlen < 4 + PAYLOAD_LEN) {
      rxbuf[rxlen] = b;
      rxlen++;
      if (rxlen == 4 + PAYLOAD_LEN) {
        processFrame(&rxbuf[4], seq);
        in_frame = false;
        rxlen = 0;
        scan_prev = 0;  // prevent false magic trigger on next frame's leading 0xAA
      }
      continue;
    }
    // overflow (shouldn't happen) — resync
    in_frame = false;
    rxlen = 0;
    scan_prev = 0;
  }
  return read_any;
}

// ============================================================
// PANEL MAPPING TEST (diagnostic)
// STATIC frame: all 8 panels lit at once, each a distinct color,
// with a WHITE LED at each panel's top-left corner.
//   - color identifies the logical panel index (legend below)
//   - white dot position reveals a 180° rotation (dot lands on a
//     different corner if the board is physically rotated)
// Legend (logical panel index -> color):
//   0=RED 1=GREEN 2=BLUE 3=YELLOW 4=CYAN 5=MAGENTA 6=ORANGE 7=PURPLE
// ============================================================
void runMapTest() {
  static const CRGB colors[8] = {
    CRGB::Red,    CRGB::Green,  CRGB::Blue,   CRGB::Yellow,
    CRGB::Cyan,   CRGB::Magenta,CRGB::Orange, CRGB::Purple
  };
  FastLED.clear();
  for (int panel = 0; panel < 8; panel++) {
    int brow = panel / 4;      // block row (0 or 1)
    int bcol = panel % 4;      // block col (0..3)
    CRGB c = colors[panel];
    for (int i = 0; i < 64; i++) {
      int y = (brow * 8) + (i / 8);
      int x = (bcol * 8) + (i % 8);
      int idx = y * 32 + x;
      if (idx >= 0 && idx < NUM_LEDS) {
        // i==0 is the local top-left LED of this panel's 8x8 block
        leds[idx] = (i == 0) ? CRGB::White : c;
      }
    }
  }
  applyCurrentLimiter();
  FastLED.show();
  delay(100);   // static — stays put, refreshed harmlessly each loop
}

// ============================================================
// RAINBOW SWEEP (diagnostic)
// ============================================================
void runRainbowSweep() {
  static uint8_t hue = 0;
  fill_rainbow(leds, NUM_LEDS, hue, 1);
  applyCurrentLimiter();
  FastLED.show();
  hue++;
  delay(30);
}

// ============================================================
// DORMANT UDP RECEIVE (future broadcast path)
// ============================================================
#ifdef ENABLE_UDP
#include <WiFi.h>
#include <WiFiUdp.h>
const char* WIFI_SSID = "YourWiFiSSID";
const char* WIFI_PASSWORD = "YourWiFiPassword";
const uint16_t UDP_PORT = 7777;
WiFiUDP udp;

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    attempts++;
  }
  udp.begin(UDP_PORT);
}

void handleUDP() {
  int packetSize = udp.parsePacket();
  if (packetSize == 6 + PAYLOAD_LEN) {   // MAGIC(2)+LEN(2)+SEQ(2)+payload
    uint8_t buf[6 + PAYLOAD_LEN];
    udp.read(buf, sizeof(buf));
    uint16_t seq = ((uint16_t)buf[4]) | (((uint16_t)buf[5]) << 8);
    processFrame(&buf[6], seq);
  }
}
#endif

// ============================================================
// SETUP / LOOP
// ============================================================
void setup() {
  Serial.begin(921600);
  delay(500);
  FastLED.addLeds<LED_TYPE, LED_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.setBrightness(BRIGHTNESS);
  FastLED.clear();
  FastLED.show();

#ifdef ENABLE_UDP
  connectWiFi();
#endif
  if (CALIBRATION_MODE) {
    Serial.println("MODE: Calibration — rainbow sweep");
  } else if (MAP_TEST_MODE) {
    Serial.println("MODE: Panel mapping test");
  } else {
    Serial.println("MODE: USB receive — waiting for frames");
  }
}

void loop() {
  if (MAP_TEST_MODE) {
    runMapTest();
    return;
  }
  if (CALIBRATION_MODE) {
    runRainbowSweep();
    return;
  }
  if (!handleSerial()) {
    vTaskDelay(1);   // no bytes — yield so the Arduino idle task can run
  }
#ifdef ENABLE_UDP
  handleUDP();
#endif
}
