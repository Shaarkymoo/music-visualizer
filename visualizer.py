import pygame
import sys
import colorsys
from libproc import AudioProcessor

# ============================================
# CONFIG
# ============================================

MUSIC_FILE = "E:/Shaarav/playlists/heavy rock band/Nookie - limpbizkit.mp3"
MUSIC_FILE = "E:/Shaarav/playlists/"

GRID_WIDTH  = 32
GRID_HEIGHT = 16

CELL_SIZE   = 30
CELL_MARGIN = 3

FPS = 60

# Window size
WINDOW_WIDTH  = GRID_WIDTH  * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN
WINDOW_HEIGHT = GRID_HEIGHT * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN

# ============================================
# RENDERER CONFIG
# ============================================

horizontal_spread  = 8      # hue degrees per column
vertical_spread    = 3      # hue degrees per row
speed_multiplier   = 0.15   # hue animation speed

active_brightness  = 1.0
inactive_brightness = 0.04

saturation         = 0.90

# Smoothing: higher = more responsive, lower = smoother trails
# 0.6–0.8 is a good range for rock music
responsiveness     = 0.75

# ============================================
# COLORS
# ============================================

BLACK = (0, 0, 0)

# ============================================
# RGB FRAME BUILDER
# ============================================
# This class is the ONLY place that knows about
# colors. It takes band values and returns a
# 2-D list of RGB tuples:
#   frame[row][col] = (r, g, b)   r/g/b in 0–255
#
# Swap this class out for an ESP32 serial sender
# and the rest of the code stays identical.
# ============================================

class RGBFrameBuilder:

    def __init__(self, cols=GRID_WIDTH, rows=GRID_HEIGHT):

        self.cols        = cols
        self.rows        = rows
        self.time_offset = 0.0

    def build(self, band_values):
        """
        band_values : list of 32 floats in [0.0, 1.0]

        Returns:
            frame : list[GRID_HEIGHT][GRID_WIDTH] of (r, g, b) tuples
        """

        # Advance hue animation
        self.time_offset = (
            self.time_offset + horizontal_spread * speed_multiplier
        ) % 360.0

        # Pre-compute active row heights and update peak trackers
        active_heights = []
        for col, val in enumerate(band_values):
            h = min(self.rows, round(val * self.rows))
            active_heights.append(h)


        # Build the 2-D RGB frame
        # row 0 = top of grid, row (rows-1) = bottom
        frame = []
        for row in range(self.rows):
            pixel_row = []
            for col in range(self.cols):

                active_height = active_heights[col]

                # bottom-up: row 0 in our loop is the TOP of the display,
                # so "row < active_height" counts from the bottom
                display_row  = self.rows - 1 - row   # 0 = bottom
                is_active    = display_row < active_height

                # --------------------------------
                # Hue: shifts across columns AND
                # rows so the gradient feels
                # "attached" to the bar
                # --------------------------------
                hue = (
                    self.time_offset
                    + col  * horizontal_spread
                    + display_row * vertical_spread
                ) % 360.0

                hue_n = hue / 360.0

                if is_active:
                    r, g, b = colorsys.hsv_to_rgb(hue_n, saturation, active_brightness)
                else:
                    r, g, b = colorsys.hsv_to_rgb(hue_n, saturation, inactive_brightness)

                pixel_row.append((int(r * 255), int(g * 255), int(b * 255)))

            frame.append(pixel_row)

        return frame


# ============================================
# PYGAME DISPLAY
# Receives a completed RGB frame and draws it.
# Replace this class with ESP32Serial to drive
# physical LEDs — zero other changes needed.
# ============================================

class PygameDisplay:

    def __init__(self, cols=GRID_WIDTH, rows=GRID_HEIGHT):
        self.cols   = cols
        self.rows   = rows
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Audio Visualizer")

    def render(self, frame):
        """
        frame : list[rows][cols] of (r, g, b)
        """
        self.screen.fill(BLACK)

        for row in range(self.rows):
            for col in range(self.cols):
                color = frame[row][col]
                x = col * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN
                y = row * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN
                pygame.draw.rect(
                    self.screen,
                    color,
                    (x, y, CELL_SIZE, CELL_SIZE)
                )

        pygame.display.flip()


# ============================================
# EXAMPLE ESP32 DISPLAY STUB
# Uncomment and swap in place of PygameDisplay
# when you move to hardware.
#
# class ESP32SerialDisplay:
#     def __init__(self, port="COM3", baud=921600):
#         import serial
#         self.ser = serial.Serial(port, baud)
#
#     def render(self, frame):
#         # Flatten frame to bytes and send
#         packet = bytearray()
#         for row in frame:
#             for r, g, b in row:
#                 packet += bytes([r, g, b])
#         self.ser.write(packet)
# ============================================


# ============================================
# MAIN
# ============================================

def main():

    pygame.init()

    processor = AudioProcessor(MUSIC_FILE)
    builder   = RGBFrameBuilder()
    display   = PygameDisplay()

    clock     = pygame.time.Clock()

    # Smoothed band values (carried across frames)
    smoothed  = [0.0] * GRID_WIDTH

    pygame.mixer.init()
    pygame.mixer.music.load(MUSIC_FILE)
    pygame.mixer.music.play()

    while True:

        # ----------------------------------------
        # Events
        # ----------------------------------------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # ----------------------------------------
        # Sync processor to actual playback clock
        # This is the key fix for audio/visual lag:
        # we always read the FFT at the sample that
        # matches what you're hearing RIGHT NOW.
        # ----------------------------------------
        playback_ms  = pygame.mixer.music.get_pos()
        fft_values   = processor.get_frame_at(playback_ms)

        if fft_values is not None:
            # Asymmetric smoothing:
            # attack (rising) is fast, decay (falling) is slower.
            # This makes beats hit sharply but bars fall gracefully.
            for i in range(len(smoothed)):
                new = fft_values[i]
                old = smoothed[i]
                if new > old:
                    # Fast attack
                    smoothed[i] = old * (1 - responsiveness) + new * responsiveness
                else:
                    # Slower decay (half the responsiveness)
                    decay = responsiveness * 0.5
                    smoothed[i] = old * (1 - decay) + new * decay

        # ----------------------------------------
        # Build RGB frame → display
        # ----------------------------------------
        frame = builder.build(smoothed)
        display.render(frame)

        clock.tick(FPS)


if __name__ == "__main__":
    main()