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
    # one pixel (r,g,b) = (10, 20, 30) at logical index 0 (row 0, col 0)
    frame = [[(10, 20, 30)] + [(0, 0, 0)] * 31 for _ in range(16)]
    data = pack.pack_frame(frame)
    # GRB order: bytes[6]=G, bytes[7]=R, bytes[8]=B
    assert data[6] == 20, data[6]
    assert data[7] == 10, data[7]
    assert data[8] == 30, data[8]

def test_seq_increments():
    frame = [[(0, 0, 0)] * 32 for _ in range(16)]
    s1 = pack.pack_frame(frame)
    s2 = pack.pack_frame(frame)
    seq1 = int.from_bytes(s1[4:6], "little")
    seq2 = int.from_bytes(s2[4:6], "little")
    assert seq2 == (seq1 + 1) % 65536
