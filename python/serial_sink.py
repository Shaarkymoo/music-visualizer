import fcntl
import struct
import time
import serial
import serial.tools.list_ports
import pack

ACK_BYTE = b"\x01"   # must match FRAME_ACK_BYTE in src/main.cpp

# linux/serial.h — struct serial_struct layout for 64-bit, and the flag that
# makes usb-serial drivers use 1ms instead of the default 16ms buffering for
# small IN packets. Without it, our 1-byte render-ACK can sit ~16-40ms in the
# CP2102 before reaching the host.
ASYNC_LOW_LATENCY = 0x2000
TIOCGSERIAL = 0x541E
TIOCSSERIAL = 0x541F
SERIAL_STRUCT_FMT = "=i i I i i i i i H c x H H 8x Q H I Q"


class SerialSink:
    """Frame writer with lock-step flow control.

    After each frame is written, we block until the ESP32 sends its
    post-show() acknowledgement byte (ACK_BYTE). No frame is ever on the
    wire while FastLED.show() blocks the ESP32's UART RX — the frame-loss
    mode that ate 30-50% of sent frames becomes impossible by
    construction. Each ACK also proves the previous frame was rendered
    (the ack is only emitted after show()).

    Degrades gracefully: if an ACK doesn't arrive within `ack_timeout`,
    this cycle proceeds fire-and-forget and the seq=0 heartbeat in
    headless.py covers any residual desync. Talking to a firmware build
    without ACK support behaves identically (timeout every frame,
    streaming continues).
    """

    def __init__(self, port=None, baud=115200, max_fps=40, ack_timeout=0.5):
        self.port = port
        self.baud = baud
        self.max_fps = max_fps
        self._min_gap = 1.0 / max_fps
        self._last = 0.0
        self.ser = None
        self.ack_timeout = ack_timeout
        # diagnostics
        self.frames_sent = 0
        self.acks_ok = 0
        self.ack_timeouts = 0
        self.last_write_ms = 0.0
        self.last_ack_ms = 0.0

    @staticmethod
    def _autodetect():
        for p in serial.tools.list_ports.comports():
            # ESP32 typically identifies as USB Serial / CP210x / CH340
            if "USB" in (p.description or "") or "CH340" in (p.description or "") \
               or "CP210" in (p.description or "") or "Serial" in (p.description or ""):
                return p.device
        return None

    @property
    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def open(self):
        port = self.port or self._autodetect()
        if not port:
            raise RuntimeError("No serial port found; set port explicitly")
        # write_timeout: block until the full frame is written (no
        # truncation). timeout: poll granularity for the ACK wait loop —
        # pyserial's read(n) only returns early when n bytes are available,
        # so we read ONE byte per call against our own deadline instead.
        self.ser = serial.Serial(port, self.baud, timeout=0.02,
                                 write_timeout=1.0)
        # Discard anything queued from before we opened (boot banner text,
        # stale ACKs) so the first read pairs with OUR first frame.
        self.ser.reset_input_buffer()
        self.set_low_latency()

    @staticmethod
    def set_low_latency_fd(fd):
        """Flip ASYNC_LOW_LATENCY on a tty fd: usb-serial drivers then push
        small RX packets out in ~1ms instead of buffering ~16ms (CP2102
        latency timer). Raises on failure."""
        buf = bytearray(struct.calcsize(SERIAL_STRUCT_FMT))
        fcntl.ioctl(fd, TIOCGSERIAL, bytes(buf), True)
        fields = list(struct.unpack(SERIAL_STRUCT_FMT, bytes(buf)))
        fields[4] |= ASYNC_LOW_LATENCY          # serial_struct.flags
        fcntl.ioctl(fd, TIOCSSERIAL,
                    struct.pack(SERIAL_STRUCT_FMT, *fields), True)

    def set_low_latency(self):
        try:
            self.set_low_latency_fd(self.ser.fileno())
            return True
        except Exception as e:
            print(f"note: low-latency tty flag unavailable ({e})")
            return False

    def send_frame(self, frame):
        now = time.monotonic()
        gap = now - self._last
        if gap < self._min_gap:
            return
        if self.ser is None or not self.ser.is_open:
            return   # closed/unplugged — skip silently, keep audio running
        data = pack.pack_frame(frame)
        try:
            # write_timeout=1.0 makes write() block until the full frame is
            # in the OS buffer (no truncation). We deliberately do NOT call
            # flush(): flush() forces a drain-to-device round-trip and some
            # CH340/CP210x drivers block far longer than the real 16.7ms
            # transmit time, adding jitter.
            t_write = time.monotonic()
            written = self.ser.write(data)
            self.last_write_ms = (time.monotonic() - t_write) * 1000.0
            if written != len(data):
                print(f"WARN: serial write truncated ({written}/{len(data)} bytes)")
                return
            # Lock-step: hold until the ESP32 confirms show() completed.
            # read(1) returns as soon as ONE byte lands (poll granularity
            # 20ms); 0x00 idle-pings are skipped, anything else is flushed
            # wholesale. Deadline enforced by us, not by pyserial buffering.
            t_ack = time.monotonic()
            ack_ok = False
            while time.monotonic() - t_ack < self.ack_timeout:
                ack = self.ser.read(1)
                if not ack:
                    continue
                if ack == ACK_BYTE:
                    ack_ok = True
                    break
                if ack != b"\x00":
                    self.ser.reset_input_buffer()   # stray (diag text etc.)
                    break
            self.last_ack_ms = (time.monotonic() - t_ack) * 1000.0
            if ack_ok:
                self.acks_ok += 1
            else:
                self.ack_timeouts += 1
        except (serial.SerialException, OSError) as e:
            # USB unplug / port gone mid-playback: drop the link but keep the
            # visualizer thread (and audio) alive. Reconnect requires restart.
            print(f"WARN: serial write failed ({e}) — LED output disabled")
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            return
        self.frames_sent += 1
        self._last = now

    def close(self):
        if self.ser is not None and self.ser.is_open:
            self.ser.close()
