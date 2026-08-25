import pack

def test_header_magic_and_len():
    frame = [[(0, 0, 0)] * 32 for _ in range(16)]
    data = pack.pack_frame(frame)
    assert data[:2] == b"\xaa\xaa"
    assert data[2:4] == b"\x00\x06"   # LEN little-endian 0x0600

def test_payload_is_grb_1536():
    frame = [[(0, 0, 0)] * 32 for _ in range(16)]
    data = pack.pack_frame(frame)
    assert len(data) == 1542
    assert len(data[6:]) == 1536

def test_grb_reorder():
    # one pixel (r,g,b) = (10, 20, 30) at logical index 0 (row 0, col 0).
    # Find the physical LED that displays logical 0 via the remap.
    frame = [[(10, 20, 30)] + [(0, 0, 0)] * 31 for _ in range(16)]
    data = pack.pack_frame(frame)
    phys = pack.REMAP.index(0)
    # GRB order at that physical LED: bytes[6+p*3]=G, +1=R, +2=B
    assert data[6 + phys*3] == 20, (phys, data[6 + phys*3])
    assert data[6 + phys*3 + 1] == 10, (phys, data[6 + phys*3 + 1])
    assert data[6 + phys*3 + 2] == 30, (phys, data[6 + phys*3 + 2])

def test_seq_increments():
    frame = [[(0, 0, 0)] * 32 for _ in range(16)]
    s1 = pack.pack_frame(frame)
    s2 = pack.pack_frame(frame)
    seq1 = int.from_bytes(s1[4:6], "little")
    seq2 = int.from_bytes(s2[4:6], "little")
    assert seq2 == (seq1 + 1) % 65536

def test_remap_is_bijection():
    # Every physical LED maps to a unique logical index (permutation).
    assert sorted(pack.REMAP) == list(range(pack.NUM_LEDS))

def test_remap_roundtrip():
    # Deterministic logical frame. After packing, each physical LED k must
    # carry the color of the logical pixel at the wall position that k
    # drives (per CHUNK_BOARD_POS + 180-degree rotation). This locks the
    # physical model: the wall renders the logical image correctly.
    frame = [[((wr * 7 + wc) % 256, (wr + wc * 3) % 256, (wr * wc) % 256)
              for wc in range(pack.GRID_COLS)]
             for wr in range(pack.GRID_ROWS)]
    data = pack.pack_frame(frame)
    for k in range(pack.NUM_LEDS):
        g, r, b = data[6 + k*3], data[6 + k*3 + 1], data[6 + k*3 + 2]
        c, o = k // 64, k % 64
        bc, br = pack.CHUNK_BOARD_POS[c]
        lr, lc = o // 8, o % 8
        if pack.ALL_BOARDS_ROTATED_180:
            lr, lc = 7 - lr, 7 - lc
        wr, wc = br * 8 + lr, bc * 8 + lc
        assert (r, g, b) == frame[wr][wc], (k, (r, g, b), frame[wr][wc])

def test_chunk0_white_dots_go_up_from_bottom_right():
    # CONFIRMED by the map test: chunk 0 drives the bottom-left board
    # (br=1, bc=0), and the panel-marker white dots (logical row 0, cols
    # 0,8,16,24 = LEDs 0,8,16,24 in the un-remapped map test) appear on
    # that board going UP from its bottom-right corner — i.e. at wall
    # (15,7),(14,7),(13,7),(12,7). This locks the 180-degree rotation
    # model: local (0,0) -> physical local (7,7).
    bc, br = pack.CHUNK_BOARD_POS[0]
    assert (bc, br) == (0, 1)   # bottom-left
    for i, led in enumerate([0, 8, 16, 24]):
        o = led % 64
        lr, lc = 7 - (o // 8), 7 - (o % 8)
        wr, wc = br * 8 + lr, bc * 8 + lc
        assert (wr, wc) == (15 - i, 7), (i, (wr, wc))
    # Sanity: physical LED 0 (chain order) drives wall (15,7) = bottom-right
    # of the bottom-left board, i.e. it displays logical index 15*32+7.
    assert pack.REMAP[0] == 15 * 32 + 7
def test_reset_seq_forces_host_restart():
    import pack
    pack._seq = 5000                      # arbitrary mid-stream position
    pack.pack_frame([[ (0,0,0) ]*pack.GRID_COLS for _ in range(pack.GRID_ROWS)])  # seq 5000 -> 5001
    pack.reset_seq()
    d1 = pack.pack_frame([[ (0,0,0) ]*pack.GRID_COLS for _ in range(pack.GRID_ROWS)])
    s1 = int.from_bytes(d1[4:6], "little")
    assert s1 == 0                        # restart token on the wire
    d2 = pack.pack_frame([[ (0,0,0) ]*pack.GRID_COLS for _ in range(pack.GRID_ROWS)])
    s2 = int.from_bytes(d2[4:6], "little")
    assert s2 == 1                        # continues normally after resync

def _scalar_reference_pack(frame):
    """Byte-exact transcription of the pre-vectorization pack_frame
    (v1-working..b192b92 era) — guards the numpy rewrite against drift."""
    flat = []
    for row in range(pack.GRID_ROWS):
        for col in range(pack.GRID_COLS):
            r, g, b = frame[row][col]
            flat.append((r, g, b))
    remapped = [flat[pack.REMAP[i]] for i in range(pack.NUM_LEDS)]
    payload = bytearray()
    for (r, g, b) in remapped:
        payload += bytes((g, r, b))
    header = pack.MAGIC + pack.FRAME_LEN.to_bytes(2, "little") + b"\x00\x00"
    return bytes(header) + bytes(payload)   # seq zeroed for comparison


def test_vectorized_pack_matches_scalar_reference():
    import numpy as np
    rng = np.random.default_rng(123)
    arr = rng.integers(0, 256, size=(pack.GRID_ROWS, pack.GRID_COLS, 3), dtype=np.uint8)
    frame_list = [[tuple(int(c) for c in arr[r, c]) for c in range(pack.GRID_COLS)]
                  for r in range(pack.GRID_ROWS)]
    got = pack.pack_frame(frame_list)
    ref = _scalar_reference_pack(frame_list)
    assert len(got) == 1542
    # byte-identical except the SEQ field ([4:6]), which is pack_frame's
    # live counter — compare magic+LEN and the full GRB payload
    assert got[:4] == ref[:4]
    assert got[6:] == ref[6:]
