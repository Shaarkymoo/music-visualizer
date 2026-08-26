#!/usr/bin/env python3
"""Set ASYNC_LOW_LATENCY on a serial tty (run with sudo).

Cuts the CP2102's small-packet RX buffering from ~16ms to ~1ms, which
directly speeds up the render-ACK round trip in the visualizer.

Usage:  sudo .venv/bin/python tools/set_low_latency.py [DEVICE]
        (default device: /dev/ttyUSB0)

The flag lives in the kernel's port structure: it persists across opens
but resets when the device is unplugged or the machine reboots — re-run
after reconnecting the board. For permanence, add a udev rule:

    ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", \
        ATTRS{idProduct}=="ea60", RUN+="/usr/bin/setserial %p low_latency"
"""
import fcntl
import struct
import sys

ASYNC_LOW_LATENCY = 0x2000
TIOCGSERIAL = 0x541E
TIOCSSERIAL = 0x541F
SERIAL_STRUCT_FMT = "=i i I i i i i i H c x H H 8x Q H I Q"


def main():
    dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    fd = open(dev)
    buf = bytearray(struct.calcsize(SERIAL_STRUCT_FMT))
    fcntl.ioctl(fd.fileno(), TIOCGSERIAL, bytes(buf), True)
    fields = list(struct.unpack(SERIAL_STRUCT_FMT, bytes(buf)))
    before = fields[4]
    fields[4] |= ASYNC_LOW_LATENCY
    fcntl.ioctl(fd.fileno(), TIOCSSERIAL,
                struct.pack(SERIAL_STRUCT_FMT, *fields), True)
    print(f"{dev}: flags {before:#x} -> {fields[4]:#x} (low_latency set)")


if __name__ == "__main__":
    main()
