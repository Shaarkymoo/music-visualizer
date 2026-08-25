"""
settings.py — every tunable for the music visualizer, in one file.

Edit values here; no UI needed. This file is the single source of truth for
the headless rewrite (see docs/superpowers/plans/2026-08-25-headless-rewrite.md).

Sections:
  1. LED wall geometry
  2. Wire protocol          (must match src/main.cpp — do not change casually)
  3. Panel remap            (physical board layout, from chase test)
  4. Serial link
  5. FFT bands              (the EQ — biggest lever on how it looks)
  6. Smoothing / response   (second-biggest visual lever)
  7. Color / appearance
  8. ESP32-side values      (REFERENCE ONLY — edit src/main.cpp and re-flash)

All values below are the current verified-working defaults (tag v1-working).
"""

# ============================================================
# 1. LED WALL GEOMETRY
# ============================================================

NUM_LEDS = 512
GRID_COLS = 32           # wall is 32 LEDs wide
GRID_ROWS = 16           # ... and 16 tall (8 boards of 8x8)

# ============================================================
# 2. WIRE PROTOCOL  (keep in sync with src/main.cpp)
# ============================================================

MAGIC = b"\xaa\xaa"      # frame sync marker
FRAME_LEN = 0x0600       # 1536 payload bytes (512 * 3), little-endian on wire

# ============================================================
# 3. PANEL REMAP  (confirmed by chase test 2026-08-24)
# ============================================================
# The LED chain feeds the 8 boards in this order, and every board is
# mounted rotated 180 degrees. build_remap() turns this into a per-pixel
# lookup table. Do not edit unless you physically re-wire / re-mount boards.

CHUNK_BOARD_POS = [
    # chunk : (board_col, board_row)   board_row 0 = top, 1 = bottom
    (0, 1),   # chunk 0 = board 5 = bottom-left
    (0, 0),   # chunk 1 = board 1 = top-left
    (1, 1),   # chunk 2 = board 6 = bottom-mid-left
    (1, 0),   # chunk 3 = board 2 = top-mid-left
    (2, 1),   # chunk 4 = board 7 = bottom-mid-right
    (2, 0),   # chunk 5 = board 3 = top-mid-right
    (3, 1),   # chunk 6 = board 8 = bottom-right
    (3, 0),   # chunk 7 = board 4 = top-right
]
ALL_BOARDS_ROTATED_180 = True

# ============================================================
# 4. SERIAL LINK
# ============================================================

SERIAL_PORT = None       # None = auto-detect; or set e.g. "/dev/ttyUSB0"
SERIAL_BAUD = 921600     # must match src/main.cpp Serial.begin()
SERIAL_MAX_FPS = 25      # user-tuned 2026-08-26. FastLED.show() blocks ESP32
                         # RX ~16ms/frame; arrivals during that window die
                         # silently, so delivery% falls as fps rises
                         # (25fps -> ~20% delivered + lockouts, 15fps -> ~70%).
                         # seq=0 heartbeat in headless.py prevents lockouts.
                         # Hard wire ceiling is ~31fps; do not raise without
                         # the firmware async-RMT/double-buffer fix.

# ============================================================
# 5. FFT BANDS — [low_hz, high_hz, gain] x 32
# ============================================================
# Log-spaced 100 Hz -> 8 kHz. gain compensates for music energy falling
# with frequency. Raise gain on bands you want to react harder.
# Band 0-7   = bass/pulse  (~100-300 Hz)   <- most visible "beat" bands
# Band 8-15  = low mids    (~300-900 Hz)
# Band 16-23 = high mids   (~900-3000 Hz)
# Band 24-31 = treble      (~3000-8000 Hz)

BANDS = [
    [100,   120, 1.0],
    [120,   145, 1.0],
    [140,   165, 0.8],
    [160,   175, 1.0],
    [175,   200, 1.0],
    [200,   230, 1.0],
    [230,   260, 1.0],
    [260,   300, 1.0],
    [300,   345, 1.0],
    [345,   395, 1.0],
    [395,   450, 1.0],
    [450,   520, 1.0],
    [520,   595, 1.0],
    [595,   680, 1.0],
    [680,   780, 1.0],
    [780,   895, 1.0],
    [895,  1025, 1.0],
    [1025, 1175, 1.0],
    [1175, 1350, 1.0],
    [1350, 1550, 1.0],
    [1550, 1775, 1.0],
    [1775, 2035, 1.0],
    [2035, 2335, 1.0],
    [2335, 2675, 1.0],
    [2675, 3065, 1.0],
    [3065, 3520, 1.0],
    [3520, 4035, 1.0],
    [4035, 4625, 1.0],
    [4625, 5305, 1.2],
    [5305, 6085, 1.2],
    [6085, 6975, 1.2],
    [6975, 8000, 1.2],
]

# ============================================================
# 6. SMOOTHING / RESPONSE
# ============================================================

RESPONSIVENESS = 0.75    # attack speed 0..1: how fast bars jump UP on a hit.
                         # Higher = snappier.
DECAY_RATIO = 0.5        # fall speed as fraction of attack (0..1). Bars fall
                         # at RESPONSIVENESS*DECAY_RATIO. Lower = bars hang.
PEAK_DECAY = 0.998       # per-frame decay of each band's peak normalizer
                         # (0.99-0.999). Lower = auto-gain reacts faster.
GAMMA = 1.4              # exponent applied to normalized bands (>1 boosts
                         # contrast: quiet bands dimmer, loud bands full).

# ============================================================
# 7. COLOR / APPEARANCE
# ============================================================

HORIZONTAL_SPREAD = 8.0  # hue degrees per column (0 = all columns same hue)
VERTICAL_SPREAD = 3.0    # hue degrees per row within a bar
SPEED_MULTIPLIER = 0.15  # how fast the whole palette rotates over time (0..1)
SATURATION = 0.90        # 0 = white, 1 = fully saturated color
ACTIVE_BRIGHTNESS = 1.0  # brightness of "lit" pixels (0..1)
INACTIVE_BRIGHTNESS = 0.04  # brightness of unlit pixels — faint grid glow.
                         # Set to 0.0 for pure black background.

# ============================================================
# 8. ESP32-SIDE VALUES  (REFERENCE ONLY)
# ------------------------------------------------------------
# These live in src/main.cpp as #defines — edit there and re-flash:
#   LED_PIN 4, BRIGHTNESS 100, MAX_CURRENT_A 25.0,
#   LED_CURRENT_MA 20.0, FRAME_TIMEOUT_MS 50
# Mode flags: CALIBRATION_MODE, MAP_TEST_MODE, ENABLE_UDP,
#             SERIAL_DIAGNOSTICS
# ============================================================

ESP32_LED_PIN = 4
ESP32_BRIGHTNESS = 100          # 0-255 global scale (100 ≈ 39%)
ESP32_MAX_CURRENT_A = 25.0      # limiter threshold (protects 30A fuse)
ESP32_LED_CURRENT_MA = 20.0     # per-LED full-brightness estimate
ESP32_FRAME_TIMEOUT_MS = 50     # mid-frame silence before resync
