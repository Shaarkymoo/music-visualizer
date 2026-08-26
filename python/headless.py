"""Headless music visualizer: plays a folder of songs on loop, renders to the LED wall.

Usage: cd python && ../.venv/bin/python headless.py --folder /path/to/music
       optional: --fps N   (default settings.SERIAL_MAX_FPS)
                 --port DEV  (default auto-detect)
"""
import argparse
import glob
import os
import subprocess
import time

import numpy as np
import soundfile as sf

import pack
import serial_sink
import settings as S
from audio import AudioPlayer
from libproc import AudioProcessor
from render import Renderer

AUDIO_EXTS = ('*.mp3', '*.flac', '*.wav', '*.ogg', '*.m4a')


def build_playlist(folder):
    return sorted(sum([glob.glob(os.path.join(folder, e)) for e in AUDIO_EXTS], []))


def decode(path):
    """Decode any format libsndfile supports -> (samples (N,ch) float32, sr)."""
    data, sr = sf.read(path, dtype='float32', always_2d=True)
    return data, sr


def render_loop(player, processor, renderer, smoothed, sink, fps):
    """One pass of the frame loop while `player` plays. Returns when track ends.

    Pacing under lock-step: send_frame() blocks until the ESP32 acks the
    render, so the handshake itself spaces frames. We only top up to the
    fps target when the round trip is faster than the interval — no absolute
    schedule, so 'falling behind' (and its resync churn) cannot happen.
    """
    r, d = S.RESPONSIVENESS, S.RESPONSIVENESS * S.DECAY_RATIO
    frame_gap = 1.0 / fps
    # Belt-and-braces: re-announce seq=0 periodically so an unexpected
    # >8-frame gap (e.g. USB hiccup) can never lock the ESP32's SEQ gate.
    resync_every = max(1, fps * 15)
    since_resync = 0
    while not player.ended:
        iter_start = time.monotonic()
        fft = processor.get_frame_at(player.pos_ms)
        if fft is not None:
            f = np.asarray(fft)
            smoothed = np.where(f > smoothed, smoothed * (1 - r) + f * r,
                                smoothed * (1 - d) + f * d)
        renderer.advance()
        frame = renderer.build(smoothed.tolist())
        sink.send_frame(frame)
        since_resync += 1
        if since_resync >= resync_every:
            pack.reset_seq()          # next send carries seq=0 (host restart)
            since_resync = 0
        spare = frame_gap - (time.monotonic() - iter_start)
        if spare > 0:
            time.sleep(spare)
    return smoothed


def play_folder(playlist, sink, fps):
    """Play every track once, in order. Caller loops for repeat."""
    processor = AudioProcessor()
    renderer = Renderer()
    smoothed = np.zeros(len(S.BANDS))

    for path in playlist:
        print('playing:', os.path.basename(path))
        try:
            samples, sr = decode(path)
        except Exception as e:
            print(f'WARN: cannot decode {path} ({e}) — skipping')
            continue
        mono = samples.mean(axis=1) if samples.ndim > 1 else samples
        mono = mono.astype(np.float32)

        processor.load_array(mono, sr, S.BANDS)
        player = AudioPlayer(mono, sr)
        player.play()
        try:
            smoothed = render_loop(player, processor, renderer,
                                   smoothed, sink, fps)
        finally:
            player.stop()


def collect_files(selections):
    """Resolve right-click inputs: files pass through (audio extensions only),
    folders expand to the audio files they contain. Returns (sorted_paths,
    any_dir_seen) — any_dir_seen tells the caller to shuffle, so a folder
    always plays randomised while explicit selections keep their order."""
    wanted = {e.lstrip('*').lstrip('.') for e in AUDIO_EXTS}   # {'mp3', ...}
    files, had_dir = [], False
    for p in selections:
        if os.path.isdir(p):
            had_dir = True
            files += sum([glob.glob(os.path.join(p, e)) for e in AUDIO_EXTS], [])
        elif os.path.isfile(p):
            ext = os.path.splitext(p)[1].lower().lstrip('.')
            if ext in wanted:
                files.append(p)
    out = sorted({os.path.abspath(f) for f in files})
    return out, had_dir


def _notify(msg):
    """Best-effort desktop notification (COSMIC/GNOME); silent if unavailable."""
    try:
        subprocess.run(['notify-send', '-a', 'Music Visualiser', 'Music Visualiser',
                        msg], timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('inputs', nargs='*',
                    help='audio files and/or folders of audio (folders shuffle)')
    ap.add_argument('--folder',
                    help='play every audio file in this folder (loops forever)')
    ap.add_argument('--shuffle', action='store_true',
                    help='shuffle the playlist')
    ap.add_argument('--fps', type=int, default=S.SERIAL_MAX_FPS)
    ap.add_argument('--port', default=S.SERIAL_PORT)
    args = ap.parse_args()

    if args.inputs:
        playlist, had_dir = collect_files(args.inputs)
        if not playlist:
            raise SystemExit('no playable audio among: ' + ', '.join(args.inputs))
        if args.shuffle or had_dir:
            import random
            random.shuffle(playlist)
    elif args.folder:
        playlist = build_playlist(args.folder)
        if not playlist:
            raise SystemExit(f'no audio files found in {args.folder}')
        if args.shuffle:
            import random
            random.shuffle(playlist)
    else:
        ap.error('give either file/folder paths or --folder DIR')
    print(f'{len(playlist)} tracks')

    # Single pacing governor: render_loop sleeps to the fps target; the sink's
    # internal min-gap gets 2x headroom so jitter can never silently skip
    # frames (lock-step round trip already exceeds half the interval).
    sink = serial_sink.SerialSink(port=args.port, baud=S.SERIAL_BAUD,
                                  max_fps=args.fps * 2)
    try:
        sink.open()
    except Exception as e:
        _notify(f'LED board not reachable: {e}')
        raise SystemExit(1)
    print(f'serial: {sink.ser.port} @ {sink.ser.baudrate}')
    _notify(f'Playing {len(playlist)} track{"s" if len(playlist) != 1 else ""}')

    try:
        while True:                          # folder loops forever
            play_folder(playlist, sink, args.fps)
    except KeyboardInterrupt:
        print('\nstopped')
    finally:
        sink.close()
        print(f"frames sent: {sink.frames_sent} | rendered+acked: {sink.acks_ok} "
              f"| ack timeouts: {sink.ack_timeouts}")
        if sink.frames_sent:
            print(f"last cycle: write={sink.last_write_ms:.1f}ms "
                  f"ack-wait={sink.last_ack_ms:.1f}ms")


if __name__ == '__main__':
    main()
