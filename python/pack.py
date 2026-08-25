import numpy as np
import settings as S

MAGIC = S.MAGIC
FRAME_LEN = S.FRAME_LEN      # 1536 payload bytes
NUM_LEDS = S.NUM_LEDS
GRID_COLS = S.GRID_COLS
GRID_ROWS = S.GRID_ROWS

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

# Values live in settings.py (single source of truth — see
# docs/superpowers/plans/2026-08-25-headless-rewrite.md).

CHUNK_BOARD_POS = S.CHUNK_BOARD_POS
ALL_BOARDS_ROTATED_180 = S.ALL_BOARDS_ROTATED_180

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
REMAP_IDX = np.asarray(REMAP)   # fancy-index view for the numpy pack path

_seq = 0


def reset_seq():
    """Force the NEXT frame to carry seq=0 — the firmware's host-restart
    resync token (protocol: seq==0 is always accepted, expected becomes 1).

    Call after any stall that may have dropped >8 consecutive frames on the
    wire: without it, a single such gap permanently locks the SEQ gate
    (every later frame is 'stale') until the u16 counter wraps by itself.
    """
    global _seq
    _seq = 0


def pack_frame(frame):
    """frame: 16x32 array-like of (r, g, b) per pixel. Returns 1542-byte packet.

    Array-native path (numpy): REMAP as fancy indexing on the flattened
    (512, 3) array, channel axis reordered to GRB, one .tobytes() —
    byte-identical to the old scalar loop (guarded by test_pack.py).
    """
    global _seq
    arr = np.asarray(frame, dtype=np.uint8).reshape(NUM_LEDS, 3)
    grb = arr[REMAP_IDX][:, [1, 0, 2]]          # remap physical order, then R/G/B -> G/R/B
    payload = grb.tobytes()
    seq = _seq
    _seq = (_seq + 1) % 65536
    header = MAGIC + FRAME_LEN.to_bytes(2, "little") + seq.to_bytes(2, "little")
    return header + payload