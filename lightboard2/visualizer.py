"""
visualizer.py
Pygame window — positions top-left.
Reads SharedState every frame for config, bands, and playback commands.
Run this first; player.py attaches to the same SharedState via import.
"""

import pygame
import sys
import colorsys
import os
from libproc import AudioProcessor
from config  import SharedState

# ============================================
# FIXED LAYOUT (not live-tunable)
# ============================================

GRID_WIDTH  = 32
GRID_HEIGHT = 16
CELL_SIZE   = 30
CELL_MARGIN = 3
FPS         = 60

WIN_W = GRID_WIDTH  * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN
WIN_H = GRID_HEIGHT * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN

BLACK = (0, 0, 0)


# ============================================
# RGB FRAME BUILDER
# ============================================

class RGBFrameBuilder:

    def __init__(self, cfg: SharedState, cols=GRID_WIDTH, rows=GRID_HEIGHT):
        self.cfg         = cfg
        self.cols        = cols
        self.rows        = rows
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
                is_active   = display_row < active_heights[col]
                hue = (
                    self.time_offset
                    + col         * cfg.horizontal_spread
                    + display_row * cfg.vertical_spread
                ) % 360.0
                brightness = cfg.active_brightness if is_active else cfg.inactive_brightness
                r, g, b    = colorsys.hsv_to_rgb(hue / 360.0, cfg.saturation, brightness)
                pixel_row.append((int(r*255), int(g*255), int(b*255)))
            frame.append(pixel_row)

        return frame


# ============================================
# PYGAME DISPLAY
# ============================================

class PygameDisplay:

    def __init__(self):
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("Visualizer")
        # Position top-left
        os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")

    def render(self, frame):
        self.screen.fill(BLACK)
        for row in range(GRID_HEIGHT):
            for col in range(GRID_WIDTH):
                r, g, b = frame[row][col]
                x = col * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN
                y = row * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN
                pygame.draw.rect(self.screen, (r,g,b), (x, y, CELL_SIZE, CELL_SIZE))
        pygame.display.flip()


# ============================================
# MAIN  (called from player.py, not directly)
# ============================================

def run_visualizer(state: SharedState):

    # SDL window position must be set before pygame.init
    os.environ["SDL_VIDEO_WINDOW_POS"] = "0,30"   # 30px for taskbar/title

    pygame.init()
    pygame.mixer.init()

    processor = AudioProcessor(cfg=state)
    builder   = RGBFrameBuilder(cfg=state)
    display   = PygameDisplay()
    clock     = pygame.time.Clock()

    smoothed     = [0.0] * GRID_WIDTH
    is_paused    = False
    duration_s   = 0.0

    while True:

        # ---- Events ----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            # Auto-advance on song end
            if event.type == pygame.USEREVENT:
                state.command_next()

        # ---- Drain commands from player.py ----
        cmds = state.drain_commands()

        if cmds["load"]:
            with state._lock:
                idx      = state.current_index
                playlist = list(state.playlist)
            if playlist:
                path = playlist[idx]
                processor.load(path)
                duration_s = processor.total_samples / processor.sample_rate
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                pygame.mixer.music.set_endevent(pygame.USEREVENT)
                is_paused  = False
                smoothed   = [0.0] * GRID_WIDTH

        if cmds["pause"]:
            if is_paused:
                pygame.mixer.music.unpause()
                is_paused = False
            else:
                pygame.mixer.music.pause()
                is_paused = True

        if cmds["seek_frac"] is not None:
            if duration_s > 0:
                target_s = cmds["seek_frac"] * duration_s
                pygame.mixer.music.play(start=target_s)
                if is_paused:
                    pygame.mixer.music.pause()

        # ---- FFT ----
        pos_ms  = pygame.mixer.music.get_pos()
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
                alpha      = r if new > old else d
                smoothed[i] = old*(1-alpha) + new*alpha

        # ---- Draw ----
        frame = builder.build(smoothed)
        display.render(frame)

        clock.tick(FPS)
