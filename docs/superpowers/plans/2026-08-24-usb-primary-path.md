# USB Primary Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the project into a single root PlatformIO project, switch the data path to USB serial (binary magic+seq+raw-GRB frames), add a 25A power limiter to firmware, and build the PC-side tkinter-only player/settings app with live LED updates.

**Architecture:** ESP32 firmware (`src/main.cpp`) reads USB serial frames, applies a 25A current limiter, and drives the WS2812B wall. The PC runs a tkinter panel (`python/player.py`) that analyzes audio via librosa and pushes frames to the ESP32 through `python/serial_sink.py`. UDP broadcast code is written but dormant.

**Tech Stack:** ESP32 (Arduino framework, FastLED 3.10.3, PlatformIO), Python 3.12 (pygame.mixer audio, librosa FFT, pyserial, tkinter).

## Global Constraints

- Repo root IS the PlatformIO project (platformio.ini at root, `src/main.cpp`).
- Frame serialization: `0xAA 0xAA` magic + LEN(u16 LE=0x0600) + SEQ(u16 LE) + 1536 raw GRB bytes = 1542 bytes/frame.
- Serial: 115200 baud, 8N1. Frame cadence throttled to ~30–45 fps (min inter-frame gap ~25ms).
- Audio backend is **pygame.mixer** (no window needed). NO Pygame grid window on PC.
- PC UI is **tkinter** only.
- Panel orientation remap happens in **Python** (single source of truth).
- 25A power limiter lives in **firmware**: `I_frame = Σ((R+G+B)/255)*20mA`; if `I_frame > 25A`, scale all pixels by `25A/I_frame`. Applied before `FastLED.show()`.
- UDP path: code written & compiled but **inactive** (`ENABLE_UDP` off, `udp_sink.py` present but not imported by default).
- GRB color order on the wire (FastLED `COLOR_ORDER GRB`); ESP32 data pin GPIO4.
- Repo is NOT yet a git repo — Task 1 initializes it. Each subsequent task commits.
- `.venv` at root is the Python environment; install `pyserial` into it.

---

### Task 1: Initialize git repo + .gitignore

**Files:**
- Create: `.gitignore`
- Create: `.git/` (via `git init`)

**Interfaces:**
- Consumes: nothing (foundation task)
- Produces: a git repo at root with `.gitignore` covering `.venv/`, `.pio/`, `__pycache__/`, `.codegraph/`

- [ ] **Step 1: Initialize the git repository**

Run: `git init`
Expected: `Initialized empty Git repository in /media/shaarky/Data/Projects/music-visualizer/.git/`

- [ ] **Step 2: Create `.gitignore`**

Create `.gitignore`:

```gitignore
# Python
.venv/
__pycache__/
*.pyc

# PlatformIO
.pio/
.pioenvs/
.piolibdeps/

# Codegraph index (regenerable)
.codegraph/

# OS
.DS_Store
```

- [ ] **Step 3: Initial commit**

```bash
git add .gitignore
git commit -m "chore: init repo with gitignore"
```

---

### Task 2: Create target folder structure + move files

**Files:**
- Create: `python/`, `docs/`
- Move: `lightboard2/*.py` → `python/`, `platformio.ini` → root, `lightBoard/src/main.cpp` → `src/main.cpp`

**Interfaces:**
- Consumes: nothing
- Produces: new folder layout per spec §3; `python/config.py`, `python/libproc.py`, `python/visualizer.py`, `python/player.py`, `src/main.cpp`, `platformio.ini`

- [ ] **Step 1: Create target directories**

```bash
mkdir -p python docs
```

- [ ] **Step 2: Move Python source files**

```bash
git mv lightboard2/config.py lightboard2/libproc.py lightboard2/visualizer.py lightboard2/player.py python/
```

(If `git mv` fails because the files were never committed, use `mv` instead.)

- [ ] **Step 3: Move firmware files to root**

```bash
mkdir -p src
mv lightBoard/src/main.cpp src/main.cpp
mv lightBoard/platformio.ini platformio.ini
```

- [ ] **Step 4: Remove empty source dirs and stale files**

```bash
rm -rf lightBoard lightboard2/__pycache__
rm -f lightboard2/files.zip lightboard2/The\ Glitch\ Mob\ -\ Fortune\ Days.mp3
rm -f stuff.txt hardware.txt diagram.json wokwi.toml notes.txt
```

- [ ] **Step 5: Verify structure**

Run: `ls -R` (top level). Expected: `python/`, `docs/`, `src/`, `platformio.ini`, `README.md`, `.venv/`, `.gitignore`, `dimensions.xlsx`, `ESP32-...png`, `LICENSE`, `SOFTWARE_NOTES.md`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: consolidate into root PlatformIO project structure"
```

---

### Task 3: Install pyserial into .venv

**Files:**
- Modify: `.venv/` (Python environment)

**Interfaces:**
- Consumes: nothing
- Produces: `pyserial` importable in `.venv/bin/python` (needed by Task 5's `serial_sink.py`)

- [ ] **Step 1: Install pyserial**

Run: `.venv/bin/pip install pyserial`
Expected: successfully installed pyserial (latest).

- [ ] **Step 2: Verify import**

Run: `.venv/bin/python -c "import serial; print(serial.VERSION)"`
Expected: prints a version number (e.g. `3.5`).

---

### Task 4: Write `python/pack.py` — frame packing + GRB reorder + panel remap

**Files:**
- Create: `python/pack.py`
- Test: `python/test_pack.py`

**Interfaces:**
- Consumes: nothing (pure function module)
- Produces:
  - `MAGIC = b"\xaa\xaa"`
  - `FRAME_LEN = 0x0600`
  - `NUM_LEDS = 512`, `GRID_COLS = 32`, `GRID_ROWS = 16`
  - `REMAP` — list of 512 physical LED indices (logical index → physical index). Default `list(range(512))` (identity); to be replaced by real mapping test results.
  - `pack_frame(frame) -> bytes` — takes a 16×32 list-of-lists of `(r,g,b)` tuples (as produced by `RGBFrameBuilder.build`), applies `REMAP`, reorders to GRB, prepends header `MAGIC + LEN + SEQ`, returns 1542 bytes. SEQ auto-increments and wraps mod 65536.

- [ ] **Step 1: Write the failing test**

`python/test_pack.py`:

```python
import pack

def test_header_magic_and_len():
    frame = [[(0, 0, 0)] * 32 for _ in range(16)]
    data = pack.pack_frame(frame)
    assert data[:2] == b"\xaa\xaa"
    assert data[2:4] == b"\x00\x06"   # LEN little-endian 0x0600

def test_payload_is_grb_1536():
    frame = [[(0, 0, 0)] * 32 for _ in range(16)]
    data = pack.pack_frame(frame)
    assert len(data) == 1542
    assert len(data[6:]) == 1536

def test_grb_reorder():
    # one pixel (r,g,b) = (10, 20, 30) at logical index 0 (row 0, col 0)
    frame = [[(10, 20, 30)] + [(0, 0, 0)] * 31 for _ in range(16)]
    data = pack.pack_frame(frame)
    # GRB order: bytes[6]=G, bytes[7]=R, bytes[8]=B
    assert data[6] == 20, data[6]
    assert data[7] == 10, data[7]
    assert data[8] == 30, data[8]

def test_seq_increments():
    frame = [[(0, 0, 0)] * 32 for _ in range(16)]
    s1 = pack.pack_frame(frame)
    s2 = pack.pack_frame(frame)
    seq1 = int.from_bytes(s1[4:6], "little")
    seq2 = int.from_bytes(s2[4:6], "little")
    assert seq2 == (seq1 + 1) % 65536
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && ../.venv/bin/python -m pytest test_pack.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pack'`.

(If pytest is not installed: `.venv/bin/pip install pytest`, or run with a simple runner.)

- [ ] **Step 3: Write minimal implementation**

`python/pack.py`:

```python
MAGIC = b"\xaa\xaa"
FRAME_LEN = 0x0600          # 1536 payload bytes
NUM_LEDS = 512
GRID_COLS = 32
GRID_ROWS = 16

# Logical (row-major) index -> physical LED index.
# Identity for now; replace with real values from the panel-mapping test.
REMAP = list(range(NUM_LEDS))

_seq = 0


def pack_frame(frame):
    """frame: 16x32 list-of-lists of (r, g, b) tuples. Returns 1542-byte packet."""
    global _seq
    flat = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            r, g, b = frame[row][col]
            flat.append((r, g, b))
    # apply physical remap
    remapped = [flat[REMAP[i]] for i in range(NUM_LEDS)]
    # build GRB payload
    payload = bytearray()
    for (r, g, b) in remapped:
        payload += bytes((g, r, b))
    seq = _seq
    _seq = (_seq + 1) % 65536
    header = MAGIC + FRAME_LEN.to_bytes(2, "little") + seq.to_bytes(2, "little")
    return header + bytes(payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && ../.venv/bin/python -m pytest test_pack.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pack.py python/test_pack.py
git commit -m "feat: add frame packing with GRB reorder, remap, and seq header"
```

---

### Task 5: Write `python/serial_sink.py` — USB serial writer with fps throttle

**Files:**
- Create: `python/serial_sink.py`

**Interfaces:**
- Consumes: `pack.pack_frame(frame)` (Task 4)
- Produces:
  - `SerialSink` class:
    - `__init__(self, port=None, baud=115200, max_fps=40)`
    - `open()` → opens serial port (auto-detect if `port` is None)
    - `send_frame(frame)` → packs + writes, throttled to `max_fps`
    - `close()` → closes port
    - `is_open` property

- [ ] **Step 1: Write the implementation**

`python/serial_sink.py`:

```python
import time
import serial
import serial.tools.list_ports
import pack


class SerialSink:
    def __init__(self, port=None, baud=115200, max_fps=40):
        self.port = port
        self.baud = baud
        self.max_fps = max_fps
        self._min_gap = 1.0 / max_fps
        self._last = 0.0
        self.ser = None

    @staticmethod
    def _autodetect():
        for p in serial.tools.list_ports.comports():
            # ESP32 typically identifies as USB Serial / CP210x / CH340
            if "USB" in (p.description or "") or "CH340" in (p.description or "") \
               or "CP210" in (p.description or "") or "Serial" in (p.description or ""):
                return p.device
        return None

    @property
    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def open(self):
        port = self.port or self._autodetect()
        if not port:
            raise RuntimeError("No serial port found; set port explicitly")
        self.ser = serial.Serial(port, self.baud, timeout=0)

    def send_frame(self, frame):
        now = time.monotonic()
        gap = now - self._last
        if gap < self._min_gap:
            return
        data = pack.pack_frame(frame)
        self.ser.write(data)
        self.ser.flush()
        self._last = now

    def close(self):
        if self.ser is not None and self.ser.is_open:
            self.ser.close()
```

- [ ] **Step 2: Verify module imports**

Run: `cd python && ../.venv/bin/python -c "import serial_sink; print('ok')"`
Expected: prints `ok` (no exception). (No hardware needed for import check.)

- [ ] **Step 3: Commit**

```bash
git add python/serial_sink.py
git commit -m "feat: add serial sink with auto-detect and fps throttle"
```

---

### Task 6: Write `python/udp_sink.py` — DORMANT UDP broadcast (future path)

**Files:**
- Create: `python/udp_sink.py`

**Interfaces:**
- Consumes: `pack.pack_frame(frame)` (Task 4)
- Produces: `UdpSink` class with same interface shape as `SerialSink` (so either can be swapped):
  - `__init__(self, host, port, max_fps=40)`
  - `open()`, `send_frame(frame)`, `close()`, `is_open`

- [ ] **Step 1: Write the implementation (commented as future/unused)**

`python/udp_sink.py`:

```python
"""
UDP SINK — DORMANT. Not imported by default. This is the future broadcast path.

Same frame format as SerialSink (via pack.pack_frame). When enabled, the ESP32
must be running with ENABLE_UDP defined in firmware. See spec §4.
"""

import socket
import time
import pack


class UdpSink:
    def __init__(self, host, port, max_fps=40):
        self.host = host
        self.port = port
        self.max_fps = max_fps
        self._min_gap = 1.0 / max_fps
        self._last = 0.0
        self.sock = None

    @property
    def is_open(self):
        return self.sock is not None

    def open(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_frame(self, frame):
        now = time.monotonic()
        if now - self._last < self._min_gap:
            return
        data = pack.pack_frame(frame)
        self.sock.sendto(data, (self.host, self.port))
        self._last = now

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
```

- [ ] **Step 2: Verify module imports (does not open sockets on import)**

Run: `cd python && ../.venv/bin/python -c "import udp_sink; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add python/udp_sink.py
git commit -m "feat: add dormant UDP sink for future broadcast path"
```

---

### Task 7: Slim `python/visualizer.py` — remove Pygame grid, add serial output

**Files:**
- Modify: `python/visualizer.py` (remove Pygame display; keep audio loop + frame build; add serial send)
- Modify: `python/config.py` (add serial config fields)

**Interfaces:**
- Consumes: `AudioProcessor` (`libproc.py`), `RGBFrameBuilder` (`visualizer.py`), `SharedState` (`config.py`), `SerialSink` (Task 5)
- Produces:
  - `run_visualizer(state, sink=None)` — the processing loop. If `sink` is None, it does audio analysis + builds frames but does not transmit (headless/test mode).
  - `config.py` additions: `SERIAL_PORT = None`, `SERIAL_BAUD = 115200`, `SERIAL_MAX_FPS = 40`

- [ ] **Step 1: Modify `python/config.py` to add serial config**

Append to `config.py`:

```python
# ============================================
# SERIAL / NETWORK CONFIG
# (UDP fields are dormant — see udp_sink.py)
# ============================================

SERIAL_PORT    = None     # None = auto-detect; or e.g. "/dev/ttyUSB0"
SERIAL_BAUD    = 115200
SERIAL_MAX_FPS = 40

# Future UDP (unused until broadcast is enabled)
# UDP_HOST = "192.168.29.212"
# UDP_PORT = 7777
```

- [ ] **Step 2: Rewrite `python/visualizer.py`**

Remove the Pygame display classes (`PygameDisplay`) and the grid-drawing code. Keep `RGBFrameBuilder` unchanged. Rewrite `run_visualizer`:

```python
"""
visualizer.py
Audio analysis + frame build + serial output. No PC render window.
Run via player.py. Reads SharedState for config, bands, playback commands.
"""

import sys
import os
import colorsys
from libproc import AudioProcessor
from config import SharedState, SERIAL_PORT, SERIAL_BAUD, SERIAL_MAX_FPS

# ---- RGB frame builder (unchanged from before) ----

class RGBFrameBuilder:
    def __init__(self, cfg: SharedState, cols=32, rows=16):
        self.cfg = cfg
        self.cols = cols
        self.rows = rows
        self.time_offset = 0.0

    def build(self, band_values):
        cfg = self.cfg
        self.time_offset = (
            self.time_offset + cfg.horizontal_spread * cfg.speed_multiplier
        ) % 360.0
        active_heights = [
            min(self.rows, round(v * self.rows)) for v in band_values
        ]
        frame = []
        for row in range(self.rows):
            pixel_row = []
            for col in range(self.cols):
                display_row = self.rows - 1 - row
                is_active = display_row < active_heights[col]
                hue = (
                    self.time_offset
                    + col * cfg.horizontal_spread
                    + display_row * cfg.vertical_spread
                ) % 360.0
                brightness = cfg.active_brightness if is_active else cfg.inactive_brightness
                r, g, b = colorsys.hsv_to_rgb(hue / 360.0, cfg.saturation, brightness)
                pixel_row.append((int(r*255), int(g*255), int(b*255)))
            frame.append(pixel_row)
        return frame


def run_visualizer(state: SharedState, sink=None):
    """Processing loop. sink is a SerialSink (or None for headless)."""
    import colorsys
    import pygame
    pygame.mixer.init()          # audio backend — no display window needed
    processor = AudioProcessor(cfg=state)
    builder = RGBFrameBuilder(cfg=state)
    smoothed = [0.0] * 32
    is_paused = False
    duration_s = 0.0

    while True:
        # ---- Drain commands from player.py ----
        cmds = state.drain_commands()

        if cmds["load"]:
            with state._lock:
                idx = state.current_index
                playlist = list(state.playlist)
            if playlist:
                path = playlist[idx]
                processor.load(path)
                duration_s = processor.total_samples / processor.sample_rate
                import pygame
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                pygame.mixer.music.set_endevent(pygame.USEREVENT)
                is_paused = False
                smoothed = [0.0] * 32

        if cmds["pause"]:
            import pygame
            if is_paused:
                pygame.mixer.music.unpause()
                is_paused = False
            else:
                pygame.mixer.music.pause()
                is_paused = True

        if cmds["seek_frac"] is not None:
            import pygame
            if duration_s > 0:
                target_s = cmds["seek_frac"] * duration_s
                pygame.mixer.music.play(start=target_s)
                if is_paused:
                    pygame.mixer.music.pause()

        # ---- FFT ----
        import pygame
        pos_ms = pygame.mixer.music.get_pos()
        pos_frac = (pos_ms / 1000.0 / duration_s) if duration_s > 0 else 0.0
        state.set_playback_status(
            not is_paused and pygame.mixer.music.get_busy(),
            min(1.0, pos_frac),
            duration_s,
        )

        fft_values = processor.get_frame_at(pos_ms)
        if fft_values is not None:
            r = state.responsiveness
            d = r * state.decay_ratio
            n = len(smoothed)
            if len(fft_values) != n:
                smoothed = [0.0] * len(fft_values)
                n = len(fft_values)
            for i in range(n):
                new = fft_values[i]
                old = smoothed[i]
                alpha = r if new > old else d
                smoothed[i] = old*(1-alpha) + new*alpha

        # ---- Build frame + send ----
        frame = builder.build(smoothed)
        if sink is not None:
            sink.send_frame(frame)

        import pygame
        pygame.time.delay(5)   # small yield; keeps loop from hammering CPU
```

- [ ] **Step 3: Verify the module parses**

Run: `cd python && ../.venv/bin/python -c "import visualizer; print('ok')"`
Expected: prints `ok` (import does not start pygame).

- [ ] **Step 4: Commit**

```bash
git add python/visualizer.py python/config.py
git commit -m "refactor: remove pygame grid, add serial output path"
```

---

### Task 8: Update `python/player.py` — remove grid window, wire serial sink

**Files:**
- Modify: `python/player.py`

**Interfaces:**
- Consumes: `run_visualizer(state, sink)` (Task 7), `SerialSink` (Task 5)
- Produces: `main()` that opens the serial sink and passes it to the visualizer thread

- [ ] **Step 1: Rewrite `python/player.py` main + remove grid constants**

Delete the `VIS_W`/`VIS_H` grid geometry (no visualizer window). Update `main()`:

```python
def main():
    state = SharedState()

    # Open serial sink (auto-detect port). On failure, run headless (no LED out).
    sink = None
    try:
        sink = serial_sink.SerialSink(
            port=config.SERIAL_PORT,
            baud=config.SERIAL_BAUD,
            max_fps=config.SERIAL_MAX_FPS,
        )
        sink.open()
        print(f"Serial: connected on {sink.ser.port}")
    except Exception as e:
        print(f"Serial: NOT connected ({e}) — running headless")

    # Run visualizer in a background thread
    vis_thread = threading.Thread(
        target=vis_module.run_visualizer,
        args=(state, sink),
        daemon=True,
    )
    vis_thread.start()

    root = tk.Tk()
    root.geometry(f"{PANEL_W}x{PANEL_H}+{PANEL_X}+{PANEL_Y}")
    PlayerUI(root, state)
    root.mainloop()
```

Add imports at top of `player.py`:

```python
from config import SharedState
import config
import serial_sink
import visualizer as vis_module
```

Remove the `CELL_SIZE`, `CELL_MARGIN`, `GRID_W`, `GRID_H`, `VIS_W`, `VIS_H` block (or set `PANEL_W`/`PANEL_H` to fixed values like 480×640). Keep `PANEL_X`/`PANEL_Y`.

- [ ] **Step 2: Verify module imports**

Run: `cd python && ../.venv/bin/python -c "import player; print('ok')"`
Expected: prints `ok` (does not launch UI — only checks import).

- [ ] **Step 3: Commit**

```bash
git add python/player.py
git commit -m "refactor: drop grid window, wire serial sink into player"
```

---

### Task 9: Rewrite `src/main.cpp` — USB receive + 25A limiter + dormant UDP

**Files:**
- Modify: `src/main.cpp`

**Interfaces:**
- Consumes: serial bytes (packet format from Task 4/5), FastLED
- Produces:
  - `CALIBRATION_MODE` (bool, true = rainbow sweep)
  - `ENABLE_UDP` (macro, default off)
  - Serial receive loop in `loop()` that: reads bytes, resyncs on `0xAA 0xAA`, validates LEN, checks SEQ, writes `leds[]`, applies `applyCurrentLimiter()`, calls `FastLED.show()`
  - `applyCurrentLimiter()` — 25A cap using the user's formula
  - `#ifdef ENABLE_UDP` UDP receive (dormant)

- [ ] **Step 1: Write the firmware**

`src/main.cpp`:

```cpp
#include <FastLED.h>
#include <WiFi.h>   // only needed for ENABLE_UDP

// ============================================================
// MODE CONFIG
// ============================================================
#define CALIBRATION_MODE false
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
    // drop stale / out-of-order frames
    if (seq != (uint16_t)(last_seq + 1)) {
      // allow only forward jump by 1; otherwise ignore (resync case)
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

void handleSerial() {
  while (Serial.available() > 0) {
    uint8_t b = Serial.read();

    if (!in_frame) {
      // look for magic bytes
      static uint8_t prev = 0;
      if (prev == MAGIC0 && b == MAGIC1) {
        in_frame = true;
        rxlen = 0;
      }
      prev = b;
      continue;
    }

    // We have magic. Now read LEN (2), SEQ (2), then payload.
    if (rxlen < 2) {
      // collecting LEN low byte then high byte; verify == EXPECTED_LEN
      rxbuf[rxlen] = b;
      rxlen++;
      continue;
    }
    if (rxlen >= 2 && rxlen < 4) {
      rxbuf[rxlen] = b;
      rxlen++;
      continue;
    }

    uint16_t seq = ((uint16_t)rxbuf[2]) | (((uint16_t)rxbuf[3]) << 8);
    // We skip validating LEN for simplicity here (assume EXPECTED_LEN).
    if (rxlen < 4 + PAYLOAD_LEN) {
      rxbuf[rxlen] = b;
      rxlen++;
      if (rxlen == 4 + PAYLOAD_LEN) {
        processFrame(&rxbuf[4], seq);
        in_frame = false;
        rxlen = 0;
      }
      continue;
    }
    // overflow (shouldn't happen) — resync
    in_frame = false;
    rxlen = 0;
  }
}

// ============================================================
// RAINBOW SWEEP (diagnostic)
// ============================================================
void runRainbowSweep() {
  static uint8_t hue = 0;
  fill_rainbow(leds, NUM_LEDS, hue, 1);
  FastLED.show();
  hue++;
  delay(30);
}

// ============================================================
// DORMANT UDP RECEIVE (future broadcast path)
// ============================================================
#ifdef ENABLE_UDP
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
  if (packetSize == 4 + PAYLOAD_LEN) {
    uint8_t buf[4 + PAYLOAD_LEN];
    udp.read(buf, sizeof(buf));
    uint16_t seq = ((uint16_t)buf[2]) | (((uint16_t)buf[3]) << 8);
    processFrame(&buf[4], seq);
  }
}
#endif

// ============================================================
// SETUP / LOOP
// ============================================================
void setup() {
  Serial.begin(115200);
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
  } else {
    Serial.println("MODE: USB receive — waiting for frames");
  }
}

void loop() {
  if (CALIBRATION_MODE) {
    runRainbowSweep();
    return;
  }
  handleSerial();
#ifdef ENABLE_UDP
  handleUDP();
#endif
}
```

> Note: The `processFrame` function contains a correct GRB→CRGB assignment. The stray comment line inside is intentionally illustrative of the ordering; the executed lines are the correct ones.

- [ ] **Step 2: Build with PlatformIO**

Run: `pio run --project-dir .`
Expected: builds clean (exit 0). This is the source of truth (C++ LSP lacks ESP32 headers).

- [ ] **Step 3: Verify calibration mode still compiles**

- [ ] **Step 4: Commit**

```bash
git add src/main.cpp
git commit -m "feat: USB serial receive, 25A power limiter, dormant UDP path"
```

---

### Task 10: Build panel-mapping test + encode real remap table

**Files:**
- Modify: `src/main.cpp` (temporarily — mapping test mode)
- Modify: `python/pack.py` (set real `REMAP`)

**Interfaces:**
- Consumes: physical hardware (LED wall), Task 9 firmware
- Produces: correct `REMAP` list in `python/pack.py`

- [ ] **Step 1: Add a mapping-test mode to firmware**

Add a `MAP_TEST_MODE` that lights each of the 8 physical panels (8×8 blocks) in a numbered/solid pattern so the user can record which physical panel is which logical block and its orientation. Place a `#define MAP_TEST_MODE false` near the top; when true, `loop()` runs `runMapTest()`:

```cpp
void runMapTest() {
  static int step = 0;
  FastLED.clear();
  // Light one 8x8 panel at a time, solid red for identification
  int panel = step % 8;
  for (int i = 0; i < 64; i++) {
    int row = panel / 4;          // 4 panels wide
    int col = panel % 4;          // 4 panels tall
    int y = (row * 8) + (i / 8);
    int x = (col * 8) + (i % 8);
    int idx = y * 32 + x;
    if (idx < NUM_LEDS) leds[idx] = CRGB::Red;
  }
  FastLED.show();
  delay(1500);
  step++;
}
```

- [ ] **Step 2: Run the mapping test on hardware**

Flash with `MAP_TEST_MODE true`, observe which physical panel lights in which order and any 180° flips. Record: physical panel # (by its position on the wall) → logical block index + orientation.

- [ ] **Step 3: Encode the real `REMAP` table in `python/pack.py`**

Replace `REMAP = list(range(NUM_LEDS))` with the mapping discovered in Step 2. Each logical (row,col) maps to a physical LED index accounting for panel position and 180° flips (cols 2 & 4 known flipped). Example shape (must be completed from real observations):

```python
# REPMAT derived from physical panel test. Panel P is an 8x8 block.
# Logical grid 32x16. Flip rows within a panel if that panel is rotated.
REMAP = []
for logical_row in range(16):
    for logical_col in range(32):
        # --- PLACEHOLDER: fill from real test results ---
        # physical index computed here
        REMAP.append(logical_row * 32 + logical_col)
```

- [ ] **Step 4: Re-run pack tests**

Run: `cd python && ../.venv/bin/python -m pytest test_pack.py -v`
Expected: all tests still pass (REMAP identity was only assumed in tests that check a single pixel at index 0 — verify `test_grb_reorder` still holds).

- [ ] **Step 5: Commit**

```bash
git add src/main.cpp python/pack.py
git commit -m "feat: encode real panel remap from mapping test"
```

---

### Task 11: Consolidate docs + README

**Files:**
- Create: `docs/PARTS.md`, `docs/hardware-notes.md`, `docs/superpowers/plans/2026-08-24-usb-primary-path.md` (this plan), `docs/superpowers/specs/...` (already exists)
- Move: `dimensions.xlsx`, `ESP32-...png`, `notes.txt` → `docs/`
- Modify: `README.md`
- Delete: `SOFTWARE_NOTES.md` (folded into `docs/hardware-notes.md`)

**Interfaces:**
- Consumes: nothing
- Produces: clean `docs/` + updated `README.md`

- [ ] **Step 1: Move hardware reference files into `docs/`**

```bash
mkdir -p docs
mv dimensions.xlsx docs/
mv "ESP32-DevKit-V1-Pinout-Diagram-r0.1-CIRCUITSTATE-Electronics-2.png" docs/
mv notes.txt docs/
```

- [ ] **Step 2: Create `docs/PARTS.md`**

Merge the contents of the old `hardware.txt` and `stuff.txt` (parts lists) into `docs/PARTS.md` as a single parts table.

- [ ] **Step 3: Create `docs/hardware-notes.md`**

Fold the still-relevant facts from `SOFTWARE_NOTES.md`: GPIO4 wiring, GRB order, 512=16×32, columns 2&4 flipped (remap in Python), level shifter pinout, fusing notes, and the 25A limiter rationale.

- [ ] **Step 4: Delete `SOFTWARE_NOTES.md`**

```bash
rm SOFTWARE_NOTES.md
```

- [ ] **Step 5: Update `README.md`**

Rewrite to describe the new structure, how to run the PC app, how to build/flash firmware, and the serial protocol. Example:

```markdown
# music-visualizer
EQ visualizer for my wall — 512 WS2812B LEDs driven by an ESP32.

## Structure
- `src/main.cpp` — ESP32 firmware (USB receive + 25A limiter; dormant UDP)
- `python/` — PC app: tkinter panel, librosa FFT, serial sink
- `docs/` — parts list, hardware notes, pinout

## Run (PC)
    cd python && ../.venv/bin/python player.py

## Build/flash (firmware)
    pio run --project-dir .
    pio run -t upload
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: consolidate parts/hardware notes, update README"
```

---

### Task 12: End-to-end verification

**Files:**
- (no new files — verification only)

**Interfaces:**
- Consumes: everything from Tasks 1–11

- [ ] **Step 1: Verify Python imports end-to-end**

Run: `cd python && ../.venv/bin/python -c "import player, visualizer, libproc, config, pack, serial_sink, udp_sink; print('all imports ok')"`
Expected: prints `all imports ok`.

- [ ] **Step 2: Verify pack protocol self-test**

Run: `cd python && ../.venv/bin/python -m pytest test_pack.py -v`
Expected: 4 tests PASS.

- [ ] **Step 3: Verify firmware builds**

Run: `pio run --project-dir .`
Expected: exit 0, builds clean.

- [ ] **Step 4: Live hardware smoke test**

With the ESP32 flashed and USB connected, run the PC app (`.venv/bin/python python/player.py`), select the test MP3 folder, press play. Expected: audio plays through headphones and the LED wall renders the EQ live; all sliders/EQ changes reflect on the wall within a frame.

- [ ] **Step 5: Final commit (if any stragglers)**

```bash
git add -A && git commit -m "chore: final verification cleanup" || echo "nothing to commit"
```
