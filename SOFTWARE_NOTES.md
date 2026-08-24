# Software Phase — Hardware Notes & Constraints

> Reference doc for building the music-to-LED software path.
> Written after hardware bring-up (Steps 1–3 complete: board alive, PSU tested,
> single-panel + full-wall data path proven). The next session should NOT need
> to re-read this conversation — everything relevant is captured here.

---

## 1. System Overview

```
lightboard2/  (Python — all processing happens here)
  player.py        → Tkinter control panel (entry point)
  visualizer.py    → Pygame 32×16 grid render + FFT → RGB frames
  libproc.py       → librosa FFT → 32 frequency bands → normalized values
  config.py        → thread-safe SharedState (params, bands, playback)

        │  planned: UDP broadcast, raw RGB bytes, ~30–60 fps
        ▼

lightBoard/   (ESP32 firmware — dumb display, no processing)
  src/main.cpp     → currently CALIBRATION_MODE (infinite rainbow sweep)
  platformio.ini   → esp32doit-devkit-v1 / arduino / FastLED 3.10.3
```

**Design principle (user's requirement):** Python does ALL audio/visual processing.
Only RGB pixel data is sent to the ESP32. The ESP32 just receives and displays.

---

## 2. Hardware Inventory (from parts list)

| Part | Spec | Qty | Role |
|---|---|---|---|
| Mean Well LRS-350-5 | 300W / 60A / 5V SMPS | 1 | Main power |
| CJMCU 8×8 LED board | WS2812B ×64, 5V, ~60mA/LED peak | 8 | Display (8×8 each = 512 total) |
| ESP32 dev board | SquadPixel ESP-WROOM-32, D-labeled pins | 1 | Receiver |
| SN74AHCT125N | Quad buffer, DIP-14, 5V VCC | 2 | Level shifter (3.3V→5V data) |
| BK/ATC-10 fuse | 10A blade | 5 | Per-branch LED power |
| Inline fuse holders | | 1 set | |
| URS1E102MHD1TO | 1000µF 25V electrolytic | 3 | PSU output smoothing (NOT YET INSTALLED) |
| MFR50SFTE52-300R | 300Ω 0.5W axial | 6 | Data line protection (unused so far) |
| 14-pin DIP socket | | 2 | Level shifter sockets |
| Wire | 18AWG yellow (power), 22AWG black (GND), 22AWG red | | |

---

## 3. Confirmed Wiring (verified with multimeter + working sweep)

```
PSU 5V ── 10A fuse ── LED branch 1 (per-branch fusing)
PSU 5V ── 10A fuse ── LED branch 2 (etc.)
PSU 5V ────────────── level shifter VCC (pin 14)     [not the ESP32 branch]
PSU GND ───────────── common ground rail
        ├── ESP32 GND
        ├── level shifter GND (pin 7)
        └── every LED board GND

ESP32 D4 ──── level shifter pin 2 (1A)  ── input
level shifter pin 3 (1Y) ────────────── first board DIN
board DOUT ── next board DIN ── ... (serpentine chain through all 8 panels)
```

### Level shifter (SN74AHCT125N) — critical facts

| Pin | Function | Connection |
|---|---|---|
| 1, 4, 10, 13 | OE (output enable, **ACTIVE LOW**) | **ALL tied to GND** — floating = silent dead data line |
| 2 (1A) | channel 1 input | ESP32 D4 |
| 3 (1Y) | channel 1 output | first board DIN |
| 5, 9, 12 (2A/3A/4A) | unused channel inputs | tied to GND (good practice) |
| 7 | GND | common ground |
| 14 | VCC | PSU 5V |

### ESP32 pin facts

- **D4 = GPIO4** — confirmed by board silkscreen ("GPIO4" printed next to D4).
  Do NOT assume NodeMCU-32S mapping (where D4=GPIO14) — this board is D=GPIO.
- `LED_BUILTIN` = GPIO2 (works; used for alive-blink in normal mode).
- ESP32 is a clone — silkscreen D-labels, verify any new pin against silkscreen.
- Wokwi `diagram.json` is SIMULATION ONLY and out of date (pin 5, Adafruit_NeoPixel).
  Do not trust it for real wiring.

### Fusing (learned the hard way)

- A **5A fuse on the ESP32 branch melted** at power-on (inrush or transient short).
  The ESP32 only draws ~0.5A max.
- **Correct: ~1A slow-blow fuse** for the ESP32 branch (if PSU-powered at all).
- For bring-up, powering the ESP32 from **USB** is preferred over the PSU
  (removes the fuse/PSU variable entirely; laptop USB is current-limited).
- LED branches keep their own **10A** fuses.

---

## 4. Hardware Observations (must handle in software)

### 4.1 CRITICAL — Columns 2 and 4 are upside down

When the sweep ran, **columns 2 and 4 rendered upside down**. Cause: panels that
are physically rotated 180° in the serpentine chain to keep DIN→DOUT flowing.
**This is a wiring fact, not a defect. Do not "fix" the wiring.**

**Required:** a per-panel orientation / index remap layer. The software must map
logical (row, col) → physical LED index, flipping columns 2 and 4 (and verifying
the rest) before sending to `FastLED.show()`.

**Unknown to resolve during bring-up of the software phase:**
- Exact serpentine order of the 8 panels (which physical panel is #1, #2…)
- Exact orientation of each panel (only cols 2 & 4 flipped? any rows?)
- Recommend a dedicated **panel-mapping test pattern** (numbered panels,
  e.g. each panel solid white with its index) flashed to the ESP32, then encode
  the mapping table into firmware (or Python).

### 4.2 Power observations

- ~5V with slight variations under load — normal for the SMPS.
- **Add the 1000µF capacitor across the PSU output** near the LED branches
  before the full wall runs hard (smooths inrush/ripple).
- Fuses + level shifter run **warm** under load — normal. Hot (can't hold 3s) = problem.
- First LED held green when ESP32 lost power — normal WS2812 latch behavior
  (data-less boards hold last state).

### 4.3 Grid & color facts

- Full wall: **16 rows × 32 cols = 512 pixels**.
- Color order: **GRB** (FastLED `COLOR_ORDER GRB`).
- Python side already renders 32×16 (matches).
- The user's `dimensions.xlsx` exists at repo root — contains panel layout info
  (verify it matches the physical serpentine order).

---

## 5. Current Firmware State (`lightBoard/src/main.cpp`)

- `CALIBRATION_MODE true` — infinite rainbow sweep (no WiFi, no network).
- `LED_PIN 4`, `NUM_LEDS 512`, `BRIGHTNESS 100`, WS2812B GRB.
- 5-second countdown before sweep starts (Serial announcement).
- `main2,cpp` deleted (stray file, comma in name, not part of build).
- LSP shows errors for ESP32/Arduino headers — **expected** (no ESP32 toolchain
  in the C++ LSP). PlatformIO build is the source of truth: **builds clean**.
- Compile: `pio run --project-dir lightBoard` / Upload: `pio run -t upload`
  / Serial: `pio device monitor --baud 115200` (or VS Code PlatformIO toolbar).

---

## 6. Python Side (`lightboard2/`) — State & Constraints

### Architecture (already working locally)

- `player.py` is the entry point. Runs `visualizer.py` in a **daemon thread**;
  tkinter panel lives on the main thread. Communication via `SharedState`.
- `SharedState` (config.py) is thread-safe (Lock) — visual params, 32 band EQ,
  playback commands (load/pause/seek), playback status.
- `libproc.py` — librosa: fft_size 2048, hop 512, 32 bands spanning ~100 Hz →
  8 kHz, log1p compression, peak-normalized output (`compressed/peaks`).
- `visualizer.py` — Pygame 32×16 grid, HSV coloring driven by
  `horizontal_spread`, `vertical_spread`, `speed_multiplier`, brightness,
  saturation; attack/decay smoothing on FFT values; frame built via
  `RGBFrameBuilder.build(band_values)` → list of rows of (r,g,b) tuples.

### What the music-to-LED phase must add

1. **UDP broadcast** from `visualizer.py` after each frame build (target: ESP32 IP).
2. **UDP receive** on ESP32 → write into `leds[]` → `FastLED.show()`.
3. **Panel orientation remap** (Section 4.1) — decide: remap on ESP32 or Python.
   Python-side remap keeps the ESP32 dumb and keeps firmware simple; ESP32-side
   remap keeps Python independent of panel layout. **Recommend: remap in Python**
   (single source of truth = the grid the user already sees on screen).

### Latency design decisions (agreed earlier)

| Decision | Why |
|---|---|
| **UDP, not HTTP** | No connection setup/polling; fire-and-forget |
| **Raw bytes, not JSON** | 512 × 3 = **1536 bytes/frame**, zero parsing on ESP32 |
| **Sequence number in packet** | ESP32 drops stale/out-of-order frames |
| ~30–60 fps | Matches music responsiveness; UDP handles 1536B easily |

### Python environment

- `.venv` exists at repo root (numpy, librosa, pygame installed there).
- `lightboard2/` has a test MP3 ("The Glitch Mob - Fortune Days.mp3") for dev.
- `files.zip` in lightboard2/ — unknown content; verify if relevant.

---

## 7. Network Facts

- ESP32 got **192.168.29.212** via DHCP (RSSI -51 dBm, strong signal).
- **DHCP address may change** — consider static IP / DHCP reservation for the
  ESP32 before hard-coding it into Python config.
- WiFi creds still placeholders (`YourWiFiSSID`) in main.cpp — set for real use.

---

## 8. Immediate Next-Session Checklist

- [ ] Decide remap location (recommend: Python) and build the panel-mapping test
- [ ] Panel-mapping test pattern → encode orientation table (esp. cols 2 & 4)
- [ ] Rewrite `main.cpp`: CALIBRATION_MODE=false path → WiFi + UDP receive
      (keep rainbow sweep as fallback diagnostic, keep the countdown pattern)
- [ ] Add UDP broadcast to `visualizer.py` (after `builder.build()`)
- [ ] Add network config (ESP32 IP, UDP port) to `config.py`
- [ ] Add sequence numbers + stale-frame drop
- [ ] Verify dims: `dimensions.xlsx` layout vs physical serpentine order
- [ ] Install 1000µF cap across PSU output before full-wall power
- [ ] Optional: 1A slow-blow fuse for ESP32 branch, or keep USB power during dev