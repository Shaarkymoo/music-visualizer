"""Tests for headless.py right-click input handling (files/folders/shuffle)."""
import os
import pytest
import headless


@pytest.fixture
def lib(tmp_path):
    """A tiny fake library: folder with two tracks + one stray file."""
    d = tmp_path / "lib"
    d.mkdir()
    (d / "a.mp3").write_bytes(b"\x00")
    (d / "b.flac").write_bytes(b"\x00")
    (tmp_path / "single.ogg").write_bytes(b"\x00")
    (tmp_path / "notes.txt").write_text("not audio")
    return tmp_path


def test_single_file_kept_in_order(lib):
    sel = [str(lib / "single.ogg")]
    playlist, had_dir = headless.collect_files(sel)
    assert playlist == [os.path.abspath(str(lib / "single.ogg"))]
    assert had_dir is False


def test_folder_expands_and_flags_shuffle(lib):
    playlist, had_dir = headless.collect_files([str(lib / "lib")])
    names = [os.path.basename(p) for p in playlist]
    assert sorted(names) == ["a.mp3", "b.flac"]
    assert had_dir is True


def test_non_audio_selection_ignored(lib):
    playlist, _ = headless.collect_files([str(lib / "notes.txt")])
    assert playlist == []


def test_mixed_selection_dedupes_and_sorts(lib):
    # same file passed twice via different spellings
    f = str(lib / "single.ogg")
    playlist, had_dir = headless.collect_files([f, os.path.abspath(f)])
    assert len(playlist) == 1
    assert had_dir is False


def test_missing_paths_ignored_gracefully(lib):
    playlist, had_dir = headless.collect_files(
        ["/does/not/exist.mp3", str(lib / "single.ogg")])
    assert len(playlist) == 1
    assert had_dir is False


def test_empty_selections(lib):
    assert headless.collect_files([]) == ([], False)
