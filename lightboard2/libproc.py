import numpy as np
import librosa

# ============================================
# FFT AUDIO PROCESSOR
# ============================================

fft_size   = 2048
hop_length = 512

PEAK_DECAY = 0.998
PEAK_FLOOR = 1e-3


class AudioProcessor:

    def __init__(self, cfg=None):
        self._cfg          = cfg   # SharedState — may be None
        self.audio         = None
        self.sample_rate   = None
        self.total_samples = 0
        self.position      = 0
        self._peaks        = None
        self._band_cache   = None  # (bands_tuple, band_data)

    # ----------------------------------------
    # Load a new file
    # ----------------------------------------
    def load(self, filename: str):
        self.audio, self.sample_rate = librosa.load(filename, sr=None, mono=True)
        self.total_samples = len(self.audio)
        self.position      = 0
        n_bands = len(self._cfg.get_bands()) if self._cfg else 32
        self._peaks        = np.full(n_bands, PEAK_FLOOR)
        self._band_cache   = None

    # ----------------------------------------
    # Build bin→band mapping (cached)
    # Rebuilds when bands list changes.
    # ----------------------------------------
    def _get_band_data(self):
        if self._cfg is None:
            return []

        bands = self._cfg.get_bands()   # [[low,high,gain], ...]
        key   = tuple(tuple(b) for b in bands)

        if self._band_cache and self._band_cache[0] == key:
            return self._band_cache[1]

        freqs     = np.fft.rfftfreq(fft_size, d=1.0 / self.sample_rate)
        band_data = []
        for low, high, gain in bands:
            bins = np.where((freqs >= low) & (freqs < high))[0]
            band_data.append({"bins": bins, "gain": gain})

        self._band_cache = (key, band_data)
        return band_data

    # ----------------------------------------
    # Get frame aligned to playback ms
    # ----------------------------------------
    def get_frame_at(self, playback_ms: float):
        if self.audio is None:
            return None

        sample_pos    = int((playback_ms / 1000.0) * self.sample_rate)
        self.position = sample_pos

        if self.position + fft_size >= self.total_samples:
            return None

        chunk    = self.audio[self.position : self.position + fft_size]
        window   = np.hanning(len(chunk))
        fft      = np.fft.rfft(chunk * window)
        mag      = np.abs(fft)

        band_data = self._get_band_data()
        if not band_data:
            return None

        raw = np.zeros(len(band_data))
        for i, b in enumerate(band_data):
            bins = b["bins"]
            if len(bins):
                raw[i] = (0.7 * np.mean(mag[bins]) + 0.3 * np.max(mag[bins])) * b["gain"]

        compressed = np.log1p(raw)

        peak_decay = self._cfg.peak_decay if self._cfg else PEAK_DECAY
        gamma      = self._cfg.gamma      if self._cfg else 1.4

        # Resize peaks array if band count changed
        if len(self._peaks) != len(band_data):
            self._peaks = np.full(len(band_data), PEAK_FLOOR)

        self._peaks = np.maximum(self._peaks * peak_decay, compressed)
        self._peaks = np.maximum(self._peaks, PEAK_FLOOR)

        return np.power(compressed / self._peaks, gamma).tolist()
