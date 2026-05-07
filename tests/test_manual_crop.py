"""Unit tests for manual_crop — single-region rectangular crop."""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import manual_crop


def _save_solid(path: Path, size=(100, 100), color=(123, 200, 50)) -> None:
    h, w = size
    arr = np.full((h, w, 4), [*color, 255], dtype=np.uint8)
    Image.fromarray(arr).save(path)


def test_basic_crop_produces_expected_size(tmp_path):
    src = tmp_path / "pic.png"
    _save_solid(src, size=(100, 100))

    out = manual_crop.crop_image(str(src), 10, 10, 50, 50, out_dir=str(tmp_path / "alpha"))

    assert out.exists()
    assert out == tmp_path / "alpha" / "pic_crop.png"
    img = Image.open(out)
    assert img.size == (50, 50)


def test_clamps_when_region_overflows_right_bottom(tmp_path):
    src = tmp_path / "pic.png"
    _save_solid(src, size=(100, 100))

    out = manual_crop.crop_image(str(src), 80, 80, 50, 50, out_dir=str(tmp_path / "alpha"))

    img = Image.open(out)
    assert img.size == (20, 20)


def test_clamps_negative_coordinates(tmp_path):
    src = tmp_path / "pic.png"
    _save_solid(src, size=(100, 100))

    out = manual_crop.crop_image(str(src), -10, -10, 50, 50, out_dir=str(tmp_path / "alpha"))

    img = Image.open(out)
    assert img.size == (40, 40)


def test_zero_width_raises(tmp_path):
    src = tmp_path / "pic.png"
    _save_solid(src, size=(100, 100))

    with pytest.raises(ValueError, match="positive"):
        manual_crop.crop_image(str(src), 0, 0, 0, 50, out_dir=str(tmp_path / "alpha"))


def test_negative_height_raises(tmp_path):
    src = tmp_path / "pic.png"
    _save_solid(src, size=(100, 100))

    with pytest.raises(ValueError, match="positive"):
        manual_crop.crop_image(str(src), 0, 0, 50, -5, out_dir=str(tmp_path / "alpha"))


def test_region_entirely_outside_raises_after_clamp(tmp_path):
    src = tmp_path / "pic.png"
    _save_solid(src, size=(100, 100))

    with pytest.raises(ValueError, match="positive"):
        manual_crop.crop_image(str(src), 200, 200, 50, 50, out_dir=str(tmp_path / "alpha"))


def test_output_filename_uses_stem_with_crop_suffix(tmp_path):
    src = tmp_path / "my-image.001.png"
    _save_solid(src, size=(60, 60))

    out = manual_crop.crop_image(str(src), 5, 5, 20, 20, out_dir=str(tmp_path / "alpha"))

    assert out.name == "my-image.001_crop.png"


def test_out_dir_is_created_if_missing(tmp_path):
    src = tmp_path / "pic.png"
    _save_solid(src, size=(50, 50))
    target = tmp_path / "deep" / "nested" / "out"
    assert not target.exists()

    out = manual_crop.crop_image(str(src), 0, 0, 10, 10, out_dir=str(target))

    assert target.is_dir()
    assert out.exists()


# ---------- CLI --from-clipboard ----------

def test_cli_from_clipboard_crops(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "clipboard_utils.read_image_from_clipboard",
        lambda: Image.new("RGB", (50, 50), (200, 100, 50)),
    )
    out_dir = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", [
        "chromapeel-crop", "--from-clipboard",
        "--crop", "5,5,20,20",
        "--out-dir", str(out_dir),
    ])

    manual_crop._run_cli()

    cropped = list(out_dir.glob("clipboard_*_crop.png"))
    assert len(cropped) == 1
    img = Image.open(cropped[0])
    assert img.size == (20, 20)


def test_cli_requires_input_or_clipboard(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["chromapeel-crop", "--crop", "0,0,10,10"])
    with pytest.raises(SystemExit) as ei:
        manual_crop._run_cli()
    assert ei.value.code == 2


def test_cli_clipboard_pil_exception_exits_cleanly(tmp_path, monkeypatch, capsys):
    """ImageGrab 예외 시 traceback 이 아닌 사용자 메시지 + exit(1) — 회귀 방지."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "chromapeel-crop", "--from-clipboard", "--crop", "0,0,10,10",
    ])

    def _raise():
        raise OSError("xclip not installed")
    import clipboard_utils
    monkeypatch.setattr(clipboard_utils.ImageGrab, "grabclipboard", _raise)

    with pytest.raises(SystemExit) as ei:
        manual_crop._run_cli()
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "클립보드 읽기 실패" in err
    assert "Traceback" not in err
