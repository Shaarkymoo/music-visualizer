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

Frames: MAGIC(2=0xAA 0xAA) + LEN(2 LE=0x0600) + SEQ(2 LE) + 1536 raw GRB bytes = 1542 bytes/frame.
