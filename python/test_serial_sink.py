"""Unit tests for SerialSink lock-step flow control (no hardware needed)."""
import time
import serial
import serial_sink
from serial_sink import SerialSink, ACK_BYTE


class FakeSer:
    """Minimal pyserial stand-in: records writes, serves scripted reads."""
    def __init__(self, reads=None, fail_write=False):
        self.is_open = True
        self.written = []
        self._reads = list(reads or [])
        self.fail_write = fail_write
        self.input_flushed = False

    def write(self, data):
        if self.fail_write:
            raise serial.SerialException("port gone")
        self.written.append(data)
        return len(data)

    def read(self, n=1):
        if self._reads:
            return bytes([self._reads.pop(0)])
        return b""

    def reset_input_buffer(self):
        self.input_flushed = True

    def close(self):
        self.is_open = False


def make_sink(max_fps=100000):
    sink = SerialSink(port="/dev/fake", baud=921600, max_fps=max_fps)
    sink.ser = FakeSer(reads=[0x01])
    return sink


def make_frame():
    import settings as S
    return [[[10, 20, 30]] * S.GRID_COLS for _ in range(S.GRID_ROWS)]


def test_ack_consumed_after_write():
    sink = make_sink()
    sink.send_frame(make_frame())
    assert sink.frames_sent == 1
    assert sink.acks_ok == 1
    assert sink.ack_timeouts == 0
    # frame is a full 1542-byte packet on the wire
    assert len(sink.ser.written[0]) == 1542


def test_ack_timeout_tolerated():
    sink = make_sink()
    sink.ser._reads = []            # no ack will arrive
    sink.send_frame(make_frame())
    assert sink.frames_sent == 1
    assert sink.ack_timeouts == 1   # empty read handled as fire-and-forget
    # next send still works after a timeout
    sink.ser._reads = [0x01]
    sink.send_frame(make_frame())
    assert sink.acks_ok == 1 and sink.frames_sent == 2


def test_wrong_byte_counts_as_timeout():
    sink = make_sink()
    sink.ser._reads = [ord("M")]    # e.g. banner text, not an ACK
    sink.send_frame(make_frame())
    assert sink.ack_timeouts == 1 and sink.acks_ok == 0


def test_throttle_still_applies():
    sink = SerialSink(port="/dev/fake", baud=921600, max_fps=25)
    sink.ser = FakeSer(reads=[0x01, 0x01])
    f = make_frame()
    sink.send_frame(f)              # first passes (_last starts at 0)
    sink.send_frame(f)              # immediate second call -> throttled away
    assert sink.frames_sent == 1
    time.sleep(1.0 / 25 + 0.01)
    sink.send_frame(f)
    assert sink.frames_sent == 2


def test_write_failure_drops_link_gracefully():
    sink = make_sink()
    sink.ser.fail_write = True
    sink.send_frame(make_frame())   # must not raise
    assert sink.ser is None         # link dropped
    assert sink.frames_sent == 0
    # subsequent sends are silent no-ops (audio keeps running)
    sink.send_frame(make_frame())
    assert sink.frames_sent == 0


def test_ack_byte_matches_firmware():
    # guard against protocol drift: firmware define is parsed from source
    import re
    src = open("../src/main.cpp").read()
    m = re.search(r"#define FRAME_ACK_BYTE\s+(0x[0-9A-Fa-f]+)", src)
    assert m, "FRAME_ACK_BYTE missing from firmware"
    assert ACK_BYTE == bytes([int(m.group(1), 16)])
