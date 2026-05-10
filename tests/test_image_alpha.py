"""Unit tests for imageAlpha — algorithm correctness and folder workflow."""
import sys
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


# ---------- trim_transparent_edges (helper) ----------

def test_trim_bbox_finds_opaque_region():
    # 10x10 fully transparent canvas with a 2x2 opaque block at (3,4)..(4,5)
    arr = np.zeros((10, 10, 4), dtype=np.uint8)
    arr[4:6, 3:5, :] = [10, 20, 30, 255]
    bbox = imageAlpha.trim_transparent_edges(arr)
    assert bbox == (3, 4, 5, 6)  # (left, top, right, bottom), exclusive


def test_trim_bbox_returns_none_when_all_transparent():
    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    assert imageAlpha.trim_transparent_edges(arr) is None


def test_trim_bbox_padding_clamped_to_image():
    arr = np.zeros((6, 6, 4), dtype=np.uint8)
    arr[2:4, 2:4, :] = [10, 20, 30, 255]
    # padding=1 should give (1, 1, 5, 5)
    assert imageAlpha.trim_transparent_edges(arr, padding=1) == (1, 1, 5, 5)
    # padding=10 (huge) should clamp to image bounds
    assert imageAlpha.trim_transparent_edges(arr, padding=10) == (0, 0, 6, 6)


def test_trim_bbox_alpha_threshold():
    arr = np.zeros((6, 6, 4), dtype=np.uint8)
    arr[2, 2, :] = [10, 20, 30, 50]   # semi-transparent
    arr[3, 3, :] = [10, 20, 30, 200]  # more opaque
    # threshold=0: both pixels qualify → bbox covers (2,2)..(3,3)
    assert imageAlpha.trim_transparent_edges(arr, alpha_threshold=0) == (2, 2, 4, 4)
    # threshold=100: only the 200-alpha pixel qualifies
    assert imageAlpha.trim_transparent_edges(arr, alpha_threshold=100) == (3, 3, 4, 4)


# ---------- remove_color with auto_trim ----------

def test_auto_trim_crops_transparent_edges(tmp_path):
    """An image with a small opaque region surrounded by background → output is cropped."""
    arr = _solid((255, 37, 255), (12, 12))  # all magenta background
    arr[4:7, 5:8] = [50, 200, 100, 255]  # 3x3 opaque block in the middle
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0,
                            auto_trim=True, trim_padding=0)
    out = np.array(Image.open(out_p))
    # Cropped to the 3x3 opaque region
    assert out.shape == (3, 3, 4)
    assert (out[..., 3] == 255).all()
    assert (out[..., :3] == [50, 200, 100]).all()


def test_auto_trim_with_padding(tmp_path):
    arr = _solid((255, 37, 255), (12, 12))
    arr[4:7, 5:8] = [50, 200, 100, 255]
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0,
                            auto_trim=True, trim_padding=1)
    out = np.array(Image.open(out_p))
    # 3x3 opaque + 1px padding on each side = 5x5
    assert out.shape == (5, 5, 4)
    # The padding ring is transparent (was magenta → alpha=0)
    assert out[0, 0, 3] == 0
    # Original opaque block sits at (1,1)..(3,3)
    assert (out[1:4, 1:4, 3] == 255).all()


def test_auto_trim_skipped_when_all_transparent(tmp_path, caplog):
    """All-transparent result should keep original dimensions and emit a warning."""
    arr = _solid((255, 37, 255), (8, 8))  # entirely background → fully transparent after removal
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    with caplog.at_level("WARNING"):
        imageAlpha.remove_color(str(in_p), str(out_p),
                                target_color=(255, 37, 255), tolerance=10,
                                feather=0, decontaminate=False, edge_erosion=0,
                                auto_trim=True, trim_padding=0)

    out = np.array(Image.open(out_p))
    assert out.shape == (8, 8, 4)  # not cropped
    assert (out[..., 3] == 0).all()
    assert any("자동 트림 스킵" in r.message for r in caplog.records)


def test_auto_trim_off_keeps_full_dimensions(tmp_path):
    arr = _solid((255, 37, 255), (8, 8))
    arr[3:5, 3:5] = [50, 200, 100, 255]
    in_p, out_p = tmp_path / "in.png", tmp_path / "out.png"
    _save(arr, in_p)

    imageAlpha.remove_color(str(in_p), str(out_p),
                            target_color=(255, 37, 255), tolerance=10,
                            feather=0, decontaminate=False, edge_erosion=0,
                            auto_trim=False)
    out = np.array(Image.open(out_p))
    assert out.shape == (8, 8, 4)  # original size preserved


# ---------- process_folder with auto_trim ----------

def test_process_folder_propagates_auto_trim(tmp_path):
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    arr = _solid((255, 37, 255), (10, 10))
    arr[4:6, 4:6] = [50, 200, 100, 255]
    _save(arr, in_dir / "a.png")

    imageAlpha.process_folder(
        str(in_dir), str(out_dir),
        target_color=(255, 37, 255), tolerance=10,
        auto_trim=True, trim_padding=0,
        max_workers=1,
    )
    out = np.array(Image.open(out_dir / "a.png"))
    assert out.shape == (2, 2, 4)  # cropped to the 2x2 opaque region


def test_process_folder_propagates_trim_alpha_threshold(tmp_path):
    """배치 API 가 trim_alpha_threshold 를 remove_color 까지 전달하는지 회귀 방지.

    같은 입력에 대해 threshold=0 vs threshold=100 이 서로 다른 bbox 를 만들어야
    한다 — 즉 process_folder 가 인자를 단순 무시하지 않는다는 증거. 이전에는
    process_folder 시그니처에 매개변수가 없어서 항상 default 0 으로 고정됐다.
    """
    in_dir = tmp_path / "in"
    in_dir.mkdir()

    # 10x10 magenta 배경에 두 개의 부분 투명 픽셀을 직접 박는다.
    # remove_color 는 magenta 픽셀의 alpha 만 0 으로 만들고, 색상이 다른
    # 두 픽셀은 alpha 를 그대로 유지한다 → trim_alpha_threshold 만이
    # bbox 크기를 갈라놓는 변수가 된다.
    arr = _solid((255, 37, 255), (10, 10))
    arr[3, 3] = [50, 200, 100, 50]    # alpha=50 (낮음)
    arr[7, 7] = [50, 200, 100, 200]   # alpha=200 (높음)
    _save(arr, in_dir / "a.png")

    out_low = tmp_path / "out_low"
    out_high = tmp_path / "out_high"

    imageAlpha.process_folder(
        str(in_dir), str(out_low),
        target_color=(255, 37, 255), tolerance=10,
        feather=0, decontaminate=False, edge_erosion=0,
        auto_trim=True, trim_padding=0, trim_alpha_threshold=0,
        max_workers=1,
    )
    imageAlpha.process_folder(
        str(in_dir), str(out_high),
        target_color=(255, 37, 255), tolerance=10,
        feather=0, decontaminate=False, edge_erosion=0,
        auto_trim=True, trim_padding=0, trim_alpha_threshold=100,
        max_workers=1,
    )

    low = np.array(Image.open(out_low / "a.png"))
    high = np.array(Image.open(out_high / "a.png"))

    # threshold=0: 두 픽셀 모두 bbox 에 포함 → (3,3)..(7,7) inclusive → 5x5
    assert low.shape == (5, 5, 4)
    # threshold=100: alpha=50 픽셀 제외, alpha=200 픽셀만 → 1x1
    assert high.shape == (1, 1, 4)


# ---------- CLI --from-clipboard ----------

def test_cli_from_clipboard_stages_and_processes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "clipboard_utils.read_image_from_clipboard",
        lambda: Image.new("RGB", (8, 8), (255, 37, 255)),
    )
    monkeypatch.setattr(sys, "argv", ["chromapeel-cli", "--from-clipboard"])

    imageAlpha._run_cli()

    staged = list((tmp_path / "base").glob("clipboard_*.png"))
    assert len(staged) == 1
    processed = list((tmp_path / "alpha").glob("clipboard_*.png"))
    assert len(processed) == 1
    assert processed[0].name == staged[0].name
    out = np.array(Image.open(processed[0]))
    # Full magenta input → fully transparent after crop
    assert (out[..., 3] == 0).all()


def test_cli_from_clipboard_errors_when_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("clipboard_utils.read_image_from_clipboard", lambda: None)
    monkeypatch.setattr(sys, "argv", ["chromapeel-cli", "--from-clipboard"])

    with pytest.raises(SystemExit) as ei:
        imageAlpha._run_cli()
    assert ei.value.code != 0
    assert "클립보드" in capsys.readouterr().err


def test_cli_from_clipboard_handles_pil_exception(tmp_path, monkeypatch, capsys):
    """ImageGrab 예외도 traceback 없이 사용자 메시지로 종료 — 회귀 방지."""
    monkeypatch.chdir(tmp_path)

    def _raise():
        raise OSError("xclip not installed")
    import clipboard_utils
    monkeypatch.setattr(clipboard_utils.ImageGrab, "grabclipboard", _raise)
    monkeypatch.setattr(sys, "argv", ["chromapeel-cli", "--from-clipboard"])

    with pytest.raises(SystemExit) as ei:
        imageAlpha._run_cli()
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "클립보드 읽기 실패" in err
    assert "Traceback" not in err
