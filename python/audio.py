import numpy as np
import sounddevice as sd

class AudioPlayer:
    """sounddevice playback with exact position tracking.

    `self._pos` (sample index) is the single source of truth for playback
    position — it is advanced inside the PortAudio callback, so analysis
    reading `pos_ms` is sample-accurate by construction.
    """

    def __init__(self, samples, samplerate):
        self.samples = np.asarray(samples, dtype=np.float32)
        if self.samples.ndim == 2:          # stereo kept as-is
            self.channels = self.samples.shape[1]
        else:                               # mono -> column vector
            self.samples = self.samples[:, None]
            self.channels = 1
        self.sr = int(samplerate)
        self._pos = 0                       # sample index = playback position
        self._stream = None
        self._playing_flag = False

    @property
    def duration_ms(self):
        return len(self.samples) / self.sr * 1000.0

    def _callback(self, outdata, frames, time_info, status):
        remaining = len(self.samples) - self._pos
        n = min(frames, remaining)
        if n > 0:
            outdata[:n] = self.samples[self._pos:self._pos + n]
            self._pos += n
        if n < frames:
            outdata[n:] = 0
            raise sd.CallbackStop()         # _pos already at end -> ended fires

    def play(self):
        if self._stream is not None:
            self._stream.close()
        if self.ended:
            self._pos = 0                   # replay from start
        self._stream = sd.OutputStream(
            samplerate=self.sr, channels=self.samples.shape[1],
            dtype='float32', callback=self._callback)
        self._stream.start()
        self._playing_flag = True

    def pause(self):
        if self._stream is not None:
            self._stream.stop()
        self._playing_flag = False

    def resume(self):
        if self._stream is not None:
            self._stream.start()
        self._playing_flag = True

    def stop(self):
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._pos = 0
        self._playing_flag = False

    def seek_fraction(self, frac):
        self._pos = int(max(0.0, min(1.0, frac)) * len(self.samples))

    @property
    def pos_ms(self):
        return self._pos / self.sr * 1000.0

    @property
    def playing(self):
        return self._playing_flag and self._pos < len(self.samples)

    @property
    def ended(self):
        return self._pos >= len(self.samples)
