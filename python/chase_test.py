"""
chase_test.py — Panel/chain chase test for determining the physical board order.

Sends RAW physical-LED frames over the USB serial link (bypassing pack.py's
REMAP on purpose — its job is to DISCOVER which physical board each chunk
drives, so the real REMAP can be encoded from the observations).

Each step lights ONE 64-LED chunk (one physical 8x8 board) solid white, with
the chunk's FIRST LED red as an orientation marker, for HOLD_SECONDS, then
moves to the next chunk.

Use: watch the wall and note, for each chunk number printed here, WHICH
physical board lights up (top-left, bottom-left, etc.) and where the red
marker sits (corner of the board).

Run:  cd python && ../.venv/bin/python chase_test.py
"""

import sys
import time
import settings
import serial_sink
import pack

HOLD_SECONDS = 3.0


def raw_pack_physical(phys_colors, seq):
    """phys_colors: list of 512 (r,g,b) in PHYSICAL chain order.
    seq: frame sequence number (must increment per frame — the firmware
    drops stale/out-of-order frames, so a constant seq would freeze the
    display after the first frame).
    Returns a full frame packet WITHOUT applying pack.REMAP — payload is
    sent in chain order as-is (GRB bytes)."""
    payload = bytearray()
    for (r, g, b) in phys_colors:
        payload += bytes((g, r, b))
    header = pack.MAGIC + pack.FRAME_LEN.to_bytes(2, "little") + (seq & 0xFFFF).to_bytes(2, "little")
    return header + bytes(payload)


def build_chunk_physical(chunk: int):
    """512 (r,g,b) in physical chain order; one 64-LED chunk lit white,
    first LED of the chunk red."""
    colors = [(0, 0, 0)] * pack.NUM_LEDS
    for i in range(64):
        k = chunk * 64 + i
        colors[k] = (255, 0, 0) if i == 0 else (255, 255, 255)
    return colors


def main():
    sink = serial_sink.SerialSink(
        port=settings.SERIAL_PORT,
        baud=settings.SERIAL_BAUD,
        max_fps=100,  # don't throttle the chase
    )
    try:
        sink.open()
        print(f"Serial connected: {getattr(sink.ser, 'port', '?')}")
    except Exception as e:
        print(f"Serial NOT connected: {e}")
        sys.exit(1)

    print("Chase test: lighting one 8x8 board at a time (raw chain order).")
    print("For each chunk, note WHICH physical board lights + where the RED")
    print("marker sits on that board.")
    try:
        seq = 0
        while True:
            for chunk in range(8):
                print(f"--- CHUNK {chunk} (LEDs {chunk*64}..{chunk*64+63}) ---",
                      flush=True)
                colors = build_chunk_physical(chunk)
                deadline = time.monotonic() + HOLD_SECONDS
                while time.monotonic() < deadline:
                    frame = raw_pack_physical(colors, seq)
                    seq = (seq + 1) & 0xFFFF
                    sink.ser.write(frame)
                    sink.ser.flush()
                    time.sleep(0.01)
            print("cycle complete — repeating")
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        sink.close()


if __name__ == "__main__":
    main()