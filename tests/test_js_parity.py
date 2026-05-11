"""Verify the web JS port of the algorithm matches Python byte-for-byte.

Skipped automatically if `node` is not installed.
"""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import imageAlpha

JS_RUNNER = Path(__file__).parent / "js_parity_runner.mjs"


def _build_test_image(w=36, h=24):
    """Background, a solid interior block, and a magenta-ramped antialiased edge."""
    arr = np.full((h, w, 4), [255, 37, 255, 255], dtype=np.uint8)
    arr[6:18, 8:28] = [200, 100, 50, 255]
    for x in range(28, 32):
        t = (x - 27) / 5.0
        arr[6:18, x, 0] = int(200 * (1 - t) + 255 * t)
        arr[6:18, x, 1] = int(100 * (1 - t) + 37 * t)
        arr[6:18, x, 2] = int(50 * (1 - t) + 255 * t)
    return arr


def _build_multi_color_test_image(w=36, h=24):
    """Two-color background (magenta + cyan) with an orange foreground block.

    Foreground 의 우측 엣지에는 magenta 와 섞이는 antialias ramp 가 들어가 있어,
    decontaminate 가 pixel 별 nearest target color 로 동작하는지를 검증한다.
    """
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 3] = 255
    arr[:h // 2, :, :3] = [255, 37, 255]   # 상단: magenta
    arr[h // 2:, :, :3] = [50, 200, 200]   # 하단: cyan
    arr[6:18, 8:28, :3] = [200, 100, 50]   # 전경: orange
    for x in range(28, 32):
        t = (x - 27) / 5.0
        arr[6:18, x, 0] = int(200 * (1 - t) + 255 * t)
        arr[6:18, x, 1] = int(100 * (1 - t) + 37 * t)
        arr[6:18, x, 2] = int(50 * (1 - t) + 255 * t)
    return arr


def _run_js_parity(tmp_path, arr, params, meta_extra):
    """Python 으로 처리한 결과와 JS 결과가 byte-for-byte 일치하는지 확인하는 헬퍼."""
    h, w = arr.shape[:2]

    in_png = tmp_path / "in.png"
    Image.fromarray(arr).save(in_png)
    arr.tofile(tmp_path / "in.rgba")

    py_out = tmp_path / "py.png"
    imageAlpha.remove_color(str(in_png), str(py_out), **params)
    py_arr = np.array(Image.open(py_out))
    py_arr.tofile(tmp_path / "py.rgba")
    py_h, py_w = py_arr.shape[:2]

    meta = {"w": w, "h": h, **params, **meta_extra}
    (tmp_path / "meta.json").write_text(json.dumps(meta))

    result = subprocess.run(
        ["node", str(JS_RUNNER), str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"node runner failed: {result.stderr}"

    js_meta = json.loads((tmp_path / "js_meta.json").read_text())
    assert (js_meta["w"], js_meta["h"]) == (py_w, py_h), (
        f"output dimensions diverge: py={py_w}x{py_h}, js={js_meta['w']}x{js_meta['h']}"
    )

    py = (tmp_path / "py.rgba").read_bytes()
    js = (tmp_path / "js.rgba").read_bytes()
    assert len(py) == len(js)
    assert py == js, "JS algorithm output diverges from Python reference"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
@pytest.mark.parametrize("auto_trim,trim_padding", [
    (False, 0),
    (True, 0),
    (True, 2),
])
def test_js_matches_python(tmp_path, auto_trim, trim_padding):
    arr = _build_test_image()
    params = dict(target_color=(255, 37, 255), tolerance=20, feather=100,
                  decontaminate=True, edge_erosion=1,
                  auto_trim=auto_trim, trim_padding=trim_padding)
    _run_js_parity(
        tmp_path, arr, params,
        meta_extra={"target_color": list(params["target_color"])},
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
@pytest.mark.parametrize("auto_trim,trim_padding", [
    (False, 0),
    (True, 2),
])
def test_js_matches_python_multi_color(tmp_path, auto_trim, trim_padding):
    """다색 target_colors 경로가 Python 과 byte-for-byte 일치하는지 확인."""
    arr = _build_multi_color_test_image()
    colors = [(255, 37, 255), (50, 200, 200)]
    params = dict(target_colors=colors, tolerance=20, feather=100,
                  decontaminate=True, edge_erosion=1,
                  auto_trim=auto_trim, trim_padding=trim_padding)
    _run_js_parity(
        tmp_path, arr, params,
        meta_extra={"target_colors": [list(c) for c in colors]},
    )
