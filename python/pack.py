MAGIC = b"\xaa\xaa"
FRAME_LEN = 0x0600          # 1536 payload bytes
NUM_LEDS = 512
GRID_COLS = 32
GRID_ROWS = 16

# ============================================================
# PHYSICAL BOARD LAYOUT
#
# The wall is 32 cols x 16 rows = 8 physical 8x8 boards arranged
# in 4 board-columns x 2 board-rows. The LED chain feeds chunks of
# 64 LEDs; each chunk (0..7) drives one physical board.
#
# CHUNK_BOARD_POS[c] = (board_col, board_row) of the board that
# chunk c drives. Board-row 0 = top of wall, 1 = bottom.
# Board-col 0 = left, 3 = right.
#
# The firmware image is row-major over the 32x16 grid: chunk 0 =
# logical rows 0-1 (all 32 cols), chunk 1 = rows 2-3, etc. Because a
# board is only 8 wide, each chunk's 64 LEDs (2 full-width rows) get
# folded into the board: LED k -> local (row=k//8, col=k%8), and every
# board is mounted rotated 180 degrees, so local (lr,lc) appears at
# physical local (7-lr, 7-lc).
#
# CONFIRMED by the map test (2026-08-24):
#   - chunk 0 -> bottom-left board, rotated 180 (white dots at the
#     bottom-right corner going up; rows read R,G,B,Y,R,G,B,Y)
#   - chunk 4 -> lower-middle-right board, rotated 180 (same pattern,
#     C,M,O,P cycle)
#   - left half of the wall (chunks 0-3) renders the image's TOP rows;
#     right half (chunks 4-7) renders the BOTTOM rows.
#
# The remaining positions are filled from the chase test.
# ============================================================

CHUNK_BOARD_POS = [
    # chunk : (board_col, board_row)
    # CONFIRMED by chase test (2026-08-24): lighting order was
    # 5,1,6,2,7,3,8,4 with boards numbered 1-8 left-to-right,
    # top-to-bottom. board_row 0 = top, board_col 0 = left.
    (0, 1),   # 0 = board 5 = bottom-left
    (0, 0),   # 1 = board 1 = top-left
    (1, 1),   # 2 = board 6 = bottom-mid-left
    (1, 0),   # 3 = board 2 = top-mid-left
    (2, 1),   # 4 = board 7 = bottom-mid-right
    (2, 0),   # 5 = board 3 = top-mid-right
    (3, 1),   # 6 = board 8 = bottom-right
    (3, 0),   # 7 = board 4 = top-right
]

ALL_BOARDS_ROTATED_180 = True

# HARDWARE QUIRK (not a remap issue): physical LED 0 (chunk 0's first LED,
# the very first LED in the chain) has a stuck-green channel on this build.
# It shows yellow when sent red, and a faint green when dark. Board 5
# (bottom-left) is where this LED lives. Cosmetic; ignore in mapping.


def build_remap():
    """REMAP[physical_led] = logical_index.

    For each physical LED k (chain order), find the wall position it
    drives, then return the logical index of that wall position so the
    wall renders the logical image correctly.
    """
    remap = [0] * NUM_LEDS
    for c in range(8):
        bc, br = CHUNK_BOARD_POS[c]
        for o in range(64):
            k = c * 64 + o
            # local position within the 8x8 board, rotated 180 degrees
            lr, lc = o // 8, o % 8
            if ALL_BOARDS_ROTATED_180:
                lr, lc = 7 - lr, 7 - lc
            wr = br * 8 + lr
            wc = bc * 8 + lc
            remap[k] = wr * GRID_COLS + wc
    return remap


REMAP = build_remap()

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