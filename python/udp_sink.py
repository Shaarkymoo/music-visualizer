"""
UDP SINK — DORMANT. Not imported by default. This is the future broadcast path.

Same frame format as SerialSink (via pack.pack_frame). When enabled, the ESP32
must be running with ENABLE_UDP defined in firmware. See spec §4.
"""

import socket
import time
import pack


class UdpSink:
    def __init__(self, host, port, max_fps=40):
        self.host = host
        self.port = port
        self.max_fps = max_fps
        self._min_gap = 1.0 / max_fps
        self._last = 0.0
        self.sock = None

    @property
    def is_open(self):
        return self.sock is not None

    def open(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_frame(self, frame):
        now = time.monotonic()
        if now - self._last < self._min_gap:
            return
        data = pack.pack_frame(frame)
        self.sock.sendto(data, (self.host, self.port))
        self._last = now

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
