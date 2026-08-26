# HANDOFF — Music Visualizer (512-LED Wall)

> Anchor doc for resuming work in a fresh session. Everything needed to
> understand, run, debug, and continue this project. Last verified working
> state: tag **`v1-working`** (commit `be3c1a7`).

---

## 1. What this is

An EQ music visualizer driving a wall of **512 WS2812B LEDs** (8 panels of 8×8,
arranged **4 columns × 2 rows** = 32 cols × 16 rows).

- **Music plays on the PC** through headphones/ speakers.
- The PC does ALL analysis: decodes the mp3, FFTs it into 32 frequency bands,
  builds a 16×32 RGB frame, packs it, and streams it over USB serial.
- The ESP32 is a **dumb display**: receives 1542-byte frames over USB serial,
  applies a 25A current limiter, and drives the LEDs via FastLED.

```
PC (python/)                                ESP32 (src/main.cpp)
┌──────────────────────────┐   USB 921600   ┌─────────────────────────┐
│ soundfile decode         │ ─────────────► │ UART RX (4096B buffer)  │
│ → numpy FFT (32 bands)   │  1542 B/frame  │ → magic/LEN/SEQ parse   │
│ → vectorized HSV frame   │  @25 fps       │ → 25A current limiter   │
│ → pack (GRB + REMAP)     │ ◄───────────── │ → FastLED.show()        │
└──────────────────────────┘  diag lines    │   (15.86ms for 512 LED) │
                                            └───────────┬─────────────┘
                                                   GPIO4 → level shifter
                                                        → 8× WS2812B boards
```

## 2. Verified working state

**v1 (pygame/tkinter stack):** user-confirmed smooth/synced/zero-corruption.
Tag **`v1-working`** (`be3c1a7`) preserved as revert point.

**v2 (headless rewrite, 2026-08-26):** accepted on hardware by the user.
sounddevice+numpy stack, seq=0 heartbeat resync, 25 fps. Hardware-verified:
no corruption/lockouts; palette motion smooth. Known characteristic: ~50–70%
of sent frames are lost to `show()` RX-starvation windows (see §9) — each
delivered frame is still audio-synced, so the wall shows a slightly sparser
but correct animation.

| Component | State |
|---|---|
| Firmware (`src/main.cpp`) | ✅ v2 build flashed — USB receive @921600, SERIAL_DIAGNOSTICS off |
| Python app (`python/headless.py`) | ✅ entry point, hardware-accepted |
| Panel remap | ✅ confirmed by chase test — see §5 |
| Tests | ✅ 8/8 `test_pack.py`, 2/2 `test_render.py`, 3/3 `test_audio.py`, pipeline PASS |

**Tag `v2-headless` = current accepted state. Tag `v1-working` = pre-rewrite
revert point.**

## 3. Key numbers (memorize these)

| Quantity | Value | Why it matters |
|---|---|---|
| `FastLED.show()` | **15.86 ms** | Hardware floor: 512×24 bits × 1.25 µs. Cannot be improved in code. |
| Frame on wire | **16.7 ms** | 1542 bytes × 10 bits ÷ 921600 baud |
| **Frame ceiling** | **~31 fps** | receive + show are serialized; 32+ fps ⇒ RX overflow ⇒ corruption |
| Current cap | **24 fps** | `settings.py: SERIAL_MAX_FPS` — user-chosen; measured ceiling ~27 fps @921600 under lock-step |
| Serial baud | 921600 | must match on both sides; firmware prints it at boot |
| ESP32 UART RX buffer | 4096 B | `setRxBufferSize(4096)` before `begin()`; default 256 B overflows instantly |
| Frame size | 1542 B | magic 2 + LEN 2 + SEQ 2 + payload 512×3 |
| Frame timeout | 50 ms | firmware resyncs if mid-frame silence exceeds this |
| 25 A limiter | Σ((R+G+B)/255)×20 mA per pixel; scale all if > 25 A | protects 30 A fuse (max possible draw 30.7 A) |

## 4. Hardware facts

- **Data pin:** GPIO4 (D4, confirmed by silkscreen) → SN74AHCT125N level shifter → first board DIN.
- **Color order:** GRB (FastLED `COLOR_ORDER GRB`; payload bytes are `[G][R][B]` per pixel).
- **Level shifter:** OE pins (1,4,10,13) tied GND (active-low); unused inputs grounded.
- **Power:** Mean Well LRS-350-5 (5 V 60 A), 1000 µF caps installed at output.
  Fusing: 10 A per LED branch, 30 A total line (protected by the 25 A limiter).
- **Board quirk:** physical LED 0 (first in chain, lives on bottom-left board)
  has a stuck green channel — shows yellow when fed red, faint green when dark.
  Cosmetic, ignore.

### Panel map (confirmed by chase test)

Boards numbered 1–8 left→right, top row then bottom row.
Chain order (chunk c → board): **5, 1, 6, 2, 7, 3, 8, 4**.
Every board is mounted **rotated 180°**.

```python
CHUNK_BOARD_POS = [   # chunk : (board_col, board_row)
    (0, 1),           # 0 = board 5 = bottom-left
    (0, 0),           # 1 = board 1 = top-left
    (1, 1),           # 2 = board 6 = bottom-mid-left
    (1, 0),           # 3 = board 2 = top-mid-left
    (2, 1),           # 4 = board 7 = bottom-mid-right
    (2, 0),           # 5 = board 3 = top-mid-right
    (3, 1),           # 6 = board 8 = bottom-right
    (3, 0),           # 7 = board 4 = top-right
]
# All boards rotated 180°: local (lr,lc) appears at physical (7-lr, 7-lc).
# Encoded in python/pack.py -> build_remap() -> REMAP.
```

## 5. File map (current architecture)

```
src/main.cpp            ESP32 firmware (C++/Arduino/FastLED 3.10.3 via PlatformIO)
python/
├── headless.py         ENTRY POINT — folder loop: play → FFT → render → serial
├── settings.py         every tunable in one file (geometry, protocol, bands, colors)
├── audio.py            AudioPlayer: sounddevice playback, exact sample position
├── libproc.py          AudioProcessor: 32-band FFT from pre-decoded samples
├── render.py           Renderer: numpy-vectorized HSV frame build (16x32 RGB)
├── pack.py             pack_frame(): header + GRB payload + REMAP (values from settings)
├── serial_sink.py      SerialSink: pyserial writer (throttled, graceful-fail)
├── udp_sink.py         DORMANT future UDP path (not imported anywhere)
├── chase_test.py       hardware diagnostic: white chunk chase w/ red marker
├── pipeline_test.py    headless end-to-end verification (self-contained)
├── test_pack.py        7 unit tests (protocol, remap bijection, roundtrip)
├── test_render.py      golden test vs scalar reference (bit-exact)
└── test_audio.py       position math + end-of-stream regression tests
docs/
├── PARTS.md, hardware-notes.md, notes.txt, dimensions.xlsx, pinout png
└── superpowers/{specs,plans}/   design docs (see git history)
```

## 6. How to run / build / debug

```bash
# Flash firmware (from repo root)
pio run --project-dir . -t upload

# Run the player (folder loops forever; Ctrl+C stops)
cd python && ../.venv/bin/python headless.py --folder /path/to/music

# Or without a terminal: right-click song(s)/folder -> Open With -> Music
# Visualiser (installed via ~/.local/share/applications/music-visualiser.desktop;
# helper: tools/play-with-visualiser; stop: "Stop Music Visualiser" in launcher)

# Headless end-to-end verification (no hardware needed)
cd python && ../.venv/bin/python pipeline_test.py

# Unit tests
cd python && ../.venv/bin/python -m pytest test_pack.py test_render.py test_audio.py -q

# Read ESP32 boot banner / diagnostics (after flashing or reset)
cd python && ../.venv/bin/python -c "
import serial, time
ser = serial.Serial('/dev/ttyUSB0', 921600, timeout=1)
ser.setDTR(False); ser.setRTS(True); time.sleep(0.1); ser.setRTS(False)
time.sleep(0.5); print(ser.read(400).decode(errors='replace')); ser.close()"
```

**Diagnostics:** firmware prints `[diag] rx=N stale=N resync=N shows=N show_us=N`
every 2 s — but it's gated behind `#define SERIAL_DIAGNOSTICS` (currently OFF in
committed source; uncomment + re-flash to enable). Rising `stale`/`resync` =
wire corruption; flat counts with bad visuals = upstream content problem.

**Hardware diagnostic:** `chase_test.py` lights each 8×8 board white in chain
order (red marker = first LED of the chunk). Confirms chain order + rotation.

## 7. Wire protocol (must stay in sync both sides)

```
MAGIC (0xAA 0xAA) | LEN u16 LE (=0x0600) | SEQ u16 LE | 512×3 GRB bytes
```
- Total 1542 bytes. SEQ increments per frame, wraps mod 65536.
- ESP32 accepts: exact next seq, `seq==0` (host restart), forward jump ≤8.
  Anything else dropped silently.
- LEN validated ≠ 0x0600 → resync. Mid-frame silence > 50 ms → resync.
- **Flow control (lock-step):** after each `FastLED.show()` completes, the
  ESP32 sends one ACK byte `0x01` (`FRAME_ACK_BYTE` in main.cpp). The host
  (`serial_sink.py`) waits for it before sending the next frame, so no bytes
  are ever transmitted during the show() RX-starvation window. A lost/late
  ACK → that cycle proceeds fire-and-forget (`ack_timeouts` counter); old
  firmware without ACK support still works (timeout every frame).

## 8. Debug history (what we fixed and why — short index)

Full detail in git log; the lessons that matter:

1. **`show()` inside the serial drain starved display** — rx climbed, shows
   stuck at 2. Fix: `processFrame()` only sets `frame_ready`; `loop()` shows.
   Never call blocking show() inside a drain loop.
2. **No recovery from mid-frame byte loss** — parser stayed in-frame forever.
   Fix: 50 ms assembly timeout → resync. (UDP-style: drop broken frames.)
3. **256-byte default UART RX buffer** overflowed during show(). Fix:
   `setRxBufferSize(4096)` before `begin()`.
4. **Non-blocking writes truncated frames.** Fix: `write_timeout=1.0`
   (blocking writes). Later removed `flush()` (driver-dependent latency).
5. **`get_pos()` returns −1 when not playing** → negative slice → FFT crash →
   silent daemon-thread death. Guard in `get_frame_at`.
6. **Chase/map tests froze after one chunk** — test tool sent constant seq=0;
   firmware gate rejected everything after the first. Test tools must
   increment seq too.
7. **Auto-advance race** fixed in `_tick` (was firing on transient
   `get_busy()==False`).

## 9. Known limits & quirks

- **Frame delivery: ~100% via lock-step handshake.** Historical issue: show()
  blocked ESP32 RX ~15.9 ms/frame and arrivals in that window died silently
  (30–50% loss, cascading SEQ-gate lockouts). Fixed 2026-08-26 with the ACK
  handshake (§7): the host never transmits inside the danger window. The
  seq=0 heartbeat remains as a belt-and-braces resync. Throughput ceiling is
  now round-trip bound (~30 fps) — above the 25 fps setting.
- Reading serial while player runs: opening /dev/ttyUSB0 toggles DTR/RTS and
  can reset the board mid-run. Read diag only between runs.
- ~31 fps hard wire ceiling (§3); handshake round-trip caps practical rate
  near 30 fps. 25 fps chosen empirically (2026-08-26): user preferred its
  motion over 15/20.
- Board 5 first-LED color quirk (§4).
- `udp_sink.py` is written but dormant; firmware UDP path behind
  `ENABLE_UDP`, also dormant. Enabling requires fixing the UDP handler
  (packet-size check expects 1540, should be 1542; header offset wrong) —
  noted in review, never exercised.
- `dimensions.xlsx` is an old density-comparison sheet, NOT panel order data.
- Hardware test sessions: keep runs ≤30 s unless the user asks otherwise;
  board needs cooling after long sessions (it was once disconnected for that).

## 10. What's next (optional future work)

v2 is accepted and tagged `v2-headless`. If smoother motion is ever wanted:
- **Firmware async/double-buffered show()** (overlapping receive+render) —
  the real fix; would lift delivery toward ~100% and make >25 fps viable.
  Currently deferred by design.
- Wire CRC8 (recommendation #6 from an old review) — hardening, only if EMI
  ever shows up.
Revert points: `git checkout v2-headless` (accepted state) or `v1-working`
(pre-rewrite).
