import numpy as np
import librosa

# ============================================
# FFT AUDIO PROCESSOR
# ============================================

min_freq = 40
max_freq = 14000
fft_size = 1024
bands = 32
hop_length = 512 # 50% overlap

class AudioProcessor:

    def __init__(
        self,
        filename,
        fft_size=fft_size,
        bands=bands
    ):

        # ------------------------------------
        # Load MP3
        # ------------------------------------

        self.audio, self.sample_rate = librosa.load(
            filename,
            sr=None,
            mono=True
        )

        # ------------------------------------
        # SETTINGS
        # ------------------------------------

        self.fft_size = fft_size
        self.hop_length = hop_length
        self.bands = bands

        # Current playback position
        self.position = 0

        # Total samples
        self.total_samples = len(self.audio)

        # ------------------------------------
        # PRECOMPUTE LOG BANDS
        # ------------------------------------

        # FFT frequencies
        freqs = np.fft.rfftfreq(
            fft_size,
            d=1.0 / self.sample_rate
        )

        # Human hearing is logarithmic
        # so equalizer bands should be too

        # Create logarithmic frequency edges
        band_edges = np.logspace(
            np.log10(min_freq),
            np.log10(max_freq),
            bands + 1
        )

        self.band_bins = []

        for i in range(bands):

            low = band_edges[i]
            high = band_edges[i + 1]

            #print(f"Band {i}: {low:.1f} Hz - {high:.1f} Hz")

            # FFT bin indices in this range
            bins = np.where(
                (freqs >= low) &
                (freqs < high)
            )[0]

            self.band_bins.append(bins)

    # ========================================
    # GET NEXT FFT FRAME
    # ========================================

    def get_next_frame(self):

        # ------------------------------------
        # End of audio
        # ------------------------------------

        if self.position + self.fft_size >= self.total_samples:

            return None

        # ------------------------------------
        # Extract audio chunk
        # ------------------------------------

        chunk = self.audio[
            self.position:
            self.position + self.fft_size
        ]

        # Move forward
        # self.position += self.fft_size
        # self.position += self.fft_size // 4
        self.position += self.hop_length

        # ------------------------------------
        # Apply window
        # ------------------------------------

        # Reduces FFT artifacts
        window = np.hanning(len(chunk))
        chunk = chunk * window

        # ------------------------------------
        # FFT
        # ------------------------------------

        fft = np.fft.rfft(chunk)

        # Magnitude spectrum
        magnitude = np.abs(fft)

        # ------------------------------------
        # CREATE 16 BANDS
        # ------------------------------------

        band_values = []
        

        for i, bins in enumerate(self.band_bins):

            if len(bins) == 0:
                value = 0

            else:
                # Average energy in band
                #value = np.mean(magnitude[bins])
                #value = np.max(magnitude[bins])
                value = np.sqrt(np.mean(magnitude[bins] ** 2))

            weight = 1.0 + (i / self.bands) * 3
            value *= weight
                
            band_values.append(value)

        band_values = np.array(band_values)
        #band_values = np.power(band_values, 0.65)

        # ------------------------------------
        # LOG SCALE
        # ------------------------------------

        # Human hearing is logarithmic
        band_values = np.log1p(band_values)

        # ------------------------------------
        # NORMALIZE TO 0-1
        # ------------------------------------

        max_value = np.max(band_values)

        if max_value > 0:
            band_values /= max_value
        
        band_values = np.power(band_values, 0.7)

        # ------------------------------------
        # RETURN
        # ------------------------------------

        return band_values.tolist()