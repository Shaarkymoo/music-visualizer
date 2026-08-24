MAGIC = b"\xaa\xaa"
FRAME_LEN = 0x0600          # 1536 payload bytes
NUM_LEDS = 512
GRID_COLS = 32
GRID_ROWS = 16

# Logical (row-major) index -> physical LED index.
# Identity for now; replace with real values from the panel-mapping test.
REMAP = list(range(NUM_LEDS))

_seq = 0


def pack_frame(frame):
    """frame: 16x32 list-of-lists of (r, g, b) tuples. Returns 1542-byte packet."""
    global _seq
    flat = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            r, g, b = frame[row][col]
            flat.append((r, g, b))
    # apply physical remap
    remapped = [flat[REMAP[i]] for i in range(NUM_LEDS)]
    # build GRB payload
    payload = bytearray()
    for (r, g, b) in remapped:
        payload += bytes((g, r, b))
    seq = _seq
    _seq = (_seq + 1) % 65536
    header = MAGIC + FRAME_LEN.to_bytes(2, "little") + seq.to_bytes(2, "little")
    return header + bytes(payload)
