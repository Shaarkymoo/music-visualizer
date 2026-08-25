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
        # truncate (not round): bit-exact with the original scalar builder's
        # int(r*255) conversion — verified by test_render.py golden test
        return (np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)
