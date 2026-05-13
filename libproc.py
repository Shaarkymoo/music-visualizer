import numpy as np
import librosa

# ============================================
# FFT AUDIO PROCESSOR
# ============================================

fft_size  = 2048
hop_length = 512
bands     = 32

BANDS = [
    #  low    high   gain
    (115,   120,   1.0),   # 0  ← was 0.5, raised so col 3 isn't invisible
    (120,   145,   1.0),   # 1
    (145,   160,   1.0),   # 2
    (160,   175,   1.0),   # 3  ← this was your "missing" column
    (175,   200,   1.0),   # 4
    (200,   230,   1.0),   # 5
    (230,   260,   1.0),   # 6
    (260,   300,   1.0),   # 7
    (300,   345,   1.0),   # 8
    (345,   395,   1.0),   # 9
    (395,   450,   1.0),   # 10
    (450,   520,   1.0),   # 11
    (520,   595,   1.0),   # 12
    (595,   680,   1.0),   # 13
    (680,   780,   1.0),   # 14
    (780,   895,   1.0),   # 15
    (895,   1025,  1.0),   # 16
    (1025,  1175,  1.0),   # 17
    (1175,  1350,  1.0),   # 18
    (1350,  1550,  1.0),   # 19
    (1550,  1775,  1.0),   # 20
    (1775,  2035,  1.0),   # 21
    (2035,  2335,  1.0),   # 22
    (2335,  2675,  1.0),   # 23
    (2675,  3065,  1.0),   # 24
    (3065,  3520,  1.0),   # 25
    (3520,  4035,  1.0),   # 26
    (4035,  4625,  1.0),   # 27
    (4625,  5305,  1.2),   # 28
    (5305,  6085,  1.2),   # 29
    (6085,  6975,  1.2),   # 30
    (6975,  8000,  1.2),   # 31
]

# ============================================
# RUNNING PEAK TRACKER
# Used for per-band normalization so quiet
# bands still show activity instead of
# being crushed by loud ones.
# ============================================

PEAK_DECAY   = 0.998   # how fast peaks fall (per frame)
PEAK_FLOOR   = 1e-3    # prevents division by near-zero

class AudioProcessor:

    def __init__(self, filename, fft_size=fft_size, bands=bands):

        # ------------------------------------
        # Load audio
        # ------------------------------------
        self.audio, self.sample_rate = librosa.load(
            filename,
            sr=None,
            mono=True
        )

        self.hop_length   = hop_length
        self.bands        = bands
        self.position     = 0
        self.total_samples = len(self.audio)

        # Running per-band peak for adaptive normalization
        self._peaks = np.full(len(BANDS), PEAK_FLOOR)

        # ------------------------------------
        # Pre-compute FFT bin → band mapping
        # ------------------------------------
        freqs = np.fft.rfftfreq(fft_size, d=1.0 / self.sample_rate)

        self.band_data = []
        for low, high, gain in BANDS:
            bins = np.where((freqs >= low) & (freqs < high))[0]
            self.band_data.append({"bins": bins, "gain": gain})

    # ========================================
    # GET FRAME ALIGNED TO PLAYBACK POSITION
    # Call this every frame, passing the
    # current pygame.mixer.music.get_pos() ms.
    # ========================================

    def get_frame_at(self, playback_ms):
        """
        Seek to the sample that matches current playback position
        and return processed band values [0.0 – 1.0] × 32.
        Returns None when past end of audio.
        """
        sample_pos = int((playback_ms / 1000.0) * self.sample_rate)
        self.position = sample_pos
        return self._process_frame()

    # ========================================
    # INTERNAL: process one FFT frame
    # ========================================

    def _process_frame(self):

        if self.position + fft_size >= self.total_samples:
            return None

        chunk = self.audio[self.position : self.position + fft_size]

        # Hanning window reduces spectral leakage
        window    = np.hanning(len(chunk))
        windowed  = chunk * window

        # FFT → magnitude
        fft       = np.fft.rfft(windowed)
        magnitude = np.abs(fft)

        # ------------------------------------
        # Band extraction
        # ------------------------------------
        raw = np.zeros(len(self.band_data))
        for i, band in enumerate(self.band_data):
            bins = band["bins"]
            gain = band["gain"]
            if len(bins):
                # Mean gives smoother response; max is punchier.
                # Using a weighted blend here: 70% mean + 30% max
                # gives body AND transient snap.
                val       = 0.7 * np.mean(magnitude[bins]) + 0.3 * np.max(magnitude[bins])
                raw[i]    = val * gain

        # ------------------------------------
        # Log compression (perceptual loudness)
        # ------------------------------------
        compressed = np.log1p(raw)

        # ------------------------------------
        # Adaptive per-band normalization
        #
        # Each band's peak decays slowly, so
        # every band fills the full 0–1 range
        # over time rather than being dominated
        # by the loudest band.
        # ------------------------------------
        self._peaks     = np.maximum(self._peaks * PEAK_DECAY, compressed)
        self._peaks     = np.maximum(self._peaks, PEAK_FLOOR)
        normalized      = compressed / self._peaks

        # ------------------------------------
        # Gamma curve: pulls mid-level values
        # upward so the display looks fuller
        # (0.7 = slightly convex, values below
        # 1 get boosted toward 1)
        # ------------------------------------
        output = np.power(normalized, 1.6)

        return output.tolist()