import threading
import socket
import json
import copy

# ============================================
# BAND DEFAULTS  (matches libproc.py BANDS)
# ============================================

DEFAULT_BANDS = [
    [100,   120,   1.0],
    [120,   145,   1.0],
    [140,   165,   0.8],
    [160,   175,   1.0],
    [175,   200,   1.0],
    [200,   230,   1.0],
    [230,   260,   1.0],
    [260,   300,   1.0],
    [300,   345,   1.0],
    [345,   395,   1.0],
    [395,   450,   1.0],
    [450,   520,   1.0],
    [520,   595,   1.0],
    [595,   680,   1.0],
    [680,   780,   1.0],
    [780,   895,   1.0],
    [895,   1025,  1.0],
    [1025,  1175,  1.0],
    [1175,  1350,  1.0],
    [1350,  1550,  1.0],
    [1550,  1775,  1.0],
    [1775,  2035,  1.0],
    [2035,  2335,  1.0],
    [2335,  2675,  1.0],
    [2675,  3065,  1.0],
    [3065,  3520,  1.0],
    [3520,  4035,  1.0],
    [4035,  4625,  1.0],
    [4625,  5305,  1.2],
    [5305,  6085,  1.2],
    [6085,  6975,  1.2],
    [6975,  8000,  1.2],
]


# ============================================
# SHARED STATE
# One instance shared between visualizer.py
# (reads every frame) and player.py (writes).
# All fields are plain Python — no pygame refs.
# ============================================

class SharedState:

    def __init__(self):
        self._lock = threading.Lock()

        # ---- Visual / renderer ----
        self.horizontal_spread   = 8.0
        self.vertical_spread     = 3.0
        self.speed_multiplier    = 0.15
        self.active_brightness   = 1.0
        self.inactive_brightness = 0.04
        self.saturation          = 0.90
        self.responsiveness      = 0.75
        self.decay_ratio         = 0.5
        self.gamma               = 1.4
        self.peak_decay          = 0.998

        # ---- Band EQ  (list of [low, high, gain]) ----
        self.bands = copy.deepcopy(DEFAULT_BANDS)

        # ---- Playback (written by player.py, read by visualizer.py) ----
        self.playlist        = []      # list of absolute file paths
        self.current_index   = 0
        self.is_playing      = False
        self.shuffle         = False
        self.repeat          = False   # repeat current track

        # Commands the visualizer should act on next frame.
        # visualizer clears these after handling.
        self._cmd_load       = False   # load & play current_index
        self._cmd_pause      = False   # toggle pause
        self._cmd_seek_frac  = None    # float 0-1 or None

    # --------------------------------------------------
    # Visual config — thread-safe get/set
    # --------------------------------------------------
    def update_visual(self, d: dict):
        with self._lock:
            for k, v in d.items():
                if hasattr(self, k) and not k.startswith("_"):
                    setattr(self, k, type(getattr(self, k))(v))

    def snapshot_visual(self) -> dict:
        with self._lock:
            keys = [
                "horizontal_spread","vertical_spread","speed_multiplier",
                "active_brightness","inactive_brightness","saturation",
                "responsiveness","decay_ratio","gamma","peak_decay",
            ]
            return {k: getattr(self, k) for k in keys}

    # --------------------------------------------------
    # Band EQ — thread-safe
    # --------------------------------------------------
    def get_bands(self):
        with self._lock:
            return copy.deepcopy(self.bands)

    def set_band(self, index: int, low: float, high: float, gain: float):
        with self._lock:
            self.bands[index] = [low, high, gain]

    # --------------------------------------------------
    # Playback helpers — thread-safe
    # --------------------------------------------------
    def load_playlist(self, paths: list):
        with self._lock:
            self.playlist      = list(paths)
            self.current_index = 0
            self._cmd_load     = True

    def command_play_index(self, index: int):
        with self._lock:
            self.current_index = index
            self._cmd_load     = True

    def command_pause(self):
        with self._lock:
            self._cmd_pause = True

    def command_seek(self, frac: float):
        with self._lock:
            self._cmd_seek_frac = max(0.0, min(1.0, frac))

    def command_next(self):
        with self._lock:
            if not self.playlist:
                return
            if self.shuffle:
                import random
                self.current_index = random.randrange(len(self.playlist))
            else:
                self.current_index = (self.current_index + 1) % len(self.playlist)
            self._cmd_load = True

    def command_prev(self):
        with self._lock:
            if not self.playlist:
                return
            self.current_index = (self.current_index - 1) % len(self.playlist)
            self._cmd_load = True

    # --------------------------------------------------
    # Called by visualizer each frame to drain commands
    # Returns dict of pending actions (clears them)
    # --------------------------------------------------
    def drain_commands(self) -> dict:
        with self._lock:
            cmds = {
                "load":      self._cmd_load,
                "pause":     self._cmd_pause,
                "seek_frac": self._cmd_seek_frac,
            }
            self._cmd_load      = False
            self._cmd_pause     = False
            self._cmd_seek_frac = None
            return cmds

    # --------------------------------------------------
    # Written by visualizer so player.py can read it
    # --------------------------------------------------
    def set_playback_status(self, is_playing: bool, pos_frac: float, duration_s: float):
        with self._lock:
            self.is_playing  = is_playing
            self._pos_frac   = pos_frac      # 0-1
            self._duration_s = duration_s

    def get_playback_status(self):
        with self._lock:
            return (
                self.is_playing,
                getattr(self, "_pos_frac",   0.0),
                getattr(self, "_duration_s", 0.0),
            )
