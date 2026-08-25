#include <FastLED.h>

// ============================================================
// MODE CONFIG
// ============================================================
#define CALIBRATION_MODE false
#define MAP_TEST_MODE false
// #define ENABLE_UDP        // UNCOMMENT to enable future UDP broadcast receive
// #define SERIAL_DIAGNOSTICS   // UNCOMMENT to print "[diag] rx= stale= ..." every 2s

// Lock-step flow control: byte sent after each FastLED.show() completes.
// The host (python/serial_sink.py) waits for it before sending the next
// frame, so no UART bytes ever arrive during the show() RX-starvation
// window. An unacknowledging host simply never reads it (harmless).
#define FRAME_ACK_BYTE 0x01

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
// Timestamp of the last byte read, for the frame-assembly timeout. If a byte
// is lost mid-frame (RX overflow), rxlen stalls; after FRAME_TIMEOUT_MS of
// silence we resync instead of staying stuck. A full frame takes ~17ms at
// 921600, so 50ms is a safe "this frame is dead" threshold.
static uint32_t last_byte_ms = 0;
const uint32_t FRAME_TIMEOUT_MS = 50;
// Set by processFrame() when a complete frame has been written into leds[].
// loop() clears it after calling FastLED.show() — so showing happens at the
// loop rate, never inside the serial drain (which must not block).
static bool frame_ready = false;

// ---- diagnostics ----
static uint32_t diag_frames_rx = 0;     // complete frames parsed
static uint32_t diag_frames_stale = 0;  // seq-gate drops
static uint32_t diag_len_resync = 0;    // LEN-validation resyncs
static uint32_t diag_shows = 0;         // FastLED.show() calls
static uint32_t diag_last_show_us = 0;  // last show() duration, microseconds

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
      diag_frames_stale++;
      return;
    }
  }
  last_seq = seq;
  have_seq = true;
  diag_frames_rx++;

  // Payload is GRB order: [G][R][B] per pixel.
  // FastLED CRGB stores .r/.g/.b fields.
  // So: g_byte = payload[i*3+0], r_byte = payload[i*3+1], b_byte = payload[i*3+2].
  for (int i = 0; i < NUM_LEDS; i++) {
    leds[i].g = payload[i*3 + 0];
    leds[i].r = payload[i*3 + 1];
    leds[i].b = payload[i*3 + 2];
  }
  applyCurrentLimiter();
  // NOTE: FastLED.show() is deliberately NOT called here. Showing inside the
  // serial drain loop blocks for ~15-30ms (512 LEDs), which stalls the drain,
  // overflows the RX buffer under continuous frames, corrupts frames, and
  // desyncs the receiver. loop() calls show() once per iteration instead,
  // so the drain never blocks on the LED update.
  frame_ready = true;
}

bool handleSerial() {
  bool read_any = false;
  // Frame-assembly timeout: if we're mid-frame but no byte arrives for longer
  // than a full frame period, a byte was lost (RX overflow) and rxlen will
  // never reach the expected length — the parser would otherwise stay stuck
  // in-frame forever, consuming the next frames' bytes as payload and
  // desyncing permanently. Resync instead (UDP-style: drop the broken frame).
  if (in_frame && (millis() - last_byte_ms > FRAME_TIMEOUT_MS)) {
    in_frame = false;
    rxlen = 0;
    scan_prev = 0;
    diag_len_resync++;
  }
  while (Serial.available() > 0) {
    read_any = true;
    last_byte_ms = millis();
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
          diag_len_resync++;
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
        // Return immediately so loop() runs FastLED.show() for this frame.
        // If we kept draining here, continuous streaming would keep the
        // buffer non-empty and show() would starve (frames parsed but never
        // displayed). Remaining bytes stay buffered for the next iteration.
        return true;
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
  // Enlarge the UART RX buffer: default is only 256 bytes, but a frame is
  // 1542 bytes arriving in ~16ms at 921600 baud. While FastLED.show() runs
  // (~2-3ms) incoming bytes would overflow the tiny FIFO -> lost bytes ->
  // corrupt frames -> false magic sync -> "drop stale". 4096 holds several
  // frames of headroom.
  Serial.setRxBufferSize(4096);
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
  // Boot banner for confirming the firmware build: baud must match the
  // Python side (config.SERIAL_BAUD). Mismatch = garbage + "drop stale".
  Serial.print("BAUD: ");
  Serial.println(921600);
  Serial.println("READY");
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
  if (frame_ready) {
    frame_ready = false;
    uint32_t t0 = micros();
    FastLED.show();
    diag_last_show_us = micros() - t0;
    diag_shows++;
    // Flow-control token (lock-step handshake): the host holds its next
    // frame until it sees this byte, so no UART bytes ever arrive during
    // the show() window above — the RX-starvation frame-loss mode becomes
    // impossible by construction. 1 byte/frame is negligible TX traffic,
    // and an unacknowledging host simply never reads it (harmless).
    Serial.write(FRAME_ACK_BYTE);
  }
  // periodic diagnostics (every ~2s)
#ifdef SERIAL_DIAGNOSTICS
  static uint32_t last_diag = 0;
  uint32_t now_ms = millis();
  if (now_ms - last_diag >= 2000) {
    last_diag = now_ms;
    Serial.print("[diag] rx=");
    Serial.print(diag_frames_rx);
    Serial.print(" stale=");
    Serial.print(diag_frames_stale);
    Serial.print(" resync=");
    Serial.print(diag_len_resync);
    Serial.print(" shows=");
    Serial.print(diag_shows);
    Serial.print(" show_us=");
    Serial.println(diag_last_show_us);
  }
#endif
#ifdef ENABLE_UDP
  handleUDP();
#endif
}
