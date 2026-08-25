import numpy as np, pytest
from audio import AudioPlayer

def make_ap(sr=1000, seconds=2):
    samples = np.zeros(sr*seconds, dtype=np.float32)
    return AudioPlayer(samples, sr)

def test_pos_math():
    ap = make_ap()
    ap._pos = 500
    assert ap.pos_ms == 500.0
    assert ap.duration_ms == 2000.0
    assert not ap.ended
    ap._pos = 2000
    assert ap.ended

def test_seek():
    ap = make_ap()
    ap.seek_fraction(0.5)
    assert ap._pos == 1000
    ap.seek_fraction(-1)     # clamps
    assert ap._pos == 0
    ap.seek_fraction(2)      # clamps
    assert ap._pos == 2000

def test_callback_advances_to_end():
    # regression: final partial buffer must advance _pos so `ended` fires
    ap = make_ap()
    ap._pos = 1950           # 50 samples remain, callback asked for 512
    out = np.zeros((512, 1), dtype=np.float32)
    try:
        ap._callback(out, 512, None, None)
        stopped_by_exception = False
    except Exception:
        stopped_by_exception = True   # sd.CallbackStop expected here
    assert stopped_by_exception, "callback must stop at end of stream"
    assert ap._pos == 2000
    assert ap.ended
