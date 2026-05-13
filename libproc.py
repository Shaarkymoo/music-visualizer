import numpy as np
import librosa

# ============================================
# FFT AUDIO PROCESSOR
# ============================================

min_freq = 100
max_freq = 8000
fft_size = 2048
bands = 32
hop_length = 512 # 50% overlap

BANDS = [

    (100,   120,   0.5),        #0
    (115,   130,   0.5),        #1
    (125,   155,   0.5),        #2
    (150,   175,   0.5),        #3
    (175,   200,   0.5),        #4
    (200,   230,   1.0),        #5
    (230,   260,   1.0),        #6
    (260,   300,   1.0),        #7
    (300,   345,   1.0),        #8
    (345,   395,   1.0),        #9
    (395,   450,   1.0),        #10
    (450,   520,   1.0),        #11
    (520,   595,   1.0),        #12
    (595,   680,   1.0),        #13
    (680,   780,   1.0),        #14
    (780,   895,   1.0),        #15
    (895,   1025,  1.0),        #16
    (1025,  1175,  1.0),        #17
    (1175,  1350,  1.0),        #18
    (1350,  1550,  1.0),        #19
    (1550,  1775,  1.0),        #20
    (1775,  2035,  1.0),        #21
    (2035,  2335,  1.0),        #22
    (2335,  2675,  1.0),        #23
    (2675,  3065,  1.0),        #24
    (3065,  3520,  1.0),        #25
    (3520,  4035,  1.0),        #26
    (4035,  4625,  1.0),        #27
    (4625,  5305,  1.0),        #28
    (5305,  6085,  1.0),        #29
    (6085,  6975,  1.0),        #30
    (6975,  8000,  1.0),        #31


]


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

        self.band_data = []

        for low, high, gain in BANDS:

            bins = np.where(
                (freqs >= low) &
                (freqs < high)
            )[0]

            self.band_data.append(
                {
                    "bins": bins,
                    "gain": gain
                }
            )

    # ========================================
    # GET NEXT FFT FRAME
    # ========================================

    def get_next_frame(self):

        # ------------------------------------
        # End of audio
        # ------------------------------------

        if self.position + fft_size >= self.total_samples:

            return None

        # ------------------------------------
        # Extract audio chunk
        # ------------------------------------

        chunk = self.audio[
            self.position:
            self.position + fft_size
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
        # CREATE BANDS
        # ------------------------------------

        band_values = []
        
        for band in self.band_data:

            bins = band["bins"]
            gain = band["gain"]

            if len(bins) == 0:
                value = 0

            else:
                value = np.mean(magnitude[bins])
                # value = np.max(magnitude[bins])
                # value = np.sqrt(np.mean(magnitude[bins] ** 2))
                # value = np.sum(magnitude[bins])

                # APPLY GAIN
                value *= gain

            band_values.append(value)

        band_values = np.array(band_values)
        #band_values = np.power(band_values, 0.65)

        # ------------------------------------
        # LOG SCALE
        # ------------------------------------

        band_values = np.log1p(band_values)
        #band_values = np.sqrt(band_values)
        #band_values = np.power(band_values, 0.4)

        # ------------------------------------
        # NORMALIZE TO 0-1
        # ------------------------------------

        max_value = np.max(band_values)

        if max_value > 0:
            band_values /= max_value
        
        #band_values = np.power(band_values, 0.7)

        # ------------------------------------
        # RETURN
        # ------------------------------------

        return band_values.tolist()