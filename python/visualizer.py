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
