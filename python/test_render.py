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
