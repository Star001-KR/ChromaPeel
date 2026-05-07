"""Unit tests for clipboard_utils — dispatch + per-platform invocation safety.

The actual OS clipboard is never touched: subprocess.run / shutil.which / sys
are monkeypatched so these tests are platform-agnostic.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

import clipboard_utils
from clipboard_utils import (
    ClipboardImageError,
    copy_image_to_clipboard,
    read_image_from_clipboard,
    stage_clipboard_image,
)


def _make_png(path: Path) -> Path:
    Image.new("RGB", (2, 2), (255, 0, 0)).save(path)
    return path


# ---------- top-level dispatch ----------

def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        copy_image_to_clipboard(tmp_path / "does_not_exist.png")


@pytest.mark.parametrize("platform,target", [
    ("win32", "_copy_windows"),
    ("darwin", "_copy_macos"),
    ("linux", "_copy_linux"),
    ("freebsd", "_copy_linux"),  # any non-win/non-mac falls through to linux path
])
def test_dispatches_per_platform(monkeypatch, tmp_path, platform, target):
    src = _make_png(tmp_path / "in.png")
    calls = []
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(clipboard_utils, target, lambda p: calls.append(p))
    copy_image_to_clipboard(src)
    assert calls == [src]


# ---------- macOS ----------

def test_macos_uses_safe_temp_symlink_not_user_path(monkeypatch, tmp_path):
    """B3 regression: paths with shell-meaningful chars must not leak into osascript."""
    # Use chars valid on all OS (Windows reserves " and \). The point is to confirm
    # the implementation never embeds the user's path into the AppleScript string,
    # regardless of what characters it contains.
    src = _make_png(tmp_path / "a' b.png")  # single quote + space

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr(clipboard_utils.subprocess, "run", fake_run)

    clipboard_utils._copy_macos(src)

    cmd = captured["cmd"]
    assert cmd[0] == "osascript"
    assert cmd[1] == "-e"
    script = cmd[2]
    # Script references the safe symlink basename
    assert "image.png" in script
    # Original user-controlled path (with metacharacters) must not appear
    assert str(src) not in script
    assert src.name not in script


def test_macos_raises_on_osascript_failure(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(
        clipboard_utils.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="boom"),
    )
    with pytest.raises(OSError, match="osascript"):
        clipboard_utils._copy_macos(src)


# ---------- Linux ----------

def _which_factory(available: dict[str, str]):
    """Return a fake shutil.which that resolves only the listed tool names."""
    return lambda name: available.get(name)


def test_linux_prefers_wl_copy_when_available(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which",
                        _which_factory({"wl-copy": "/usr/bin/wl-copy", "xclip": "/usr/bin/xclip"}))

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(clipboard_utils.subprocess, "run", fake_run)

    clipboard_utils._copy_linux(src)

    assert captured["cmd"][0] == "wl-copy"
    assert "image/png" in captured["cmd"]


def test_linux_falls_back_to_xclip_when_wl_copy_missing(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which",
                        _which_factory({"xclip": "/usr/bin/xclip"}))

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(clipboard_utils.subprocess, "run", fake_run)

    clipboard_utils._copy_linux(src)

    assert captured["cmd"][0] == "xclip"
    assert "-selection" in captured["cmd"]
    assert "clipboard" in captured["cmd"]


def test_linux_raises_when_neither_tool_available(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which", _which_factory({}))
    with pytest.raises(OSError, match="wl-clipboard|xclip"):
        clipboard_utils._copy_linux(src)


def test_linux_wl_copy_failure_raises(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which",
                        _which_factory({"wl-copy": "/usr/bin/wl-copy"}))
    monkeypatch.setattr(
        clipboard_utils.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"nope"),
    )
    with pytest.raises(OSError, match="wl-copy"):
        clipboard_utils._copy_linux(src)


def test_linux_xclip_failure_raises(monkeypatch, tmp_path):
    src = _make_png(tmp_path / "in.png")
    monkeypatch.setattr(clipboard_utils.shutil, "which",
                        _which_factory({"xclip": "/usr/bin/xclip"}))
    monkeypatch.setattr(
        clipboard_utils.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"nope"),
    )
    with pytest.raises(OSError, match="xclip"):
        clipboard_utils._copy_linux(src)


# ---------- read_image_from_clipboard ----------

def _patch_grabclipboard(monkeypatch, value):
    monkeypatch.setattr(
        clipboard_utils.ImageGrab, "grabclipboard", lambda: value
    )


def test_read_image_returns_pil_image_when_clipboard_has_image(monkeypatch):
    fake = Image.new("RGB", (4, 4), (10, 20, 30))
    _patch_grabclipboard(monkeypatch, fake)

    result = read_image_from_clipboard()

    assert isinstance(result, Image.Image)
    assert result.size == (4, 4)


def test_read_image_returns_none_when_clipboard_empty(monkeypatch):
    _patch_grabclipboard(monkeypatch, None)
    assert read_image_from_clipboard() is None


def test_read_image_returns_none_when_clipboard_has_text_or_unknown(monkeypatch):
    _patch_grabclipboard(monkeypatch, [])
    assert read_image_from_clipboard() is None

    _patch_grabclipboard(monkeypatch, ["/some/path/document.txt"])
    assert read_image_from_clipboard() is None


def test_read_image_loads_first_image_when_clipboard_has_file_paths(monkeypatch, tmp_path):
    png_path = tmp_path / "clip.png"
    Image.new("RGB", (5, 7), (200, 100, 50)).save(png_path)
    _patch_grabclipboard(monkeypatch, [str(png_path)])

    result = read_image_from_clipboard()

    assert isinstance(result, Image.Image)
    assert result.size == (5, 7)


def test_read_image_returns_none_when_clipboard_returns_unsupported_type(monkeypatch):
    _patch_grabclipboard(monkeypatch, 42)
    assert read_image_from_clipboard() is None


# ---------- stage_clipboard_image ----------

def test_stage_writes_timestamped_png(monkeypatch, tmp_path):
    """기본 동작: clipboard PIL 이미지를 staging_dir 에 PNG로 저장."""
    _patch_grabclipboard(
        monkeypatch, Image.new("RGB", (3, 4), (10, 20, 30)),
    )
    out = stage_clipboard_image(tmp_path / "stage")

    assert out.is_file()
    assert out.parent == tmp_path / "stage"
    assert out.name.startswith("clipboard_")
    assert out.suffix == ".png"
    img = Image.open(out)
    assert img.size == (3, 4)


def test_stage_uses_microseconds_to_avoid_collision(monkeypatch, tmp_path):
    """동일 초에 두 번 호출되어도 파일명 충돌이 없어야 한다 (마이크로초 포함).

    회귀 방지: 이전에 grid_split/manual_crop/imageAlpha 가 각각 ``%Y%m%d_%H%M%S``
    (초 단위) 만 사용하여 같은 초에 두 번 호출 시 덮어쓰기 위험이 있었다.
    """
    monkeypatch.setattr(
        clipboard_utils.ImageGrab, "grabclipboard",
        lambda: Image.new("RGB", (2, 2), (255, 0, 0)),
    )
    out1 = stage_clipboard_image(tmp_path)
    out2 = stage_clipboard_image(tmp_path)

    assert out1 != out2
    assert out1.exists() and out2.exists()


def test_stage_raises_clipboard_image_error_when_empty(monkeypatch, tmp_path):
    _patch_grabclipboard(monkeypatch, None)
    with pytest.raises(ClipboardImageError, match="이미지가 없습니다"):
        stage_clipboard_image(tmp_path)


def test_stage_wraps_pil_exception_as_clipboard_image_error(monkeypatch, tmp_path):
    """PIL.ImageGrab.grabclipboard() 가 예외를 던지는 시나리오 (Linux wl-paste 미설치 등).

    회귀 방지: CLI 가 ``--from-clipboard`` 를 처리할 때 traceback 을 그대로 노출
    하지 않고 사용자 친화 메시지로 변환해야 한다.
    """
    def _raise():
        raise OSError("wl-paste not installed")
    monkeypatch.setattr(clipboard_utils.ImageGrab, "grabclipboard", _raise)

    with pytest.raises(ClipboardImageError, match="클립보드 읽기 실패"):
        stage_clipboard_image(tmp_path)


def test_stage_creates_missing_directory(monkeypatch, tmp_path):
    _patch_grabclipboard(monkeypatch, Image.new("RGB", (1, 1), (0, 0, 0)))
    target = tmp_path / "deep" / "nested" / "stage"
    assert not target.exists()

    out = stage_clipboard_image(target)

    assert target.is_dir()
    assert out.is_file()
