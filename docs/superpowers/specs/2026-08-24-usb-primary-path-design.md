# Design Spec — USB Primary Path + Consolidated Project Structure

**Date:** 2026-08-24
**Status:** Approved (pending user review)
**Project:** music-visualizer — 512-LED wall EQ visualizer

---

## 1. Goal

Consolidate the two existing codebases (`lightBoard/` ESP32 firmware + `lightboard2/`
Python processor) into a **single PlatformIO project at the repo root**, and switch the
primary data path from the (never-built) UDP broadcast to **USB serial**.

- Music plays on the PC, audio out through local headphones.
- The live-synced hardware LED wall renders the EQ — **no renderer window on the PC**.
- The PC runs a VLC-style player + settings panel (tkinter) whose changes are reflected
  live on the LED boards.
- The UDP broadcast path is **written, commented, and inactive** — implemented later.

## 2. Current State (verified)

- `lightboard2/` — working Python audio/visual core. `player.py` (tkinter panel) launches
  `visualizer.py` (Pygame 32×16 grid) in a thread; `libproc.py` does librosa FFT → 32 bands;
  `config.py` holds thread-safe `SharedState`.
- `lightBoard/` — ESP32 firmware in **CALIBRATION_MODE** (rainbow sweep). Data path proven.
- `dimensions.xlsx` — LED-density/coverage comparison spreadsheet (NOT the serpentine
  order — panel order still unknown, to be locked via mapping test).
- `files.zip` — stale May-2026 backup; verified near-identical to current files (only two
  band-default values differ, current file is newer). **Safe to delete.**
- Wiring facts (from SOFTWARE_NOTES): GPIO4 = data, GRB color order, 512 LEDs = 16×32,
  columns 2 & 4 physically upside down (need remap), PSU 5V / 30A total fuse.

## 3. Target Structure

```
music-visualizer/                 # ROOT = PlatformIO project
├── platformio.ini                # moved from lightBoard/, env: esp32doit-devkit-v1
├── src/
│   └── main.cpp                  # rewritten for USB receive + future UDP
├── python/                       # PC-side app (replaces lightboard2/)
│   ├── player.py                 # tkinter panel — entry point
│   ├── visualizer.py             # audio analysis + frame build, NO pygame grid
│   ├── libproc.py                # unchanged FFT/band engine
│   ├── config.py                 # SharedState + serial config + future UDP config
│   ├── serial_sink.py            # NEW: serial framing + write
│   └── udp_sink.py               # NEW: UDP broadcast, INACTIVE/commented (future)
├── docs/
│   ├── PARTS.md                  # merged parts list (from hardware.txt + stuff.txt)
│   ├── dimensions.xlsx
│   ├── ESP32-...pinout.png
│   ├── notes.txt
│   └── hardware-notes.md         # surviving facts folded from SOFTWARE_NOTES.md
├── .venv/                        # stays at root (Python env)
├── .gitignore                    # NEW: .venv/, .pio/, __pycache__/, .codegraph/
└── README.md                     # updated: new structure + how to run
```

### Deleted
- Root: `hardware.txt`, `stuff.txt`, `diagram.json`, `wokwi.toml`, `notes.txt`,
  `SOFTWARE_NOTES.md`
- `lightboard2/files.zip` (after verified-stale check)
- Empty `lightBoard/` and `lightboard2/` after migration
- `.codegraph/` — regenerable index artifact, git-ignored (delete or ignore)

## 4. Serial Protocol (USB Primary Path)

Each frame over serial (1542 bytes):

```
┌────────┬────────┬────────┬──────────────────────────┐
│ 0xAA 0xAA │ LEN u16 │ SEQ u16 │ 512 × 3 GRB bytes       │
│ 2 magic    │ =0x0600  │ wraps   │ (1536 payload bytes)   │
└────────┴────────┴────────┴──────────────────────────┘
```

- **MAGIC:** `0xAA 0xAA` — ESP32 scans for this to resync after any truncation/garbage.
- **LEN:** 2 bytes little-endian, always `0x0600` (1536). Included for forward-compat / frame
  validation.
- **SEQ:** 2 bytes little-endian, increments per frame, wraps at 65536. ESP32 drops stale /
  out-of-order frames (reject any SEQ that isn't `last+1` or a small forward jump on resync).
- **Payload:** 512 pixels × 3 bytes in **GRB** order (matches FastLED `COLOR_ORDER GRB`).
  The current `RGBFrameBuilder` outputs `(r,g,b)` tuples — packing reorders to GRB.
- **Serial:** 115200 baud, 8N1. Frame cadence throttled to **~30–45 fps** (~25–33ms min gap)
  so we never overrun the serial buffer.

### Future UDP reuse (written now, inactive)
The frame is built by a shared `pack_frame()` helper. `udp_sink.py` wraps the *identical*
byte blob in a UDP datagram to the ESP32's IP — no format change. Enabled later via config
flag. ESP32 UDP-receive code lives behind `#ifdef ENABLE_UDP` (or bool), compiled but not
exercised.

## 5. PC-side Architecture (Python)

- **`player.py`** — entry point. Starts the processing thread; tkinter panel on main thread
  (same pattern as today). **No Pygame grid window.**
- **`visualizer.py`** — Pygame display code removed. Remaining loop: read audio position →
  `processor.get_frame_at()` → smooth → `builder.build()` → `serial_sink.send_frame(frame)`;
  drains SharedState commands; keeps playback status current.
- **Audio backend:** **pygame.mixer** (plays with no window — `pygame.mixer.init()` only).
  Preserves load/pause/seek/endevent machinery. The same audio clock (`get_pos()`) drives
  the visuals.
- **Live changes → LED boards:** sliders/EQ write into `SharedState` thread-safely; the
  visualizer reads it every frame, so any change reflects on the next serial frame. No
  extra wiring needed.
- **`config.py`** — adds serial config (port auto-detect w/ override, baud 115200, fps cap)
  and a commented future-UDP block (IP, port).

## 6. ESP32 Firmware (`src/main.cpp`)

- **`CALIBRATION_MODE=true`** — keep rainbow sweep (diagnostic).
- **`CALIBRATION_MODE=false`** — **USB receive**: read serial, resync on magic, drop stale
  SEQ, write `leds[]`, `FastLED.show()`.
- **Future UDP:** `#ifdef ENABLE_UDP` receive path, inactive by default.
- **Panel orientation remap: in Python** (single source of truth = the grid the user
  sees). Remap table is a Python constant; exact values locked by the mapping test
  (numbered panels) since cols 2 & 4 are confirmed flipped and full order is unknown.

## 7. 25A Power Limiter (ESP32, per user requirement)

Protect the 30A total power fuse. Compute per-frame current draw and scale the whole frame
down if it would exceed 25A:

```
I_frame = Σ over all pixels of ((R + G + B) / 255) × 20mA
if I_frame > 25A:
    scale = 25A / I_frame
    multiply every pixel by scale
```

- Applied **after** UDP/USB receive writes the frame, **before** `FastLED.show()`.
- Peak theoretical draw = 512 × 60mA = 30.7A at full white — the limiter caps at 25A.
- Implemented in firmware (single place, applies to every path). Scaling is a linear RGB
  multiply (integer-safe; result kept in range 0–255).

## 8. Hardware (already done)

- 1000µF caps installed across PSU output. ✅ (noted for completeness)
- Fusing: LED branches 10A each; 30A total on the power line — the 25A limiter protects this.

## 9. Open items / unknowns

- **Exact panel order + orientation** of all 8 boards — locked via a numbered panel-mapping
  test pattern, then encoded as the Python remap constant.
- **ESP32 USB-CDC vs UART0:** need to confirm the board enumerates as a serial device over
  USB and what port it appears on. Python auto-detects / allows manual port override.

## 10. Out of scope (this phase)

- UDP broadcast enablement (code present, dormant).
- PC-side grid preview window (can add a toggle later if desired).
- Sample-exact audio clock rewrite (pygame.mixer retained).
