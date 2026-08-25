# music-visualizer

EQ visualizer for my wall — 512 WS2812B LEDs driven by an ESP32. The PC does
all analysis (decode → FFT → frame build) and streams frames over USB serial;
the ESP32 is a dumb display with a 25 A current limiter.

## Structure

- `src/main.cpp` — ESP32 firmware (USB receive + 25A power limiter; dormant UDP; MAP_TEST_MODE)
- `python/` — PC app, headless (no UI):
  - `headless.py` — ENTRY POINT: folder loop → sounddevice playback → FFT → render → serial
  - `settings.py` — every tunable in one file (geometry, protocol, remap, bands, colors)
  - `audio.py` / `libproc.py` / `render.py` / `pack.py` / `serial_sink.py`
  - `pipeline_test.py`, `test_pack.py`, `test_render.py`, `test_audio.py` — verification
  - `chase_test.py`, `udp_sink.py` — hardware diagnostic / dormant UDP path
- `docs/` — parts list, hardware notes, pinout, HANDOFF.md

## Run (PC)

```
cd python && ../.venv/bin/python headless.py --folder /path/to/music
# optional: --fps N (default 25), --port /dev/ttyUSB0 (default auto-detect)
```

## Build/flash (firmware)

```
pio run --project-dir .
pio run -t upload
```

## Serial protocol

- **Baud:** 921600 (both `src/main.cpp` and `python/settings.py` — must match)
- **Frames:** MAGIC(2=0xAA 0xAA) + LEN(2 LE=0x0600) + SEQ(2 LE) + 1536 raw GRB bytes = 1542 bytes/frame
- The ESP32 prints `BAUD: 921600` at boot — confirms the firmware matches the PC side. If Python sends a different baud than the firmware listens at, you get garbage and `drop stale` spam.

## Serial fixes (2026-08-24)

- `python/serial_sink.py`: blocking writes (`write_timeout=1.0`) so frames are never truncated; degrades gracefully if the USB link dies mid-playback (audio keeps running).
- `src/main.cpp`: `Serial.setRxBufferSize(4096)` before `begin()` — the default 256-byte UART FIFO overflows while `FastLED.show()` runs at 921600, corrupting frames.
- Firmware SEQ gate accepts resync (`seq==0`) and small forward jumps, so a dropped frame or host restart doesn't freeze the wall.

## Headless rewrite (2026-08-25)

Replaced the pygame/tkinter stack with sounddevice+numpy (`soundfile` decodes
mp3 via libsndfile). Playback position comes from the audio callback counter,
so analysis is sample-synced by construction. All tunables live in
`python/settings.py`. See `docs/superpowers/plans/2026-08-25-headless-rewrite.md`.
