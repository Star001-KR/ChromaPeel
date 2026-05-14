"""Unit tests for grid_split — both modes, edge cases, naming, and CLI."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import grid_split


def _make_input(tmp_path, w, h, color=(120, 80, 200, 255), name="image"):
    p = tmp_path / f"{name}.png"
    Image.new("RGBA", (w, h), color).save(p, "PNG")
    return p


# ---------- Mode A: rows × cols ----------

def test_mode_a_evenly_divisible(tmp_path):
    in_p = _make_input(tmp_path, 100, 100)
    out_dir = tmp_path / "out"

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), rows=2, cols=2,
    )

    assert result["rows"] == 2
    assert result["cols"] == 2
    assert result["cell_w"] == 50
    assert result["cell_h"] == 50
    assert result["clipped"] == (0, 0)
    assert len(result["files"]) == 4

    names = {f.name for f in out_dir.glob("*.png")}
    assert names == {
        "image_r0c0.png", "image_r0c1.png",
        "image_r1c0.png", "image_r1c1.png",
    }
    for f in result["files"]:
        assert Image.open(f).size == (50, 50)


def test_mode_a_with_clipping(tmp_path):
    in_p = _make_input(tmp_path, 105, 103)
    out_dir = tmp_path / "out"

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), rows=2, cols=2,
    )

    assert result["cell_w"] == 52   # 105 // 2
    assert result["cell_h"] == 51   # 103 // 2
    assert result["clipped"] == (1, 1)
    assert len(result["files"]) == 4
    for f in result["files"]:
        assert Image.open(f).size == (52, 51)


# ---------- Mode B: cell w × h ----------

def test_mode_b_evenly_divisible(tmp_path):
    in_p = _make_input(tmp_path, 100, 100)
    out_dir = tmp_path / "out"

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), cell_w=50, cell_h=50,
    )

    assert result["rows"] == 2
    assert result["cols"] == 2
    assert result["cell_w"] == 50
    assert result["cell_h"] == 50
    assert result["clipped"] == (0, 0)
    assert len(result["files"]) == 4


def test_mode_b_with_clipping(tmp_path):
    in_p = _make_input(tmp_path, 105, 100)
    out_dir = tmp_path / "out"

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), cell_w=50, cell_h=50,
    )

    assert result["rows"] == 2
    assert result["cols"] == 2
    assert result["cell_w"] == 50
    assert result["cell_h"] == 50
    assert result["clipped"] == (5, 0)
    assert len(result["files"]) == 4


# ---------- Edge shapes ----------

def test_one_by_one_grid_returns_full_image(tmp_path):
    in_p = _make_input(tmp_path, 40, 30)
    out_dir = tmp_path / "out"

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), rows=1, cols=1,
    )

    assert len(result["files"]) == 1
    assert result["cell_w"] == 40
    assert result["cell_h"] == 30
    assert result["clipped"] == (0, 0)
    assert Image.open(result["files"][0]).size == (40, 30)


def test_n_by_one_vertical_strips(tmp_path):
    in_p = _make_input(tmp_path, 40, 200)
    out_dir = tmp_path / "out"

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), rows=4, cols=1,
    )

    assert result["rows"] == 4
    assert result["cols"] == 1
    assert result["cell_w"] == 40
    assert result["cell_h"] == 50
    assert len(result["files"]) == 4
    for f in result["files"]:
        assert Image.open(f).size == (40, 50)


# ---------- Pixel preservation ----------

def test_rgba_alpha_is_preserved(tmp_path):
    in_p = tmp_path / "alpha.png"
    arr = np.zeros((10, 10, 4), dtype=np.uint8)
    arr[..., 0] = 200
    arr[..., 1] = 100
    arr[..., 2] = 50
    # Vary alpha by row so we can detect any silent flattening.
    for y in range(10):
        arr[y, :, 3] = y * 25
    Image.fromarray(arr).save(in_p, "PNG")

    out_dir = tmp_path / "out"
    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), rows=2, cols=2,
    )

    # Top-left cell should mirror arr[0:5, 0:5] exactly.
    cell = np.array(Image.open(result["files"][0]))
    assert cell.shape == (5, 5, 4)
    np.testing.assert_array_equal(cell, arr[0:5, 0:5])


def test_rgb_input_is_handled(tmp_path):
    in_p = tmp_path / "rgb.png"
    Image.new("RGB", (20, 20), (10, 20, 30)).save(in_p, "PNG")

    out_dir = tmp_path / "out"
    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), rows=2, cols=2,
    )

    assert len(result["files"]) == 4
    out = Image.open(result["files"][0])
    assert out.size == (10, 10)
    assert out.mode in ("RGB", "RGBA")
    arr = np.array(out)
    assert tuple(arr[0, 0, :3]) == (10, 20, 30)


# ---------- Filename zero-padding ----------

def test_filename_pad_single_digit(tmp_path):
    in_p = _make_input(tmp_path, 90, 90)
    out_dir = tmp_path / "out"

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), rows=9, cols=9,
    )

    names = {f.name for f in result["files"]}
    assert "image_r0c0.png" in names
    assert "image_r8c8.png" in names
    # Must NOT use 2-digit padding when max < 10.
    assert "image_r00c00.png" not in names


def test_filename_pad_two_digits(tmp_path):
    in_p = _make_input(tmp_path, 100, 100)
    out_dir = tmp_path / "out"

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), rows=10, cols=10,
    )

    names = {f.name for f in result["files"]}
    assert "image_r00c00.png" in names
    assert "image_r09c09.png" in names
    assert "image_r0c0.png" not in names


def test_filename_pad_three_digits(tmp_path):
    # Mode B with 200×2 image and 2×2 cells → cols=100, rows=1, pad=3.
    in_p = _make_input(tmp_path, 200, 2)
    out_dir = tmp_path / "out"

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), cell_w=2, cell_h=2,
    )

    assert result["rows"] == 1
    assert result["cols"] == 100
    names = {f.name for f in result["files"]}
    assert "image_r000c000.png" in names
    assert "image_r000c099.png" in names


# ---------- Argument validation ----------

@pytest.mark.parametrize("kwargs", [
    {"rows": 2},                                          # Mode A incomplete
    {"cols": 2},                                          # Mode A incomplete
    {"cell_w": 50},                                       # Mode B incomplete
    {"cell_h": 50},                                       # Mode B incomplete
    {"rows": 2, "cols": 2, "cell_w": 50, "cell_h": 50},   # Both modes
    {"rows": 2, "cell_w": 50},                            # Mixed partial
    {},                                                   # Neither
    {"rows": 0, "cols": 2},                               # Zero
    {"rows": 2, "cols": -1},                              # Negative
    {"cell_w": 0, "cell_h": 50},                          # Zero
    {"cell_w": 50, "cell_h": -10},                        # Negative
])
def test_invalid_args_raise_value_error(tmp_path, kwargs):
    in_p = _make_input(tmp_path, 100, 100)
    with pytest.raises(ValueError):
        grid_split.split_image_grid(str(in_p), str(tmp_path / "out"), **kwargs)


def test_mode_b_cell_larger_than_image_raises(tmp_path):
    in_p = _make_input(tmp_path, 50, 50)
    with pytest.raises(ValueError):
        grid_split.split_image_grid(
            str(in_p), str(tmp_path / "out"),
            cell_w=100, cell_h=100,
        )


# ---------- CLI ----------

def test_cli_mode_a_success(tmp_path, capsys):
    in_p = _make_input(tmp_path, 100, 100)
    out_root = tmp_path / "alpha"

    rc = grid_split._run_cli([
        str(in_p), "-o", str(out_root),
        "--rows", "2", "--cols", "2",
    ])

    assert rc == 0
    captured = capsys.readouterr()
    assert "완료: 4개 파일" in captured.out
    assert "격자: 2×2" in captured.out
    assert "셀: 50×50px" in captured.out
    assert "잔여: 0×0px" in captured.out
    # CLI nests output under {out_root}/{stem}_split/.
    assert (out_root / "image_split" / "image_r0c0.png").exists()


def test_cli_mixed_mode_args_exit_2(tmp_path):
    in_p = _make_input(tmp_path, 100, 100)
    with pytest.raises(SystemExit) as ei:
        grid_split._run_cli([
            str(in_p), "--rows", "2", "--cell-w", "50",
        ])
    assert ei.value.code == 2


def test_cli_subprocess_mode_b(tmp_path):
    in_p = _make_input(tmp_path, 60, 60)
    out_root = tmp_path / "alpha"
    repo_root = Path(__file__).resolve().parent.parent

    proc = subprocess.run(
        [sys.executable, "-m", "grid_split",
         str(in_p), "-o", str(out_root),
         "--cell-w", "30", "--cell-h", "30"],
        capture_output=True, text=True, cwd=str(repo_root),
    )

    assert proc.returncode == 0, proc.stderr
    assert "완료: 4개 파일" in proc.stdout
    assert (out_root / "image_split" / "image_r0c0.png").exists()
    assert (out_root / "image_split" / "image_r1c1.png").exists()


# ---------- CLI --from-clipboard ----------

def test_cli_from_clipboard_uses_clipboard_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "clipboard_utils.read_image_from_clipboard",
        lambda: Image.new("RGB", (100, 60), (255, 255, 255)),
    )

    rc = grid_split._run_cli([
        "--from-clipboard", "--rows", "2", "--cols", "2", "-o", "out",
    ])
    assert rc == 0

    staged = list((tmp_path / "base").glob("clipboard_*.png"))
    assert len(staged) == 1
    split_dirs = list((tmp_path / "out").glob("clipboard_*_split"))
    assert len(split_dirs) == 1
    cells = list(split_dirs[0].glob("*.png"))
    assert len(cells) == 4


def test_cli_requires_input_or_clipboard(tmp_path, capsys):
    with pytest.raises(SystemExit) as ei:
        grid_split._run_cli(["--rows", "2", "--cols", "2"])
    assert ei.value.code == 2


def test_cli_rejects_both_input_and_clipboard(tmp_path):
    in_p = _make_input(tmp_path, 100, 100)
    with pytest.raises(SystemExit) as ei:
        grid_split._run_cli([
            str(in_p), "--from-clipboard", "--rows", "2", "--cols", "2",
        ])
    assert ei.value.code == 2


def test_split_auto_numbers_when_cells_collide(tmp_path):
    """기존 셀 파일과 충돌 시 _01 자동 부여 (resolve_unique_path 공통 정책)."""
    in_p = _make_input(tmp_path, 100, 100)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # r0c0 만 미리 점유 → 그 셀만 _01 로 회피
    (out_dir / "image_r0c0.png").write_bytes(b"")

    result = grid_split.split_image_grid(
        str(in_p), str(out_dir), rows=2, cols=2,
    )
    saved = {f.name for f in result["files"]}
    assert "image_r0c0_01.png" in saved
    assert "image_r0c1.png" in saved
    assert "image_r1c0.png" in saved
    assert "image_r1c1.png" in saved


def test_cli_clipboard_pil_exception_exits_cleanly(tmp_path, monkeypatch, capsys):
    """ImageGrab.grabclipboard() 가 예외를 던지는 환경 (Linux wl-paste 미설치 등) 회귀.

    이전에는 CLI 가 traceback 을 그대로 노출했음. 지금은 stderr 메시지 + exit(1).
    """
    monkeypatch.chdir(tmp_path)

    def _raise():
        raise OSError("wl-paste not installed")
    import clipboard_utils
    monkeypatch.setattr(clipboard_utils.ImageGrab, "grabclipboard", _raise)

    with pytest.raises(SystemExit) as ei:
        grid_split._run_cli([
            "--from-clipboard", "--rows", "2", "--cols", "2", "-o", "out",
        ])
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "클립보드 읽기 실패" in err
    assert "Traceback" not in err
