"""Unit tests for imageAlpha — algorithm correctness and folder workflow."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import imageAlpha


def _solid(color, size=(8, 8)):
    h, w = size
    arr = np.full((h, w, 4), [*color, 255], dtype=np.uint8)
    return arr


def _save(arr, path):
    Image.fromarray(arr).save(path)


# ---------- detect_background_color ----------

def test_detect_background_solid_border():
    arr = _solid((255, 37, 255), (10, 10))
    arr[3:7, 3:7] = [50, 200, 100, 255]  # interior differs but border is uniform
    assert imageAlpha.detect_background_color(arr) == (255, 37, 255)


def test_detect_background_picks_mode_when_border_mixed():
    """A border with mostly white and a few magenta pixels should pick white."""
    arr = _solid((255, 255, 255), (10, 10))
    # Inject a few magenta pixels on the border (count is less than white)
    arr[0, 0:3] = [255, 0, 255, 255]
    assert imageAlpha.detect_background_color(arr) == (255, 255, 255)


def test_detect_background_accepts_float_input():
    arr = _solid((10, 20, 30), (6, 6)).astype(np.float32)
    assert imageAlpha.detect_background_color(arr) == (10, 20, 30)


# ---------- remove_color ----------

def test_target_color_becomes_transparent(tmp_path):
    arr = _solid((255, 37, 255), (8, 8))
    arr[3:5, 3:5] = [50, 200, 100, 255]
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0)
    out = np.array(Image.open(out_p))
    assert out[0, 0, 3] == 0  # background became transparent
    assert out[3, 3, 3] == 255  # foreground kept opaque
    assert tuple(out[3, 3, :3]) == (50, 200, 100)  # color preserved


def test_auto_detect_when_target_is_none(tmp_path):
    arr = _solid((10, 20, 30), (8, 8))
    arr[3:5, 3:5] = [200, 200, 200, 255]
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=None, tolerance=5,
                            feather=0, decontaminate=False, edge_erosion=0)
    out = np.array(Image.open(out_p))
    assert out[0, 0, 3] == 0  # auto-detected (10,20,30) → transparent


def test_feather_creates_partial_alpha(tmp_path):
    """A pixel whose distance is mid-feather should get an intermediate alpha."""
    arr = _solid((255, 37, 255), (4, 4))
    # Put one pixel at distance 50 from target (tolerance=10, feather=80
    # → m = (50-10)/80 = 0.5)
    arr[1, 1] = [205, 87, 205, 255]  # max channel diff = 50
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=80, decontaminate=False, edge_erosion=0)
    out = np.array(Image.open(out_p))
    # 0.5 * 255 = 127.5 → truncated to 127 by .astype(uint8)
    assert out[1, 1, 3] == 127


def test_edge_erosion_eats_into_opaque(tmp_path):
    """An opaque pixel adjacent to transparent area gets erased after one pass."""
    arr = _solid((255, 37, 255), (5, 5))
    arr[2, 2] = [50, 200, 100, 255]  # single opaque pixel surrounded by background
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    # Without erosion, the center pixel survives.
    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0)
    no_erosion = np.array(Image.open(out_p))
    assert no_erosion[2, 2, 3] == 255

    # With erosion=1, the center pixel is eaten.
    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=1)
    eroded = np.array(Image.open(out_p))
    assert eroded[2, 2, 3] == 0


# ---------- process_folder ----------

def test_process_folder_processes_all_pngs(tmp_path):
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    for name in ("a.png", "b.png"):
        _save(_solid((255, 37, 255)), in_dir / name)

    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        progress_callback=lambda i, n, ip, op, err: events.append((i, n, Path(ip).name, op is not None, err)),
    )
    assert (out_dir / "a.png").exists()
    assert (out_dir / "b.png").exists()
    # Default mode is parallel; completion order is non-deterministic.
    # Verify the set of events instead of strict order.
    assert {e[2] for e in events} == {"a.png", "b.png"}
    assert all(e[1] == 2 and e[3] is True and e[4] is None for e in events)
    assert sorted(e[0] for e in events) == [1, 2]


def test_process_folder_max_workers_one_preserves_order(tmp_path):
    """max_workers=1 falls back to sequential processing with deterministic callback order."""
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    for name in ("a.png", "b.png", "c.png"):
        _save(_solid((255, 37, 255)), in_dir / name)

    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        progress_callback=lambda i, n, ip, op, err: events.append((i, Path(ip).name)),
        max_workers=1,
    )
    assert events == [(1, "a.png"), (2, "b.png"), (3, "c.png")]


def test_process_folder_parallel_correctness(tmp_path):
    """Many files in parallel: every input produces an output and a success callback."""
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    names = [f"f{i:02d}.png" for i in range(8)]
    for name in names:
        _save(_solid((255, 37, 255)), in_dir / name)

    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        progress_callback=lambda i, n, ip, op, err: events.append((i, n, Path(ip).name, op is not None, err)),
        # Force >1 workers even when cpu_count is low (e.g. CI runners).
        max_workers=4,
    )
    # Every file produced an output
    for name in names:
        assert (out_dir / name).exists()
    # Every file emitted exactly one success event
    assert {e[2] for e in events} == set(names)
    assert all(e[1] == len(names) and e[3] is True and e[4] is None for e in events)
    # Indices cover 1..len(names) exactly
    assert sorted(e[0] for e in events) == list(range(1, len(names) + 1))


def test_process_folder_continues_on_per_file_failure(tmp_path):
    """A corrupt file fails its own callback but the next file still runs."""
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    # Valid file
    _save(_solid((255, 37, 255)), in_dir / "good.png")
    # Bogus file with .png extension
    (in_dir / "bad.png").write_bytes(b"this is not a png")

    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        progress_callback=lambda *args: events.append(args),
    )

    # Both files reported, bad with error, good with success
    assert len(events) == 2
    by_name = {Path(e[2]).name: e for e in events}
    assert by_name["bad.png"][3] is None       # out_path None on failure
    assert by_name["bad.png"][4] is not None   # error set
    assert by_name["good.png"][3] is not None  # out_path set on success
    assert by_name["good.png"][4] is None      # no error
    assert (out_dir / "good.png").exists()


def test_process_folder_missing_input_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        imageAlpha.process_folder(
            str(tmp_path / "does_not_exist"),
            str(tmp_path / "out"),
            target_color=(0, 0, 0),
        )


def test_process_folder_empty_input_is_noop(tmp_path):
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    events = []
    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(0, 0, 0),
        progress_callback=lambda *args: events.append(args),
    )
    assert events == []
    assert out_dir.is_dir()  # still created
