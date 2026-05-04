"""Unit tests for manual_crop — single-region rectangular crop."""
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
