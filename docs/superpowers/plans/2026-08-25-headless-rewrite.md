# Headless Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace pygame/tkinter with a minimal sounddevice+numpy headless stack; vectorize rendering; unify all tunables into `python/settings.py`. Same wire protocol, same visual output, fewer dependencies, sample-accurate audio sync.

**Architecture:** `headless.py` (entry point) drives: decode mp3 → numpy samples → `sounddevice` playback with a callback that tracks the exact sample position → FFT bands from `samples[position:position+2048]` → vectorized frame build → `pack_frame()` → serial. Because playback and analysis share one position counter, sync is exact by construction — no `get_pos()` polling.

**Tech Stack:** Python 3.12, existing `.venv`. New deps: `sounddevice` (PortAudio playback), `soundfile` (decode; libsndfile ≥1.2 reads mp3 natively). Removed deps after migration: `pygame`, `tkinter`, `librosa` (only if soundfile decodes the test mp3 — otherwise keep librosa for load only).

**Read first:** `docs/HANDOFF.md` (state, hardware facts, key numbers, debug history).

## Global Constraints

- **Wire protocol is frozen:** MAGIC `0xAA 0xAA` + LEN u16 LE 0x0600 + SEQ u16 LE + 1536 GRB bytes = 1542 B/frame. Do not change.
- **Panel remap is frozen:** `CHUNK_BOARD_POS` order 5,1,6,2,7,3,8,4; every board rotated 180°. Values live in `settings.py`; logic in `pack.py`.
- **Frame ceiling ~31 fps; run at 25 fps** (`SERIAL_MAX_FPS`). show() alone is 15.86 ms — never regress this.
- **ESP32 firmware (`src/main.cpp`) is NOT touched by this rewrite.**
- **Keep passing:** `test_pack.py` (7 tests). Update `pipeline_test.py` imports if modules move.
- **All tunables read from `python/settings.py`** — no duplicated constants elsewhere.
- User does not want a UI. No tkinter, no pygame display window, no live reflection on PC.
- Audio out = headphones/speakers on this machine; music must stay on the PC.

---

### Task 1: Dependencies + decode capability check

**Files:**
- Modify: `.venv` (pip installs)

**Interfaces:**
- Produces: `sounddevice` and `soundfile` importable; decision recorded on whether librosa stays.

- [ ] **Step 1: Install**

```bash
sudo apt-get install -y libportaudio2   # runtime lib for sounddevice
cd python && ../.venv/bin/pip install sounddevice soundfile
```

- [ ] **Step 2: Verify soundfile decodes the repo mp3 natively**

```bash
cd python && ../.venv/bin/python -c "
import soundfile as sf
data, sr = sf.read('../The Glitch Mob - Fortune Days.mp3', dtype='float32', always_2d=True)
print('decoded:', data.shape, sr)
"
```

Expected: prints shape like `(N, 2) 48000`. If it raises (`libsndfile` too old for mp3), record: **keep librosa.load as decoder** and skip Task 5's "drop librosa" step.

- [ ] **Step 3: Verify sounddevice sees an output device**

```bash
cd python && ../.venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"
```

Expected: at least one output device listed. Note its index/name.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: add sounddevice+soundfile deps" || echo "nothing to commit"
```

---

### Task 2: `settings.py` adoption — single source of truth

**Files:**
- Modify: `python/pack.py` (read geometry/remap/protocol constants from settings)
- Create already done: `python/settings.py` (committed with this plan — verify values match HANDOFF §3/§5)

**Interfaces:**
- Consumes: `settings.py` (exists).
- Produces: `pack.MAGIC`, `pack.REMAP` etc. unchanged in behavior — same values, sourced from settings. `test_pack.py` must still pass unchanged.

- [ ] **Step 1: In `pack.py`, replace hardcoded constants with imports**

Top of `pack.py` becomes:

```python
import settings as S

MAGIC = S.MAGIC
FRAME_LEN = S.FRAME_LEN
NUM_LEDS = S.NUM_LEDS
GRID_COLS = S.GRID_COLS
GRID_ROWS = S.GRID_ROWS
CHUNK_BOARD_POS = S.CHUNK_BOARD_POS
ALL_BOARDS_ROTATED_180 = S.ALL_BOARDS_ROTATED_180
```

Delete the now-duplicated literal definitions (keep `build_remap()` and `_seq` logic untouched).

- [ ] **Step 2: Run pack tests**

Run: `cd python && ../.venv/bin/python -m pytest test_pack.py -q`
Expected: 7 passed. If any fail, a value was mistranscribed — diff against `v1-working`.

- [ ] **Step 3: Commit**

```bash
git add python/pack.py && git commit -m "refactor: pack.py reads constants from settings.py"
```

---

### Task 3: Vectorized frame builder (`render.py`)

**Files:**
- Create: `python/render.py`
- Test: `python/test_render.py`

**Interfaces:**
- Consumes: `settings.py` color/geometry constants.
- Produces: `build_frame(band_values, time_offset) -> np.ndarray (16,32,3) uint8` — pure function plus a tiny `Renderer` class holding `time_offset` state:

```python
class Renderer:
    def __init__(self): self.time_offset = 0.0
    def advance(self): ...            # time_offset += HORIZONTAL_SPREAD * SPEED_MULTIPLIER % 360
    def build(self, band_values) -> np.ndarray  # (16,32,3) uint8, RGB order
```

Note output is RGB `(r,g,b)` per pixel; GRB reordering stays in `pack.pack_frame`.

- [ ] **Step 1: Write golden-comparison test FIRST**

`python/test_render.py` — compare vectorized output against a scalar reference implementation (transcribe the old `RGBFrameBuilder.build` loop into the test):

```python
import numpy as np, colorsys
import settings as S
from render import Renderer

def reference_build(band_values, time_offset):
    rows, cols = S.GRID_ROWS, S.GRID_COLS
    frame = []
    for row in range(rows):
        pixel_row = []
        for col in range(cols):
            display_row = rows - 1 - row
            is_active = display_row < min(rows, round(band_values[col] * rows))
            hue = (time_offset + col * S.HORIZONTAL_SPREAD
                   + display_row * S.VERTICAL_SPREAD) % 360.0
            brightness = S.ACTIVE_BRIGHTNESS if is_active else S.INACTIVE_BRIGHTNESS
            r, g, b = colorsys.hsv_to_rgb(hue / 360.0, S.SATURATION, brightness)
            pixel_row.append((int(r*255), int(g*255), int(b*255)))
        frame.append(pixel_row)
    return np.array(frame, dtype=np.uint8)

def test_matches_reference():
    rng = np.random.default_rng(42)
    bands = rng.random(32).tolist()
    r = Renderer(); r.time_offset = 123.4
    out = r.build(bands)
    ref = reference_build(bands, r.time_offset)
    assert out.shape == (16, 32, 3)
    assert (out == ref).all()

def test_advances_time_offset():
    r = Renderer()
    t0 = r.time_offset
    r.advance()
    assert abs(r.time_offset - ((t0 + S.HORIZONTAL_SPREAD*S.SPEED_MULTIPLIER) % 360)) < 1e-9
```

- [ ] **Step 2: Run — expect ImportError (render not created)**

`cd python && ../.venv/bin/python -m pytest test_render.py -q`

- [ ] **Step 3: Implement `render.py`**

```python
import numpy as np
import settings as S

class Renderer:
    def __init__(self):
        self.time_offset = 0.0
        rows, cols = S.GRID_ROWS, S.GRID_COLS
        # display_row 0 = bottom of wall (matches original builder semantics)
        self._display_rows = np.arange(rows)[::-1].astype(np.float64)   # (rows,)
        self._cols = np.arange(cols).astype(np.float64)                 # (cols,)

    def advance(self):
        self.time_offset = (self.time_offset
                            + S.HORIZONTAL_SPREAD * S.SPEED_MULTIPLIER) % 360.0

    @staticmethod
    def _hsv_to_rgb(h, s, v):
        """Vectorized HSV->RGB. h,s,v arrays same shape, h in degrees."""
        h = (h % 360.0) / 60.0
        i = np.floor(h).astype(int) % 6
        f = h - np.floor(h)
        p = v * (1.0 - s)
        q = v * (1.0 - s * f)
        t = v * (1.0 - s * (1.0 - f))
        r = np.select([i==0, i==1, i==2, i==3, i==4], [v, q, p, p, t], default=v)
        g = np.select([i==0, i==1, i==2, i==3, i==4], [t, v, v, q, p], default=p)
        b = np.select([i==0, i==1, i==2, i==3, i==4], [p, p, t, v, v], default=q)
        return r, g, b

    def build(self, band_values):
        bv = np.asarray(band_values, dtype=np.float64)
        heights = np.minimum(S.GRID_ROWS, np.round(bv * S.GRID_ROWS)).astype(np.int64)
        active = self._display_rows[:, None] < heights[None, :]        # (rows, cols)
        hue = (np.full((S.GRID_ROWS, S.GRID_COLS), self.time_offset)
               + self._cols[None, :] * S.HORIZONTAL_SPREAD
               + self._display_rows[:, None] * S.VERTICAL_SPREAD)      # (rows, cols)
        bright = np.where(active, S.ACTIVE_BRIGHTNESS, S.INACTIVE_BRIGHTNESS)
        r, g, b = Renderer._hsv_to_rgb(hue, S.SATURATION, bright)
        rgb = np.stack([r, g, b], axis=-1)                             # (rows, cols, 3)
        return (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
```

- [ ] **Step 4: Run — expect 2 passed**

- [ ] **Step 5: Commit**

```bash
git add python/render.py python/test_render.py
git commit -m "feat: numpy-vectorized frame builder with golden reference test"
```

---

### Task 4: Audio engine (`audio.py`) — sounddevice playback + exact position

**Files:**
- Create: `python/audio.py`
- Test: `python/test_audio.py`

**Interfaces:**
- Consumes: `sounddevice`, decoded numpy samples `(N,) float32 mono` (or `(N,2)`).
- Produces:

```python
class AudioPlayer:
    def __init__(self, samples, samplerate): ...
    def play(self): ...                 # (re)start from current position
    def stop(self): ...
    def pause(self)/resume(self): ...
    def seek_fraction(self, frac): ...
    @property pos_ms -> float           # exact position from callback counter
    @property playing -> bool
    @property duration_ms -> float
    def ended -> bool                   # True when past end
```

Position source of truth: `self._pos` (sample index), advanced inside the PortAudio callback. Analysis reads the same counter ⇒ perfect sync.

- [ ] **Step 1: Write position-math test first (no audio device needed)**

`python/test_audio.py`: instantiate `AudioPlayer` with a fake 1-second sine array but do NOT call play(); instead drive the internal counter directly (`ap._pos = 12345`) and assert `pos_ms == 12345/22050*1000`. Also test `seek_fraction(0.5)` sets `_pos` to half the samples, and `ended` logic.

```python
import numpy as np, pytest
from audio import AudioPlayer

def make_ap(sr=1000, seconds=2):
    samples = np.zeros(sr*seconds, dtype=np.float32)
    return AudioPlayer(samples, sr)

def test_pos_math():
    ap = make_ap()
    ap._pos = 500
    assert ap.pos_ms == 500.0
    assert ap.duration_ms == 2000.0
    assert not ap.ended
    ap._pos = 2000
    assert ap.ended

def test_seek():
    ap = make_ap()
    ap.seek_fraction(0.5)
    assert ap._pos == 1000
    ap.seek_fraction(-1)     # clamps
    assert ap._pos == 0
    ap.seek_fraction(2)      # clamps
    assert ap._pos == 2000
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `audio.py`**

```python
import numpy as np
import sounddevice as sd
import settings as S

class AudioPlayer:
    def __init__(self, samples, samplerate):
        self.samples = np.asarray(samples, dtype=np.float32)
        if self.samples.ndim == 2:          # stereo -> duplicate-mono downmix kept 2ch
            self.channels = self.samples.shape[1]
        else:
            self.samples = self.samples[:, None]
            self.channels = 1
        self.sr = int(samplerate)
        self._pos = 0                       # sample index = playback position
        self._stream = None
        self._playing_flag = False

    def duration_ms(self):
        return len(self.samples) / self.sr * 1000.0

    def _callback(self, outdata, frames, time_info, status):
        remaining = len(self.samples) - self._pos
        n = min(frames, remaining)
        if n > 0:
            outdata[:n] = self.samples[self._pos:self._pos+n]
        if n < frames:
            outdata[n:] = 0
            raise sd.CallbackStop()
        self._pos += frames

    def play(self):
        if self._stream is not None:
            self._stream.close()
        self._stream = sd.OutputStream(
            samplerate=self.sr, channels=self.samples.shape[1],
            dtype='float32', callback=self._callback)
        self._stream.start()
        self._playing_flag = True

    def pause(self):
        if self._stream is not None: self._stream.stop()
        self._playing_flag = False

    def resume(self):
        if self._stream is not None: self._stream.start()
        self._playing_flag = True

    def stop(self):
        if self._stream is not None: self._stream.close(); self._stream = None
        self._pos = 0
        self._playing_flag = False

    def seek_fraction(self, frac):
        self._pos = int(max(0.0, min(1.0, frac)) * len(self.samples))

    @property
    def pos_ms(self): return self._pos / self.sr * 1000.0

    @property
    def playing(self): return self._playing_flag and self._pos < len(self.samples)

    @property
    def ended(self): return self._pos >= len(self.samples)
```

- [ ] **Step 4: Run unit tests — expect passed. Then a manual smoke test WITH speakers:**

```bash
cd python && ../.venv/bin/python -c "
import numpy as np, soundfile as sf, audio, time
data, sr = sf.read('../The Glitch Mob - Fortune Days.mp3', dtype='float32', always_2d=True)
mono = data.mean(axis=1).astype(np.float32)
ap = audio.AudioPlayer(mono, sr)
ap.play()
for _ in range(6):
    time.sleep(0.5); print('pos_ms=', round(ap.pos_ms), 'playing=', ap.playing)
"
```

Expected: audible music through headphones, pos advancing ~500ms per line. **User confirms audio plays.**

- [ ] **Step 5: Commit**

```bash
git add python/audio.py python/test_audio.py
git commit -m "feat: sounddevice audio engine with exact position tracking"
```

---

### Task 5: `headless.py` — entry point wiring everything

**Files:**
- Create: `python/headless.py`

**Interfaces:**
- Consumes: `AudioPlayer`, `Renderer`, `libproc.AudioProcessor` (band FFT — change it to accept preloaded samples + settings.BANDS), `pack.pack_frame`, `serial_sink.SerialSink`.
- Produces: working headless app: `../.venv/bin/python headless.py [--folder DIR] [--fps N] [--port DEV]`

- [ ] **Step 1: Adapt `libproc.py` to take samples from settings-driven decode**

Change `load()` to accept an optional pre-decoded array OR keep librosa path per Task 1 decision; read band list from `settings.BANDS` instead of `cfg.get_bands()`. Smoothing params come from `settings` (RESPONSIVENESS etc.).

- [ ] **Step 2: Write `headless.py`**

Structure (complete):

```python
"""Headless music visualizer: plays a folder of songs on loop, renders to the LED wall.
Usage: cd python && ../.venv/bin/python headless.py --folder /path/to/music"""
import argparse, glob, os, time
import numpy as np
import settings as S
import serial_sink
from audio import AudioPlayer
from render import Renderer
from libproc import AudioProcessor

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder', required=True)
    ap.add_argument('--fps', type=int, default=S.SERIAL_MAX_FPS)
    args = ap.parse_args()

    exts = ('*.mp3','*.flac','*.wav','*.ogg','*.m4a')
    playlist = sorted(sum([glob.glob(os.path.join(args.folder, e)) for e in exts], []))
    if not playlist:
        raise SystemExit(f'no audio files found in {args.folder}')
    print(f'{len(playlist)} tracks')

    sink = serial_sink.SerialSink(port=S.SERIAL_PORT, baud=S.SERIAL_BAUD,
                                  max_fps=args.fps)
    sink.open()
    print(f'serial: {sink.ser.port} @ {sink.ser.baudrate}')

    processor = AudioProcessor(cfg=None)   # will be fed settings.BANDS directly
    renderer = Renderer()
    smoothed = np.zeros(len(S.BANDS))

    while True:                            # folder loops forever
        for path in playlist:
            print('playing:', os.path.basename(path))
            samples, sr = decode(path)             # helper: soundfile w/ librosa fallback
            mono = samples.mean(axis=1) if samples.ndim > 1 else samples
            player = audio.AudioPlayer(mono.astype(np.float32), sr)
            processor.load_array(mono.astype(np.float32), sr, S.BANDS)
            player.play()
            while not player.ended:
                pos_ms = player.pos_ms
                fft = processor.get_frame_at(pos_ms)
                if fft is not None:
                    r, d = S.RESPONSIVENESS, S.RESPONSIVENESS * S.DECAY_RATIO
                    smoothed = np.where(fft > smoothed,
                                        smoothed*(1-r) + fft*r,
                                        smoothed*(1-d) + fft*d)
                renderer.advance()
                frame = renderer.build(smoothed.tolist())
                sink.send_frame(frame)
                time.sleep(1.0 / args.fps)
            player.stop()

if __name__ == '__main__':
    main()
```

(Exact code may be adjusted during implementation; the contract is: folder loop → per-track play → position-synced FFT → renderer → sink.)

- [ ] **Step 3: Add `load_array(samples, sr, bands)` to `libproc.AudioProcessor`**

Same body as `load()` but takes the decoded array directly (no file I/O); sets `_peaks` from `len(bands)`; `_get_band_data` uses the passed bands. Keep old `load()` working or delete it once nothing references it.

- [ ] **Step 4: Smoke-test locally (speakers/headphones on), user watches wall**

Run: `cd python && ../.venv/bin/python headless.py --folder ..`
Expected: music plays, wall shows moving EQ bars smoothly, synced. Let it run ≥60s to confirm no corruption creep.

- [ ] **Step 5: Read diag during run to confirm clean**

Enable `#define SERIAL_DIAGNOSTICS` + re-flash if you want counters; expect `stale≈0, resync≈0, shows tracking rx`.

- [ ] **Step 6: Commit**

```bash
git add python/headless.py python/libproc.py
git commit -m "feat: headless entry point (folder loop, synced FFT->serial)"
```

---

### Task 6: Cleanup — remove dead UI stack

**Files:**
- Delete: `python/player.py`, `python/visualizer.py`, `python/config.py`
- Modify: `python/pipeline_test.py` (update imports: `render.Renderer` replaces `visualizer.RGBFrameBuilder`; drop pygame usage), `README.md`

- [ ] **Step 1: Grep for stragglers referencing deleted modules**

`grep -rn "import config\|from config\|import visualizer\|from visualizer\|pygame\|tkinter" python/*.py` — fix each (config→settings, visualizer→render).

- [ ] **Step 2: Delete**

```bash
git rm python/player.py python/visualizer.py python/config.py
```

- [ ] **Step 3: Full verification**

```bash
cd python && ../.venv/bin/python -c "import headless, render, audio, libproc, pack, serial_sink, settings; print('ok')"
../.venv/bin/python -m pytest test_pack.py test_render.py test_audio.py -q
../.venv/bin/python pipeline_test.py   # after import fixes
pio run --project-dir .                # firmware untouched, should stay SUCCESS
```

- [ ] **Step 4: Update README.md** — new structure/run instructions (headless.py replaces player.py).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: remove pygame/tkinter UI stack; headless-only architecture"
```

---

### Task 7: Hardware acceptance with user watching

- [ ] Run ≥2 full minutes of music via headless.py; user confirms smooth + synced + no corruption.
- [ ] Read `[diag]` (temporarily enable SERIAL_DIAGNOSTICS + flash) — confirm stale/resync ≈ 0 over the full run.
- [ ] Confirm board-5 LED-0 quirk still cosmetic-only.
- [ ] Final commit + push. Tag `v2-headless` if desired.

---

### Out of scope (explicitly deferred)

- Payload checksum/CRC8 on the wire (recommendation #6) — hardening, do later if EMI ever shows up.
- Overlapping receive+show on ESP32 (double-buffering / async RMT) — only if >31fps is ever wanted.
- VLC integration — rejected (heavier than the alternatives).
