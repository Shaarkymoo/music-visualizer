import pygame
import random
import sys
import colorsys
from libproc import AudioProcessor

# ============================================
# CONFIG
# ============================================

GRID_WIDTH = 32
GRID_HEIGHT = 16

CELL_SIZE = 30
CELL_MARGIN = 3

FPS = 60

# Window size
WINDOW_WIDTH = GRID_WIDTH * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN
WINDOW_HEIGHT = GRID_HEIGHT * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN

# OPTIONAL SMOOTHING
responsiveness = 1 # 1 = no smoothing, 0 = max smoothing meaning no values.

# ============================================
# COLORS
# ============================================

BLACK = (0, 0, 0)
DARK_GRAY = (25, 25, 25)

# ============================================
# PYGAME INIT
# ============================================

pygame.init()

screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("16x16 Audio Visualizer")

clock = pygame.time.Clock()

# ============================================
# VISUALIZER CLASS
# ============================================

class Equalizer16x16:

    def __init__(self):

        self.columns = GRID_WIDTH
        self.time_offset = 0
        self.rows = GRID_HEIGHT

        # Current FFT heights
        self.values = [0] * self.columns

    # ----------------------------------------
    # Set FFT values
    # Input:
    # [0.0 -> 1.0] * 16
    # ----------------------------------------
    def update(self, fft_values):

        if len(fft_values) != self.columns:
            raise ValueError("Need exactly 16 FFT values")

        # Clamp values to 0-1
        self.values = [
            max(0.0, min(1.0, v))
            for v in fft_values
        ]
        
    # ============================================
    # DRAW MATRIX
    # ============================================

    def draw(self, surface):

        surface.fill(BLACK)

        # ----------------------------------------
        # COLOR SETTINGS
        # ----------------------------------------

        horizontal_spread = 10
        vertical_spread = 3

        active_brightness = 1.0
        inactive_brightness = 0.05

        saturation = 0.85

        # ----------------------------------------
        # Animate hue shift
        # ----------------------------------------

        self.time_offset += horizontal_spread * 0.25

        # Keep hue wrapped
        self.time_offset %= 360

        # ----------------------------------------
        # Draw cells
        # ----------------------------------------

        for col in range(self.columns):

            # Convert normalized FFT value to height
            active_height = min(self.rows, round(self.values[col] * self.rows))

            for row in range(self.rows):

                # --------------------------------
                # Bottom-up rendering
                # --------------------------------

                inverted_row = self.rows - 1 - row

                x = col * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN
                y = inverted_row * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN

                # --------------------------------
                # Determine active state
                # --------------------------------

                is_active = row < active_height

                # --------------------------------
                # HSV COLOR GENERATION
                # --------------------------------

                # visual_row makes gradient
                # feel attached to the bar
                visual_row = row

                hue = (
                    self.time_offset
                    + col * horizontal_spread
                    + visual_row * vertical_spread
                ) % 360

                # HSV expects:
                # H = 0→1
                # S = 0→1
                # V = 0→1

                hue_normalized = hue / 360.0

                brightness = (
                    active_brightness
                    if is_active
                    else inactive_brightness
                )

                r, g, b = colorsys.hsv_to_rgb(
                    hue_normalized,
                    saturation,
                    brightness
                )

                # Convert float RGB to pygame RGB
                color = (
                    int(r * 255),
                    int(g * 255),
                    int(b * 255)
                )

                # --------------------------------
                # DRAW CELL
                # --------------------------------

                pygame.draw.rect(
                    surface,
                    color,
                    (x, y, CELL_SIZE, CELL_SIZE)
                )


# ============================================
# CREATE VISUALIZER
# ============================================

visualizer = Equalizer16x16()

# ============================================
# TEST MODE
# Random fake FFT values
# ============================================

def generate_fake_fft():

    return [
        random.random()
        for _ in range(32)
    ]

# ============================================
# MAIN LOOP
# ============================================

MUSIC_FILE = "E:\\Shaarav\\playlists\\heavy rock band\\Limp Bizkit - Rollin'.mp3"

processor = AudioProcessor(MUSIC_FILE)

pygame.mixer.init()
pygame.mixer.music.load(MUSIC_FILE)
pygame.mixer.music.play()

while True:

    # ----------------------------------------
    # EVENTS
    # ----------------------------------------
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

    # ----------------------------------------
    # Get playback position
    # ----------------------------------------

    music_pos_ms = pygame.mixer.music.get_pos()

    # Convert ms → samples
    sample_position = int(
        (music_pos_ms / 1000.0)
        * processor.sample_rate
    )

    # Update processor position
    processor.position = sample_position

    # ----------------------------------------
    # UPDATE FFT VALUES
    # ----------------------------------------
    #fft_values = generate_fake_fft()
    # fft_values = processor.get_next_frame()

    # if fft_values is not None:
    #     visualizer.update(fft_values)

    fft_values = processor.get_next_frame()

    if fft_values is not None:

        visualizer.values = [
            old * (1 - responsiveness) + new * responsiveness
            for old, new in zip(
                visualizer.values,
                fft_values
            )
        ]

    # ----------------------------------------
    # DRAW
    # ----------------------------------------
    visualizer.draw(screen)

    pygame.display.flip()

    clock.tick(FPS)