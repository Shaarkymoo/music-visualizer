# music-visualizer

EQ visualizer for my wall — 512 WS2812B LEDs driven by an ESP32.

## Structure

- `src/main.cpp` — ESP32 firmware (USB receive + 25A power limiter; dormant UDP; MAP_TEST_MODE)
- `python/` — PC app: tkinter panel, librosa FFT, serial sink
- `docs/` — parts list, hardware notes, pinout

## Run (PC)

```
cd python && ../.venv/bin/python player.py
```

## Build/flash (firmware)

```
pio run --project-dir .
pio run -t upload
```

## Serial protocol

- **Baud:** 921600 (both `src/main.cpp` and `python/config.py` — must match)
- **Frames:** MAGIC(2=0xAA 0xAA) + LEN(2 LE=0x0600) + SEQ(2 LE) + 1536 raw GRB bytes = 1542 bytes/frame
- The ESP32 prints `BAUD: 921600` at boot — confirms the firmware matches the PC side. If Python sends a different baud than the firmware listens at, you get garbage and `drop stale` spam.

## Serial fixes (2026-08-24)

- `python/serial_sink.py`: blocking writes (`write_timeout=1.0`) so frames are never truncated; degrades gracefully if the USB link dies mid-playback (audio keeps running).
- `src/main.cpp`: `Serial.setRxBufferSize(4096)` before `begin()` — the default 256-byte UART FIFO overflows while `FastLED.show()` runs at 921600, corrupting frames.
- Firmware SEQ gate accepts resync (`seq==0`) and small forward jumps, so a dropped frame or host restart doesn't freeze the wall.
