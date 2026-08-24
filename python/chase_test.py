"""
chase_test.py — Panel/chain chase test for determining the physical board order.

Sends frames over the USB serial link (through the REAL pack.py + serial_sink.py
pipeline). Each step lights ONE 64-LED chunk (one physical 8x8 board) solid
white, with the chunk's FIRST LED red as an orientation marker, for
HOLD_SECONDS, then moves to the next chunk.

Use: watch the wall and note, for each chunk number printed here, WHICH
physical board lights up (top-left, bottom-left, etc.) and where the red
marker sits (corner of the board).

Run:  cd python && ../.venv/bin/python chase_test.py
"""

import sys
import time
import config
import serial_sink
import pack

HOLD_SECONDS = 3.0


def build_chunk_frame(chunk: int):
    """Frame with one 64-LED chunk lit: white, first LED of chunk = red."""
    frame = [[(0, 0, 0)] * pack.GRID_COLS for _ in range(pack.GRID_ROWS)]
    for i in range(64):
        row = chunk // 4  # chunk index -> block row (2 rows of 4 chunks)
        col = chunk % 4
        y = row * 8 + (i // 8)
        x = col * 8 + (i % 8)
        frame[y][x] = (255, 0, 0) if i == 0 else (255, 255, 255)
    return frame


def main():
    sink = serial_sink.SerialSink(
        port=config.SERIAL_PORT,
        baud=config.SERIAL_BAUD,
        max_fps=100,  # don't throttle the chase
    )
    try:
        sink.open()
        print(f"Serial connected: {getattr(sink.ser, 'port', '?')}")
    except Exception as e:
        print(f"Serial NOT connected: {e}")
        sys.exit(1)

    print("Chase test: lighting one 8x8 board at a time (chain order).")
    print("For each chunk, note WHICH physical board lights + where the RED")
    print("marker sits on that board.")
    try:
        while True:
            for chunk in range(8):
                print(f"--- CHUNK {chunk} (LEDs {chunk*64}..{chunk*64+63}) ---",
                      flush=True)
                frame = build_chunk_frame(chunk)
                deadline = time.monotonic() + HOLD_SECONDS
                while time.monotonic() < deadline:
                    sink.send_frame(frame)
                    time.sleep(0.01)
            print("cycle complete — repeating")
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        sink.close()


if __name__ == "__main__":
    main()