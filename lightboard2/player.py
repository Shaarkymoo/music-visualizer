"""
player.py  — THE ENTRY POINT.  Run this.

Layout:
  Left  : pygame visualizer window (32×16 grid, top-left of screen)
  Right : tkinter control panel (tabs + playback bar)
"""

import tkinter as tk
from tkinter import ttk, filedialog
import threading
import os
import glob

from config     import SharedState
import visualizer as vis_module


# ============================================
# DIMENSIONS  (must match visualizer.py)
# ============================================

CELL_SIZE    = 30
CELL_MARGIN  = 3
GRID_W       = 32
GRID_H       = 16

VIS_W = GRID_W * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN   # 1027
VIS_H = GRID_H * (CELL_SIZE + CELL_MARGIN) + CELL_MARGIN   #  531

PANEL_W = 480
PANEL_H = VIS_H + 90   # visualizer height + playback bar

VIS_X   = 0
VIS_Y   = 30    # below title bar
PANEL_X = VIS_W + 2
PANEL_Y = VIS_Y


# ============================================
# THEME
# ============================================

BG       = "#0e0e0e"
BG2      = "#161616"
BG3      = "#1f1f1f"
ACCENT   = "#c8ff00"    # sharp yellow-green
FG       = "#e0e0e0"
FG_DIM   = "#555555"
FONT     = ("Courier New", 9)
FONT_SM  = ("Courier New", 8)
FONT_LG  = ("Courier New", 10, "bold")


# ============================================
# SLIDER DEFINITIONS  (visual tab)
# ============================================

VISUAL_SLIDERS = [
    # attr                   label                  lo      hi      step    default
    ("gamma",                "Gamma",               0.3,    3.0,    0.05,   1.4),
    ("peak_decay",           "Peak decay",          0.980,  0.999,  0.001,  0.998),
    ("responsiveness",       "Attack",              0.05,   1.0,    0.05,   0.75),
    ("decay_ratio",          "Decay ratio",         0.1,    1.0,    0.05,   0.5),
    ("saturation",           "Saturation",          0.0,    1.0,    0.05,   0.90),
    ("active_brightness",    "Active bright",       0.1,    1.0,    0.05,   1.0),
    ("inactive_brightness",  "Dim bright",          0.0,    0.2,    0.005,  0.04),
    ("horizontal_spread",    "Hue / column",        0.0,    30.0,   0.5,    8.0),
    ("vertical_spread",      "Hue / row",           0.0,    15.0,   0.5,    3.0),
    ("speed_multiplier",     "Hue speed",           0.0,    1.0,    0.01,   0.15),
]


# ============================================
# HELPERS
# ============================================

def fmt_time(seconds: float) -> str:
    s = int(seconds)
    return f"{s//60}:{s%60:02d}"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ============================================
# PLAYER UI
# ============================================

class PlayerUI:

    def __init__(self, root: tk.Tk, state: SharedState):
        self.root  = root
        self.state = state

        root.title("player")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.geometry(f"{PANEL_W}x{PANEL_H}+{PANEL_X}+{PANEL_Y}")

        self._build_tabs()
        self._build_playback_bar()

        self._seek_dragging = False
        self._tick()

    # ------------------------------------------
    # TABS
    # ------------------------------------------

    def _build_tabs(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TP.TNotebook",
            background=BG, borderwidth=0, tabmargins=0)
        style.configure("TP.TNotebook.Tab",
            background=BG3, foreground=FG_DIM,
            font=FONT_LG, padding=(16, 6),
            borderwidth=0)
        style.map("TP.TNotebook.Tab",
            background=[("selected", BG2)],
            foreground=[("selected", ACCENT)])
        style.configure("TP.TFrame", background=BG2)

        nb = ttk.Notebook(self.root, style="TP.TNotebook")
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        vis_frame  = ttk.Frame(nb, style="TP.TFrame")
        band_frame = ttk.Frame(nb, style="TP.TFrame")

        nb.add(vis_frame,  text="  VISUAL  ")
        nb.add(band_frame, text="  BANDS   ")

        self._build_visual_tab(vis_frame)
        self._build_band_tab(band_frame)

    # ---- Visual tab ----

    def _build_visual_tab(self, parent):
        canvas = tk.Canvas(parent, bg=BG2, highlightthickness=0)
        sb     = tk.Scrollbar(parent, orient="vertical", command=canvas.yview,
                              bg=BG3, troughcolor=BG, width=8)
        canvas.configure(yscrollcommand=sb.set)

        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG2)
        win_id = canvas.create_window((0,0), window=inner, anchor="nw")

        def on_resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", on_resize)

        inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._vis_vars = []

        for attr, label, lo, hi, step, default in VISUAL_SLIDERS:
            row = tk.Frame(inner, bg=BG2, pady=4)
            row.pack(fill="x", padx=14)

            tk.Label(row, text=label.upper(), bg=BG2, fg=FG_DIM,
                     font=FONT_SM, width=18, anchor="w").pack(side="left")

            val_lbl = tk.Label(row, text=f"{default:.3f}", bg=BG2,
                               fg=ACCENT, font=FONT, width=7, anchor="e")
            val_lbl.pack(side="right")

            var = tk.DoubleVar(value=default)

            def make_cb(a, v, lbl, s, lo_, hi_):
                def cb(*_):
                    raw     = v.get()
                    rounded = round(clamp(round(raw/s)*s, lo_, hi_), 6)
                    v.set(rounded)
                    lbl.config(text=f"{rounded:.3f}")
                    self.state.update_visual({a: rounded})
                return cb

            cb = make_cb(attr, var, val_lbl, step, lo, hi)

            tk.Scale(
                row, variable=var, from_=lo, to=hi, resolution=step,
                orient="horizontal", length=260, showvalue=False,
                bg=BG2, fg=FG, troughcolor=BG3,
                activebackground=ACCENT, highlightthickness=0,
                command=cb,
            ).pack(side="left", padx=(6,4))

            self._vis_vars.append((attr, var))

    # ---- Band tab ----

    def _build_band_tab(self, parent):
        # Header
        hdr = tk.Frame(parent, bg=BG2)
        hdr.pack(fill="x", padx=14, pady=(8,0))
        for text, w in [("#", 3), ("LOW Hz", 8), ("HIGH Hz", 8), ("GAIN", 6)]:
            tk.Label(hdr, text=text, bg=BG2, fg=FG_DIM,
                     font=FONT_SM, width=w, anchor="center").pack(side="left", padx=2)

        # Scrollable band rows
        canvas = tk.Canvas(parent, bg=BG2, highlightthickness=0)
        sb     = tk.Scrollbar(parent, orient="vertical", command=canvas.yview,
                              bg=BG3, troughcolor=BG, width=8)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG2)
        win_id = canvas.create_window((0,0), window=inner, anchor="nw")

        def on_resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", on_resize)
        inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._band_vars = []   # list of (low_var, high_var, gain_var)

        bands = self.state.get_bands()

        for i, (low, high, gain) in enumerate(bands):
            row = tk.Frame(inner, bg=BG2 if i%2==0 else BG3, pady=3)
            row.pack(fill="x", padx=8)

            # Index label
            tk.Label(row, text=str(i), bg=row["bg"], fg=FG_DIM,
                     font=FONT_SM, width=3, anchor="center").pack(side="left", padx=2)

            low_v  = tk.DoubleVar(value=low)
            high_v = tk.DoubleVar(value=high)
            gain_v = tk.DoubleVar(value=gain)

            def make_band_cb(idx, lv, hv, gv):
                def cb(*_):
                    self.state.set_band(idx, lv.get(), hv.get(), gv.get())
                return cb

            cb = make_band_cb(i, low_v, high_v, gain_v)

            for var, lo_v, hi_v, res, w in [
                (low_v,  20,    8000, 1,    8),
                (high_v, 20,    8000, 1,    8),
                (gain_v, 0.0,   3.0,  0.05, 6),
            ]:
                sp = tk.Spinbox(
                    row, textvariable=var, from_=lo_v, to=hi_v,
                    increment=res, width=w, font=FONT,
                    bg=BG3, fg=FG, insertbackground=FG,
                    buttonbackground=BG3, highlightthickness=0,
                    relief="flat", command=cb,
                )
                sp.pack(side="left", padx=4)
                sp.bind("<Return>", cb)
                sp.bind("<FocusOut>", cb)

            self._band_vars.append((low_v, high_v, gain_v))

    # ------------------------------------------
    # PLAYBACK BAR
    # ------------------------------------------

    def _build_playback_bar(self):
        bar = tk.Frame(self.root, bg=BG, height=90)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        # ---- Seek bar ----
        seek_row = tk.Frame(bar, bg=BG)
        seek_row.pack(fill="x", padx=16, pady=(10,0))

        self._time_lbl = tk.Label(seek_row, text="0:00", bg=BG, fg=FG_DIM, font=FONT_SM)
        self._time_lbl.pack(side="left")

        self._dur_lbl = tk.Label(seek_row, text="0:00", bg=BG, fg=FG_DIM, font=FONT_SM)
        self._dur_lbl.pack(side="right")

        self._seek_var = tk.DoubleVar(value=0.0)
        self._seekbar  = tk.Scale(
            seek_row, variable=self._seek_var,
            from_=0.0, to=1.0, resolution=0.001,
            orient="horizontal", showvalue=False, length=330,
            bg=BG, fg=FG, troughcolor=BG3,
            activebackground=ACCENT, highlightthickness=0,
            command=self._on_seek_move,
        )
        self._seekbar.pack(side="left", padx=8, fill="x", expand=True)
        self._seekbar.bind("<ButtonPress-1>",   self._seek_start)
        self._seekbar.bind("<ButtonRelease-1>", self._seek_end)

        # ---- Buttons ----
        btn_row = tk.Frame(bar, bg=BG)
        btn_row.pack(pady=(6,0))

        def btn(parent, text, cmd, toggle_attr=None):
            """Plain text button; toggle_attr highlights when state attr is True."""
            b = tk.Label(
                parent, text=text, bg=BG, fg=FG,
                font=("Courier New", 13), padx=10, cursor="hand2",
            )
            b.pack(side="left", padx=6)
            b.bind("<Button-1>", lambda e: cmd())
            if toggle_attr:
                self._toggle_btns[toggle_attr] = b
            return b

        self._toggle_btns = {}

        btn(btn_row, "⏮",  self._prev)
        btn(btn_row, "⏸",  self._pause)
        btn(btn_row, "⏭",  self._next)
        btn(btn_row, "⇄",  self._toggle_shuffle, "shuffle")
        btn(btn_row, "↺",  self._toggle_repeat,  "repeat")

        # Folder picker — slightly different style
        folder_btn = tk.Label(
            btn_row, text="📁", bg=BG, fg=FG,
            font=("Courier New", 13), padx=10, cursor="hand2",
        )
        folder_btn.pack(side="left", padx=6)
        folder_btn.bind("<Button-1>", lambda e: self._pick_folder())

        # Song name label
        self._song_lbl = tk.Label(
            bar, text="no folder selected", bg=BG, fg=FG_DIM,
            font=FONT_SM, pady=0,
        )
        self._song_lbl.pack()

    # ------------------------------------------
    # BUTTON ACTIONS
    # ------------------------------------------

    def _pause(self):
        self.state.command_pause()

    def _next(self):
        self.state.command_next()

    def _prev(self):
        self.state.command_prev()

    def _toggle_shuffle(self):
        self.state.shuffle = not self.state.shuffle
        self._refresh_toggles()

    def _toggle_repeat(self):
        self.state.repeat = not self.state.repeat
        self._refresh_toggles()

    def _refresh_toggles(self):
        for attr, lbl in self._toggle_btns.items():
            active = getattr(self.state, attr, False)
            lbl.config(fg=ACCENT if active else FG)

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Select music folder")
        if not folder:
            return
        exts   = ("*.mp3","*.flac","*.wav","*.ogg","*.aac","*.m4a")
        paths  = []
        for ext in exts:
            paths += glob.glob(os.path.join(folder, ext))
        paths.sort()
        if paths:
            self.state.load_playlist(paths)
            self._update_song_label()

    # ------------------------------------------
    # SEEK
    # ------------------------------------------

    def _seek_start(self, e):
        self._seek_dragging = True

    def _seek_end(self, e):
        self._seek_dragging = False
        self.state.command_seek(self._seek_var.get())

    def _on_seek_move(self, *_):
        if self._seek_dragging:
            _, _, dur = self.state.get_playback_status()
            self._time_lbl.config(text=fmt_time(self._seek_var.get() * dur))

    # ------------------------------------------
    # TICK — updates seek bar and song label
    # ------------------------------------------

    def _update_song_label(self):
        with self.state._lock:
            idx      = self.state.current_index
            playlist = self.state.playlist
        if playlist:
            name = os.path.splitext(os.path.basename(playlist[idx]))[0]
            self._song_lbl.config(text=name[:60])

    def _tick(self):
        is_playing, pos_frac, dur = self.state.get_playback_status()

        if not self._seek_dragging:
            self._seek_var.set(pos_frac)
            self._time_lbl.config(text=fmt_time(pos_frac * dur))

        self._dur_lbl.config(text=fmt_time(dur))
        self._update_song_label()

        self.root.after(100, self._tick)


# ============================================
# ENTRY POINT
# ============================================

def main():
    state = SharedState()

    # Run visualizer in a background thread
    vis_thread = threading.Thread(
        target=vis_module.run_visualizer,
        args=(state,),
        daemon=True,
    )
    vis_thread.start()

    # Build tkinter panel
    root = tk.Tk()
    root.geometry(f"{PANEL_W}x{PANEL_H}+{PANEL_X}+{PANEL_Y}")
    PlayerUI(root, state)
    root.mainloop()


if __name__ == "__main__":
    main()
