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

JS_RUNNER = Path(__file__).parent / "js_parity_runner.js"


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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_js_matches_python(tmp_path):
    arr = _build_test_image()
    h, w = arr.shape[:2]

    in_png = tmp_path / "in.png"
    Image.fromarray(arr).save(in_png)
    arr.tofile(tmp_path / "in.rgba")

    params = dict(target_color=(255, 37, 255), tolerance=20, feather=100,
                  decontaminate=True, edge_erosion=1)
    py_out = tmp_path / "py.png"
    imageAlpha.remove_color(str(in_png), str(py_out), **params)
    np.array(Image.open(py_out)).tofile(tmp_path / "py.rgba")

    meta = {"w": w, "h": h, **params, "target_color": list(params["target_color"])}
    (tmp_path / "meta.json").write_text(json.dumps(meta))

    result = subprocess.run(
        ["node", str(JS_RUNNER), str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"node runner failed: {result.stderr}"

    py = (tmp_path / "py.rgba").read_bytes()
    js = (tmp_path / "js.rgba").read_bytes()
    assert len(py) == len(js)
    assert py == js, "JS algorithm output diverges from Python reference"
