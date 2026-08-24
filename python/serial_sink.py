import time
import serial
import serial.tools.list_ports
import pack


class SerialSink:
    def __init__(self, port=None, baud=115200, max_fps=40):
        self.port = port
        self.baud = baud
        self.max_fps = max_fps
        self._min_gap = 1.0 / max_fps
        self._last = 0.0
        self.ser = None

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
        self.ser = serial.Serial(port, self.baud, timeout=0)

    def send_frame(self, frame):
        now = time.monotonic()
        gap = now - self._last
        if gap < self._min_gap:
            return
        data = pack.pack_frame(frame)
        self.ser.write(data)
        self.ser.flush()
        self._last = now

    def close(self):
        if self.ser is not None and self.ser.is_open:
            self.ser.close()
